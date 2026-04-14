"""
Tests for FR-03 — Context window usage and warning.

Covers:
  1. CONTEXT_WINDOW_TABLE structure and consistency with COST_TABLE
  2. context_window_usage() arithmetic
  3. context_window_usage() edge cases
  4. context_window_warning() threshold logic
  5. context_window_warning() returns worst-case model
  6. context_warn_pct default in config
"""

from __future__ import annotations

import sys
import types
import unittest.mock as mock
from pathlib import Path

import pytest

# ── Stub winreg for Linux CI ─────────────────────────────────────────────────
if "winreg" not in sys.modules:
    _fw = types.ModuleType("winreg")
    for _a in ("OpenKey", "CloseKey", "SetValueEx", "DeleteValue",
                "QueryValueEx", "HKEY_CURRENT_USER", "KEY_SET_VALUE",
                "KEY_READ", "REG_SZ"):
        setattr(_fw, _a, mock.MagicMock())
    sys.modules["winreg"] = _fw

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.token_counter import (  # noqa: E402
    COST_TABLE,
    CONTEXT_WINDOW_TABLE,
    CONTEXT_WARN_PCT,
    CONTEXT_ALERT_PCT,
    context_window_usage,
    context_window_warning,
)
from contextcruncher.config import _DEFAULT_CONFIG   # noqa: E402


# ---------------------------------------------------------------------------
# CONTEXT_WINDOW_TABLE structure
# ---------------------------------------------------------------------------

def test_context_window_table_not_empty():
    assert len(CONTEXT_WINDOW_TABLE) > 0


def test_context_window_table_matches_cost_table_keys():
    """Every model in COST_TABLE must also appear in CONTEXT_WINDOW_TABLE."""
    for model in COST_TABLE:
        assert model in CONTEXT_WINDOW_TABLE, (
            f"Model {model!r} is in COST_TABLE but missing from CONTEXT_WINDOW_TABLE"
        )


def test_context_window_table_all_positive():
    for model, size in CONTEXT_WINDOW_TABLE.items():
        assert size > 0, f"Context window for {model!r} must be positive"


def test_context_window_table_all_integers():
    for model, size in CONTEXT_WINDOW_TABLE.items():
        assert isinstance(size, int), f"Context window for {model!r} must be int"


def test_context_window_thresholds_ordered():
    assert CONTEXT_WARN_PCT < CONTEXT_ALERT_PCT, (
        "CONTEXT_WARN_PCT must be less than CONTEXT_ALERT_PCT"
    )


def test_context_window_thresholds_sane():
    assert 0 < CONTEXT_WARN_PCT < 100
    assert 0 < CONTEXT_ALERT_PCT <= 100


# ---------------------------------------------------------------------------
# context_window_usage() arithmetic
# ---------------------------------------------------------------------------

def test_context_window_usage_returns_all_models():
    result = context_window_usage(1000)
    assert set(result.keys()) == set(CONTEXT_WINDOW_TABLE.keys())


def test_context_window_usage_zero_tokens():
    result = context_window_usage(0)
    for model, pct in result.items():
        assert pct == 0.0


def test_context_window_usage_full_window():
    """A text the exact size of a window must yield ~100%."""
    for model, window_size in CONTEXT_WINDOW_TABLE.items():
        result = context_window_usage(window_size)
        assert abs(result[model] - 100.0) < 0.01, (
            f"{model}: expected 100%, got {result[model]}"
        )


def test_context_window_usage_half_window():
    """Half the window size must yield ~50%."""
    for model, window_size in CONTEXT_WINDOW_TABLE.items():
        result = context_window_usage(window_size // 2)
        assert abs(result[model] - 50.0) < 0.1


def test_context_window_usage_over_100_allowed():
    """Text larger than context window must yield > 100%, not capped."""
    # Use the largest window to ensure we can exceed it
    max_window = max(CONTEXT_WINDOW_TABLE.values())
    result = context_window_usage(max_window * 2)
    for model, pct in result.items():
        if CONTEXT_WINDOW_TABLE[model] == max_window:
            assert pct > 100.0


def test_context_window_usage_scales_linearly():
    r1 = context_window_usage(10_000)
    r2 = context_window_usage(20_000)
    for model in CONTEXT_WINDOW_TABLE:
        assert abs(r2[model] - r1[model] * 2) < 0.01


def test_context_window_usage_values_are_floats():
    result = context_window_usage(5000)
    for model, pct in result.items():
        assert isinstance(pct, float)


# ---------------------------------------------------------------------------
# context_window_warning() threshold logic
# ---------------------------------------------------------------------------

def test_warning_returns_none_below_threshold():
    """With 100 tokens, no model should exceed even the lowest threshold."""
    result = context_window_warning(100, warn_pct=CONTEXT_WARN_PCT)
    assert result is None


def test_warning_returns_none_when_exactly_below():
    """Just below threshold must return None."""
    # Pick smallest window, compute tokens for 1% below threshold
    min_window = min(CONTEXT_WINDOW_TABLE.values())
    tokens = int(min_window * (CONTEXT_ALERT_PCT - 1) / 100)
    result = context_window_warning(tokens, warn_pct=CONTEXT_ALERT_PCT)
    assert result is None


def test_warning_fires_when_threshold_exceeded():
    """Tokens at 100% of any window must trigger a warning."""
    min_window = min(CONTEXT_WINDOW_TABLE.values())
    result = context_window_warning(min_window, warn_pct=50.0)
    assert result is not None


def test_warning_returns_tuple_of_model_and_pct():
    min_window = min(CONTEXT_WINDOW_TABLE.values())
    result = context_window_warning(min_window, warn_pct=50.0)
    assert isinstance(result, tuple)
    assert len(result) == 2
    model, pct = result
    assert isinstance(model, str)
    assert isinstance(pct, float)


def test_warning_returns_worst_case_model():
    """Warning must return the model whose window is most consumed (highest %)."""
    # Use a token count that fills 100% of the smallest window
    min_window = min(CONTEXT_WINDOW_TABLE.values())
    worst_model = min(CONTEXT_WINDOW_TABLE, key=lambda m: CONTEXT_WINDOW_TABLE[m])

    result = context_window_warning(min_window, warn_pct=50.0)
    assert result is not None
    returned_model, _ = result
    assert returned_model == worst_model, (
        f"Expected worst-case model {worst_model!r}, got {returned_model!r}"
    )


def test_warning_model_name_in_table():
    """The returned model name must exist in CONTEXT_WINDOW_TABLE."""
    min_window = min(CONTEXT_WINDOW_TABLE.values())
    result = context_window_warning(min_window, warn_pct=50.0)
    assert result is not None
    model, _ = result
    assert model in CONTEXT_WINDOW_TABLE


def test_warning_pct_above_threshold():
    """Returned usage percentage must be >= warn_pct."""
    min_window = min(CONTEXT_WINDOW_TABLE.values())
    threshold = 50.0
    result = context_window_warning(min_window, warn_pct=threshold)
    assert result is not None
    _, pct = result
    assert pct >= threshold


# ---------------------------------------------------------------------------
# Config default
# ---------------------------------------------------------------------------

def test_context_warn_pct_in_default_config():
    assert "context_warn_pct" in _DEFAULT_CONFIG, (
        "FR-03 requires 'context_warn_pct' in _DEFAULT_CONFIG"
    )


def test_context_warn_pct_default_value_sane():
    val = _DEFAULT_CONFIG["context_warn_pct"]
    assert isinstance(val, (int, float))
    assert 0 < val <= 100
