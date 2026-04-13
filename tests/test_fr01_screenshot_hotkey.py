"""
Tests for FR-01 — Full Screen OCR hotkey.

Verifies:
  1. DEFAULT_HOTKEYS contains 'screenshot_full'
  2. HOTKEY_ACTION_LABELS contains 'screenshot_full'
  3. HotkeyManager accepts and stores on_screenshot_full callback
  4. HotkeyManager wires screenshot_full combo → callback when binding present
  5. HotkeyManager silently skips screenshot_full when no binding configured
  6. New hotkey has no collision with existing defaults
"""

from __future__ import annotations

import sys
import types
import unittest.mock as mock
from pathlib import Path

import pytest

# ── Stub winreg for Linux CI ─────────────────────────────────────────────────
if "winreg" not in sys.modules:
    _fake_winreg = types.ModuleType("winreg")
    for _attr in (
        "OpenKey", "CloseKey", "SetValueEx", "DeleteValue",
        "QueryValueEx", "HKEY_CURRENT_USER", "KEY_SET_VALUE",
        "KEY_READ", "REG_SZ",
    ):
        setattr(_fake_winreg, _attr, mock.MagicMock())
    sys.modules["winreg"] = _fake_winreg

# ── Stub pynput for Linux CI ──────────────────────────────────────────────────
if "pynput" not in sys.modules:
    _pynput = types.ModuleType("pynput")
    _pynput_kb = types.ModuleType("pynput.keyboard")

    class _FakeGlobalHotKeys:
        def __init__(self, hotkeys):
            self._hotkeys = hotkeys
            self.daemon = False

        def start(self):
            pass

        def stop(self):
            pass

    _pynput_kb.GlobalHotKeys = _FakeGlobalHotKeys
    _pynput.keyboard = _pynput_kb
    sys.modules["pynput"] = _pynput
    sys.modules["pynput.keyboard"] = _pynput_kb

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.config import DEFAULT_HOTKEYS, HOTKEY_ACTION_LABELS, find_hotkey_collision  # noqa: E402
from contextcruncher.hotkeys import HotkeyManager  # noqa: E402


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

def test_screenshot_full_in_default_hotkeys():
    """DEFAULT_HOTKEYS must include a binding for 'screenshot_full'."""
    assert "screenshot_full" in DEFAULT_HOTKEYS, (
        "FR-01 requires 'screenshot_full' in DEFAULT_HOTKEYS"
    )


def test_screenshot_full_default_combo_nonempty():
    """The default combo for screenshot_full must be a non-empty string."""
    combo = DEFAULT_HOTKEYS.get("screenshot_full", "")
    assert combo, "Default combo for screenshot_full must not be empty"


def test_screenshot_full_in_action_labels():
    """HOTKEY_ACTION_LABELS must have a display name for 'screenshot_full'."""
    assert "screenshot_full" in HOTKEY_ACTION_LABELS, (
        "FR-01 requires 'screenshot_full' in HOTKEY_ACTION_LABELS"
    )


def test_screenshot_full_label_nonempty():
    """The display label for screenshot_full must be a non-empty string."""
    label = HOTKEY_ACTION_LABELS.get("screenshot_full", "")
    assert label, "Display label for screenshot_full must not be empty"


def test_default_hotkeys_no_collision():
    """All default hotkeys must be free of collisions (including new combo)."""
    collision = find_hotkey_collision(DEFAULT_HOTKEYS)
    assert collision is None, (
        f"Collision detected in DEFAULT_HOTKEYS: {collision}"
    )


def test_screenshot_full_combo_differs_from_scan():
    """screenshot_full and scan must not share the same combo."""
    assert DEFAULT_HOTKEYS.get("screenshot_full") != DEFAULT_HOTKEYS.get("scan"), (
        "screenshot_full and scan must have distinct hotkeys"
    )


# ---------------------------------------------------------------------------
# HotkeyManager tests
# ---------------------------------------------------------------------------

def _make_manager(on_screenshot_full=None, bindings=None) -> HotkeyManager:
    noop = lambda: None  # noqa: E731
    return HotkeyManager(
        on_scan=noop,
        on_navigate_up=noop,
        on_navigate_down=noop,
        on_screenshot_full=on_screenshot_full,
        hotkey_bindings=bindings if bindings is not None else DEFAULT_HOTKEYS,
    )


def test_hotkey_manager_accepts_screenshot_full_callback():
    """HotkeyManager must accept on_screenshot_full without raising."""
    cb = mock.MagicMock()
    mgr = _make_manager(on_screenshot_full=cb)
    assert mgr._on_screenshot_full is cb


def test_hotkey_manager_screenshot_full_defaults_to_none():
    """on_screenshot_full must default to None when not provided."""
    mgr = _make_manager()
    assert mgr._on_screenshot_full is None


def test_hotkey_manager_wires_screenshot_full_when_binding_present():
    """start() must include screenshot_full combo in GlobalHotKeys when binding set."""
    cb = mock.MagicMock()
    bindings = {"screenshot_full": "<ctrl>+<alt>+f"}
    mgr = _make_manager(on_screenshot_full=cb, bindings=bindings)
    mgr.start()
    assert "<ctrl>+<alt>+f" in mgr._listener._hotkeys, (
        "screenshot_full combo must be registered in GlobalHotKeys"
    )
    assert mgr._listener._hotkeys["<ctrl>+<alt>+f"] is cb


def test_hotkey_manager_skips_screenshot_full_when_callback_none():
    """start() must NOT register the combo when on_screenshot_full is None."""
    bindings = {"screenshot_full": "<ctrl>+<alt>+f"}
    mgr = _make_manager(on_screenshot_full=None, bindings=bindings)
    mgr.start()
    assert "<ctrl>+<alt>+f" not in mgr._listener._hotkeys, (
        "Combo must not be registered when callback is None"
    )


def test_hotkey_manager_skips_screenshot_full_when_no_binding():
    """start() must NOT register a callback when no binding is configured."""
    cb = mock.MagicMock()
    bindings = {}  # no screenshot_full entry
    mgr = _make_manager(on_screenshot_full=cb, bindings=bindings)
    mgr.start()
    registered_callbacks = list(mgr._listener._hotkeys.values())
    assert cb not in registered_callbacks, (
        "Callback must not be registered when binding is absent from config"
    )
