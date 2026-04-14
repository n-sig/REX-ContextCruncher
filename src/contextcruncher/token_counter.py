"""
token_counter.py — Token counting and cost estimation for LLM text.

Uses tiktoken (OpenAI's tokenizer) to measure actual LLM token counts
for compression benchmarks and statistics. Falls back to a word-based
estimate if tiktoken is not available.

FR-02: cost_estimate() maps a token count to per-model costs in US cents.
Prices reflect publicly listed input rates (per 1 M tokens) as of 2025.
"""

from __future__ import annotations

_enc = None
_FALLBACK = False

# ---------------------------------------------------------------------------
# FR-02 — Model price table
# Key  : display name shown in the UI
# Value: USD cost per 1 000 000 input tokens  (= cost_per_token × 1 000 000)
# ---------------------------------------------------------------------------
COST_TABLE: dict[str, float] = {
    "GPT-4o":            2.50,
    "GPT-4o mini":       0.15,
    "o3 mini":           1.10,
    "Claude 3.5 Sonnet": 3.00,
    "Claude 3.5 Haiku":  0.80,
    "Claude 3 Opus":    15.00,
}


def _get_encoder():
    """Lazy-load the tiktoken encoder (cl100k_base = GPT-4o, Claude, etc.)."""
    global _enc, _FALLBACK
    if _enc is not None or _FALLBACK:
        return _enc
    try:
        import tiktoken
        _enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _FALLBACK = True
        _enc = None
    return _enc


def count_tokens(text: str) -> int:
    """Count the number of LLM tokens in *text*.

    Uses cl100k_base (GPT-4o / Claude tokenizer) for accurate counts.
    Falls back to a rough word-based estimate (×1.3) if tiktoken is unavailable.
    """
    if not text:
        return 0
    enc = _get_encoder()
    if enc:
        return len(enc.encode(text))
    # Fallback: ~1.3 tokens per word is a reasonable average for English
    return int(len(text.split()) * 1.3)


# ---------------------------------------------------------------------------
# FR-03 — Context window sizes (tokens)
# ---------------------------------------------------------------------------
CONTEXT_WINDOW_TABLE: dict[str, int] = {
    "GPT-4o":            128_000,
    "GPT-4o mini":       128_000,
    "o3 mini":           200_000,
    "Claude 3.5 Sonnet": 200_000,
    "Claude 3.5 Haiku":  200_000,
    "Claude 3 Opus":     200_000,
}

# Warning thresholds for context window usage.
CONTEXT_WARN_PCT  = 50   # ⚠  yellow — more than half the window consumed
CONTEXT_ALERT_PCT = 75   # 🚨 red   — danger zone


def context_window_usage(token_count: int) -> dict[str, float]:
    """Return the percentage of each model's context window consumed.

    Args:
        token_count: Number of tokens in the text.

    Returns:
        ``{model_name: usage_percent}`` — values can exceed 100 when the
        text is longer than the context window.
    """
    result: dict[str, float] = {}
    for model, window in CONTEXT_WINDOW_TABLE.items():
        pct = token_count / window * 100.0
        result[model] = round(pct, 2)
    return result


def context_window_warning(token_count: int, warn_pct: float = CONTEXT_ALERT_PCT
                           ) -> tuple[str, float] | None:
    """Return (model_name, usage_pct) for the most-filled model above *warn_pct*.

    Returns ``None`` when no model exceeds the threshold.

    The model with the *smallest* context window (worst case for the user)
    is returned so the warning is maximally informative.
    """
    usage = context_window_usage(token_count)
    candidates = [(model, pct) for model, pct in usage.items() if pct >= warn_pct]
    if not candidates:
        return None
    # Return worst case: model whose window is most filled
    return max(candidates, key=lambda x: x[1])


def cost_estimate(token_count: int) -> dict[str, float]:
    """Return estimated input cost in US cents for each model in COST_TABLE.

    Args:
        token_count: Number of tokens (e.g. from count_tokens()).

    Returns:
        ``{model_name: cost_in_us_cents}`` for every entry in COST_TABLE.
        Values are rounded to 6 decimal places to keep sub-cent precision.

    Example::

        >>> cost_estimate(1000)
        {'GPT-4o': 0.25, 'GPT-4o mini': 0.015, ...}
    """
    result: dict[str, float] = {}
    for model, usd_per_million in COST_TABLE.items():
        cents = token_count * usd_per_million / 1_000_000 * 100
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
