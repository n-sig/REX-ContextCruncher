"""
Tests for Phase 3 of AI Context Manager:
  - _relevance_score() keyword matching
  - context_pack logic (multi-file packing, budget allocation, ranking)
"""

import pytest
from pathlib import Path

from contextcruncher.token_counter import count_tokens, truncate_to_budget
from contextcruncher.content_router import smart_route, detect_content_type
from contextcruncher.security_scanner import redact_secrets


# ---------------------------------------------------------------------------
# _relevance_score (standalone re-implementation for testability)
# ---------------------------------------------------------------------------

def _relevance_score(text: str, question: str) -> float:
    """Mirror of mcp_server._relevance_score for testing."""
    if not question:
        return 1.0
    q_words = set(question.lower().split())
    t_words = set(text[:2000].lower().split())
    if not q_words:
        return 1.0
    overlap = q_words & t_words
    return len(overlap) / len(q_words)


class TestRelevanceScore:
    """Tests for keyword-overlap relevance scoring."""

    def test_no_question_returns_1(self):
        assert _relevance_score("any text", "") == 1.0

    def test_full_match(self):
        score = _relevance_score("the quick brown fox", "quick fox")
        assert score == 1.0

    def test_partial_match(self):
        score = _relevance_score("the quick brown fox", "quick zebra")
        assert 0.0 < score < 1.0
        assert score == 0.5  # 1 out of 2 words match

    def test_no_match(self):
        score = _relevance_score("the quick brown fox", "zebra elephant")
        assert score == 0.0

    def test_case_insensitive(self):
        score = _relevance_score("The QUICK Brown FOX", "quick fox")
        assert score == 1.0


# ---------------------------------------------------------------------------
# context_pack logic (replicated without MCP server import)
# ---------------------------------------------------------------------------

_MIN_TOKENS_PER_FILE = 200


def _context_pack(paths, token_budget=10000, question=""):
    """Mirror of mcp_server.context_pack logic for testing."""
    _MAX_FILE_SIZE = 10 * 1024 * 1024

    if not paths:
        return {"error": "No file paths provided."}
    if token_budget < _MIN_TOKENS_PER_FILE:
        return {"error": f"Token budget too small (min: {_MIN_TOKENS_PER_FILE})."}

    file_data = []
    for fp in paths:
        p = Path(fp).resolve()
        if not p.is_file():
            continue
        if p.stat().st_size > _MAX_FILE_SIZE:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if not text.strip():
            continue

        text = redact_secrets(text)
        score = _relevance_score(text, question)
        file_data.append({
            "path": str(p), "name": p.name, "text": text,
            "tokens": count_tokens(text), "score": score,
        })

    if not file_data:
        return {"error": "No readable files found in the provided paths."}

    file_data.sort(key=lambda x: x["score"], reverse=True)

    total_score = sum(f["score"] for f in file_data) or 1.0
    allocations = []
    for f in file_data:
        share = f["score"] / total_score
        alloc = int(token_budget * share)
        if alloc < _MIN_TOKENS_PER_FILE:
            continue
        allocations.append({**f, "budget": alloc})

    if not allocations:
        per_file = token_budget // len(file_data)
        if per_file < _MIN_TOKENS_PER_FILE:
            allocations = [file_data[0]]
            allocations[0]["budget"] = token_budget
        else:
            for f in file_data:
                allocations.append({**f, "budget": per_file})

    packed_parts = []
    file_details = []
    tokens_used = 0

    for alloc in allocations:
        result = smart_route(alloc["text"], intent="understand", filename=alloc["name"])
        compressed, actual = truncate_to_budget(result.compressed_text, alloc["budget"])
        packed_parts.append(f"--- {alloc['name']} ---\n{compressed}")
        tokens_used += actual
        file_details.append({
            "file": alloc["name"],
            "original_tokens": alloc["tokens"],
            "allocated_budget": alloc["budget"],
            "actual_tokens": actual,
            "relevance_score": round(alloc["score"], 2),
            "is_complete": alloc["tokens"] <= alloc["budget"],
        })

    packed_context = "\n\n".join(packed_parts)
    total_original = sum(f["original_tokens"] for f in file_details)
    saved = total_original - tokens_used

    return {
        "packed_context": packed_context,
        "files_included": len(file_details),
        "files_skipped": len(paths) - len(file_details),
        "token_budget": token_budget,
        "tokens_used": tokens_used,
        "total_original_tokens": total_original,
        "tokens_saved": saved,
        "saved_percent": round(saved / total_original * 100, 1) if total_original > 0 else 0,
        "per_file": file_details,
        "question": question or "(none)",
    }


class TestContextPack:
    """Tests for context_pack logic."""

    @pytest.fixture
    def three_files(self, tmp_path):
        """Create 3 temp files with different content types."""
        py = tmp_path / "main.py"
        py.write_text(
            "def hello():\n    print('hello')\n\n"
            "def goodbye():\n    print('goodbye')\n\n"
            "class Greeter:\n    def greet(self):\n        return 'hi'\n",
            encoding="utf-8",
        )
        md = tmp_path / "README.md"
        md.write_text(
            "# Project\n\nThis is a test project for greeting.\n\n"
            "## Usage\n\nRun `python main.py` to start.\n\n"
            "## API\n\nThe Greeter class provides greeting methods.\n",
            encoding="utf-8",
        )
        log = tmp_path / "server.log"
        lines = [f"2025-01-{i:02d} INFO Request {i} processed\n" for i in range(1, 31)]
        log.write_text("".join(lines), encoding="utf-8")

        return [str(py), str(md), str(log)]

    def test_packs_multiple_files(self, three_files):
        result = _context_pack(three_files, token_budget=5000)
        assert "error" not in result
        assert result["files_included"] >= 2
        assert "--- main.py ---" in result["packed_context"]

    def test_respects_token_budget(self, three_files):
        result = _context_pack(three_files, token_budget=500)
        assert result["tokens_used"] <= 500

    def test_question_ranking(self, three_files):
        result = _context_pack(three_files, token_budget=5000, question="greeter class")
        # main.py and README.md mention "greeter" — they should be prioritized
        per_file = result["per_file"]
        if len(per_file) >= 2:
            # Files with higher relevance should come first
            assert per_file[0]["relevance_score"] >= per_file[-1]["relevance_score"]

    def test_equal_distribution_without_question(self, three_files):
        result = _context_pack(three_files, token_budget=3000)
        per_file = result["per_file"]
        if len(per_file) == 3:
            budgets = [f["allocated_budget"] for f in per_file]
            assert max(budgets) == min(budgets)  # Equal scores → equal budgets

    def test_empty_paths(self):
        result = _context_pack([])
        assert "error" in result

    def test_nonexistent_files(self):
        result = _context_pack(["/nonexistent/a.py", "/nonexistent/b.py"])
        assert "error" in result

    def test_budget_too_small(self, three_files):
        result = _context_pack(three_files, token_budget=50)
        assert "error" in result

    def test_file_headers_present(self, three_files):
        result = _context_pack(three_files, token_budget=5000)
        assert "--- main.py ---" in result["packed_context"]
        assert "--- README.md ---" in result["packed_context"]

    def test_saved_percent_non_negative(self, three_files):
        result = _context_pack(three_files, token_budget=5000)
        assert result["saved_percent"] >= 0.0

    def test_single_file(self, three_files):
        result = _context_pack([three_files[0]], token_budget=5000)
        assert result["files_included"] == 1
        assert "--- main.py ---" in result["packed_context"]
