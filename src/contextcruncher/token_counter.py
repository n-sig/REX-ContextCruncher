"""
token_counter.py — Token counting and cost estimation for LLM text.

Uses tiktoken (OpenAI's tokenizer) to measure actual LLM token counts
for compression benchmarks and statistics. Falls back to a word-based
estimate if tiktoken is not available.

FR-02: cost_estimate() maps a token count to per-model costs in US cents.
Prices reflect publicly listed input rates (per 1 M tokens) as of 2025.
"""

from __future__ import annotations

_encs = {}
_FALLBACK = False

import os
import sys
import json
from pathlib import Path

if sys.platform == "win32":
    _APP_DIR = Path(os.getenv("APPDATA", os.path.expanduser("~"))) / "ContextCruncher"
else:
    _APP_DIR = Path("~/.config/ContextCruncher").expanduser()

def _load_json_config(filename: str, default_data: dict) -> dict:
    try:
        path = _APP_DIR / filename
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged = dict(default_data)
                    merged.update(data)
                    return merged
    except Exception:
        pass
    return default_data

# ---------------------------------------------------------------------------
# FR-02 — Model price table
# Key  : display name shown in the UI
# Value: USD cost per 1 000 000 input tokens  (= cost_per_token × 1 000 000)
# ---------------------------------------------------------------------------
_DEFAULT_COST_TABLE: dict[str, float] = {
    "GPT-4o":            2.50,
    "GPT-4o mini":       0.15,
    "o3 mini":           1.10,
    "Claude 3.5 Sonnet": 3.00,
    "Claude 3.5 Haiku":  0.80,
    "Claude 3 Opus":    15.00,
}

COST_TABLE = _load_json_config("prices.json", _DEFAULT_COST_TABLE)


def get_model_encoding(model: str) -> str:
    """Return the tiktoken encoding name for a given model."""
    if "GPT-4o" in model or "o1" in model or "o3" in model:
        return "o200k_base"
    # Claude uses a custom tokenizer (different from cl100k_base)
    # but cl100k_base is a reasonable approximation for cost estimation.
    return "cl100k_base"


def _get_encoder(encoding_name: str = "o200k_base"):
    """Lazy-load the tiktoken encoder."""
    global _encs, _FALLBACK
    if encoding_name in _encs or _FALLBACK:
        return _encs.get(encoding_name)
    try:
        import tiktoken
        _encs[encoding_name] = tiktoken.get_encoding(encoding_name)
    except Exception:
        _FALLBACK = True
        _encs[encoding_name] = None
    return _encs.get(encoding_name)


def count_tokens(text: str, encoding: str = "o200k_base") -> int:
    """Count the number of LLM tokens in *text*.

    Uses tiktoken for accurate counts. Defaults to o200k_base (GPT-4o).
    Falls back to a rough word-based estimate (×1.3) if tiktoken is unavailable.
    """
    if not text:
        return 0
    enc = _get_encoder(encoding)
    if enc:
        return len(enc.encode(text))
    # Fallback: ~1.3 tokens per word is a reasonable average for English
    return int(len(text.split()) * 1.3)


def truncate_to_budget(text: str, token_budget: int,
                       encoding: str = "o200k_base") -> tuple[str, int]:
    """Truncate *text* to fit within *token_budget* tokens.

    Uses tiktoken encode → slice → decode for exact token-level precision.
    Returns ``(truncated_text, actual_token_count)``.  If the text already
    fits, it is returned unchanged.
    """
    if not text or token_budget <= 0:
        return "", 0
    tokens = count_tokens(text, encoding)
    if tokens <= token_budget:
        return text, tokens
    enc = _get_encoder(encoding)
    if enc:
        encoded = enc.encode(text)
        # Decode and re-check: boundary tokens may expand on re-encode.
        end = token_budget
        while end > 0:
            truncated = enc.decode(encoded[:end])
            actual = len(enc.encode(truncated))
            if actual <= token_budget:
                return truncated, actual
            end -= 1
        return "", 0
    # Fallback: character-ratio approximation
    ratio = token_budget / tokens
    cut_point = int(len(text) * ratio)
    return text[:cut_point], token_budget


# ---------------------------------------------------------------------------
# FR-03 — Context window sizes (tokens)
# ---------------------------------------------------------------------------
_DEFAULT_CONTEXT_WINDOW_TABLE: dict[str, int] = {
    "GPT-4o":            128_000,
    "GPT-4o mini":       128_000,
    "o3 mini":           200_000,
    "Claude 3.5 Sonnet": 200_000,
    "Claude 3.5 Haiku":  200_000,
    "Claude 3 Opus":     200_000,
}

CONTEXT_WINDOW_TABLE = _load_json_config("context_windows.json", _DEFAULT_CONTEXT_WINDOW_TABLE)

# Warning thresholds for context window usage.
CONTEXT_WARN_PCT  = 50   # ⚠  yellow — more than half the window consumed
CONTEXT_ALERT_PCT = 75   # 🚨 red   — danger zone


def context_window_usage(text_or_tokens: str | int) -> dict[str, float]:
    """Return the percentage of each model's context window consumed.

    Args:
        text_or_tokens: Text to evaluate (will use exact per-model tokens)
                        or hardcoded token count (int) for all models.

    Returns:
        ``{model_name: usage_percent}``
    """
    result: dict[str, float] = {}
    if isinstance(text_or_tokens, str):
        tok_o200k = count_tokens(text_or_tokens, "o200k_base")
        tok_cl100k = count_tokens(text_or_tokens, "cl100k_base")
    else:
        tok_o200k = text_or_tokens
        tok_cl100k = text_or_tokens

    for model, window in CONTEXT_WINDOW_TABLE.items():
        if isinstance(text_or_tokens, str):
            enc_name = get_model_encoding(model)
            tc = tok_o200k if enc_name == "o200k_base" else tok_cl100k
        else:
            tc = text_or_tokens
            
        pct = tc / window * 100.0
        result[model] = round(pct, 2)
    return result


def context_window_warning(text_or_tokens: str | int, warn_pct: float = CONTEXT_ALERT_PCT
                           ) -> tuple[str, float] | None:
    """Return (model_name, usage_pct) for the most-filled model above *warn_pct*.

    Returns ``None`` when no model exceeds the threshold.
    """
    usage = context_window_usage(text_or_tokens)
    candidates = [(model, pct) for model, pct in usage.items() if pct >= warn_pct]
    if not candidates:
        return None
    # Return worst case: model whose window is most filled
    return max(candidates, key=lambda x: x[1])


def cost_estimate(text_or_tokens: str | int) -> dict[str, float]:
    """Return estimated input cost in US cents for each model in COST_TABLE.

    Args:
        text_or_tokens: Text (uses exact tokenizer mapping) or raw token count (int).

    Returns:
        ``{model_name: cost_in_us_cents}`` for every entry in COST_TABLE.
    """
    result: dict[str, float] = {}
    
    if isinstance(text_or_tokens, str):
        tok_o200k = count_tokens(text_or_tokens, "o200k_base")
        tok_cl100k = count_tokens(text_or_tokens, "cl100k_base")
    else:
        tok_o200k = text_or_tokens
        tok_cl100k = text_or_tokens
        
    for model, usd_per_million in COST_TABLE.items():
        if isinstance(text_or_tokens, str):
            enc_name = get_model_encoding(model)
            tc = tok_o200k if enc_name == "o200k_base" else tok_cl100k
        else:
            tc = text_or_tokens
            
        cents = tc * usd_per_million / 1_000_000 * 100
        result[model] = round(cents, 6)
    return result


def format_cost(cents: float) -> str:
    """Format a cost value in US cents for human display.

    Automatically picks a sensible number of decimal places:
    - < 0.01 ¢  → 4 decimal places  (e.g. "0.0025 ¢")
    - < 1.00 ¢  → 3 decimal places  (e.g. "0.250 ¢")
    - >= 1.00 ¢ → 2 decimal places  (e.g. "12.50 ¢")
    """
    if cents < 0.01:
        return f"{cents:.4f} ¢"
    if cents < 1.0:
        return f"{cents:.3f} ¢"
    return f"{cents:.2f} ¢"


def token_stats(original: str, compressed: str) -> dict:
    """Compare token counts between original and compressed text.

    Returns:
        A dict with original_tokens, compressed_tokens, tokens_saved,
        saved_percent, and a human-readable summary.
    """
    orig_tokens = count_tokens(original)
    comp_tokens = count_tokens(compressed)
    saved = orig_tokens - comp_tokens
    pct = (saved / orig_tokens * 100.0) if orig_tokens > 0 else 0.0

    return {
        "original_tokens": orig_tokens,
        "compressed_tokens": comp_tokens,
        "tokens_saved": saved,
        "saved_percent": round(pct, 1),
        "summary": f"{orig_tokens} → {comp_tokens} tokens ({pct:.1f}% saved)",
    }
