"""
Tests for config.find_hotkey_collision() — BUG-05.

Pure function, no Tkinter or Windows APIs needed.
"""

import sys
import types
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# config.py imports winreg (Windows-only) — stub it for Linux CI
if "winreg" not in sys.modules:
    fake_winreg = types.ModuleType("winreg")
    for attr in ("HKEY_CURRENT_USER", "KEY_READ", "KEY_SET_VALUE", "REG_SZ",
                 "OpenKey", "QueryValueEx", "SetValueEx", "DeleteValue", "CloseKey"):
        setattr(fake_winreg, attr, mock.MagicMock())
    sys.modules["winreg"] = fake_winreg

from contextcruncher.config import find_hotkey_collision, HOTKEY_ACTION_LABELS


# ---------------------------------------------------------------------------
# No collision cases
# ---------------------------------------------------------------------------

def test_no_collision_all_unique():
    hotkeys = {
        "scan":          "<ctrl>+<alt>+s",
        "ai_compact":    "<ctrl>+<alt>+c",
        "navigate_up":   "<ctrl>+<shift>+<up>",
        "navigate_down": "<ctrl>+<shift>+<down>",
    }
    assert find_hotkey_collision(hotkeys) is None


def test_no_collision_empty_combos_ignored():
    """Unassigned (empty) hotkeys must not be treated as conflicts with each other."""
    hotkeys = {
        "scan":          "<ctrl>+<alt>+s",
        "ai_compact":    "",            # cleared
        "navigate_up":   "",            # cleared
        "navigate_down": "<ctrl>+<shift>+<down>",
    }
    assert find_hotkey_collision(hotkeys) is None


def test_no_collision_all_empty():
    hotkeys = {"scan": "", "ai_compact": "", "navigate_up": ""}
    assert find_hotkey_collision(hotkeys) is None


def test_no_collision_single_entry():
    assert find_hotkey_collision({"scan": "<ctrl>+<alt>+s"}) is None


def test_no_collision_empty_dict():
    assert find_hotkey_collision({}) is None


# ---------------------------------------------------------------------------
# Collision detected
# ---------------------------------------------------------------------------

def test_collision_two_actions_same_combo():
    hotkeys = {
        "scan":       "<ctrl>+<alt>+s",
        "ai_compact": "<ctrl>+<alt>+s",   # same as scan!
    }
    result = find_hotkey_collision(hotkeys)
    assert result is not None
    combo, a1, a2 = result
    assert combo == "<ctrl>+<alt>+s"
    assert set([a1, a2]) == {"scan", "ai_compact"}


def test_collision_returns_first_found():
    """When multiple collisions exist, only the first is returned."""
    hotkeys = {
        "scan":          "<ctrl>+<alt>+s",
        "ai_compact":    "<ctrl>+<alt>+s",  # collision 1
        "navigate_up":   "<ctrl>+<alt>+s",  # collision 2 (same combo, third action)
    }
    result = find_hotkey_collision(hotkeys)
    assert result is not None
    combo, a1, a2 = result
    assert combo == "<ctrl>+<alt>+s"
    # First two entries to conflict are scan vs ai_compact
    assert a1 == "scan"
    assert a2 == "ai_compact"


def test_collision_partial_empty_not_confused():
    """Only the duplicated non-empty combo should be flagged."""
    hotkeys = {
        "scan":          "<ctrl>+<alt>+s",
        "ai_compact":    "",                # cleared — should not conflict
        "navigate_up":   "<ctrl>+<alt>+s",  # collision with scan
        "navigate_down": "<ctrl>+<shift>+<down>",
    }
    result = find_hotkey_collision(hotkeys)
    assert result is not None
    combo, a1, a2 = result
    assert combo == "<ctrl>+<alt>+s"
    assert set([a1, a2]) == {"scan", "navigate_up"}


def test_collision_result_is_tuple_of_three_strings():
    hotkeys = {"a": "x+y", "b": "x+y"}
    result = find_hotkey_collision(hotkeys)
    assert isinstance(result, tuple)
    assert len(result) == 3
    assert all(isinstance(s, str) for s in result)


# ---------------------------------------------------------------------------
# Integration: action labels are resolvable via HOTKEY_ACTION_LABELS
# ---------------------------------------------------------------------------

def test_collision_actions_have_display_labels():
    """Both colliding action names must be valid keys in HOTKEY_ACTION_LABELS."""
    hotkeys = {
        "scan":       "<ctrl>+<alt>+s",
        "ai_compact": "<ctrl>+<alt>+s",
    }
    _, a1, a2 = find_hotkey_collision(hotkeys)
    assert a1 in HOTKEY_ACTION_LABELS, f"'{a1}' not in HOTKEY_ACTION_LABELS"
    assert a2 in HOTKEY_ACTION_LABELS, f"'{a2}' not in HOTKEY_ACTION_LABELS"


def test_no_collision_real_default_hotkeys():
    """The factory-default hotkeys must never collide with each other."""
    from contextcruncher.config import DEFAULT_HOTKEYS
    assert find_hotkey_collision(DEFAULT_HOTKEYS) is None
