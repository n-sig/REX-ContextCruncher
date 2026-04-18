"""
test_mcp_ai_compress.py — Tests for the `ai_compress` MCP tool.

ai_compress wraps prompt_optimizer.compress() as an MCP tool so AI agents
(Claude Desktop, Gemini, etc.) can invoke LLM-based semantic compression
via the standard MCP protocol.

This file uses TWO strategies so it runs everywhere:

  1. AST-based structural tests — parse mcp_server.py without importing it,
     verifying the @mcp.tool() decorator is in place and the function
     signature matches the documented contract.  These run on any OS.

  2. Functional tests — import mcp_server and call ai_compress() with a
     mocked po_compress.  Runs on full dev installs; skipped gracefully
     when optional deps (pynput, pystray, full-featured mcp) aren't
     available in the CI sandbox.
"""

from __future__ import annotations

import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

MCP_SERVER_PATH = (
    Path(__file__).parent.parent / "src" / "contextcruncher" / "mcp_server.py"
)


# ---------------------------------------------------------------------------
# Strategy 1: AST-based structural validation (always runs)
# ---------------------------------------------------------------------------

class TestAiCompressRegistered(unittest.TestCase):
    """Verify ai_compress is properly declared in mcp_server.py."""

    @classmethod
    def setUpClass(cls):
        cls.source = MCP_SERVER_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _find_fn(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def test_ai_compress_function_exists(self):
        fn = self._find_fn("ai_compress")
        self.assertIsNotNone(fn, "ai_compress function not defined")

    def test_ai_compress_has_mcp_tool_decorator(self):
        fn = self._find_fn("ai_compress")
        self.assertIsNotNone(fn)
        has_decorator = False
        for dec in fn.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if dec.func.attr == "tool":
                    has_decorator = True
                    break
        self.assertTrue(
            has_decorator,
            "ai_compress is missing the @mcp.tool() decorator",
        )

    def test_ai_compress_signature(self):
        fn = self._find_fn("ai_compress")
        self.assertIsNotNone(fn)
        arg_names = [a.arg for a in fn.args.args]
        self.assertEqual(
            arg_names,
            ["text", "aggressive", "provider", "model"],
            f"Unexpected signature: {arg_names}",
        )

    def test_ai_compress_returns_dict(self):
        fn = self._find_fn("ai_compress")
        self.assertIsNotNone(fn)
        self.assertIsNotNone(fn.returns, "ai_compress must declare return type")
        self.assertEqual(
            getattr(fn.returns, "id", None), "dict",
            "ai_compress must return dict",
        )

    def test_header_docstring_mentions_ai_compress(self):
        # The top-level module docstring lists the tool catalog; ai_compress
        # should appear there so agents discover it.
        self.assertIn("ai_compress", self.source[:3000])

    def test_tool_count_updated_to_23(self):
        # The header "Exposed tools (23):" line is our source-of-truth counter.
        self.assertIn("Exposed tools (23)", self.source[:3000])


# ---------------------------------------------------------------------------
# Strategy 2: Functional tests with mocked po_compress
# ---------------------------------------------------------------------------

# Winreg shim for Linux
if "winreg" not in sys.modules:
    _fake_winreg = types.ModuleType("winreg")
    for _attr in ("OpenKey", "CloseKey", "SetValueEx", "DeleteValue",
                   "QueryValueEx", "HKEY_CURRENT_USER", "KEY_SET_VALUE",
                   "KEY_READ", "REG_SZ"):
        setattr(_fake_winreg, _attr, MagicMock())
    sys.modules["winreg"] = _fake_winreg

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _try_import_mcp_server():
    """Attempt to import mcp_server.  Returns (module, error_str)."""
    try:
        from contextcruncher import mcp_server  # noqa: F401
        return mcp_server, ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


_MCP_MOD, _MCP_ERR = _try_import_mcp_server()


@unittest.skipUnless(_MCP_MOD is not None, f"mcp_server unavailable: {_MCP_ERR}")
class TestAiCompressFunctional(unittest.TestCase):
    """Functional tests — require mcp + deps to be installed."""

    def test_empty_text_returns_error_without_llm_call(self):
        with patch("contextcruncher.mcp_server.po_compress") as mock_compress:
            result = _MCP_MOD.ai_compress("")
            self.assertIn("error", result)
            mock_compress.assert_not_called()

    def test_whitespace_only_returns_error(self):
        with patch("contextcruncher.mcp_server.po_compress") as mock_compress:
            result = _MCP_MOD.ai_compress("   \n\t  ")
            self.assertIn("error", result)
            mock_compress.assert_not_called()

    def test_success_path_returns_all_fields(self):
        from contextcruncher.prompt_optimizer import CompressResult
        fake = CompressResult(
            original_text="hello world this is a test",
            compressed_text="hello world test",
            provider="ollama", model="llama3.2",
            original_tokens=7, compressed_tokens=4,
            saved_percent=42.9, latency_ms=180,
            error="", warnings=[],
        )
        with patch("contextcruncher.mcp_server.po_compress",
                   return_value=fake) as mock_compress:
            out = _MCP_MOD.ai_compress("hello world this is a test")
            mock_compress.assert_called_once()
            _, kwargs = mock_compress.call_args
            self.assertFalse(kwargs.get("aggressive", True))
            self.assertEqual(kwargs.get("provider_override"), "")
            self.assertEqual(kwargs.get("model_override"), "")
            self.assertEqual(out["compressed_text"], "hello world test")
            self.assertEqual(out["provider"], "ollama")
            self.assertEqual(out["saved_percent"], 42.9)
            self.assertEqual(out["warnings"], [])
            self.assertFalse(out["aggressive"])
            self.assertNotIn("error", out)

    def test_aggressive_flag_forwarded(self):
        from contextcruncher.prompt_optimizer import CompressResult
        fake = CompressResult(
            original_text="x", compressed_text="x",
            provider="openai", model="gpt-4o-mini",
            original_tokens=1, compressed_tokens=1,
            saved_percent=0.0, latency_ms=50,
        )
        with patch("contextcruncher.mcp_server.po_compress",
                   return_value=fake) as mock_compress:
            out = _MCP_MOD.ai_compress("x", aggressive=True)
            _, kwargs = mock_compress.call_args
            self.assertTrue(kwargs.get("aggressive"))
            self.assertTrue(out["aggressive"])

    def test_provider_and_model_overrides_forwarded(self):
        from contextcruncher.prompt_optimizer import CompressResult
        fake = CompressResult(
            original_text="x", compressed_text="x",
            provider="anthropic", model="claude-3-haiku",
            original_tokens=1, compressed_tokens=1,
            saved_percent=0.0, latency_ms=50,
        )
        with patch("contextcruncher.mcp_server.po_compress",
                   return_value=fake) as mock_compress:
            _MCP_MOD.ai_compress(
                "x", provider="anthropic", model="claude-3-haiku",
            )
            _, kwargs = mock_compress.call_args
            self.assertEqual(kwargs.get("provider_override"), "anthropic")
            self.assertEqual(kwargs.get("model_override"), "claude-3-haiku")

    def test_error_from_provider_is_surfaced(self):
        from contextcruncher.prompt_optimizer import CompressResult
        fake = CompressResult(
            original_text="x", compressed_text="",
            provider="openai", model="gpt-4o",
            original_tokens=1, compressed_tokens=0,
            saved_percent=0.0, latency_ms=120,
            error="HTTP 401: API key invalid or not authorized (openai).",
        )
        with patch("contextcruncher.mcp_server.po_compress", return_value=fake):
            out = _MCP_MOD.ai_compress("x")
            self.assertIn("error", out)
            self.assertIn("401", out["error"])

    def test_warnings_are_forwarded(self):
        from contextcruncher.prompt_optimizer import CompressResult
        fake = CompressResult(
            original_text="x", compressed_text="y",
            provider="ollama", model="llama3.2",
            original_tokens=1, compressed_tokens=1,
            saved_percent=0.0, latency_ms=60,
            warnings=["Token count grew by 12%",
                      "Constraint 'NEVER' may be lost"],
        )
        with patch("contextcruncher.mcp_server.po_compress", return_value=fake):
            out = _MCP_MOD.ai_compress("x")
            self.assertEqual(len(out["warnings"]), 2)
            self.assertIn("Token count grew", out["warnings"][0])


if __name__ == "__main__":
    unittest.main()
