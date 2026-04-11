"""
normalize.py — Smart number normalization for OCR results.

Detects formatted numbers (credit cards, IBANs, phone numbers, etc.) and
produces a compact variant with separators stripped.  The caller can then
push both the original and the compact version onto the stack so the user
can switch between them with a single hotkey.

Rules:
  • A text is considered a "formatted number" when:
      1. It is a single line (no line breaks).
      2. After removing common visual separators (space, dash, dot, slash)
         the remainder is ≥ 60 % digits.
      3. The original text actually *contains* at least one separator
         (otherwise there's nothing to strip).
      4. The compact form differs from the original (obvious, but a guard).
  • Common patterns that match:
      – Credit cards:    4532 1234 5678 9012
      – IBANs:           DE89 3704 0044 0532 0130 00
      – Phone numbers:   +49 176 123 456 78
      – Dates:           11.04.2026  /  11/04/2026
      – Serial numbers:  A1B2-C3D4-E5F6
  • Texts that should NOT be stripped:
      – Normal prose with spaces ("Hello World").
      – Mixed content where digits are a minority.
"""

from __future__ import annotations

import re

# Characters considered "visual separators" in formatted numbers.
_SEPARATORS = set(" -./")


def compact_variant(text: str) -> str | None:
    """Return a whitespace/separator-stripped version of *text*, or *None*.

    Returns *None* if *text* does not look like a formatted number and
    should therefore be kept as-is (no extra stack entry needed).
    """
    # Only single-line texts qualify.
    if "\n" in text:
        return None

    stripped = text.strip()
    if not stripped:
        return None

    # Does the text contain any separators at all?
    if not any(ch in _SEPARATORS for ch in stripped):
        return None

    # Remove all separator characters.
    compact = re.sub(r"[\s\-./]+", "", stripped)

    # Nothing left? Bail.
    if not compact:
        return None

    # Count how many characters are digits (or '+' for phone prefix).
    digit_like = sum(1 for ch in compact if ch.isdigit() or ch == "+")
    ratio = digit_like / len(compact)

    # Threshold: at least 60 % digit-like characters.
    if ratio < 0.60:
        return None

    # Make sure stripping actually changed something.
    if compact == stripped:
        return None

    return compact
