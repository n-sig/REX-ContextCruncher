"""
Tests for ClipboardMonitor — specifically the BUG-03 min_text_length filter.

Because ClipboardMonitor.__init__ calls ctypes.windll (Windows-only), we
patch it out so the tests run on any platform (Linux CI included).
"""

import sys
import types
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Platform shim — inject a fake ctypes.windll so imports work on Linux
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Build a minimal fake windll
_fake_windll = MagicMock()
_fake_windll.user32.GetClipboardSequenceNumber.return_value = 0
_fake_windll.kernel32.CreateMutexW.return_value = 1
_fake_windll.kernel32.GetLastError.return_value = 0

import ctypes as _ctypes
if not hasattr(_ctypes, "windll"):
    _ctypes.windll = _fake_windll  # type: ignore[attr-defined]
else:
    _fake_windll = _ctypes.windll  # use real one if available (Windows)

from contextcruncher.clipboard_monitor import ClipboardMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_monitor(callback=None, min_length=5) -> ClipboardMonitor:
    """Create a ClipboardMonitor without starting its background thread."""
    with patch.object(_ctypes.windll.user32, "GetClipboardSequenceNumber", return_value=0):
        monitor = ClipboardMonitor(
            check_interval=0.5,
            on_clipboard_changed=callback,
            min_text_length=min_length,
        )
    return monitor


# ---------------------------------------------------------------------------
# Constructor / parameter tests
# ---------------------------------------------------------------------------

def test_default_min_length():
    m = _make_monitor()
    assert m.min_text_length == 5

def test_custom_min_length():
    m = _make_monitor(min_length=20)
    assert m.min_text_length == 20

def test_min_length_zero_disables_filter():
    m = _make_monitor(min_length=0)
    assert m.min_text_length == 0

def test_negative_min_length_clamped_to_zero():
    m = _make_monitor(min_length=-10)
    assert m.min_text_length == 0


# ---------------------------------------------------------------------------
# Filter logic — simulate what _run() does before calling the callback
# ---------------------------------------------------------------------------

def _simulate_clipboard_event(monitor: ClipboardMonitor, text: str) -> str | None:
    """
    Reproduce exactly the filter logic from ClipboardMonitor._run()
    without spawning a thread.  Returns the callback's return value, or
    the sentinel string '__FILTERED__' when the monitor would have skipped
    the entry.
    """
    if not text or not str(text).strip():
        return "__FILTERED__"
    t = str(text)
    if monitor.min_text_length > 0 and len(t.strip()) < monitor.min_text_length:
        return "__FILTERED__"
    if monitor.on_clipboard_changed:
        return monitor.on_clipboard_changed(t)
    return None


def test_filter_blocks_empty_string():
    called = []
    m = _make_monitor(callback=lambda t: called.append(t) or None)
    result = _simulate_clipboard_event(m, "")
    assert result == "__FILTERED__"
    assert called == []

def test_filter_blocks_whitespace_only():
    called = []
    m = _make_monitor(callback=lambda t: called.append(t) or None)
    result = _simulate_clipboard_event(m, "   \n\t  ")
    assert result == "__FILTERED__"
    assert called == []

def test_filter_blocks_below_threshold():
    called = []
    m = _make_monitor(callback=lambda t: called.append(t) or None, min_length=5)
    for short in ["a", "ab", "abc", "abcd"]:   # 1-4 chars
        called.clear()
        result = _simulate_clipboard_event(m, short)
        assert result == "__FILTERED__", f"Expected filter for {short!r}"
        assert called == [], f"Callback was called for {short!r}"

def test_filter_allows_at_threshold():
    called = []
    m = _make_monitor(callback=lambda t: called.append(t) or None, min_length=5)
    result = _simulate_clipboard_event(m, "hello")   # exactly 5 chars
    assert result != "__FILTERED__"
    assert "hello" in called

def test_filter_allows_above_threshold():
    called = []
    m = _make_monitor(callback=lambda t: called.append(t) or None, min_length=5)
    result = _simulate_clipboard_event(m, "Hello, World!")
    assert result != "__FILTERED__"
    assert "Hello, World!" in called

def test_filter_strips_whitespace_before_length_check():
    """'  hi  ' is 6 chars total but only 2 stripped — should be filtered."""
    called = []
    m = _make_monitor(callback=lambda t: called.append(t) or None, min_length=5)
    result = _simulate_clipboard_event(m, "  hi  ")
    assert result == "__FILTERED__"
    assert called == []

def test_filter_disabled_at_zero_allows_single_char():
    called = []
    m = _make_monitor(callback=lambda t: called.append(t) or None, min_length=0)
    result = _simulate_clipboard_event(m, "x")
    assert result != "__FILTERED__"
    assert "x" in called

def test_callback_receives_exact_text():
    received = []
    m = _make_monitor(callback=lambda t: received.append(t) or None, min_length=5)
    _simulate_clipboard_event(m, "clipboard content here")
    assert received == ["clipboard content here"]

def test_callback_return_value_propagated():
    m = _make_monitor(callback=lambda t: "REPLACED", min_length=5)
    result = _simulate_clipboard_event(m, "some long clipboard text")
    assert result == "REPLACED"

def test_no_callback_returns_none():
    m = _make_monitor(callback=None, min_length=5)
    result = _simulate_clipboard_event(m, "some long clipboard text")
    assert result is None


# ---------------------------------------------------------------------------
# Stack integration: verify stack doesn't grow with short entries
# ---------------------------------------------------------------------------

def test_stack_not_inflated_by_short_clipboard_events():
    """
    Simulate the scenario from BUG-03: user copies 2 things, but 32 background
    events fire.  With the filter (min_length=5), only user copies should reach
    the stack.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from contextcruncher.stack import TextStack

    stack = TextStack()

    def fake_handle(text: str) -> None:
        stack.push(text)
        return None

    m = _make_monitor(callback=fake_handle, min_length=5)

    # Simulate 32 background "noise" events (< 5 chars)
    noise = ["a", "1", "ok", "px", "id", "no", "if", "fn", "", "  "]
    for _ in range(3):
        for n in noise:
            _simulate_clipboard_event(m, n)

    assert stack.size() == 0, f"Stack should be empty after noise, got {stack.size()}"

    # Simulate 2 real user copies
    _simulate_clipboard_event(m, "SELECT * FROM users WHERE id = 42")
    _simulate_clipboard_event(m, "https://github.com/n-sig/ContextCruncher")

    assert stack.size() == 2, f"Stack should have exactly 2 entries, got {stack.size()}"
