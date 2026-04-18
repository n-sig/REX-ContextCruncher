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
# agent_config detection (BUG-14 fix)
# ---------------------------------------------------------------------------

class TestDetectAgentConfig:
    """BUG-14: CLAUDE.md, .cursorrules and system-prompt files must be
    detected as agent_config so compress() can apply ULTRA-CONSERVATIVE mode.

    Detection precedence (highest first):
      1. Known agent-config filename
      2. File extension
      3. Heuristic: ≥5 constraint keywords in the first 5000 chars
    """

    # -- 1. filename-based detection --------------------------------------

    def test_claude_md_filename(self):
        assert detect_content_type("short text", filename="CLAUDE.md") == "agent_config"

    def test_claude_md_lowercase_filename(self):
        assert detect_content_type("short text", filename="claude.md") == "agent_config"

    def test_agents_md_filename(self):
        assert detect_content_type("hello", filename="AGENTS.md") == "agent_config"

    def test_gemini_md_filename(self):
        assert detect_content_type("hello", filename="GEMINI.md") == "agent_config"

    def test_copilot_md_filename(self):
        assert detect_content_type("hello", filename="COPILOT.md") == "agent_config"

    def test_cursorrules_filename(self):
        assert detect_content_type("rules", filename=".cursorrules") == "agent_config"

    def test_cursorignore_filename(self):
        assert detect_content_type("patterns", filename=".cursorignore") == "agent_config"

    def test_system_prompt_filename(self):
        assert detect_content_type("hi", filename="system_prompt.md") == "agent_config"
        assert detect_content_type("hi", filename="system-prompt.txt") == "agent_config"

    def test_path_with_subdir(self):
        """Basenames must be extracted from full paths (both / and \\)."""
        assert detect_content_type("x", filename="/repo/CLAUDE.md") == "agent_config"
        assert detect_content_type("x", filename="C:\\proj\\CLAUDE.md") == "agent_config"

    def test_agent_filename_wins_over_generic_extension(self):
        """CLAUDE.md must stay agent_config even though .md would be markdown."""
        assert detect_content_type("# Title\n", filename="CLAUDE.md") == "agent_config"

    # -- 2. content heuristic ---------------------------------------------

    def test_heuristic_triggers_with_5_constraint_keywords(self):
        """5+ constraint keywords → agent_config regardless of filename."""
        text = (
            "Intro.\n"
            "NEVER commit secrets.\n"
            "ALWAYS verify inputs.\n"
            "MUST NOT bypass auth.\n"
            "DO NOT skip tests.\n"
            "CRITICAL: run linter.\n"
        )
        assert detect_content_type(text) == "agent_config"

    def test_heuristic_does_not_trigger_with_few_keywords(self):
        """2-3 scattered keywords are normal prose, not agent_config."""
        text = (
            "Some prose about normal things.\n"
            "We should always test our code.\n"
            "It is important to write docs.\n"
        )
        # At most 2 keyword hits → stays as prose/markdown
        assert detect_content_type(text) != "agent_config"

    def test_heuristic_detects_german_keywords(self):
        text = (
            "NIEMALS Secrets committen.\n"
            "IMMER Eingaben validieren.\n"
            "DARF NICHT ohne Tests mergen.\n"
            "VERBOTEN ist das Umgehen der Security.\n"
            "CRITICAL: Code-Review vor Merge.\n"
        )
        assert detect_content_type(text) == "agent_config"

    def test_heuristic_only_scans_first_5000_chars(self):
        """Constraint keywords buried past 5000 chars must NOT trigger."""
        padding = "Just some regular prose. " * 500  # ~12500 chars, no keywords
        hidden_config = (
            "\nNEVER x.\nALWAYS y.\nMUST NOT z.\nDO NOT w.\nFORBIDDEN q.\n"
        )
        text = padding + hidden_config
        # Only the first 5000 chars are scanned → no match
        assert detect_content_type(text) != "agent_config"

    # -- 3. category mapping ---------------------------------------------

    def test_agent_config_maps_to_agent_config_category(self):
        assert _content_type_category("agent_config") == "agent_config"


class TestSmartRouteAgentConfig:
    """agent_config inputs must NOT be skeletonized — they must only go
    through redact + compress so constraints survive."""

    SAMPLE = (
        "# Project Rules\n"
        "NEVER create additional tk.Tk() instances.\n"
        "ALWAYS redact secrets.\n"
        "MUST NOT commit keys.\n"
        "DO NOT skip tests.\n"
        "CRITICAL: verify all hotkeys on startup.\n"
    )

    def test_claude_md_routed_to_agent_config(self):
        r = smart_route(self.SAMPLE, filename="CLAUDE.md")
        assert r.content_type == "agent_config"

    def test_no_skeleton_step_for_agent_config(self):
        """skeleton would destroy the constraint text — strategy must skip it."""
        r = smart_route(self.SAMPLE, filename="CLAUDE.md", intent="understand")
        # Strategy string joined by " → " — none of the techniques may be 'skeleton:*'
        assert "skeleton:" not in r.strategy_used

    def test_constraints_survive_compression(self):
        r = smart_route(self.SAMPLE, filename="CLAUDE.md")
        # The constraints themselves must survive deterministic compression
        assert "NEVER" in r.compressed_text.upper()
        assert "tk.Tk()" in r.compressed_text

    def test_confidence_is_high_for_agent_config(self):
        """Agent configs must remain 100% faithful → confidence ≥ 0.9."""
        r = smart_route(self.SAMPLE, filename="CLAUDE.md")
        assert r.confidence >= 0.9


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
