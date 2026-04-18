"""
content_router.py — Intelligent content-type detection and compression routing.

Detects the content type of input text (code, data, logs, prose) and routes
it through the optimal compression pipeline based on the AI agent's intent.

This module is the dispatch layer between raw text and ContextCruncher's
existing compression tools (text_processor, skeletonizer, token_counter).

Intents:
  - "understand":    Preserve meaning, remove noise (default)
  - "code_review":   Keep code structure, remove prose
  - "extract_data":  Keep numbers/names/dates, remove narrative
  - "summarize":     Maximum reduction, keep key facts only
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict

from contextcruncher.text_processor import minify_for_ai, _detect_content_type
from contextcruncher.skeletonizer import crunch_skeleton
from contextcruncher.security_scanner import redact_secrets
from contextcruncher.token_counter import count_tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content-type categories (coarser grouping for strategy lookup)
# ---------------------------------------------------------------------------

_CATEGORY_MAP: dict[str, str] = {
    "code_python":  "code",
    "code_js":      "code",
    "code_ts":      "code",
    "code_generic": "code",
    "data_json":    "data",
    "data_xml":     "data",
    "data_yaml":    "data",
    "log":          "log",
    "markdown":     "prose",
    "prose":        "prose",
    "email":        "prose",
    "web_scrape":   "prose",
    "agent_config": "agent_config",
}


def _content_type_category(content_type: str) -> str:
    """Map a specific content type to its coarse category."""
    return _CATEGORY_MAP.get(content_type, "prose")


# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------

@dataclass
class _Strategy:
    """A named sequence of compression steps with a base confidence."""
    steps: list[str]
    base_confidence: float


# (category, intent) → Strategy
# Note: "compress" step runs minify_for_ai() which always uses full single-pass.
_STRATEGY_MAP: dict[tuple[str, str], _Strategy] = {
    # CODE strategies
    ("code", "understand"):    _Strategy(["redact", "skeleton", "compress"], 0.93),
    ("code", "code_review"):   _Strategy(["redact", "compress"],             0.99),
    ("code", "extract_data"):  _Strategy(["redact", "skeleton"],             0.90),
    ("code", "summarize"):     _Strategy(["redact", "skeleton"],             0.88),

    # DATA strategies (JSON/XML/YAML)
    ("data", "understand"):    _Strategy(["redact", "skeleton"],             0.95),
    ("data", "code_review"):   _Strategy(["redact", "skeleton"],             0.95),
    ("data", "extract_data"):  _Strategy(["redact", "skeleton"],             0.95),
    ("data", "summarize"):     _Strategy(["redact", "skeleton"],             0.90),

    # LOG strategies
    ("log", "understand"):     _Strategy(["redact", "compress"],             0.85),
    ("log", "code_review"):    _Strategy(["redact", "compress"],             0.95),
    ("log", "extract_data"):   _Strategy(["redact", "compress"],             0.80),
    ("log", "summarize"):      _Strategy(["redact", "compress"],             0.70),

    # PROSE strategies (markdown, email, web scrape, generic)
    ("prose", "understand"):   _Strategy(["redact", "compress"],             0.85),
    ("prose", "code_review"):  _Strategy(["redact", "compress"],             0.95),
    ("prose", "extract_data"): _Strategy(["redact", "compress"],             0.75),
    ("prose", "summarize"):    _Strategy(["redact", "compress"],             0.70),

    # AGENT CONFIG strategies (CLAUDE.md, .cursorrules, system prompts)
    # Conservative: only deterministic compression, NEVER skeleton (loses constraints).
    # High confidence — these files must remain 100% faithful.
    ("agent_config", "understand"):   _Strategy(["redact", "compress"],      0.98),
    ("agent_config", "code_review"):  _Strategy(["redact", "compress"],      0.99),
    ("agent_config", "extract_data"): _Strategy(["redact", "compress"],      0.95),
    ("agent_config", "summarize"):    _Strategy(["redact", "compress"],      0.90),
}


# ---------------------------------------------------------------------------
# CrunchResult
# ---------------------------------------------------------------------------

@dataclass
class CrunchResult:
    """Result of an intelligent compression pass."""
    compressed_text: str
    strategy_used: str
    content_type: str
    what_was_removed: list[str] = field(default_factory=list)
    confidence: float = 1.0
    original_tokens: int = 0
    compressed_tokens: int = 0
    saved_percent: float = 0.0


# ---------------------------------------------------------------------------
# Extended content-type detection
# ---------------------------------------------------------------------------

# File-extension → content_type (used when a filename hint is provided)
_EXT_MAP: dict[str, str] = {
    ".py":   "code_python",
    ".pyw":  "code_python",
    ".js":   "code_js",
    ".jsx":  "code_js",
    ".ts":   "code_ts",
    ".tsx":  "code_ts",
    ".json": "data_json",
    ".xml":  "data_xml",
    ".yaml": "data_yaml",
    ".yml":  "data_yaml",
    ".md":   "markdown",
    ".log":  "log",
    ".csv":  "data_json",   # treat tabular data like structured data
    ".html": "web_scrape",
    ".css":  "code_generic",
    ".sql":  "code_generic",
    ".sh":   "code_generic",
    ".bash": "code_generic",
    ".ps1":  "code_generic",
    ".java": "code_generic",
    ".c":    "code_generic",
    ".cpp":  "code_generic",
    ".h":    "code_generic",
    ".hpp":  "code_generic",
    ".rs":   "code_generic",
    ".go":   "code_generic",
    ".rb":   "code_generic",
    ".swift":"code_generic",
    ".kt":   "code_generic",
    ".cs":   "code_generic",
    ".r":    "code_generic",
    ".php":  "code_generic",
    ".lua":  "code_generic",
}


# Known agent-config filenames (case-insensitive basenames)
_AGENT_CONFIG_NAMES: frozenset[str] = frozenset({
    "claude.md", "agents.md", "gemini.md", "copilot.md",
    ".cursorrules", ".cursorignore",
    ".github/copilot-instructions.md",
    "system_prompt.md", "system_prompt.txt",
    "system-prompt.md", "system-prompt.txt",
})

import re as _re

# Heuristic: text with many constraint keywords is likely an agent config.
# Kept in sync with prompt_optimizer._CONSTRAINT_RE so the same language
# coverage exists on both sides of the pipeline (detect → extract).
_AGENT_CONFIG_KEYWORDS_RE = _re.compile(
    r'\b(?:NEVER|ALWAYS|MUST NOT|DO NOT|SHALL NOT|FORBIDDEN|CRITICAL|'
    r'IMPORTANT.*?rule|Key Design Decision|design decision|'
    r'VERBOTEN|NIEMALS|IMMER|MUSS|DARF NICHT)\b',
    _re.IGNORECASE,
)


def detect_content_type(text: str, filename: str = "") -> str:
    """Detect the content type of *text*, optionally using *filename* as a hint.

    Priority: agent-config filename > filename extension (if recognized)
    > agent-config content heuristic > log/email/markdown heuristic
    > JSON/XML structural check > prose fallback.

    The log/email/markdown heuristic runs BEFORE the structural JSON/XML check so
    that JSON-formatted log files (where each line is a JSON object starting with
    ``{``) are correctly classified as ``log`` rather than ``data_json``.
    """
    # 0. Check for known agent-config filenames FIRST (highest priority)
    if filename:
        basename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
        if basename in _AGENT_CONFIG_NAMES:
            return "agent_config"

    # 1. Try filename extension first (most reliable)
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext in _EXT_MAP:
            return _EXT_MAP[ext]

    # 1b. Heuristic: if text has many constraint keywords → agent_config
    #     Threshold: ≥5 constraint keywords in the text signals an instruction file
    constraint_hits = len(_AGENT_CONFIG_KEYWORDS_RE.findall(text[:5000]))
    if constraint_hits >= 5:
        return "agent_config"

    # 2. Run the text heuristic for log/email/markdown BEFORE the structural
    #    JSON/XML check.  A strong semantic signal (≥3 log-level lines) should
    #    override what looks like structured data at the byte level.
    tp_type = _detect_content_type(text)
    if tp_type in ("log", "email", "web_scrape", "markdown"):
        _SEMANTIC_MAP = {
            "log":        "log",
            "email":      "email",
            "web_scrape": "web_scrape",
            "markdown":   "markdown",
        }
        return _SEMANTIC_MAP[tp_type]

    # 3. Try JSON/YAML/XML detection by content (fast structural checks)
    stripped = text.strip()
    if stripped:
        first_char = stripped[0]
        if first_char in "{[" and stripped[-1] in "}]":
            return "data_json"
        if first_char == "<" and stripped[-1] == ">":
            return "data_xml"

    # 4. Prose fallback
    return "prose"


def _guess_skeleton_filename(content_type: str) -> str:
    """Guess a filename for the skeletonizer based on content type."""
    _SKEL_MAP = {
        "code_python":  "code.py",
        "code_js":      "code.js",
        "code_ts":      "code.ts",
        "code_generic": "code.py",
        "data_json":    "data.json",
        "data_xml":     "data.xml",
        "data_yaml":    "data.yaml",
    }
    return _SKEL_MAP.get(content_type, "text.txt")


# ---------------------------------------------------------------------------
# Core router
# ---------------------------------------------------------------------------

def smart_route(text: str, intent: str = "understand",
                filename: str = "") -> CrunchResult:
    """Route text through the optimal compression pipeline.

    Args:
        text: The text to compress.
        intent: One of "understand", "code_review", "extract_data", "summarize".
        filename: Optional filename hint for better content-type detection.

    Returns:
        A CrunchResult with the compressed text and full metadata.
    """
    if not text or not text.strip():
        return CrunchResult(
            compressed_text=text or "",
            strategy_used="none",
            content_type="empty",
        )

    # Validate intent
    valid_intents = {"understand", "code_review", "extract_data", "summarize"}
    if intent not in valid_intents:
        intent = "understand"

    # Detect content type
    content_type = detect_content_type(text, filename)
    category = _content_type_category(content_type)

    # Look up strategy
    strategy = _STRATEGY_MAP.get((category, intent))
    if strategy is None:
        # Fallback: generic understand
        strategy = _STRATEGY_MAP[("prose", "understand")]

    # Count original tokens
    original_tokens = count_tokens(text)

    # Execute strategy steps
    result_text = text
    techniques: list[str] = []
    removed: list[str] = []
    confidence = strategy.base_confidence

    skel_filename = filename or _guess_skeleton_filename(content_type)

    for step in strategy.steps:
        if step == "redact":
            before = result_text
            result_text = redact_secrets(result_text)
            if result_text != before:
                techniques.append("secret_redaction")
                removed.append("Secrets redacted")

        elif step == "skeleton":
            before_tokens = count_tokens(result_text)
            result_text = crunch_skeleton(result_text, skel_filename)
            after_tokens = count_tokens(result_text)
            if after_tokens < before_tokens:
                saved = before_tokens - after_tokens
                techniques.append(f"skeleton:{content_type}")
                removed.append(
                    f"Skeleton stripped {saved} tokens "
                    f"({saved / before_tokens * 100:.0f}% of structure)"
                )

        elif step == "compress":
            result_text, stats = minify_for_ai(result_text)
            techniques.extend(stats.get("techniques_applied", []))
            removed.extend(stats.get("what_was_removed", []))

    # Compute final stats
    compressed_tokens = count_tokens(result_text)
    saved = original_tokens - compressed_tokens
    saved_pct = (saved / original_tokens * 100.0) if original_tokens > 0 else 0.0

    return CrunchResult(
        compressed_text=result_text,
        strategy_used=" → ".join(techniques) if techniques else "passthrough",
        content_type=content_type,
        what_was_removed=removed[:5],  # cap at 5 samples
        confidence=round(confidence, 2),
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        saved_percent=round(saved_pct, 1),
    )
