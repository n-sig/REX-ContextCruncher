"""
prompt_optimizer.py — AI-powered text compression for ContextCruncher.

Uses LLM backends (OpenAI, Anthropic, Ollama) to semantically compress text
far beyond what deterministic rules can achieve.  The LLM understands meaning
and can rewrite/condense while preserving all facts.

Two modes:
  - compress()   — Aggressive semantic compression (GUI hotkey flow)
  - optimize()   — Prompt rewriting into structured format (MCP tool)

Key principles:
  - Zero vendor SDKs — uses httpx for all HTTP calls
  - Strictly opt-in — user must provide API keys or Ollama endpoint
  - API keys stored in %APPDATA%/ContextCruncher/llm_keys.json
  - Custom profiles stored in %APPDATA%/ContextCruncher/profiles.json
"""

from __future__ import annotations

import json
import os
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

import re

from contextcruncher.token_counter import count_tokens
from contextcruncher.security_scanner import redact_secrets

# -----------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------
_APP_DIR = os.path.join(os.environ.get("APPDATA", "."), "ContextCruncher")
_PROFILES_PATH = os.path.join(_APP_DIR, "profiles.json")
_LLM_KEYS_PATH = os.path.join(_APP_DIR, "llm_keys.json")

# -----------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------


@dataclass
class LLMProfile:
    """A named prompt-optimization profile."""

    name: str
    provider: str  # "openai" | "anthropic" | "ollama"
    model: str
    system_prompt: str
    temperature: float = 0.3
    max_output_tokens: int = 2000
    endpoint: str = ""  # Only used for Ollama

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> LLMProfile:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class OptimizeResult:
    """Result of a prompt optimization call."""

    original_text: str
    optimized_prompt: str
    profile_used: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    error: str = ""


# -----------------------------------------------------------------------
# Code extraction — neuro-symbolic hybrid (keeps code out of LLM)
# -----------------------------------------------------------------------

# Matches fenced code blocks: ```lang\n...\n```
_FENCED_CODE_RE = re.compile(
    r'(```[^\n]*\n.*?```)',
    re.DOTALL,
)

# Matches indented code blocks: 4+ spaces or tab at start, with code-like content
_INDENTED_CODE_RE = re.compile(
    r'((?:^(?:    |\t).+\n?){3,})',  # 3+ consecutive indented lines
    re.MULTILINE,
)

_CODE_PLACEHOLDER = "⟨CODE_BLOCK_{idx}⟩"

# -----------------------------------------------------------------------
# Constraint extraction — protects rules, prohibitions, requirements
# -----------------------------------------------------------------------
# Lines containing words like NEVER, ALWAYS, MUST NOT, DO NOT, CRITICAL
# are architectural constraints that LLMs love to "summarize away".
# We extract them physically so the LLM cannot touch them.

_CONSTRAINT_RE = re.compile(
    r'^.*\b(?:'
    r'NEVER|ALWAYS|MUST\s+NOT|MUST\s+BE|DO\s+NOT|DON\'?T|SHALL\s+NOT|'
    r'CANNOT|IMPORTANT|CRITICAL|REQUIRED|FORBIDDEN|PROHIBITED|'
    r'VERBOTEN|NIEMALS|IMMER|MUSS|DARF\s+NICHT'
    r')\b.*$',
    re.MULTILINE | re.IGNORECASE,
)
_CONSTRAINT_PLACEHOLDER = "⟨RULE_{idx}⟩"

# -----------------------------------------------------------------------
# Inline code extraction — protects `backtick` identifiers from hallucination
# -----------------------------------------------------------------------
# LLMs hallucinate filenames/identifiers: `main.py` → `tkui.py`.
# We extract all `backtick` references so the LLM never sees them.

_INLINE_CODE_RE = re.compile(r'`[^`\n]+`')
_INLINE_CODE_PLACEHOLDER = "⟨REF_{idx}⟩"

# -----------------------------------------------------------------------
# Markdown table extraction — tables survive well but rows get rearranged
# -----------------------------------------------------------------------
_MD_TABLE_BLOCK_RE = re.compile(
    r'((?:^\|.+\|[ \t]*\n)+)',  # consecutive lines starting and ending with |
    re.MULTILINE,
)
_TABLE_PLACEHOLDER = "⟨TABLE_{idx}⟩"

# Post-validation patterns — critical data that MUST survive compression
_VALIDATION_PATTERNS = {
    "numbers": re.compile(r'\b\d{2,}\b'),                              # 2+ digit numbers
    "dates": re.compile(r'\b\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\b'),   # DD.MM.YYYY etc.
    "weekdays": re.compile(r'\b(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b', re.IGNORECASE),
    "deadlines": re.compile(r'\b(?:deadline|frist|bis zum|until|due|fällig)\b', re.IGNORECASE),
    "todos": re.compile(r'\b(?:TODO|FIXME|HACK|XXX|WARNING|WARN|NOTE)\b'),
    "versions": re.compile(r'\bv?\d+\.\d+(?:\.\d+)?(?:-\w+)?\b'),     # v1.2.3-beta
}


_po_logger = logging.getLogger(__name__)


def _validate_compression(original: str, compressed: str) -> list[str]:
    """Compare critical data between original and compressed text.

    Returns a list of human-readable warnings for any data that was
    present in the original but missing from the compressed output.
    An empty list means nothing critical was lost.
    """
    warnings: list[str] = []

    for label, pattern in _VALIDATION_PATTERNS.items():
        orig_matches = set(pattern.findall(original))
        comp_matches = set(pattern.findall(compressed))
        lost = orig_matches - comp_matches

        if not lost:
            continue

        # Skip trivially small numbers (single digits get noisy)
        if label == "numbers":
            lost = {n for n in lost if len(n) >= 3 or int(n) >= 10}
        if not lost:
            continue

        samples = sorted(lost)[:5]
        warnings.append(
            f"[{label}] lost {len(lost)}: {', '.join(samples)}"
        )
        _po_logger.warning("AI compress lost %s: %s", label, samples)

    return warnings


def _extract_constraints(text: str) -> tuple[str, list[str]]:
    """Extract constraint/rule sentences from text.

    Lines containing NEVER, ALWAYS, MUST NOT, DO NOT, CRITICAL etc. are
    replaced with numbered ⟨RULE_N⟩ placeholders.  The original lines
    are returned for verbatim reinsertion after LLM compression.
    """
    rules: list[str] = []

    def _replace(m: re.Match) -> str:
        line = m.group(0)
        # Skip lines that are already placeholders
        if "⟨CODE_BLOCK_" in line or "⟨RULE_" in line:
            return line
        idx = len(rules)
        rules.append(line)
        return _CONSTRAINT_PLACEHOLDER.format(idx=idx)

    text = _CONSTRAINT_RE.sub(_replace, text)
    return text, rules


def _reinsert_constraints(text: str, rules: list[str]) -> str:
    """Replace ⟨RULE_N⟩ placeholders with original constraint lines."""
    for idx, rule in enumerate(rules):
        placeholder = _CONSTRAINT_PLACEHOLDER.format(idx=idx)
        text = text.replace(placeholder, rule)
    return text


def _extract_inline_refs(text: str) -> tuple[str, list[str]]:
    """Extract `backtick` inline code references from text.

    Protects identifiers like `main.py`, `stack.py`, `tk.Tk()` from
    being hallucinated/renamed by the LLM.  Each reference is replaced
    with ⟨REF_N⟩ and the original is stored for reinsertion.
    """
    refs: list[str] = []

    def _replace(m: re.Match) -> str:
        ref = m.group(0)
        idx = len(refs)
        refs.append(ref)
        return _INLINE_CODE_PLACEHOLDER.format(idx=idx)

    text = _INLINE_CODE_RE.sub(_replace, text)
    return text, refs


def _reinsert_inline_refs(text: str, refs: list[str]) -> str:
    """Replace ⟨REF_N⟩ placeholders with original inline code references."""
    for idx, ref in enumerate(refs):
        placeholder = _INLINE_CODE_PLACEHOLDER.format(idx=idx)
        text = text.replace(placeholder, ref)
    return text


def _extract_tables(text: str) -> tuple[str, list[str]]:
    """Extract Markdown tables from text.

    Consecutive lines starting and ending with | are treated as table blocks
    and replaced with ⟨TABLE_N⟩ placeholders.
    """
    tables: list[str] = []

    def _replace(m: re.Match) -> str:
        idx = len(tables)
        tables.append(m.group(0))
        return _TABLE_PLACEHOLDER.format(idx=idx) + "\n"

    text = _MD_TABLE_BLOCK_RE.sub(_replace, text)
    return text, tables


def _reinsert_tables(text: str, tables: list[str]) -> str:
    """Replace ⟨TABLE_N⟩ placeholders with original Markdown tables."""
    for idx, table in enumerate(tables):
        placeholder = _TABLE_PLACEHOLDER.format(idx=idx)
        text = text.replace(placeholder, table.rstrip())
    return text


def _extract_code_blocks(text: str) -> tuple[str, list[str]]:
    """Extract all code blocks from text, replacing them with placeholders.

    Returns (text_with_placeholders, list_of_extracted_blocks).
    The LLM only sees the placeholders — original code is never touched.
    """
    blocks: list[str] = []

    def _replace_fenced(m: re.Match) -> str:
        idx = len(blocks)
        blocks.append(m.group(0))
        return _CODE_PLACEHOLDER.format(idx=idx)

    # First pass: fenced code blocks (``` ... ```)
    text = _FENCED_CODE_RE.sub(_replace_fenced, text)

    # Second pass: indented code blocks (only if they look like code)
    def _replace_indented(m: re.Match) -> str:
        block = m.group(0)
        # Heuristic: must contain code-like patterns (=, (), def, if, return, import)
        code_signals = sum(1 for p in ['=', '(', ')', 'def ', 'if ', 'return', 'import ',
                                        'class ', 'for ', 'while ', 'try:', 'except']
                          if p in block)
        if code_signals < 2:
            return block  # Not code-like enough, leave it
        idx = len(blocks)
        blocks.append(block)
        return _CODE_PLACEHOLDER.format(idx=idx)

    text = _INDENTED_CODE_RE.sub(_replace_indented, text)

    return text, blocks


def _reinsert_code_blocks(text: str, blocks: list[str]) -> str:
    """Replace placeholders with the original code blocks."""
    for idx, block in enumerate(blocks):
        placeholder = _CODE_PLACEHOLDER.format(idx=idx)
        text = text.replace(placeholder, block)
    return text


# -----------------------------------------------------------------------
# Compression system prompt — the core of AI compression
# -----------------------------------------------------------------------

_COMPRESS_SYSTEM_PROMPT = """\
You are a text compressor. Your ONLY job: reduce token count while preserving ALL semantic information.

RULES (violating any = failure):
1. Output ONLY the compressed text. No commentary, no headers, no "Here is...", no explanations.
2. Preserve ALL: facts, numbers, names, dates, URLs, code snippets, commands.
3. Remove: filler words, redundant phrases, hedging, pleasantries, repetition.
4. Abbreviate aggressively: configuration→config, information→info, application→app, management→mgmt, environment→env, repository→repo, documentation→docs, implementation→impl, development→dev, authentication→auth, authorization→authz.
5. Collapse verbose sentences into telegraphic form. "The system is able to process" → "system processes".
6. Compress tables into minimal notation. Compress lists by removing bullet markers.
7. Strip markdown formatting (bold, italic) — keep the content and section structure.
8. Merge duplicate/overlapping information.
9. The output must be fully understandable by another AI reading it as context.
10. Preserve structure (sections, groupings) via minimal separators.
11. CODE PROTECTION (CRITICAL): NEVER delete, modify, reorder, or summarize lines of code. Every line of code (assignments, function calls, returns, imports, conditionals) must survive VERBATIM. This includes cursor.execute(), db.commit(), connection.close() etc. — these are NOT redundant!
12. COMMENT PROTECTION: Preserve ALL TODO, FIXME, HACK, WARNING, NOTE annotations and developer instructions. These are task assignments, not filler.
13. LANGUAGE RULE: Preserve the ORIGINAL LANGUAGE. If input is German, output MUST be German. If mixed, keep the mix. NEVER translate.
14. ANTI-HALLUCINATION (CRITICAL): NEVER invent, rename, or approximate identifiers. If the input says `main.py`, output `main.py` — not `tkui.py` or `app.py`. NEVER guess filenames, class names, function names, or paths. If unsure, keep the EXACT original word.
15. COMMAND PROTECTION: Shell commands (python -m pytest, pip install, git ...) MUST survive EXACTLY. NEVER convert shell commands into Python function calls or pseudo-code.
16. CONSTRAINT PROTECTION: Sentences containing NEVER, ALWAYS, MUST, DO NOT are architectural rules. Preserve them VERBATIM — do not summarize, paraphrase, or shorten them. "Never create additional tk.Tk() instances" must NOT become "Single Tk root".
17. PLACEHOLDER PROTECTION: Lines containing ⟨CODE_BLOCK_N⟩, ⟨RULE_N⟩, ⟨REF_N⟩, or ⟨TABLE_N⟩ are protected placeholders. Copy them EXACTLY to the output — do not modify, remove, or reorder them.
18. Target: 50-70% of original token count. Go as low as possible.
"""

_COMPRESS_SYSTEM_PROMPT_AGGRESSIVE = """\
You are an extreme text compressor. Reduce to absolute minimum tokens while keeping ALL facts recoverable.

RULES:
1. Output ONLY compressed text. Zero meta-commentary.
2. ALL facts, numbers, names, dates, code, URLs MUST survive.
3. Use telegraphic style: drop articles, copulas, filler. "The server is running on port 8080" → "server: port 8080".
4. Abbreviate everything: config, info, app, mgmt, env, repo, docs, impl, dev, auth, fn, var, param, req, resp, err, msg, val, dir, fmt, pkg, lib, dep, exec, util.
5. Merge related info. Collapse repetition to single mention.
6. Tables → key:value notation. Lists → comma-separated.
7. Strip ALL formatting. No markdown, no bullets, no headers.
8. CODE PROTECTION (CRITICAL): NEVER delete, modify, or reorder ANY line of code. Every function call, assignment, return, and import must survive VERBATIM. Code logic is NEVER redundant.
9. COMMENT PROTECTION: Preserve ALL TODO, FIXME, HACK, WARNING annotations. These are task assignments.
10. LANGUAGE RULE: Keep the ORIGINAL LANGUAGE. NEVER translate. German stays German.
11. ANTI-HALLUCINATION: NEVER invent, rename, or guess identifiers/filenames. `main.py` stays `main.py`. NEVER convert shell commands to code.
12. CONSTRAINT PROTECTION: Lines with NEVER/ALWAYS/MUST/DO NOT are rules — keep VERBATIM, never summarize.
13. PLACEHOLDER PROTECTION: ⟨CODE_BLOCK_N⟩, ⟨RULE_N⟩, ⟨REF_N⟩, ⟨TABLE_N⟩ → copy EXACTLY, never modify.
14. Target: 30-50% of original token count.
"""


# -----------------------------------------------------------------------
# Built-in Profiles (immutable)
# -----------------------------------------------------------------------

_BUILTIN_PROFILES: dict[str, LLMProfile] = {
    "compress": LLMProfile(
        name="compress",
        provider="openai",
        model="gpt-4o-mini",
        system_prompt=_COMPRESS_SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=4000,
    ),
    "compress_aggressive": LLMProfile(
        name="compress_aggressive",
        provider="openai",
        model="gpt-4o-mini",
        system_prompt=_COMPRESS_SYSTEM_PROMPT_AGGRESSIVE,
        temperature=0.1,
        max_output_tokens=4000,
    ),
    "general": LLMProfile(
        name="general",
        provider="openai",
        model="gpt-4o-mini",
        system_prompt=(
            "You are a prompt engineer. Rewrite the following text as a clear, "
            "structured LLM prompt. Preserve all facts, data, and intent. "
            "Add structure (numbered steps, bullet points) where helpful. "
            "Output ONLY the improved prompt, nothing else."
        ),
    ),
    "code_reviewer": LLMProfile(
        name="code_reviewer",
        provider="openai",
        model="gpt-4o-mini",
        system_prompt=(
            "You are a prompt engineer specializing in code review. "
            "Rewrite the following text as a code review request prompt. "
            "Include: 1) File/function context, 2) Expected vs actual behavior, "
            "3) Specific review questions. Output ONLY the improved prompt."
        ),
    ),
    "data_analyst": LLMProfile(
        name="data_analyst",
        provider="openai",
        model="gpt-4o-mini",
        system_prompt=(
            "You are a prompt engineer specializing in data analysis. "
            "Rewrite the following text as a data analysis prompt. "
            "Structure: 1) Data description, 2) Analysis goal, "
            "3) Expected output format. Output ONLY the improved prompt."
        ),
    ),
    "summarizer": LLMProfile(
        name="summarizer",
        provider="openai",
        model="gpt-4o-mini",
        system_prompt=(
            "You are a prompt engineer specializing in summarization. "
            "Rewrite the following text as a summarization prompt. "
            "Specify: 1) Target length, 2) Audience, 3) Key topics to preserve. "
            "Output ONLY the improved prompt."
        ),
    ),
    "translator": LLMProfile(
        name="translator",
        provider="openai",
        model="gpt-4o-mini",
        system_prompt=(
            "You are a prompt engineer specializing in translation. "
            "Rewrite the following text as a translation prompt. "
            "Preserve: tone, technical terms, formatting. "
            "Specify source and target language clearly. "
            "Output ONLY the improved prompt."
        ),
    ),
}

_BUILTIN_NAMES = frozenset(_BUILTIN_PROFILES.keys())

# -----------------------------------------------------------------------
# Profile Management
# -----------------------------------------------------------------------


def _ensure_app_dir() -> None:
    os.makedirs(_APP_DIR, exist_ok=True)


def list_profiles() -> list[dict]:
    """Return all profiles (built-in + custom) as dicts."""
    profiles = []
    for p in _BUILTIN_PROFILES.values():
        d = p.to_dict()
        d["is_builtin"] = True
        profiles.append(d)

    custom = _load_custom_profiles()
    for p in custom:
        d = p.to_dict()
        d["is_builtin"] = False
        profiles.append(d)

    return profiles


def get_profile(name: str) -> LLMProfile | None:
    """Get a profile by name (built-in or custom)."""
    if name in _BUILTIN_PROFILES:
        return _BUILTIN_PROFILES[name]
    for p in _load_custom_profiles():
        if p.name == name:
            return p
    return None


def save_profile(profile: LLMProfile) -> dict:
    """Save or update a custom profile. Built-in names are protected."""
    if profile.name in _BUILTIN_NAMES:
        return {"error": f"Cannot overwrite built-in profile '{profile.name}'."}

    if profile.provider not in ("openai", "anthropic", "ollama"):
        return {"error": f"Unknown provider '{profile.provider}'. Use: openai, anthropic, ollama."}

    custom = _load_custom_profiles()
    # Replace existing or append
    custom = [p for p in custom if p.name != profile.name]
    custom.append(profile)
    _save_custom_profiles(custom)
    return {"status": "saved", "name": profile.name}


def delete_profile(name: str) -> dict:
    """Delete a custom profile. Built-in profiles cannot be deleted."""
    if name in _BUILTIN_NAMES:
        return {"error": f"Cannot delete built-in profile '{name}'."}

    custom = _load_custom_profiles()
    before = len(custom)
    custom = [p for p in custom if p.name != name]
    if len(custom) == before:
        return {"error": f"Profile '{name}' not found."}

    _save_custom_profiles(custom)
    return {"status": "deleted", "name": name}


def _load_custom_profiles() -> list[LLMProfile]:
    if not os.path.isfile(_PROFILES_PATH):
        return []
    try:
        with open(_PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [LLMProfile.from_dict(d) for d in data.get("custom_profiles", [])]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def _save_custom_profiles(profiles: list[LLMProfile]) -> None:
    _ensure_app_dir()
    data = {"custom_profiles": [p.to_dict() for p in profiles]}
    with open(_PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# -----------------------------------------------------------------------
# Provider Config (API Keys & Endpoints)
# -----------------------------------------------------------------------


def get_provider_config() -> dict:
    """Load API keys and endpoints from llm_keys.json."""
    if not os.path.isfile(_LLM_KEYS_PATH):
        return {}
    try:
        with open(_LLM_KEYS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, TypeError):
        return {}


def save_provider_config(config: dict) -> dict:
    """Save API keys and endpoints to llm_keys.json."""
    _ensure_app_dir()
    with open(_LLM_KEYS_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return {"status": "saved"}


# -----------------------------------------------------------------------
# Connection Probe (Settings "Test Connection" button)
# -----------------------------------------------------------------------

@dataclass
class ConnectionProbeResult:
    """Outcome of probing an LLM provider endpoint.

    ``ok`` is True when the endpoint responded to a basic capability query
    (Ollama: ``GET /api/tags``). ``models`` is the list of model names
    returned by the endpoint when available (Ollama only). ``error`` is a
    short human-readable reason when the probe failed.
    """
    ok: bool
    models: list[str] = field(default_factory=list)
    error: str = ""
    latency_ms: int = 0


def probe_ollama(endpoint: str = "http://localhost:11434",
                 timeout: float = 3.0) -> ConnectionProbeResult:
    """Probe an Ollama endpoint with a ``GET /api/tags`` request.

    Returns a :class:`ConnectionProbeResult` describing whether the server
    is reachable and which models are installed. Short timeout by design —
    this is called from the Settings dialog and must not block the UI.
    """
    if httpx is None:
        return ConnectionProbeResult(
            ok=False, error="httpx not installed. Run: pip install httpx",
        )

    url = endpoint.rstrip("/") + "/api/tags"
    start = time.perf_counter_ns()
    try:
        resp = httpx.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json() or {}
    except Exception as e:
        elapsed = (time.perf_counter_ns() - start) // 1_000_000
        return ConnectionProbeResult(
            ok=False,
            error=_friendly_provider_error(e, "ollama", ""),
            latency_ms=elapsed,
        )

    elapsed = (time.perf_counter_ns() - start) // 1_000_000
    models_raw = data.get("models", []) if isinstance(data, dict) else []
    model_names: list[str] = []
    for m in models_raw:
        if isinstance(m, dict):
            name = m.get("name") or m.get("model") or ""
            if name:
                model_names.append(str(name))
    return ConnectionProbeResult(
        ok=True, models=model_names, latency_ms=elapsed,
    )


# -----------------------------------------------------------------------
# Provider Implementations (httpx-based)
# -----------------------------------------------------------------------

_REQUEST_TIMEOUT = 30.0  # seconds


def _friendly_provider_error(exc: Exception, provider: str, model: str) -> str:
    """Translate a provider-call exception into a short user-facing message.

    The returned string is intended for display in a toast (capped ~90 chars).
    Preserves the existing "Request timed out after Xs." / "HTTP N: ..." shape
    so tests that substring-match those patterns keep passing, but adds
    specific hints for:

      * ConnectError / network errors → "cannot reach endpoint" (Ollama)
      * HTTP 401 / 403              → "invalid API key / not authorized"
      * HTTP 404                    → "model not found" (often wrong model name)
      * HTTP 429                    → "rate limited"
    """
    # Timeout — same phrasing callers already rely on
    if httpx is not None and isinstance(exc, httpx.TimeoutException):
        return f"Request timed out after {_REQUEST_TIMEOUT}s."

    # HTTP status errors — keep the "HTTP N:" prefix but enrich the tail
    if httpx is not None and isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        try:
            body_msg = exc.response.json().get("error", {})
            if isinstance(body_msg, dict):
                body_msg = body_msg.get("message", "")
            elif not isinstance(body_msg, str):
                body_msg = str(body_msg)
        except Exception:
            body_msg = ""
        body_msg = body_msg or str(exc)

        if status in (401, 403):
            return f"HTTP {status}: API key invalid or not authorized ({provider})."
        if status == 404:
            return f"HTTP {status}: model '{model}' not found on {provider}."
        if status == 429:
            return f"HTTP {status}: rate limit reached for {provider}."
        return f"HTTP {status}: {body_msg}"

    # Connection errors — most commonly "Ollama not running"
    if httpx is not None and isinstance(
        exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError),
    ):
        if provider == "ollama":
            return (
                "Cannot reach Ollama endpoint. Is `ollama serve` running?"
            )
        return f"Cannot reach {provider} endpoint: {exc}"

    # Fallback
    return str(exc) or f"{type(exc).__name__} from {provider}"


def _call_openai(text: str, profile: LLMProfile, api_key: str) -> tuple[str, dict]:
    """Call OpenAI-compatible API. Returns (response_text, usage_dict)."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": profile.model,
        "messages": [
            {"role": "system", "content": profile.system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": profile.temperature,
        "max_tokens": profile.max_output_tokens,
    }

    resp = httpx.post(url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return content, {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


def _call_anthropic(text: str, profile: LLMProfile, api_key: str) -> tuple[str, dict]:
    """Call Anthropic Messages API. Returns (response_text, usage_dict)."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": profile.model,
        "max_tokens": profile.max_output_tokens,
        "system": profile.system_prompt,
        "messages": [
            {"role": "user", "content": text},
        ],
        "temperature": profile.temperature,
    }

    resp = httpx.post(url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    content = data["content"][0]["text"]
    usage = data.get("usage", {})
    return content, {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


def _call_ollama(text: str, profile: LLMProfile, endpoint: str) -> tuple[str, dict]:
    """Call local Ollama API. Returns (response_text, usage_dict)."""
    base = endpoint.rstrip("/") if endpoint else "http://localhost:11434"
    url = f"{base}/api/chat"
    payload = {
        "model": profile.model,
        "messages": [
            {"role": "system", "content": profile.system_prompt},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "options": {
            "temperature": profile.temperature,
            "num_predict": profile.max_output_tokens,
        },
    }

    resp = httpx.post(url, json=payload, timeout=60.0)  # Ollama can be slow
    resp.raise_for_status()
    data = resp.json()

    content = data.get("message", {}).get("content", "")
    # Ollama returns eval/prompt token counts
    return content, {
        "input_tokens": data.get("prompt_eval_count", 0),
        "output_tokens": data.get("eval_count", 0),
    }


_PROVIDERS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "ollama": _call_ollama,
}


# -----------------------------------------------------------------------
# Main Optimize Function
# -----------------------------------------------------------------------


def optimize(
    text: str,
    profile_name: str = "general",
    provider_override: str = "",
    model_override: str = "",
) -> OptimizeResult:
    """Optimize text into a structured prompt using the specified profile.

    Args:
        text: Raw text to optimize into a prompt.
        profile_name: Name of the profile to use (built-in or custom).
        provider_override: Override the profile's provider (optional).
        model_override: Override the profile's model (optional).

    Returns:
        OptimizeResult with the optimized prompt or error details.
    """
    start = time.perf_counter_ns()

    # Validate input
    if not text or not text.strip():
        return OptimizeResult(
            original_text=text, optimized_prompt="", profile_used=profile_name,
            provider="", model="", input_tokens=0, output_tokens=0,
            latency_ms=0, error="Empty text provided.",
        )

    # Resolve profile
    profile = get_profile(profile_name)
    if profile is None:
        return OptimizeResult(
            original_text=text, optimized_prompt="", profile_used=profile_name,
            provider="", model="", input_tokens=0, output_tokens=0,
            latency_ms=0, error=f"Profile '{profile_name}' not found.",
        )

    # Apply overrides
    provider = provider_override or profile.provider
    model = model_override or profile.model

    # Resolve credentials
    config = get_provider_config()
    api_key = ""
    endpoint = ""

    if provider == "openai":
        api_key = config.get("openai_api_key", "")
        if not api_key:
            return OptimizeResult(
                original_text=text, optimized_prompt="", profile_used=profile_name,
                provider=provider, model=model, input_tokens=0, output_tokens=0,
                latency_ms=0, error="OpenAI API key not configured. Save it via manage_optimizer_profile or add to llm_keys.json.",
            )
    elif provider == "anthropic":
        api_key = config.get("anthropic_api_key", "")
        if not api_key:
            return OptimizeResult(
                original_text=text, optimized_prompt="", profile_used=profile_name,
                provider=provider, model=model, input_tokens=0, output_tokens=0,
                latency_ms=0, error="Anthropic API key not configured. Save it via manage_optimizer_profile or add to llm_keys.json.",
            )
    elif provider == "ollama":
        endpoint = config.get("ollama_endpoint", profile.endpoint or "http://localhost:11434")
    else:
        return OptimizeResult(
            original_text=text, optimized_prompt="", profile_used=profile_name,
            provider=provider, model=model, input_tokens=0, output_tokens=0,
            latency_ms=0, error=f"Unknown provider '{provider}'. Use: openai, anthropic, ollama.",
        )

    # Create a modified profile with overrides
    effective_profile = LLMProfile(
        name=profile.name,
        provider=provider,
        model=model,
        system_prompt=profile.system_prompt,
        temperature=profile.temperature,
        max_output_tokens=profile.max_output_tokens,
        endpoint=endpoint,
    )

    # Check httpx availability (just before network call, after all validations)
    if httpx is None:
        return OptimizeResult(
            original_text=text, optimized_prompt="", profile_used=profile_name,
            provider=provider, model=model, input_tokens=0, output_tokens=0,
            latency_ms=0, error="httpx not installed. Run: pip install httpx",
        )

    # Call provider
    try:
        call_fn = _PROVIDERS[provider]
        if provider == "ollama":
            response_text, usage = call_fn(text, effective_profile, endpoint)
        else:
            response_text, usage = call_fn(text, effective_profile, api_key)
    except httpx.TimeoutException:
        elapsed = (time.perf_counter_ns() - start) // 1_000_000
        return OptimizeResult(
            original_text=text, optimized_prompt="", profile_used=profile_name,
            provider=provider, model=model, input_tokens=0, output_tokens=0,
            latency_ms=elapsed, error=f"Request timed out after {_REQUEST_TIMEOUT}s.",
        )
    except httpx.HTTPStatusError as e:
        elapsed = (time.perf_counter_ns() - start) // 1_000_000
        status = e.response.status_code
        detail = ""
        try:
            detail = e.response.json().get("error", {}).get("message", str(e))
        except Exception:
            detail = str(e)
        return OptimizeResult(
            original_text=text, optimized_prompt="", profile_used=profile_name,
            provider=provider, model=model, input_tokens=0, output_tokens=0,
            latency_ms=elapsed, error=f"HTTP {status}: {detail}",
        )
    except Exception as e:
        elapsed = (time.perf_counter_ns() - start) // 1_000_000
        return OptimizeResult(
            original_text=text, optimized_prompt="", profile_used=profile_name,
            provider=provider, model=model, input_tokens=0, output_tokens=0,
            latency_ms=elapsed, error=f"Provider error: {e}",
        )

    elapsed = (time.perf_counter_ns() - start) // 1_000_000

    return OptimizeResult(
        original_text=text,
        optimized_prompt=response_text.strip(),
        profile_used=profile_name,
        provider=provider,
        model=model,
        input_tokens=usage.get("input_tokens", count_tokens(text)),
        output_tokens=usage.get("output_tokens", count_tokens(response_text)),
        latency_ms=elapsed,
    )


# -----------------------------------------------------------------------
# Compression Result
# -----------------------------------------------------------------------

@dataclass
class CompressResult:
    """Result of an AI compression call."""

    original_text: str
    compressed_text: str
    provider: str
    model: str
    original_tokens: int
    compressed_tokens: int
    saved_percent: float
    latency_ms: int
    error: str = ""
    warnings: list[str] = field(default_factory=list)


# -----------------------------------------------------------------------
# AI Compress — main entry point for GUI flow
# -----------------------------------------------------------------------

def compress(
    text: str,
    aggressive: bool = False,
    provider_override: str = "",
    model_override: str = "",
) -> CompressResult:
    """Compress text using an LLM for semantic understanding.

    This is the primary function for the GUI hotkey flow.  It sends the
    (already deterministically compressed) text to an LLM with a compression
    system prompt, getting back an even shorter version.

    Args:
        text: Text to compress (typically already deterministically compressed).
        aggressive: If True, use the more aggressive compression profile.
        provider_override: Override the configured provider.
        model_override: Override the configured model.

    Returns:
        CompressResult with compressed text and metadata.
    """
    start = time.perf_counter_ns()

    if not text or not text.strip():
        return CompressResult(
            original_text=text or "", compressed_text=text or "",
            provider="", model="", original_tokens=0, compressed_tokens=0,
            saved_percent=0.0, latency_ms=0, error="Empty text.",
        )

    # BUG-09 FIX: ALWAYS redact secrets before sending to external LLM API.
    # This is critical — we must never leak secrets to OpenAI/Anthropic/Ollama.
    text = redact_secrets(text)

    # HYBRID ARCHITECTURE (BUG-14 FIX): Extract ALL structured content BEFORE
    # the LLM sees the text.  Each category is replaced with numbered placeholders.
    # After compression, originals are reinserted verbatim — the LLM can only
    # compress the prose between placeholders.
    #
    # Extraction order (biggest structures first → finest granularity last):
    #   1. Fenced & indented code blocks  (``` ... ```, 4-space indent)
    #   2. Markdown tables                (| ... | rows)
    #   3. Inline code references         (`backtick` identifiers)
    #   4. Constraint sentences           (NEVER, ALWAYS, MUST NOT, DO NOT, ...)
    text_for_llm, extracted_code = _extract_code_blocks(text)
    text_for_llm, extracted_tables = _extract_tables(text_for_llm)
    text_for_llm, extracted_refs = _extract_inline_refs(text_for_llm)
    text_for_llm, extracted_rules = _extract_constraints(text_for_llm)

    original_tokens = count_tokens(text)

    # Pick the compression profile
    profile_name = "compress_aggressive" if aggressive else "compress"
    profile = _BUILTIN_PROFILES[profile_name]

    # Resolve provider from config or override
    from contextcruncher.config import load_config
    cfg = load_config()
    provider = provider_override or cfg.get("ai_compress_provider", profile.provider)
    model = model_override or cfg.get("ai_compress_model", profile.model)

    # Resolve credentials
    keys_config = get_provider_config()
    api_key = ""
    endpoint = ""

    if provider == "openai":
        api_key = keys_config.get("openai_api_key", "")
        if not api_key:
            elapsed = (time.perf_counter_ns() - start) // 1_000_000
            return CompressResult(
                original_text=text, compressed_text="",
                provider=provider, model=model,
                original_tokens=original_tokens, compressed_tokens=0,
                saved_percent=0.0, latency_ms=elapsed,
                error="OpenAI API key not configured. Set it in Settings → AI Compression.",
            )
    elif provider == "anthropic":
        api_key = keys_config.get("anthropic_api_key", "")
        if not api_key:
            elapsed = (time.perf_counter_ns() - start) // 1_000_000
            return CompressResult(
                original_text=text, compressed_text="",
                provider=provider, model=model,
                original_tokens=original_tokens, compressed_tokens=0,
                saved_percent=0.0, latency_ms=elapsed,
                error="Anthropic API key not configured. Set it in Settings → AI Compression.",
            )
    elif provider == "ollama":
        endpoint = keys_config.get("ollama_endpoint", "http://localhost:11434")
    else:
        elapsed = (time.perf_counter_ns() - start) // 1_000_000
        return CompressResult(
            original_text=text, compressed_text="",
            provider=provider, model=model,
            original_tokens=original_tokens, compressed_tokens=0,
            saved_percent=0.0, latency_ms=elapsed,
            error=f"Unknown provider '{provider}'.",
        )

    # CONTENT-TYPE HINT: Tell the LLM what kind of text it's compressing
    # so it can apply domain-appropriate compression strategies.
    from contextcruncher.content_router import detect_content_type
    content_type = detect_content_type(text)
    _CONTENT_HINTS: dict[str, str] = {
        "code_python":  "INPUT TYPE: Python source code. Preserve all logic, imports, and structure.",
        "code_js":      "INPUT TYPE: JavaScript/TypeScript code. Preserve all logic and structure.",
        "code_ts":      "INPUT TYPE: TypeScript code. Preserve all logic, types, and structure.",
        "code_generic": "INPUT TYPE: Source code. Preserve all logic and structure.",
        "data_json":    "INPUT TYPE: JSON data. Preserve all keys, values, and nesting.",
        "data_xml":     "INPUT TYPE: XML data. Preserve all elements, attributes, and hierarchy.",
        "data_yaml":    "INPUT TYPE: YAML config. Preserve all keys, values, and indentation.",
        "log":          "INPUT TYPE: Log output. Preserve timestamps, log levels, and error messages.",
        "markdown":     "INPUT TYPE: Markdown documentation. Compress prose, preserve section structure.",
        "email":        "INPUT TYPE: Email. Preserve sender, recipient, dates, and action items.",
        "web_scrape":   "INPUT TYPE: Web content. Remove navigation/boilerplate, keep article text.",
        "prose":        "INPUT TYPE: General text. Compress aggressively while preserving all facts.",
        "agent_config": (
            "INPUT TYPE: AI agent configuration / system prompt (CLAUDE.md, .cursorrules, or similar).\n"
            "ULTRA-CONSERVATIVE MODE:\n"
            "- Every constraint sentence (containing Never/Always/Must/Do not) MUST survive VERBATIM.\n"
            "- Every filename, path, and identifier MUST be preserved EXACTLY — NEVER rename or guess.\n"
            "- Every CLI command / bash snippet MUST survive EXACTLY — NEVER convert to code.\n"
            "- Directory trees MUST preserve exact filenames — NEVER invent or approximate.\n"
            "- Only compress filler prose between rules. Rules themselves are UNTOUCHABLE."
        ),
    }
    hint = _CONTENT_HINTS.get(content_type, "")
    system_prompt = f"{hint}\n\n{profile.system_prompt}" if hint else profile.system_prompt

    # Build effective profile with overrides
    effective_profile = LLMProfile(
        name=profile.name, provider=provider, model=model,
        system_prompt=system_prompt,
        temperature=profile.temperature,
        max_output_tokens=max(profile.max_output_tokens, original_tokens),
        endpoint=endpoint,
    )

    # Check httpx
    if httpx is None:
        elapsed = (time.perf_counter_ns() - start) // 1_000_000
        return CompressResult(
            original_text=text, compressed_text="",
            provider=provider, model=model,
            original_tokens=original_tokens, compressed_tokens=0,
            saved_percent=0.0, latency_ms=elapsed,
            error="httpx not installed. Run: pip install httpx",
        )

    # Call provider — send ONLY prose with placeholders (code is extracted)
    try:
        call_fn = _PROVIDERS[provider]
        if provider == "ollama":
            response_text, usage = call_fn(text_for_llm, effective_profile, endpoint)
        else:
            response_text, usage = call_fn(text_for_llm, effective_profile, api_key)
    except Exception as e:
        elapsed = (time.perf_counter_ns() - start) // 1_000_000
        error_msg = _friendly_provider_error(e, provider, model)
        return CompressResult(
            original_text=text, compressed_text="",
            provider=provider, model=model,
            original_tokens=original_tokens, compressed_tokens=0,
            saved_percent=0.0, latency_ms=elapsed,
            error=error_msg,
        )

    elapsed = (time.perf_counter_ns() - start) // 1_000_000
    compressed = response_text.strip()

    # HYBRID: Reinsert all extracted content (reverse extraction order)
    if extracted_rules:
        compressed = _reinsert_constraints(compressed, extracted_rules)
    if extracted_refs:
        compressed = _reinsert_inline_refs(compressed, extracted_refs)
    if extracted_tables:
        compressed = _reinsert_tables(compressed, extracted_tables)
    if extracted_code:
        compressed = _reinsert_code_blocks(compressed, extracted_code)

    compressed_tokens = count_tokens(compressed)
    saved = original_tokens - compressed_tokens
    saved_pct = (saved / original_tokens * 100.0) if original_tokens > 0 else 0.0

    # Sanity check: if LLM output is LONGER, return original
    if compressed_tokens >= original_tokens:
        return CompressResult(
            original_text=text, compressed_text=text,
            provider=provider, model=model,
            original_tokens=original_tokens, compressed_tokens=original_tokens,
            saved_percent=0.0, latency_ms=elapsed,
            error="LLM output was not shorter than input.",
        )

    # POST-VALIDATION: check that critical data survived the LLM compression.
    # Compare numbers, dates, weekdays, deadlines, TODOs, versions between
    # original and compressed text.  Warnings are attached to the result so
    # the GUI can display them — but we never reject a shorter result.
    validation_warnings = _validate_compression(text, compressed)

    return CompressResult(
        original_text=text,
        compressed_text=compressed,
        provider=provider,
        model=model,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        saved_percent=round(saved_pct, 1),
        latency_ms=elapsed,
        warnings=validation_warnings,
    )


def is_ai_compress_configured() -> bool:
    """Check if AI compression has a usable provider configured."""
    from contextcruncher.config import load_config
    cfg = load_config()

    if not cfg.get("ai_compress_enabled", False):
        return False

    provider = cfg.get("ai_compress_provider", "ollama")
    keys_config = get_provider_config()

    if provider == "openai":
        return bool(keys_config.get("openai_api_key"))
    elif provider == "anthropic":
        return bool(keys_config.get("anthropic_api_key"))
    elif provider == "ollama":
        return True  # Ollama is local, always "configured"
    return False
