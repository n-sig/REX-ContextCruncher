"""
Regression tests for the TextStack dedup window (stack.py).

Context: Bild 1 showed near-duplicates stacking up (entries 1+5, 2+6, 3+4)
because push_variants() previously only compared the incoming original
against index 0 of the deque. Copying A → B → A then produced [A, B, A]
instead of [A, B].

The fix: check the last _DEDUP_WINDOW entries; if a match is found, move
it to the front (recency) and skip the new push.
"""

import os
import sys
import types
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# stack.py → config.py imports winreg (Windows-only); stub for Linux CI.
if "winreg" not in sys.modules:
    fake = types.ModuleType("winreg")
    for attr in (
        "HKEY_CURRENT_USER", "KEY_READ", "KEY_SET_VALUE", "REG_SZ",
        "OpenKey", "QueryValueEx", "SetValueEx", "DeleteValue", "CloseKey",
    ):
        setattr(fake, attr, mock.MagicMock())
    sys.modules["winreg"] = fake

from contextcruncher.stack import TextStack, Variant, _DEDUP_WINDOW  # noqa: E402


def _v(text: str) -> list[Variant]:
    return [Variant(label="Original", text=text)]


def test_consecutive_duplicate_still_dedups():
    """Back-compat: A then A stays as a single entry."""
    s = TextStack()
    s.push_variants(_v("A"))
    s.push_variants(_v("A"))
    assert s.size() == 1


def test_ping_pong_duplicate_dedups():
    """A → B → A should NOT create a new entry for the second A.

    Before the fix, only index 0 was checked; since index 0 was B, the
    second A slipped through and the stack grew to 3 entries.
    """
    s = TextStack()
    s.push_variants(_v("A"))
    s.push_variants(_v("B"))
    s.push_variants(_v("A"))
    assert s.size() == 2


def test_ping_pong_reuses_front_position():
    """When the duplicate is re-encountered, recency wins — it jumps to the front."""
    s = TextStack()
    s.push_variants(_v("A"))
    s.push_variants(_v("B"))
    s.push_variants(_v("A"))  # A is already at index 1, should re-front
    assert s.current() == "A"
    assert s.get_entry(0).original == "A"
    assert s.get_entry(1).original == "B"


def test_dedup_respects_window_boundary():
    """An entry older than the dedup window is treated as new again."""
    s = TextStack(max_size=50)
    # Push _DEDUP_WINDOW + 2 distinct entries, then re-push the very first
    # one. Since it's outside the window, it should be accepted as new.
    for i in range(_DEDUP_WINDOW + 2):
        s.push_variants(_v(f"entry_{i}"))
    size_before = s.size()
    s.push_variants(_v("entry_0"))  # outside window → new entry
    assert s.size() == size_before + 1
    assert s.current() == "entry_0"


def test_dedup_inside_window_with_variants_preserved():
    """When an existing entry is re-fronted, its variants are preserved."""
    s = TextStack()
    s.push_variants([
        Variant(label="Original", text="A"),
        Variant(label="Compact", text="a"),
    ])
    s.push_variants(_v("B"))
    # A re-pushed — should re-front existing entry, NOT drop its Compact variant
    s.push_variants(_v("A"))
    entry = s.current_entry()
    assert entry is not None
    assert entry.original == "A"
    assert len(entry.variants) == 2
    assert entry.variants[1].text == "a"
