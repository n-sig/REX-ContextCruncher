"""
test_bug13_code_safe.py — Regression tests for BUG-13.

BUG-13: Deterministic compression was destroying unfenced source code by:
  1. Classifying it as 'prose' in _detect_content_type
  2. Running _phase_trim (line.split() + " ".join()) which strips leading
     indentation
  3. Running stop-word filtering that drops single-letter identifiers
     (parameters named `a`, `b`, etc.)
  4. Running _phase_optimize synonym replacement inside string literals
  5. Finalize's _MULTI_SPACE collapse compressing 4-space indent to 1 space

Fix: _detect_raw_code_language() detects Python/JS/generic code and sets
content_type = code_python / code_js / code_generic.  Main pipeline skips
the destructive prose-only phases when content_type starts with 'code_'.
Normalize and FINALIZE use indentation-preserving variants for code.
"""

from __future__ import annotations

import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Stub winreg for Linux CI
if "winreg" not in sys.modules:
    _fake_winreg = types.ModuleType("winreg")
    for _attr in (
        "OpenKey", "CloseKey", "SetValueEx", "DeleteValue",
        "QueryValueEx", "HKEY_CURRENT_USER", "KEY_SET_VALUE",
        "KEY_READ", "REG_SZ",
    ):
        setattr(_fake_winreg, _attr, MagicMock())
    sys.modules["winreg"] = _fake_winreg

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.text_processor import (  # noqa: E402
    minify_for_ai,
    _detect_content_type,
    _detect_raw_code_language,
)


# ---------------------------------------------------------------------------
# _detect_raw_code_language
# ---------------------------------------------------------------------------

class TestDetectRawCodeLanguage(unittest.TestCase):
    """Unit tests for the raw-code detector (no fences required)."""

    def test_returns_empty_for_pure_prose(self):
        prose = (
            "The quarterly review covered a variety of factors that affected "
            "team morale. Due to the fact that deadlines shifted, we need to "
            "reprioritize. Please note that stakeholder input is essential."
        )
        self.assertEqual(_detect_raw_code_language(prose), "")

    def test_detects_python_from_def_and_indent(self):
        code = "def add(a, b):\n    return a + b\n"
        self.assertEqual(_detect_raw_code_language(code), "code_python")

    def test_detects_python_from_multiple_signals(self):
        code = (
            "import os\n"
            "from pathlib import Path\n"
            "def main():\n"
            "    print(os.getcwd())\n"
        )
        self.assertEqual(_detect_raw_code_language(code), "code_python")

    def test_detects_python_from_class(self):
        code = "class Foo:\n    def bar(self):\n        return 1\n"
        self.assertEqual(_detect_raw_code_language(code), "code_python")

    def test_detects_js_from_const_and_arrow(self):
        code = (
            "import { useState } from 'react';\n"
            "const Counter = () => {\n"
            "  return 1;\n"
            "};\n"
        )
        # Either code_js or code_generic is acceptable here
        self.assertIn(_detect_raw_code_language(code), ("code_js", "code_generic"))

    def test_word_def_in_prose_not_misclassified(self):
        # "def" appears once as an abbreviation — should not trigger code mode
        prose = "The def of this term is unclear in the standard."
        self.assertEqual(_detect_raw_code_language(prose), "")


# ---------------------------------------------------------------------------
# Full pipeline: raw code preservation
# ---------------------------------------------------------------------------

class TestRawCodePreservation(unittest.TestCase):
    """Unfenced Python/JS must round-trip through minify_for_ai intact."""

    PY_SNIPPET = (
        "def calculate_tax(income, rate):\n"
        "    if income <= 0:\n"
        "        return 0\n"
        "    if rate < 0 or rate > 1:\n"
        "        raise ValueError('Rate must be between 0 and 1')\n"
        "    tax = income * rate\n"
        "    return round(tax, 2)\n"
        "\n"
        "class Calculator:\n"
        "    def __init__(self):\n"
        "        self.history = []\n"
        "\n"
        "    def add(self, a, b):\n"
        "        result = a + b\n"
        "        self.history.append((a, b, result))\n"
        "        return result\n"
    )

    def test_python_content_type_is_code(self):
        _, stats = minify_for_ai(self.PY_SNIPPET)
        self.assertEqual(stats["content_type"], "code_python")

    def test_python_indentation_is_preserved(self):
        out, _ = minify_for_ai(self.PY_SNIPPET)
        # 4-space and 8-space indents must both survive
        four_space = [l for l in out.splitlines() if l.startswith("    ")
                      and not l.startswith("        ")]
        eight_space = [l for l in out.splitlines() if l.startswith("        ")]
        self.assertGreaterEqual(
            len(four_space), 2,
            f"4-space indents lost.\nOUT:\n{out}",
        )
        self.assertGreaterEqual(
            len(eight_space), 3,
            f"8-space indents lost.\nOUT:\n{out}",
        )

    def test_python_single_letter_params_survive(self):
        out, _ = minify_for_ai(self.PY_SNIPPET)
        # Stop-word filter used to drop `a`, `b` — must NOT happen for code.
        self.assertIn("def add(self, a, b):", out)
        self.assertIn("result = a + b", out)

    def test_string_literals_not_synonym_replaced(self):
        out, _ = minify_for_ai(self.PY_SNIPPET)
        # _phase_optimize would have turned "between" into "btwn" — must NOT.
        self.assertIn("between", out)
        self.assertNotIn("btwn", out)

    def test_output_parses_as_valid_python(self):
        out, _ = minify_for_ai(self.PY_SNIPPET)
        # Round-trip via ast.parse — any syntax error = test failure.
        try:
            ast.parse(out)
        except SyntaxError as exc:
            self.fail(
                f"Compressed output is not valid Python: {exc}\n"
                f"OUTPUT:\n{out}"
            )

    def test_code_safe_mode_flag_in_techniques(self):
        _, stats = minify_for_ai(self.PY_SNIPPET)
        self.assertIn("code_safe_mode", stats["techniques_applied"])
        # The destructive phases must NOT be in the list
        for bad in ("filler_trim", "synonyms", "telegraphic"):
            matches = [t for t in stats["techniques_applied"] if t.startswith(bad)]
            self.assertEqual(
                matches, [],
                f"Destructive phase {bad} ran on code: {stats['techniques_applied']}",
            )


# ---------------------------------------------------------------------------
# Regression: prose compression still works
# ---------------------------------------------------------------------------

class TestProseStillCompresses(unittest.TestCase):
    """The BUG-13 fix must NOT reduce prose compression quality."""

    PROSE = (
        "In order to succeed, we need to take into account a variety of "
        "factors. Due to the fact that the deadline is approaching, it is "
        "important to prioritize tasks carefully. Please note that we should "
        "make sure to communicate with stakeholders on a regular basis. "
        "At the same time, we must keep track of progress. The team should "
        "be aware of the fact that resources are limited."
    )

    def test_prose_content_type_is_prose(self):
        _, stats = minify_for_ai(self.PROSE)
        self.assertEqual(stats["content_type"], "prose")

    def test_prose_compresses_meaningfully(self):
        _, stats = minify_for_ai(self.PROSE)
        # Old behavior was ~25% savings for prose — anything above 10%
        # indicates the prose path still runs the destructive phases.
        self.assertGreater(
            stats["saved_percent"], 10.0,
            f"Prose compression regressed: only {stats['saved_percent']}% saved",
        )


if __name__ == "__main__":
    unittest.main()
