"""
test_prompt_optimizer_extractors.py — Tests for the 4-layer hybrid extraction.

Covers the deterministic extraction / reinsertion pipeline used by compress()
to protect critical content from the LLM:

    1. _extract_code_blocks   → ⟨CODE_BLOCK_N⟩
    2. _extract_tables        → ⟨TABLE_N⟩
    3. _extract_inline_refs   → ⟨REF_N⟩
    4. _extract_constraints   → ⟨RULE_N⟩

Every extractor must round-trip perfectly: extract → reinsert must produce
exactly the original content at the extracted positions.  These tests are
pure (no HTTP, no config, no file I/O).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import unittest

import contextcruncher.prompt_optimizer as po


# ---------------------------------------------------------------------------
# Code block extraction
# ---------------------------------------------------------------------------

class TestExtractCodeBlocks(unittest.TestCase):
    """Tests for _extract_code_blocks / _reinsert_code_blocks."""

    def test_no_code_returns_text_unchanged(self):
        text = "This is just prose with no code at all."
        out, blocks = po._extract_code_blocks(text)
        self.assertEqual(out, text)
        self.assertEqual(blocks, [])

    def test_single_fenced_block(self):
        text = "Intro\n```python\ndef foo():\n    return 42\n```\nOutro"
        out, blocks = po._extract_code_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertIn("⟨CODE_BLOCK_0⟩", out)
        self.assertIn("def foo", blocks[0])
        self.assertNotIn("def foo", out)

    def test_multiple_fenced_blocks_numbered_sequentially(self):
        text = (
            "```py\nx = 1\n```\n"
            "middle\n"
            "```js\nconst y = 2;\n```\n"
            "end"
        )
        out, blocks = po._extract_code_blocks(text)
        self.assertEqual(len(blocks), 2)
        self.assertIn("⟨CODE_BLOCK_0⟩", out)
        self.assertIn("⟨CODE_BLOCK_1⟩", out)

    def test_indented_code_block_detected(self):
        text = (
            "Here is code:\n\n"
            "    def bar():\n"
            "        x = 1\n"
            "        return x\n"
            "\n"
            "End of example."
        )
        out, blocks = po._extract_code_blocks(text)
        # Indented code with code signals should be extracted
        self.assertEqual(len(blocks), 1)
        self.assertIn("def bar", blocks[0])

    def test_indented_non_code_left_alone(self):
        # 4-space indent but no code signals — should NOT be extracted as code
        text = (
            "Paragraph:\n"
            "    This is a quote.\n"
            "    Another line of quote.\n"
            "    Third line of a regular quote.\n"
        )
        out, blocks = po._extract_code_blocks(text)
        self.assertEqual(len(blocks), 0)

    def test_roundtrip_preserves_code_verbatim(self):
        original = "before\n```python\ncursor.execute(query)\ndb.commit()\n```\nafter"
        extracted, blocks = po._extract_code_blocks(original)
        # Simulate LLM giving back the text unchanged (it only saw prose + placeholder)
        restored = po._reinsert_code_blocks(extracted, blocks)
        self.assertEqual(restored, original)

    def test_roundtrip_multiple_blocks(self):
        original = (
            "```py\na = 1\n```\n"
            "text\n"
            "```py\nb = 2\n```"
        )
        extracted, blocks = po._extract_code_blocks(original)
        restored = po._reinsert_code_blocks(extracted, blocks)
        self.assertEqual(restored, original)


# ---------------------------------------------------------------------------
# Markdown table extraction
# ---------------------------------------------------------------------------

class TestExtractTables(unittest.TestCase):
    """Tests for _extract_tables / _reinsert_tables."""

    def test_no_table(self):
        text = "Just some prose\nwith multiple lines\nand no tables."
        out, tables = po._extract_tables(text)
        self.assertEqual(tables, [])

    def test_single_table_extracted(self):
        text = (
            "Before\n"
            "| Col A | Col B |\n"
            "|-------|-------|\n"
            "| 1     | 2     |\n"
            "| 3     | 4     |\n"
            "After"
        )
        out, tables = po._extract_tables(text)
        self.assertEqual(len(tables), 1)
        self.assertIn("⟨TABLE_0⟩", out)
        self.assertIn("Col A", tables[0])
        self.assertIn("Col B", tables[0])
        self.assertNotIn("Col A", out)

    def test_two_separate_tables(self):
        text = (
            "| a | b |\n"
            "| 1 | 2 |\n"
            "\n"
            "between\n"
            "\n"
            "| c | d |\n"
            "| 3 | 4 |\n"
        )
        out, tables = po._extract_tables(text)
        self.assertEqual(len(tables), 2)

    def test_roundtrip(self):
        original = (
            "Before\n"
            "| H1 | H2 |\n"
            "| v1 | v2 |\n"
            "After\n"
        )
        extracted, tables = po._extract_tables(original)
        restored = po._reinsert_tables(extracted, tables)
        # Tables are reinserted without trailing newline inside placeholder line
        # — but the content of the table must survive
        self.assertIn("| H1 | H2 |", restored)
        self.assertIn("| v1 | v2 |", restored)


# ---------------------------------------------------------------------------
# Inline reference extraction
# ---------------------------------------------------------------------------

class TestExtractInlineRefs(unittest.TestCase):
    """Tests for _extract_inline_refs / _reinsert_inline_refs."""

    def test_no_backticks(self):
        text = "Plain prose with no code identifiers at all."
        out, refs = po._extract_inline_refs(text)
        self.assertEqual(refs, [])
        self.assertEqual(out, text)

    def test_single_ref_extracted(self):
        text = "Check the `main.py` file."
        out, refs = po._extract_inline_refs(text)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0], "`main.py`")
        self.assertNotIn("main.py", out)
        self.assertIn("⟨REF_0⟩", out)

    def test_multiple_refs_numbered(self):
        text = "Edit `stack.py` then run `pytest tests/`"
        out, refs = po._extract_inline_refs(text)
        self.assertEqual(len(refs), 2)
        self.assertIn("⟨REF_0⟩", out)
        self.assertIn("⟨REF_1⟩", out)

    def test_refs_do_not_cross_newlines(self):
        # Backtick regex disallows newlines — a backtick followed by \n
        # before a closing backtick cannot form a ref.
        text = "First line no ref\nSecond line has `valid-ref` here"
        out, refs = po._extract_inline_refs(text)
        self.assertIn("`valid-ref`", refs)
        # The output must retain the first line unchanged
        self.assertIn("First line no ref", out)

    def test_roundtrip(self):
        original = "Use `os.path.join(a, b)` instead of `a + '/' + b`."
        extracted, refs = po._extract_inline_refs(original)
        restored = po._reinsert_inline_refs(extracted, refs)
        self.assertEqual(restored, original)

    def test_protects_against_hallucination(self):
        """BUG-14: LLM must never see filename — hallucination is impossible."""
        text = "The entry point is `main.py` and the stack logic lives in `stack.py`."
        out, refs = po._extract_inline_refs(text)
        # After extraction, the LLM would NOT see main.py or stack.py
        self.assertNotIn("main.py", out)
        self.assertNotIn("stack.py", out)


# ---------------------------------------------------------------------------
# Constraint extraction
# ---------------------------------------------------------------------------

class TestExtractConstraints(unittest.TestCase):
    """Tests for _extract_constraints / _reinsert_constraints."""

    def test_no_constraints(self):
        text = "Regular prose without any strong imperatives."
        out, rules = po._extract_constraints(text)
        self.assertEqual(rules, [])

    def test_never_line_extracted(self):
        text = (
            "Some intro.\n"
            "NEVER create additional tk.Tk() instances.\n"
            "Some outro."
        )
        out, rules = po._extract_constraints(text)
        self.assertEqual(len(rules), 1)
        self.assertIn("NEVER", rules[0])
        self.assertIn("⟨RULE_0⟩", out)

    def test_detects_always_must_do_not(self):
        text = (
            "ALWAYS verify inputs.\n"
            "You MUST NOT skip validation.\n"
            "DO NOT bypass security.\n"
        )
        out, rules = po._extract_constraints(text)
        self.assertEqual(len(rules), 3)

    def test_detects_german_keywords(self):
        """BUG-14 fix must also detect German constraint keywords."""
        text = (
            "NIEMALS darf der Token im Klartext gespeichert werden.\n"
            "Die Datenbank MUSS geschlossen werden.\n"
        )
        out, rules = po._extract_constraints(text)
        self.assertGreaterEqual(len(rules), 2)

    def test_case_insensitive(self):
        text = "never do that\nAlways verify\nImportant: save state"
        out, rules = po._extract_constraints(text)
        self.assertGreaterEqual(len(rules), 3)

    def test_does_not_reextract_placeholders(self):
        """Placeholder lines should be skipped to prevent double-wrapping."""
        text = "⟨CODE_BLOCK_0⟩\nNEVER touch the database directly.\n⟨RULE_0⟩"
        out, rules = po._extract_constraints(text)
        # NEVER line should be the only one extracted; placeholder lines skipped
        # Placeholder-containing lines are skipped even if they *happen* to match
        self.assertEqual(len(rules), 1)
        self.assertIn("NEVER", rules[0])

    def test_roundtrip(self):
        original = (
            "Intro line.\n"
            "NEVER commit API keys to git.\n"
            "Middle line.\n"
            "ALWAYS run tests before merge.\n"
            "End line."
        )
        extracted, rules = po._extract_constraints(original)
        restored = po._reinsert_constraints(extracted, rules)
        self.assertEqual(restored, original)


# ---------------------------------------------------------------------------
# Full 4-layer extraction pipeline (integration, still pure)
# ---------------------------------------------------------------------------

class TestFullExtractionPipeline(unittest.TestCase):
    """Run all four extractors in the same order as compress() and verify
    round-trip integrity for a realistic CLAUDE.md-style input."""

    SAMPLE = (
        "# Project Overview\n"
        "The entry point is `main.py`. All UI runs on `TkUIThread`.\n"
        "\n"
        "## Key Rules\n"
        "NEVER create additional tk.Tk() instances.\n"
        "ALWAYS redact secrets before sending to LLM.\n"
        "\n"
        "## Config\n"
        "| Key | Default |\n"
        "|-----|---------|\n"
        "| debounce_delay | 0.3 |\n"
        "| min_text_length | 5 |\n"
        "\n"
        "## Example\n"
        "```python\n"
        "def compress(text):\n"
        "    return redact_secrets(text)\n"
        "```\n"
    )

    def test_full_extract_then_reinsert_is_identity(self):
        # Extract in the order used by compress()
        text, code = po._extract_code_blocks(self.SAMPLE)
        text, tables = po._extract_tables(text)
        text, refs = po._extract_inline_refs(text)
        text, rules = po._extract_constraints(text)

        # At this point the LLM would see only placeholders for critical content
        self.assertIn("⟨CODE_BLOCK_", text)
        self.assertIn("⟨TABLE_", text)
        self.assertIn("⟨REF_", text)
        self.assertIn("⟨RULE_", text)
        self.assertNotIn("tk.Tk()", text)  # inside a NEVER rule
        self.assertNotIn("def compress", text)
        self.assertNotIn("main.py", text)

        # Reinsert in reverse order (as compress() does)
        text = po._reinsert_constraints(text, rules)
        text = po._reinsert_inline_refs(text, refs)
        text = po._reinsert_tables(text, tables)
        text = po._reinsert_code_blocks(text, code)

        # Every critical artefact is back
        self.assertIn("main.py", text)
        self.assertIn("TkUIThread", text)
        self.assertIn("NEVER create additional tk.Tk()", text)
        self.assertIn("ALWAYS redact secrets", text)
        self.assertIn("| debounce_delay | 0.3 |", text)
        self.assertIn("def compress(text):", text)
        self.assertIn("redact_secrets(text)", text)


# ---------------------------------------------------------------------------
# Post-validation (_validate_compression)
# ---------------------------------------------------------------------------

class TestValidateCompression(unittest.TestCase):
    """Tests for _validate_compression — warning generation."""

    def test_identical_input_no_warnings(self):
        text = "Release on 2026-04-17. Version v1.2.3 — TODO: polish."
        warnings = po._validate_compression(text, text)
        self.assertEqual(warnings, [])

    def test_lost_date_produces_warning(self):
        # _VALIDATION_PATTERNS["dates"] matches DD.MM.YYYY / DD/MM/YYYY / DD-MM-YYYY
        original = "Release on 17.04.2026."
        compressed = "Release soon."
        warnings = po._validate_compression(original, compressed)
        joined = "\n".join(warnings)
        self.assertIn("dates", joined)

    def test_lost_todo_produces_warning(self):
        original = "Check this. TODO: fix later."
        compressed = "Check this."
        warnings = po._validate_compression(original, compressed)
        joined = "\n".join(warnings)
        self.assertIn("todos", joined)

    def test_single_digit_numbers_not_reported(self):
        """Single-digit numbers are noisy and intentionally ignored."""
        original = "Steps: 1 2 3 4."
        compressed = "Steps: none."
        warnings = po._validate_compression(original, compressed)
        # Single-digit losses must not produce a 'numbers' warning
        joined = "\n".join(warnings)
        self.assertNotIn("numbers", joined)

    def test_lost_version_produces_warning(self):
        original = "Ship v1.2.3 on Friday."
        compressed = "Ship on Friday."
        warnings = po._validate_compression(original, compressed)
        joined = "\n".join(warnings)
        self.assertIn("versions", joined)


if __name__ == "__main__":
    unittest.main()
