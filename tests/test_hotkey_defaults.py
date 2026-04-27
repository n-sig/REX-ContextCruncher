"""
Tests for the reworked DEFAULT_HOTKEYS (config.py).

The prior defaults used combos that collided with common OS/Office shortcuts
and — on German/European keyboard layouts — with AltGr (AltGr = Ctrl+Alt).
These tests pin down the properties the new defaults must keep so we don't
accidentally regress:

  1. No <alt>+<letter> as a standalone combo (would grab menu-bar shortcuts).
  2. No <ctrl>+<alt>+<letter> (collides with AltGr on DE/FR/IT/ES layouts).
  3. No collisions amongst defaults.
  4. Every registered action has a display label.
  5. Every default uses at least one modifier (global-hotkey requirement).
"""

import sys
import types
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

if "winreg" not in sys.modules:
    fake = types.ModuleType("winreg")
    for attr in (
        "HKEY_CURRENT_USER", "KEY_READ", "KEY_SET_VALUE", "REG_SZ",
        "OpenKey", "QueryValueEx", "SetValueEx", "DeleteValue", "CloseKey",
    ):
        setattr(fake, attr, mock.MagicMock())
    sys.modules["winreg"] = fake

from contextcruncher.config import (  # noqa: E402
    DEFAULT_HOTKEYS,
    HOTKEY_ACTION_LABELS,
    find_hotkey_collision,
)


_MODIFIERS = {"<ctrl>", "<shift>", "<alt>", "<cmd>"}


def _parts(combo: str) -> list[str]:
    return [p.strip() for p in combo.split("+") if p.strip()]


def _is_letter_token(tok: str) -> bool:
    return len(tok) == 1 and tok.isalpha()


def test_all_actions_have_labels():
    for action in DEFAULT_HOTKEYS:
        assert action in HOTKEY_ACTION_LABELS, (
            f"Action '{action}' has no display label in HOTKEY_ACTION_LABELS"
        )


def test_no_collisions_in_defaults():
    assert find_hotkey_collision(DEFAULT_HOTKEYS) is None


def test_every_default_has_a_modifier():
    """A bare letter/digit as a global hotkey would fire on normal typing."""
    for action, combo in DEFAULT_HOTKEYS.items():
        toks = _parts(combo)
        mods = [t for t in toks if t in _MODIFIERS]
        assert mods, f"Default for '{action}' ({combo!r}) has no modifier"


def test_no_bare_alt_letter_combo():
    """<alt>+<letter> hijacks Windows menu-bar shortcuts (old Alt+H → Heatmap)."""
    for action, combo in DEFAULT_HOTKEYS.items():
        toks = _parts(combo)
        mods = {t for t in toks if t in _MODIFIERS}
        keys = [t for t in toks if t not in _MODIFIERS]
        if mods == {"<alt>"} and keys and _is_letter_token(keys[0]):
            raise AssertionError(
                f"Default '{action}' = {combo!r} uses <alt>+<letter>, "
                f"which conflicts with menu-bar shortcuts."
            )


def test_no_ctrl_alt_letter_combo():
    """<ctrl>+<alt>+<letter> = AltGr on German/European layouts.

    AltGr+Q = @, AltGr+E = €, AltGr+7 = {, AltGr+8 = [, etc. Binding a
    global hotkey on Ctrl+Alt+<letter> races with character composition
    and frequently fails to trigger (or clobbers typing).
    """
    for action, combo in DEFAULT_HOTKEYS.items():
        toks = _parts(combo)
        mods = {t for t in toks if t in _MODIFIERS}
        keys = [t for t in toks if t not in _MODIFIERS]
        if mods == {"<ctrl>", "<alt>"} and keys and _is_letter_token(keys[0]):
            raise AssertionError(
                f"Default '{action}' = {combo!r} uses <ctrl>+<alt>+<letter>; "
                f"this is AltGr on DE/FR/IT/ES layouts. Pick a different combo."
            )


def test_heatmap_no_longer_uses_alt_h():
    """Historical regression guard — Alt+H opened the Office Home ribbon."""
    combo = DEFAULT_HOTKEYS.get("hotkey_heatmap", "")
    assert combo.lower() != "<alt>+h", (
        "Heatmap default must not use <alt>+h (collides with Office menus)."
    )


def test_scan_no_longer_uses_ctrl_alt_s():
    """Historical regression guard for the German-keyboard AltGr issue."""
    combo = DEFAULT_HOTKEYS.get("scan", "")
    assert combo.lower() != "<ctrl>+<alt>+s"
