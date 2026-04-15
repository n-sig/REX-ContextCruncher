"""
prompt_optimizer.py — AI Prompt Optimizer for ContextCruncher.

Rewrites raw text into structured, role-optimized prompts using configurable
LLM backends (OpenAI, Anthropic, Ollama).  Designed for MCP tool consumption.

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
from dataclasses import dataclass, field, asdict
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

from contextcruncher.token_counter import count_tokens

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
# Built-in Profiles (immutable)
# -----------------------------------------------------------------------

_BUILTIN_PROFILES: dict[str, LLMProfile] = {
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
# Provider Implementations (httpx-based)
# -----------------------------------------------------------------------

_REQUEST_TIMEOUT = 30.0  # seconds


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
