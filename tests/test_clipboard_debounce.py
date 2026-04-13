"""
Tests for ClipboardMonitor debounce logic — BUG-07.

Strategy
--------
We run the monitor's _run() loop in a real thread but substitute:
  - a mock for get_seq()       → controls what sequence numbers are "seen"
  - a mock for pyperclip.paste → returns the text we want
  - a spy callback             → records every invocation

Time is NOT mocked — we rely on the real wall clock with short delays
(debounce_delay=0.05 s, poll interval=0.02 s) so tests remain fast while
still exercising the debounce window.

Each test sets up a ClipboardMonitor, starts it, injects clipboard-change
events via a shared sequence counter, waits a controlled amount of time,
stops the monitor, and checks the callback invocation count.
"""

from __future__ import annotations

import time
import threading
import types
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ── Stub ctypes.windll so ClipboardMonitor can be imported on Linux ──────────
import ctypes

if not hasattr(ctypes, "windll"):
    windll_stub = types.SimpleNamespace(
        user32=types.SimpleNamespace(
            GetClipboardSequenceNumber=mock.MagicMock(return_value=1)
        )
    )
    ctypes.windll = windll_stub

# ── Stub pyperclip at import time ─────────────────────────────────────────────
_pyperclip_stub = types.ModuleType("pyperclip")
_pyperclip_stub.paste = mock.MagicMock(return_value="hello world")
_pyperclip_stub.copy  = mock.MagicMock()
sys.modules["pyperclip"] = _pyperclip_stub

from contextcruncher.clipboard_monitor import ClipboardMonitor  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SeqSource:
    """Thread-safe incrementing clipboard sequence counter."""

    def __init__(self, start: int = 1) -> None:
        self._seq = start
        self._lock = threading.Lock()

    def get(self) -> int:
        with self._lock:
            return self._seq

    def bump(self) -> int:
        """Increment and return the new sequence number."""
        with self._lock:
            self._seq += 1
            return self._seq


def _make_monitor(
    seq_source: _SeqSource,
    callback,
    debounce_delay: float = 0.05,
    check_interval: float = 0.02,
    min_text_length: int = 1,
) -> ClipboardMonitor:
    mon = ClipboardMonitor(
        check_interval=check_interval,
        on_clipboard_changed=callback,
        min_text_length=min_text_length,
        debounce_delay=debounce_delay,
    )
    # Replace the Windows-specific sequence-number function with our mock.
    mon.get_seq = seq_source.get
    mon.last_seq = seq_source.get()
    return mon


# ---------------------------------------------------------------------------
# Test: debounce disabled (debounce_delay=0)
# ---------------------------------------------------------------------------

def test_no_debounce_fires_on_every_change():
    """With debounce_delay=0 the callback should fire for each distinct seq change."""
    seq = _SeqSource(start=10)
    calls: list[str] = []
    _pyperclip_stub.paste.return_value = "some text"

    mon = _make_monitor(seq, lambda t: calls.append(t), debounce_delay=0.0)
    mon.start()

    try:
        seq.bump()
        time.sleep(0.08)  # let poll loop run (~4 cycles at 0.02 s)
        count_after_first = len(calls)

        seq.bump()
        time.sleep(0.08)
        count_after_second = len(calls)
    finally:
        mon.stop()

    assert count_after_first >= 1,  "First change must fire callback"
    assert count_after_second >= 2, "Second change must fire callback again"


# ---------------------------------------------------------------------------
# Test: single change fires exactly once after debounce window
# ---------------------------------------------------------------------------

def test_single_change_fires_once():
    """A single clipboard change must invoke the callback exactly once."""
    seq = _SeqSource(start=20)
    calls: list[str] = []
    _pyperclip_stub.paste.return_value = "debounced text"

    mon = _make_monitor(seq, lambda t: calls.append(t), debounce_delay=0.05)
    mon.start()

    try:
        seq.bump()
        # Wait: debounce (0.05 s) + a few poll cycles (0.02 s each) + slack
        time.sleep(0.25)
    finally:
        mon.stop()

    assert len(calls) == 1, f"Expected exactly 1 call, got {len(calls)}"


# ---------------------------------------------------------------------------
# Test: rapid changes — only final state is processed
# ---------------------------------------------------------------------------

def test_rapid_changes_only_final_processed():
    """
    Three rapid bumps inside the debounce window must result in at most ONE
    callback invocation (for the last settled state), not three.
    """
    seq = _SeqSource(start=30)
    calls: list[str] = []
    _pyperclip_stub.paste.return_value = "final text"

    # Use a longer debounce so all three bumps land inside the window.
    mon = _make_monitor(seq, lambda t: calls.append(t), debounce_delay=0.15)
    mon.start()

    try:
        # Fire three changes in quick succession (< debounce window).
        seq.bump()
        time.sleep(0.02)
        seq.bump()
        time.sleep(0.02)
        seq.bump()

        # Now wait for the debounce window to expire + extra slack.
        time.sleep(0.35)
    finally:
        mon.stop()

    assert len(calls) <= 1, (
        f"Rapid changes must collapse into at most 1 callback, got {len(calls)}"
    )


# ---------------------------------------------------------------------------
# Test: two separate bursts each produce one callback
# ---------------------------------------------------------------------------

def test_two_separated_bursts_each_fire_once():
    """
    Two bursts separated by more than debounce_delay must each fire the
    callback once — total 2 calls.
    """
    seq = _SeqSource(start=40)
    calls: list[str] = []
    _pyperclip_stub.paste.return_value = "burst text"

    mon = _make_monitor(seq, lambda t: calls.append(t), debounce_delay=0.05)
    mon.start()

    try:
        # Burst 1
        seq.bump()
        time.sleep(0.20)  # well beyond debounce window

        # Burst 2
        seq.bump()
        time.sleep(0.20)
    finally:
        mon.stop()

    assert len(calls) == 2, (
        f"Two separated bursts must yield 2 callbacks, got {len(calls)}"
    )


# ---------------------------------------------------------------------------
# Test: no callback when clipboard is unchanged
# ---------------------------------------------------------------------------

def test_no_callback_without_change():
    """When the sequence number never changes the callback must never fire."""
    seq = _SeqSource(start=50)
    calls: list[str] = []

    mon = _make_monitor(seq, lambda t: calls.append(t), debounce_delay=0.05)
    mon.start()

    try:
        time.sleep(0.20)  # let several poll cycles pass without bumping seq
    finally:
        mon.stop()

    assert len(calls) == 0, f"No change — callback must not fire, got {len(calls)}"


# ---------------------------------------------------------------------------
# Test: min_text_length guard still active with debounce enabled
# ---------------------------------------------------------------------------

def test_min_length_guard_with_debounce():
    """Short clipboard text must be ignored even when debounce is active."""
    seq = _SeqSource(start=60)
    calls: list[str] = []
    _pyperclip_stub.paste.return_value = "hi"  # length 2

    mon = _make_monitor(
        seq,
        lambda t: calls.append(t),
        debounce_delay=0.05,
        min_text_length=5,   # "hi" (2 chars) is below the threshold
    )
    mon.start()

    try:
        seq.bump()
        time.sleep(0.25)
    finally:
        mon.stop()

    assert len(calls) == 0, (
        f"Text below min_text_length must not trigger callback, got {len(calls)}"
    )


# ---------------------------------------------------------------------------
# Test: callback return value is written back to clipboard
# ---------------------------------------------------------------------------

def test_callback_writeback():
    """If the callback returns a new string it must be written to the clipboard."""
    seq = _SeqSource(start=70)
    _pyperclip_stub.paste.return_value = "original text"
    _pyperclip_stub.copy.reset_mock()

    def _transform(text: str) -> str:
        return text.upper()

    mon = _make_monitor(seq, _transform, debounce_delay=0.05)
    mon.start()

    try:
        seq.bump()
        time.sleep(0.25)
    finally:
        mon.stop()

    assert _pyperclip_stub.copy.called, "pyperclip.copy must be called for writeback"
    written = _pyperclip_stub.copy.call_args[0][0]
    assert written == "ORIGINAL TEXT", f"Unexpected writeback value: {written!r}"


# ---------------------------------------------------------------------------
# Test: callback returning None does NOT overwrite clipboard
# ---------------------------------------------------------------------------

def test_no_writeback_when_callback_returns_none():
    """If the callback returns None the clipboard must NOT be overwritten."""
    seq = _SeqSource(start=80)
    _pyperclip_stub.paste.return_value = "do not touch"
    _pyperclip_stub.copy.reset_mock()

    mon = _make_monitor(seq, lambda t: None, debounce_delay=0.05)
    mon.start()

    try:
        seq.bump()
        time.sleep(0.25)
    finally:
        mon.stop()

    assert not _pyperclip_stub.copy.called, (
        "clipboard must not be overwritten when callback returns None"
    )


# ---------------------------------------------------------------------------
# Test: callback returning identical text does NOT overwrite clipboard
# ---------------------------------------------------------------------------

def test_no_writeback_when_text_unchanged():
    """If callback returns the same text, pyperclip.copy must not be called."""
    seq = _SeqSource(start=90)
    original = "same text"
    _pyperclip_stub.paste.return_value = original
    _pyperclip_stub.copy.reset_mock()

    mon = _make_monitor(seq, lambda t: t, debounce_delay=0.05)
    mon.start()

    try:
        seq.bump()
        time.sleep(0.25)
    finally:
        mon.stop()

    assert not _pyperclip_stub.copy.called, (
        "No writeback expected when returned text equals original"
    )


# ---------------------------------------------------------------------------
# Test: monitor can be stopped and restarted
# ---------------------------------------------------------------------------

def test_start_stop_restart():
    """Monitor must be restartable after being stopped."""
    seq = _SeqSource(start=100)
    calls: list[str] = []
    _pyperclip_stub.paste.return_value = "restart test"

    mon = _make_monitor(seq, lambda t: calls.append(t), debounce_delay=0.05)

    # First run
    mon.start()
    seq.bump()
    time.sleep(0.25)
    mon.stop()
    time.sleep(0.05)  # let thread exit
    count_first = len(calls)

    # Second run
    mon.start()
    seq.bump()
    time.sleep(0.25)
    mon.stop()
    count_second = len(calls)

    assert count_first >= 1,              "First run must fire callback"
    assert count_second > count_first,    "Restart must fire callback again"
