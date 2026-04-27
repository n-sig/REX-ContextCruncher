"""
Tests for feedback.py toast stacking (Bild 9 fix).

Before: two toasts fired back-to-back landed on the exact same screen
coords, so the second one fully covered the first. We verify the new
module-level active list and reflow logic:

  * adding a toast inserts it at the head
  * removing a toast pops it off
  * stacked toasts occupy distinct Y positions separated by the configured gap
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# feedback.py hard-imports tkinter at module load; skip on Linux CI
# environments where Tk isn't compiled in. The toast-stacking logic is
# exercised on Windows where tkinter is always available.
tk = pytest.importorskip("tkinter")

from contextcruncher import feedback  # noqa: E402


class _FakeToast:
    """Minimal stand-in for a tk.Toplevel used in reflow tests."""

    def __init__(self, w: int = 200, h: int = 50, sw: int = 1920, sh: int = 1080):
        self._w = w
        self._h = h
        self._sw = sw
        self._sh = sh
        self._geometry: str | None = None
        self._alive = True

    def winfo_exists(self) -> bool:
        return self._alive

    def winfo_reqwidth(self) -> int:
        return self._w

    def winfo_reqheight(self) -> int:
        return self._h

    def winfo_screenwidth(self) -> int:
        return self._sw

    def winfo_screenheight(self) -> int:
        return self._sh

    def geometry(self, spec: str) -> None:
        self._geometry = spec

    def destroy(self) -> None:
        self._alive = False

    @property
    def y(self) -> int:
        # "+x+y"
        assert self._geometry is not None
        return int(self._geometry.rsplit("+", 1)[-1])

    @property
    def x(self) -> int:
        # "+x+y" → parts = ['', 'x', 'y']
        assert self._geometry is not None
        parts = self._geometry.split("+")
        return int(parts[1])


def _clear_active():
    feedback._active_toasts.clear()


def test_reflow_empty_is_noop():
    _clear_active()
    feedback._reflow_toasts()  # must not crash
    assert feedback._active_toasts == []


def test_reflow_positions_newest_at_bottom():
    """Newest (index 0) should be closest to the screen bottom."""
    _clear_active()
    older = _FakeToast()
    newer = _FakeToast()
    # Mimic the real insert pattern: new toast goes to head of the list.
    feedback._active_toasts.append(older)
    feedback._active_toasts.insert(0, newer)

    feedback._reflow_toasts()

    assert newer.y > older.y, (
        "Newest toast must sit lower on screen (larger Y) than older ones"
    )


def test_reflow_stacks_with_expected_gap():
    """Adjacent toasts should be separated by _TOAST_GAP pixels."""
    _clear_active()
    t_new = _FakeToast(h=50)
    t_old = _FakeToast(h=50)
    feedback._active_toasts.extend([t_new, t_old])  # index 0 is newest

    feedback._reflow_toasts()

    # t_new is at y_new; t_old sits above at y_old = y_new - h_new - gap.
    expected_gap = feedback._TOAST_GAP
    gap = t_new.y - (t_old.y + t_old._h)
    assert gap == expected_gap, (
        f"Expected gap of {expected_gap}px between toasts, got {gap}px"
    )


def test_reflow_purges_destroyed_windows():
    """Toasts whose Toplevel was destroyed must be evicted from the list."""
    _clear_active()
    alive = _FakeToast()
    dead = _FakeToast()
    dead.destroy()  # winfo_exists() now returns False

    feedback._active_toasts.extend([alive, dead])
    feedback._reflow_toasts()

    assert dead not in feedback._active_toasts
    assert alive in feedback._active_toasts


def test_reflow_respects_bottom_margin():
    """Newest toast's bottom edge sits at screen_height - _TOAST_BOTTOM_MARGIN."""
    _clear_active()
    t = _FakeToast(h=50, sh=1080)
    feedback._active_toasts.append(t)

    feedback._reflow_toasts()

    expected_bottom = 1080 - feedback._TOAST_BOTTOM_MARGIN
    assert t.y + t._h == expected_bottom


def test_reflow_anchors_bottom_left():
    """All toasts in the stack share the same left edge at _TOAST_LEFT_MARGIN.

    User request (v2.0.1): toasts moved from bottom-center to bottom-left
    (Google-style) so they no longer clash with the Windows taskbar clock
    or content in the middle of the screen.
    """
    _clear_active()
    t_new = _FakeToast(w=200, h=50)
    t_old = _FakeToast(w=300, h=50)  # different width: left edge still aligns
    feedback._active_toasts.extend([t_new, t_old])

    feedback._reflow_toasts()

    assert t_new.x == feedback._TOAST_LEFT_MARGIN, (
        f"Newest toast must be anchored at x={feedback._TOAST_LEFT_MARGIN}, "
        f"got {t_new.x}"
    )
    assert t_old.x == feedback._TOAST_LEFT_MARGIN, (
        "Older toast must share the same left-edge anchor so the stack "
        "forms a clean vertical column"
    )
