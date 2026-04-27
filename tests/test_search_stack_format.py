"""Tests for the search_stack MCP tool return format.

Verifies that search_stack returns a dict with ``stack_size`` and ``results``
keys so AI agents can distinguish between an empty stack and no matching
results.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.stack import TextStack


class TestSearchStackReturnFormat(unittest.TestCase):
    """Tests for MCP search_stack dict return value."""

    def _make_search_stack(self, stack: TextStack):
        """Build a local search_stack function bound to *stack*."""

        def search_stack(query: str = "") -> dict:
            entries = []
            q = query.lower() if query else ""
            for i in range(stack.size()):
                entry = stack.get_entry(i)
                if entry is None:
                    continue
                if not q or q in entry.original.lower():
                    entries.append({
                        "index": i,
                        "text": entry.text,
                        "original": entry.original,
                        "compact": entry.compact,
                    })

            return {
                "stack_size": stack.size(),
                "results": entries,
            }

        return search_stack

    def test_empty_stack_returns_dict_with_zero_size(self):
        stack = TextStack()
        search = self._make_search_stack(stack)
        result = search()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["stack_size"], 0)
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 0)

    def test_populated_stack_returns_dict_with_size(self):
        stack = TextStack()
        stack.push("hello world")
        stack.push("foo bar baz")
        search = self._make_search_stack(stack)
        result = search()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["stack_size"], 2)
        self.assertEqual(len(result["results"]), 2)

    def test_query_no_match_returns_size_and_message(self):
        stack = TextStack()
        stack.push("hello world")
        search = self._make_search_stack(stack)
        result = search("zzzznotfound")
        self.assertEqual(result["stack_size"], 1)
        self.assertEqual(len(result["results"]), 0)

    def test_query_match_returns_filtered(self):
        stack = TextStack()
        stack.push("apple pie")
        stack.push("banana split")
        search = self._make_search_stack(stack)
        result = search("banana")
        self.assertEqual(result["stack_size"], 2)
        self.assertEqual(len(result["results"]), 1)
        self.assertIn("banana", result["results"][0]["original"])


if __name__ == "__main__":
    unittest.main()
