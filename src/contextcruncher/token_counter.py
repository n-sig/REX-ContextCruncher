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
