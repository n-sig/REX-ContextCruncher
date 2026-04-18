"""
test_phase2_ux.py — Tests for v1.0 Phase 2 UX Polish.

Covers:
  * __version__ constant exported from contextcruncher package
  * _friendly_provider_error() error-mapping helper in prompt_optimizer
  * probe_ollama() connection probe used by the Settings "Test Connection" button

Mocks httpx so no real network calls are ever made.
"""

from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Stub winreg for Linux CI (config.py imports it at top level) ─────────
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

import contextcruncher
import contextcruncher.prompt_optimizer as po


# ---------------------------------------------------------------------------
# __version__
# ---------------------------------------------------------------------------

class TestVersionExport(unittest.TestCase):
    """The package must expose a __version__ constant for the tray/settings UI."""

    def test_version_is_defined(self):
        self.assertTrue(hasattr(contextcruncher, "__version__"))
        self.assertIsInstance(contextcruncher.__version__, str)
        self.assertTrue(contextcruncher.__version__.strip())

    def test_version_has_major_minor(self):
        # Loose sanity: the version should at least look like "X.Y" or "X.Y.Z"
        parts = contextcruncher.__version__.split(".")
        self.assertGreaterEqual(
            len(parts), 2,
            f"Expected semver-like version, got {contextcruncher.__version__!r}",
        )


# ---------------------------------------------------------------------------
# _friendly_provider_error
# ---------------------------------------------------------------------------

class TestFriendlyProviderError(unittest.TestCase):
    """_friendly_provider_error turns raw exceptions into short toast-ready text."""

    def _patched_httpx(self, mock_httpx):
        """Install distinct exception classes on a mock httpx module.

        Each category must be its own class so isinstance() in
        _friendly_provider_error picks the intended branch.
        """
        class _Timeout(Exception):
            pass

        class _HTTPErr(Exception):
            def __init__(self, msg="", response=None):
                super().__init__(msg)
                self.response = response

        class _Connect(Exception):
            pass

        class _ConnectTimeout(Exception):
            pass

        class _Network(Exception):
            pass

        mock_httpx.TimeoutException = _Timeout
        mock_httpx.HTTPStatusError = _HTTPErr
        mock_httpx.ConnectError = _Connect
        mock_httpx.ConnectTimeout = _ConnectTimeout
        mock_httpx.NetworkError = _Network
        return _Timeout, _HTTPErr, _Connect, _ConnectTimeout, _Network

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_timeout_maps_to_short_phrase(self, mock_httpx):
        _Timeout, _, _, _, _ = self._patched_httpx(mock_httpx)
        msg = po._friendly_provider_error(_Timeout(), "openai", "gpt-4o")
        self.assertIn("timed out", msg.lower())

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_connect_error_ollama_hints_at_ollama_serve(self, mock_httpx):
        _, _, _Connect, _, _ = self._patched_httpx(mock_httpx)
        msg = po._friendly_provider_error(
            _Connect("Connection refused"), "ollama", "llama3.2",
        )
        self.assertIn("Ollama", msg)
        self.assertIn("ollama serve", msg)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_connect_error_other_provider_mentions_provider(self, mock_httpx):
        _, _, _Connect, _, _ = self._patched_httpx(mock_httpx)
        msg = po._friendly_provider_error(
            _Connect("unreachable"), "openai", "gpt-4o",
        )
        # Should not recommend ollama serve for non-ollama providers
        self.assertNotIn("ollama serve", msg)
        self.assertIn("openai", msg.lower())

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_http_401_says_api_key_invalid(self, mock_httpx):
        _, _HTTPErr, _, _, _ = self._patched_httpx(mock_httpx)
        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"error": {"message": "bad key"}}
        err = _HTTPErr("auth", response=resp)
        msg = po._friendly_provider_error(err, "openai", "gpt-4o")
        self.assertIn("401", msg)
        self.assertIn("API key", msg)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_http_404_says_model_not_found_with_name(self, mock_httpx):
        _, _HTTPErr, _, _, _ = self._patched_httpx(mock_httpx)
        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {"error": {"message": "model missing"}}
        err = _HTTPErr("nope", response=resp)
        msg = po._friendly_provider_error(err, "ollama", "phi3-mini-xyz")
        self.assertIn("404", msg)
        self.assertIn("phi3-mini-xyz", msg)
        self.assertIn("not found", msg.lower())

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_http_429_says_rate_limit(self, mock_httpx):
        _, _HTTPErr, _, _, _ = self._patched_httpx(mock_httpx)
        resp = MagicMock()
        resp.status_code = 429
        resp.json.return_value = {"error": {"message": "slow down"}}
        err = _HTTPErr("limit", response=resp)
        msg = po._friendly_provider_error(err, "anthropic", "claude")
        self.assertIn("429", msg)
        self.assertIn("rate limit", msg.lower())

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_unknown_exception_falls_back_to_str(self, mock_httpx):
        # Install distinct classes so isinstance() does not accidentally match
        self._patched_httpx(mock_httpx)
        msg = po._friendly_provider_error(
            RuntimeError("something odd"), "openai", "gpt-4o",
        )
        self.assertIn("something odd", msg)


# ---------------------------------------------------------------------------
# probe_ollama
# ---------------------------------------------------------------------------

class TestProbeOllama(unittest.TestCase):
    """probe_ollama sends GET /api/tags and summarizes the outcome."""

    def _distinct_httpx_exc_classes(self, mock_httpx):
        """Give each httpx exception category a unique class so isinstance
        picks the intended branch in _friendly_provider_error."""
        class _Timeout(Exception): pass
        class _HTTPErr(Exception):
            def __init__(self, msg="", response=None):
                super().__init__(msg)
                self.response = response
        class _Connect(Exception): pass
        class _ConnectTimeout(Exception): pass
        class _Network(Exception): pass
        mock_httpx.TimeoutException = _Timeout
        mock_httpx.HTTPStatusError = _HTTPErr
        mock_httpx.ConnectError = _Connect
        mock_httpx.ConnectTimeout = _ConnectTimeout
        mock_httpx.NetworkError = _Network
        return _Timeout, _HTTPErr, _Connect, _ConnectTimeout, _Network

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_probe_returns_models_on_success(self, mock_httpx):
        self._distinct_httpx_exc_classes(mock_httpx)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "phi3-mini"},
            ],
        }
        mock_httpx.get.return_value = resp

        r = po.probe_ollama("http://localhost:11434")
        self.assertTrue(r.ok)
        self.assertIn("llama3.2:latest", r.models)
        self.assertIn("phi3-mini", r.models)
        self.assertEqual(r.error, "")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_probe_tolerates_empty_models_list(self, mock_httpx):
        self._distinct_httpx_exc_classes(mock_httpx)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"models": []}
        mock_httpx.get.return_value = resp

        r = po.probe_ollama()
        self.assertTrue(r.ok)
        self.assertEqual(r.models, [])

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_probe_reports_connect_error_with_hint(self, mock_httpx):
        _, _, _Connect, _, _ = self._distinct_httpx_exc_classes(mock_httpx)
        mock_httpx.get.side_effect = _Connect("refused")

        r = po.probe_ollama("http://localhost:11434")
        self.assertFalse(r.ok)
        self.assertIn("Ollama", r.error)
        self.assertIn("ollama serve", r.error)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_probe_reports_http_error(self, mock_httpx):
        _, _HTTPErr, _, _, _ = self._distinct_httpx_exc_classes(mock_httpx)

        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {"error": {"message": "not here"}}
        resp.raise_for_status.side_effect = _HTTPErr("404", response=resp)
        mock_httpx.get.return_value = resp

        r = po.probe_ollama("http://localhost:11434/api")
        self.assertFalse(r.ok)
        self.assertIn("404", r.error)

    def test_probe_without_httpx_returns_error(self):
        original = po.httpx
        try:
            po.httpx = None
            r = po.probe_ollama()
            self.assertFalse(r.ok)
            self.assertIn("httpx", r.error)
        finally:
            po.httpx = original


if __name__ == "__main__":
    unittest.main()
