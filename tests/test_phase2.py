"""
Tests for Phase 2 of AI Context Manager:
  - truncate_to_budget() in token_counter.py
  - DiffCache in diff_cache.py
  - budget_loader MCP tool (via direct function call)
  - diff_crunch MCP tool (via direct function call)
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.token_counter import count_tokens, truncate_to_budget
from contextcruncher.diff_cache import DiffCache, _MAX_CACHE_SIZE


# ---------------------------------------------------------------------------
# truncate_to_budget
# ---------------------------------------------------------------------------

class TestTruncateToBudget:
    """Tests for truncate_to_budget()."""

    def test_text_within_budget_returned_unchanged(self):
        text = "Hello world"
        result, tokens = truncate_to_budget(text, 100)
        assert result == text
        assert tokens == count_tokens(text)

    def test_text_exceeding_budget_is_truncated(self):
        text = "word " * 500  # ~500 tokens
        result, tokens = truncate_to_budget(text, 50)
        assert tokens == 50
        assert len(result) < len(text)

    def test_truncated_text_token_count_exact(self):
        text = "The quick brown fox jumps over the lazy dog. " * 20
        result, tokens = truncate_to_budget(text, 30)
        actual = count_tokens(result)
        assert actual <= 30

    def test_empty_text(self):
        result, tokens = truncate_to_budget("", 100)
        assert result == ""
        assert tokens == 0

    def test_zero_budget(self):
        result, tokens = truncate_to_budget("Hello", 0)
        assert result == ""
        assert tokens == 0

    def test_negative_budget(self):
        result, tokens = truncate_to_budget("Hello", -5)
        assert result == ""
        assert tokens == 0

    def test_budget_of_one(self):
        result, tokens = truncate_to_budget("Hello world this is a test", 1)
        assert tokens == 1
        assert len(result) > 0


# ---------------------------------------------------------------------------
# DiffCache
# ---------------------------------------------------------------------------

class TestDiffCache:
    """Tests for DiffCache."""

    def test_store_returns_hash(self):
        cache = DiffCache()
        h = cache.store("Hello world")
        assert isinstance(h, str)
        assert len(h) == 16

    def test_same_content_same_hash(self):
        cache = DiffCache()
        h1 = cache.store("Hello world")
        h2 = cache.store("Hello world")
        assert h1 == h2

    def test_different_content_different_hash(self):
        cache = DiffCache()
        h1 = cache.store("Hello")
        h2 = cache.store("World")
        assert h1 != h2

    def test_get_returns_stored_content(self):
        cache = DiffCache()
        h = cache.store("Test content")
        assert cache.get(h) == "Test content"

    def test_get_missing_returns_none(self):
        cache = DiffCache()
        assert cache.get("nonexistent") is None

    def test_compute_diff_modified(self):
        cache = DiffCache()
        h = cache.store("line1\nline2\nline3\n")
        result = cache.compute_diff(h, "line1\nchanged\nline3\n")
        assert result["change_type"] == "modified"
        assert result["lines_added"] > 0
        assert result["lines_removed"] > 0

    def test_compute_diff_added(self):
        cache = DiffCache()
        h = cache.store("line1\nline2\n")
        result = cache.compute_diff(h, "line1\nline2\nline3\n")
        assert result["change_type"] == "added"
        assert result["lines_added"] > 0

    def test_compute_diff_removed(self):
        cache = DiffCache()
        h = cache.store("line1\nline2\nline3\n")
        result = cache.compute_diff(h, "line1\nline3\n")
        assert result["change_type"] == "removed"
        assert result["lines_removed"] > 0

    def test_compute_diff_unchanged(self):
        cache = DiffCache()
        text = "same text\n"
        h = cache.store(text)
        result = cache.compute_diff(h, text)
        assert result["change_type"] == "unchanged"

    def test_compute_diff_missing_old_returns_full(self):
        cache = DiffCache()
        result = cache.compute_diff("missing_hash", "new text\n")
        assert result["change_type"] == "full"

    def test_size(self):
        cache = DiffCache()
        assert cache.size() == 0
        cache.store("a")
        assert cache.size() == 1
        cache.store("b")
        assert cache.size() == 2

    def test_diff_cache_eviction(self):
        """Storing more than _MAX_CACHE_SIZE entries evicts the oldest."""
        cache = DiffCache()
        hashes = []
        for i in range(150):
            h = cache.store(f"entry-{i}")
            hashes.append(h)
        # Cache must never exceed the limit.
        assert cache.size() <= _MAX_CACHE_SIZE
        # Oldest entries (0..49) should have been evicted.
        for h in hashes[:50]:
            assert cache.get(h) is None, f"entry for hash {h} should be evicted"
        # Newest entries (50..149) should still be present.
        for h in hashes[50:]:
            assert cache.get(h) is not None, f"entry for hash {h} should exist"


# ---------------------------------------------------------------------------
# budget_loader logic (tests the core logic path without mcp_server import)
# ---------------------------------------------------------------------------

class TestBudgetLoaderLogic:
    """Tests the budget_loader logic via underlying modules."""

    @pytest.fixture
    def temp_python_file(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text(
            "def hello():\n"
            "    '''Say hello.'''\n"
            "    print('hello world')\n\n"
            "def goodbye():\n"
            "    '''Say goodbye.'''\n"
            "    print('goodbye world')\n\n"
            "class MyClass:\n"
            "    def method(self):\n"
            "        return 42\n",
            encoding="utf-8",
        )
        return f

    @pytest.fixture
    def temp_log_file(self, tmp_path):
        lines = [f"2025-01-{i:02d} INFO Event {i}\n" for i in range(1, 51)]
        f = tmp_path / "app.log"
        f.write_text("".join(lines), encoding="utf-8")
        return f

    @pytest.fixture
    def temp_markdown_file(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text(
            "# Title\n\nThis is the introduction paragraph.\n\n"
            "## Section 1\n\nDetailed content for section one goes here.\n\n"
            "## Section 2\n\nMore detailed content for section two.\n",
            encoding="utf-8",
        )
        return f

    def _budget_load(self, path, token_budget, priority="auto"):
        """Simulate budget_loader logic without MCP server import."""
        from pathlib import Path
        from contextcruncher.content_router import detect_content_type
        from contextcruncher.skeletonizer import crunch_skeleton
        from contextcruncher.security_scanner import redact_secrets

        p = Path(path)
        text = p.read_text(encoding="utf-8", errors="replace")
        text = redact_secrets(text)
        original_tokens = count_tokens(text)
        is_full = original_tokens <= token_budget

        effective_priority = priority
        if effective_priority == "auto":
            ct = detect_content_type(text, p.name)
            if ct.startswith("code_"):
                effective_priority = "signatures"
            elif ct.startswith("data_"):
                effective_priority = "schema"
            elif ct == "log":
                effective_priority = "recent"
            else:
                effective_priority = "structure"

        result_text = text
        if not is_full:
            if effective_priority in ("signatures", "schema"):
                result_text = crunch_skeleton(text, p.name)
            elif effective_priority == "recent":
                lines = text.splitlines()
                lines.reverse()
                collected = []
                for line in lines:
                    collected.append(line)
                    check = "\n".join(reversed(collected))
                    if count_tokens(check) > token_budget:
                        collected.pop()
                        break
                result_text = "\n".join(reversed(collected))
            elif effective_priority == "structure":
                lines = text.splitlines()
                kept = []
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("#") or not stripped:
                        kept.append(line)
                    elif kept and kept[-1].strip().startswith("#"):
                        kept.append(line)
                result_text = "\n".join(kept) if kept else text

            result_text, _ = truncate_to_budget(result_text, token_budget)

        return {
            "is_complete": is_full,
            "priority_used": effective_priority,
            "result_tokens": count_tokens(result_text),
            "original_tokens": original_tokens,
        }

    def test_file_within_budget_is_complete(self, temp_python_file):
        result = self._budget_load(temp_python_file, 5000)
        assert result["is_complete"] is True

    def test_file_exceeding_budget_is_truncated(self, temp_python_file):
        result = self._budget_load(temp_python_file, 10)
        assert result["is_complete"] is False
        assert result["result_tokens"] <= 10

    def test_auto_priority_code(self, temp_python_file):
        result = self._budget_load(temp_python_file, 10)
        assert result["priority_used"] == "signatures"

    def test_auto_priority_log(self, temp_log_file):
        result = self._budget_load(temp_log_file, 30)
        assert result["priority_used"] == "recent"

    def test_auto_priority_markdown(self, temp_markdown_file):
        result = self._budget_load(temp_markdown_file, 10)
        assert result["priority_used"] == "structure"


# ---------------------------------------------------------------------------
# diff_crunch logic (via DiffCache + count_tokens directly)
# ---------------------------------------------------------------------------

class TestDiffCrunchLogic:
    """Tests diff_crunch logic via DiffCache directly."""

    def test_first_call_full_mode(self):
        cache = DiffCache()
        text = "Hello world"
        new_id = cache.store(text)
        assert cache.get(new_id) == text

    def test_unchanged_text_detected(self):
        cache = DiffCache()
        text = "Unchanged text for testing"
        h1 = cache.store(text)
        result = cache.compute_diff(h1, text)
        assert result["change_type"] == "unchanged"

    def test_modified_returns_delta(self):
        cache = DiffCache()
        h1 = cache.store("line1\nline2\nline3\n")
        result = cache.compute_diff(h1, "line1\nCHANGED\nline3\n")
        assert result["change_type"] == "modified"
        assert "CHANGED" in result["changes_text"]
        # Delta diff should be non-empty and contain actual changes
        assert len(result["changes_text"]) > 0
        assert result["lines_added"] > 0
        assert result["lines_removed"] > 0

    def test_invalid_previous_returns_full(self):
        cache = DiffCache()
        result = cache.compute_diff("nonexistent", "Some text")
        assert result["change_type"] == "full"

    def test_empty_text_store(self):
        cache = DiffCache()
        h = cache.store("")
        assert cache.get(h) == ""

