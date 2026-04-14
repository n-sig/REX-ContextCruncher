"""
Tests for FR-04 — Mouse side button hotkeys.

ISOLATION NOTE: This file always overwrites the pynput stub in sys.modules
and reloads contextcruncher.hotkeys so the mouse-aware code paths are
exercised regardless of which test files ran before this one.

Covers:
  1. MOUSE_BUTTON_MAP structure
  2. hotkey_display_name() for <mouse_x1> / <mouse_x2>
  3. _MouseHotkeyListener fires callbacks on button press
  4. _MouseHotkeyListener ignores non-side buttons
  5. _MouseHotkeyListener ignores button-release events
  6. HotkeyManager separates mouse bindings from keyboard bindings
  7. HotkeyManager starts/stops mouse listener correctly
"""

from __future__ import annotations

import importlib
import sys
import types
import unittest.mock as mock
from pathlib import Path

import pytest

# ── Stub winreg ───────────────────────────────────────────────────────────────
if "winreg" not in sys.modules:
    _fw = types.ModuleType("winreg")
    for _a in ("OpenKey", "CloseKey", "SetValueEx", "DeleteValue",
                "QueryValueEx", "HKEY_CURRENT_USER", "KEY_SET_VALUE",
                "KEY_READ", "REG_SZ"):
        setattr(_fw, _a, mock.MagicMock())
    sys.modules["winreg"] = _fw

# ── Build complete pynput stub (keyboard + mouse) ─────────────────────────────
# We always overwrite to ensure this file is isolated from test execution order.

_pynput_pkg = types.ModuleType("pynput")
_pynput_pkg.__package__ = "pynput"


# keyboard stub
class _FakeGlobalHotKeys:
    def __init__(self, hotkeys):
        self._hotkeys = hotkeys
        self.daemon = False
    def start(self): pass
    def stop(self): pass

class _FakeKbListener:
    def __init__(self, on_press=None, on_release=None):
        self.on_press = on_press
        self.on_release = on_release
        self.daemon = False
    def start(self): pass
    def stop(self): pass

_kb_mod = types.ModuleType("pynput.keyboard")
_kb_mod.GlobalHotKeys = _FakeGlobalHotKeys
_kb_mod.Listener = _FakeKbListener

# keyboard Key / KeyCode stubs (needed by settings.py — not used here but guarded)
_kb_mod.Key = mock.MagicMock()
_kb_mod.KeyCode = mock.MagicMock()

_pynput_pkg.keyboard = _kb_mod
sys.modules["pynput.keyboard"] = _kb_mod


# mouse stub
class _FakeButton:
    x1 = object()
    x2 = object()
    left = object()
    right = object()


class _FakeMouseListener:
    _last_instance: "_FakeMouseListener | None" = None

    def __init__(self, on_click=None):
        self.on_click = on_click
        self.daemon = False
        _FakeMouseListener._last_instance = self

    def start(self): pass
    def stop(self): pass


_ms_mod = types.ModuleType("pynput.mouse")
_ms_mod.Button = _FakeButton
_ms_mod.Listener = _FakeMouseListener

_pynput_pkg.mouse = _ms_mod
sys.modules["pynput.mouse"] = _ms_mod
sys.modules["pynput"] = _pynput_pkg


# ── Reload contextcruncher.hotkeys so it picks up the fresh stubs ─────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

if "contextcruncher.hotkeys" in sys.modules:
    importlib.reload(sys.modules["contextcruncher.hotkeys"])

from contextcruncher.hotkeys import (   # noqa: E402
    HotkeyManager, _MouseHotkeyListener, MOUSE_BUTTON_MAP,
)
from contextcruncher.config import hotkey_display_name  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fire_click(button, pressed: bool) -> None:
    """Simulate a mouse button event via the last-created _FakeMouseListener."""
    ml = _FakeMouseListener._last_instance
    if ml and ml.on_click:
        ml.on_click(0, 0, button, pressed)


def _make_manager(bindings: dict) -> HotkeyManager:
    noop = lambda: None  # noqa: E731
    return HotkeyManager(
        on_scan=noop,
        on_navigate_up=noop,
        on_navigate_down=noop,
        hotkey_bindings=bindings,
    )


# ---------------------------------------------------------------------------
# MOUSE_BUTTON_MAP
# ---------------------------------------------------------------------------

def test_mouse_button_map_has_x1_and_x2():
    assert "<mouse_x1>" in MOUSE_BUTTON_MAP
    assert "<mouse_x2>" in MOUSE_BUTTON_MAP


def test_mouse_button_map_values_distinct():
    assert MOUSE_BUTTON_MAP["<mouse_x1>"] is not MOUSE_BUTTON_MAP["<mouse_x2>"]


def test_mouse_button_map_x1_is_fake_button_x1():
    assert MOUSE_BUTTON_MAP["<mouse_x1>"] is _FakeButton.x1


def test_mouse_button_map_x2_is_fake_button_x2():
    assert MOUSE_BUTTON_MAP["<mouse_x2>"] is _FakeButton.x2


# ---------------------------------------------------------------------------
# hotkey_display_name()
# ---------------------------------------------------------------------------

def test_display_name_mouse_x1():
    result = hotkey_display_name("<mouse_x1>")
    assert "Mouse" in result


def test_display_name_mouse_x2():
    result = hotkey_display_name("<mouse_x2>")
    assert "Mouse" in result


def test_display_name_mouse_x1_x2_differ():
    assert hotkey_display_name("<mouse_x1>") != hotkey_display_name("<mouse_x2>")


def test_display_name_mouse_differs_from_keyboard():
    assert hotkey_display_name("<mouse_x1>") != hotkey_display_name("<ctrl>+<alt>+s")


def test_display_name_mouse_not_empty():
    assert hotkey_display_name("<mouse_x1>").strip()
    assert hotkey_display_name("<mouse_x2>").strip()


# ---------------------------------------------------------------------------
# _MouseHotkeyListener
# ---------------------------------------------------------------------------

def test_mouse_listener_fires_on_x1_press():
    cb = mock.MagicMock()
    ml = _MouseHotkeyListener({"<mouse_x1>": cb})
    ml.start()
    _fire_click(_FakeButton.x1, pressed=True)
    cb.assert_called_once()


def test_mouse_listener_fires_on_x2_press():
    cb = mock.MagicMock()
    ml = _MouseHotkeyListener({"<mouse_x2>": cb})
    ml.start()
    _fire_click(_FakeButton.x2, pressed=True)
    cb.assert_called_once()


def test_mouse_listener_ignores_release():
    cb = mock.MagicMock()
    ml = _MouseHotkeyListener({"<mouse_x1>": cb})
    ml.start()
    _fire_click(_FakeButton.x1, pressed=False)
    cb.assert_not_called()


def test_mouse_listener_ignores_other_buttons():
    cb = mock.MagicMock()
    ml = _MouseHotkeyListener({"<mouse_x1>": cb})
    ml.start()
    _fire_click(_FakeButton.left, pressed=True)
    cb.assert_not_called()


def test_mouse_listener_stop_clears_listener():
    ml = _MouseHotkeyListener({"<mouse_x1>": lambda: None})
    ml.start()
    ml.stop()
    assert ml._listener is None


def test_mouse_listener_empty_bindings_does_not_start():
    ml = _MouseHotkeyListener({})
    ml.start()
    assert ml._listener is None


# ---------------------------------------------------------------------------
# HotkeyManager — mouse binding separation
# ---------------------------------------------------------------------------

def test_hotkey_manager_mouse_binding_not_in_keyboard_listener():
    """A <mouse_x1> binding must NOT appear in GlobalHotKeys."""
    mgr = _make_manager({"scan": "<mouse_x1>"})
    mgr.start()
    assert "<mouse_x1>" not in mgr._listener._hotkeys


def test_hotkey_manager_keyboard_binding_not_in_mouse_listener():
    """A keyboard binding must NOT start a mouse listener."""
    mgr = _make_manager({"scan": "<ctrl>+<alt>+s"})
    mgr.start()
    assert mgr._mouse_listener is None


def test_hotkey_manager_keyboard_binding_in_keyboard_listener():
    """A keyboard binding must appear in GlobalHotKeys."""
    mgr = _make_manager({"scan": "<ctrl>+<alt>+s"})
    mgr.start()
    assert "<ctrl>+<alt>+s" in mgr._listener._hotkeys


def test_hotkey_manager_starts_mouse_listener_for_mouse_binding():
    mgr = HotkeyManager(
        on_scan=lambda: None,
        on_navigate_up=lambda: None,
        on_navigate_down=lambda: None,
        hotkey_bindings={"scan": "<mouse_x1>"},
    )
    mgr.start()
    assert mgr._mouse_listener is not None


def test_hotkey_manager_stop_clears_mouse_listener():
    mgr = HotkeyManager(
        on_scan=lambda: None,
        on_navigate_up=lambda: None,
        on_navigate_down=lambda: None,
        hotkey_bindings={"scan": "<mouse_x1>"},
    )
    mgr.start()
    mgr.stop()
    assert mgr._mouse_listener is None
