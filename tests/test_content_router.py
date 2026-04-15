"""
Tests for content_router.py — Phase 1 of AI Context Manager.

Tests content-type detection, strategy routing, and the CrunchResult output
for all supported content types and intents.
"""

import pytest
from contextcruncher.content_router import (
    detect_content_type,
    smart_route,
    CrunchResult,
    _content_type_category,
)


# ---------------------------------------------------------------------------
# Content-type detection
# ---------------------------------------------------------------------------

class TestDetectContentType:
    """Tests for detect_content_type()."""

    def test_python_by_extension(self):
        assert detect_content_type("x = 1", filename="main.py") == "code_python"

    def test_typescript_by_extension(self):
        assert detect_content_type("const x = 1;", filename="app.ts") == "code_ts"

    def test_json_by_extension(self):
        assert detect_content_type('{"a": 1}', filename="data.json") == "data_json"

    def test_json_by_content(self):
        assert detect_content_type('{"key": "value", "count": 42}') == "data_json"

    def test_xml_by_content(self):
        assert detect_content_type('<root><item>hello</item></root>') == "data_xml"

    def test_yaml_by_extension(self):
        assert detect_content_type("key: value", filename="config.yaml") == "data_yaml"

    def test_markdown_by_extension(self):
        assert detect_content_type("# Title\nSome text", filename="README.md") == "markdown"

    def test_log_by_extension(self):
        assert detect_content_type("2025-01-01 INFO started", filename="app.log") == "log"

    def test_log_by_content(self):
        text = (
            "[2025-01-01] INFO Starting server\n"
            "[2025-01-01] WARN Low memory\n"
            "[2025-01-01] ERROR Connection failed\n"
            "[2025-01-01] INFO Retrying\n"
        )
        assert detect_content_type(text) == "log"

    def test_prose_fallback(self):
        text = "This is a regular sentence with no special markers."
        assert detect_content_type(text) == "prose"

    def test_extension_takes_priority_over_content(self):
        # Content looks like JSON, but filename says .py
        assert detect_content_type('{"a": 1}', filename="parser.py") == "code_python"

    def test_unknown_extension_falls_back_to_heuristic(self):
        result = detect_content_type("Hello world", filename="notes.rtf")
        assert result == "prose"

    def test_empty_text(self):
        assert detect_content_type("") == "prose"


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

class TestCategoryMapping:
    """Tests for _content_type_category()."""

    def test_code_python(self):
        assert _content_type_category("code_python") == "code"

    def test_data_json(self):
        assert _content_type_category("data_json") == "data"

    def test_log(self):
        assert _content_type_category("log") == "log"

    def test_prose(self):
        assert _content_type_category("prose") == "prose"

    def test_unknown_defaults_to_prose(self):
        assert _content_type_category("something_new") == "prose"


# ---------------------------------------------------------------------------
# smart_route — core routing logic
# ---------------------------------------------------------------------------

class TestSmartRoute:
    """Tests for smart_route()."""

    def test_returns_crunch_result(self):
        result = smart_route("Hello world, this is a test.")
        assert isinstance(result, CrunchResult)

    def test_empty_text(self):
        result = smart_route("")
        assert result.content_type == "empty"
        assert result.strategy_used == "none"

    def test_whitespace_only(self):
        result = smart_route("   \n\n  ")
        assert result.content_type == "empty"

    def test_python_code_detection(self):
        code = (
            "def hello():\n"
            "    print('hello world')\n"
            "\n"
            "def goodbye():\n"
            "    print('goodbye')\n"
        )
        result = smart_route(code, filename="main.py")
        assert result.content_type == "code_python"
        assert result.compressed_tokens <= result.original_tokens

    def test_json_detection(self):
        data = '{"users": [{"name": "Alice", "role": "admin"}, {"name": "Bob", "role": "user"}]}'
        result = smart_route(data, filename="data.json")
        assert result.content_type == "data_json"

    def test_intent_code_review_preserves_more(self):
        code = (
            "def hello():\n"
            "    # This is a very important function\n"
            "    print('hello world')\n"
        )
        review = smart_route(code, intent="code_review", filename="main.py")
        summary = smart_route(code, intent="summarize", filename="main.py")
        # code_review should preserve more or equal tokens
        assert review.compressed_tokens >= summary.compressed_tokens

    def test_intent_summarize_saves_most(self):
        prose = (
            "It is important to note that the system should be configured "
            "with the appropriate settings. In order to achieve optimal "
            "performance, the administrator should very carefully review "
            "all the configuration parameters. As a matter of fact, this "
            "is quite essential for the overall system stability."
        )
        understand = smart_route(prose, intent="understand")
        summarize = smart_route(prose, intent="summarize")
        assert summarize.saved_percent >= understand.saved_percent

    def test_invalid_intent_defaults_to_understand(self):
        result = smart_route("Hello world", intent="invalid_intent")
        # Should not crash — falls back to "understand"
        assert isinstance(result, CrunchResult)
        assert result.compressed_tokens > 0

    def test_confidence_is_bounded(self):
        result = smart_route("Some text to compress for testing purposes.")
        assert 0.0 <= result.confidence <= 1.0

    def test_saved_percent_is_non_negative(self):
        result = smart_route("Hello world")
        assert result.saved_percent >= 0.0

    def test_strategy_used_is_populated(self):
        code = "def foo():\n    return 42\n"
        result = smart_route(code, filename="test.py")
        assert result.strategy_used != ""

    def test_what_was_removed_capped_at_5(self):
        # Even with lots of removals, max 5 samples
        result = smart_route("x" * 1000, intent="summarize")
        assert len(result.what_was_removed) <= 5

    def test_secrets_are_redacted(self):
        text = "API key: sk-proj-abcdef1234567890abcdef1234567890abcdef12345678"
        result = smart_route(text)
        assert "sk-proj-" not in result.compressed_text
        assert "REDACTED" in result.compressed_text


# ---------------------------------------------------------------------------
# Integration: MCP tool wrappers (import-level check)
# ---------------------------------------------------------------------------

class TestMCPToolImports:
    """Verify that the MCP tool functions are importable and callable."""

    def test_smart_crunch_import(self):
        # This tests that the module-level import chain works
        from contextcruncher.content_router import smart_route
        result = smart_route("test")
        assert result.compressed_text == "test"

    def test_detect_content_type_import(self):
        from contextcruncher.content_router import detect_content_type
        assert detect_content_type("hello") == "prose"
