"""Tests for the TextStack with compact variant support."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from contextcruncher.stack import TextStack


class TestTextStackBasic:
    """Basic push / current / navigate tests."""

    def test_empty_stack_returns_none(self):
        s = TextStack()
        assert s.current() is None

    def test_push_and_current(self):
        s = TextStack()
        s.push("Hello")
        assert s.current() == "Hello"

    def test_push_empty_string_ignored(self):
        s = TextStack()
        s.push("")
        assert s.size() == 0

    def test_multiple_pushes(self):
        s = TextStack()
        s.push("A")
        s.push("B")
        assert s.current() == "B"  # Newest on top.

    def test_navigate_older(self):
        s = TextStack()
        s.push("A")
        s.push("B")
        s.navigate(+1)
        assert s.current() == "A"

    def test_navigate_newer(self):
        s = TextStack()
        s.push("A")
        s.push("B")
        s.navigate(+1)
        s.navigate(-1)
        assert s.current() == "B"

    def test_navigate_out_of_bounds(self):
        s = TextStack()
        s.push("A")
        s.navigate(+10)
        assert s.current() == "A"  # Stays at boundary.

    def test_navigate_empty_stack(self):
        s = TextStack()
        assert s.navigate(+1) is None


class TestTextStackCompact:
    """Tests for the compact variant toggle feature."""

    def test_push_with_compact(self):
        s = TextStack()
        s.push("4532 1234 5678 9012", compact="4532123456789012")
        # Default: shows original.
        assert s.current() == "4532 1234 5678 9012"

    def test_toggle_to_compact(self):
        s = TextStack()
        s.push("4532 1234 5678 9012", compact="4532123456789012")
        result = s.toggle_compact()
        assert result == "4532123456789012"
        assert s.current() == "4532123456789012"

    def test_toggle_back_to_original(self):
        s = TextStack()
        s.push("4532 1234 5678 9012", compact="4532123456789012")
        s.toggle_compact()  # -> compact
        s.toggle_compact()  # -> original
        assert s.current() == "4532 1234 5678 9012"

    def test_toggle_no_compact_returns_none(self):
        s = TextStack()
        s.push("Hello World")
        assert s.toggle_compact() is None

    def test_has_compact(self):
        s = TextStack()
        s.push("4532 1234", compact="45321234")
        assert s.has_compact() is True

    def test_has_compact_false(self):
        s = TextStack()
        s.push("Hello")
        assert s.has_compact() is False

    def test_toggle_empty_stack(self):
        s = TextStack()
        assert s.toggle_compact() is None

    def test_navigate_preserves_toggle_state(self):
        s = TextStack()
        s.push("A A", compact="AA")
        s.push("B B", compact="BB")
        s.toggle_compact()  # Toggle current (B B -> BB)
        assert s.current() == "BB"
        s.navigate(+1)  # Go to older entry (A A)
        assert s.current() == "A A"  # Not toggled.
        s.navigate(-1)  # Back to B
        assert s.current() == "BB"  # Toggle state preserved.


class TestTextStackCursorReset:
    def test_cursor_reset_after_push(self):
        s = TextStack()
        s.push("A")
        s.push("B")
        s.navigate(+1)
        s.push("C")
        assert s.current() == "C"  # Cursor resets to newest.


class TestTextStackMaxSize:
    def test_default_max_size(self):
        s = TextStack()
        assert s._items.maxlen == 50

    def test_max_size_eviction(self):
        s = TextStack(max_size=3)
        s.push("A")
        s.push("B")
        s.push("C")
        s.push("D")  # Evicts "A"
        assert s.size() == 3


class TestTextStackClear:
    def test_clear(self):
        s = TextStack()
        s.push("A")
        s.clear()
        assert s.size() == 0
        assert s.current() is None


class TestTextStackLabel:
    def test_label_empty(self):
        s = TextStack()
        assert s.label() == "[0/0]"

    def test_label_with_items(self):
        s = TextStack()
        s.push("Hello")
        assert "[1/1]" in s.label()
        assert "Hello" in s.label()

    def test_label_long_text_truncated(self):
        s = TextStack()
        s.push("x" * 100)
        label = s.label()
        assert "..." in label
        assert len(label) < 60

    def test_label_shows_mode(self):
        s = TextStack()
        s.push("4532 1234", compact="45321234")
        label = s.label()
        assert "Original" in label
        s.toggle_compact()
        label = s.label()
        assert "compact" in label
