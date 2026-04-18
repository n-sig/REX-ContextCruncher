"""
test_prompt_optimizer_compress.py — Tests for the full compress() flow.

The compress() function is the entry point for the GUI AI-Compression hotkey.
It chains five deterministic guarantees around a single LLM call:

    1. Security:  redact_secrets()        — secrets never leave the machine.
    2. Extraction: 4-layer hybrid         — code / tables / refs / rules hidden.
    3. Routing:   detect_content_type()   — content-type hint is prepended.
    4. LLM call:  provider-specific HTTP  — mocked here.
    5. Reinsertion: reverse of (2)        — originals restored verbatim.
    6. Validation: warnings on lost data  — never rejects a shorter result.

These tests never hit a real network — httpx is monkey-patched to intercept
all POST calls and return deterministic JSON responses.
"""

import json
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

import contextcruncher.prompt_optimizer as po
import contextcruncher.config as cc_config


# ---------------------------------------------------------------------------
# Path isolation
# ---------------------------------------------------------------------------
#
# Other test modules (notably test_prompt_optimizer.py) also monkey-patch
# po._APP_DIR / po._LLM_KEYS_PATH / po._PROFILES_PATH at import time.  When
# both modules are loaded by pytest in the same session, the one that
# imports last wins — which silently corrupts the other's assumptions.
#
# We avoid that by doing the override *per test* in setUp / tearDown and
# by using a mixin class to keep the boilerplate in one place.
# ---------------------------------------------------------------------------

class _PathIsolationMixin:
    """Redirect po and cc_config to a per-test temp dir; restore afterwards."""

    def setUp(self):  # noqa: N802 — unittest convention
        self._tmp_dir = tempfile.mkdtemp()
        self._orig_paths = (
            po._APP_DIR, po._PROFILES_PATH, po._LLM_KEYS_PATH,
            cc_config._APP_DIR, cc_config.CONFIG_PATH,
        )
        po._APP_DIR = self._tmp_dir
        po._PROFILES_PATH = os.path.join(self._tmp_dir, "profiles.json")
        po._LLM_KEYS_PATH = os.path.join(self._tmp_dir, "llm_keys.json")
        cc_config._APP_DIR = self._tmp_dir
        cc_config.CONFIG_PATH = os.path.join(self._tmp_dir, "config.json")

    def tearDown(self):  # noqa: N802
        (
            po._APP_DIR, po._PROFILES_PATH, po._LLM_KEYS_PATH,
            cc_config._APP_DIR, cc_config.CONFIG_PATH,
        ) = self._orig_paths


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _setup_keys(openai: str = "sk-test-openai",
                anthropic: str = "sk-ant-test",
                ollama: str = "http://localhost:11434") -> None:
    po.save_provider_config({
        "openai_api_key": openai,
        "anthropic_api_key": anthropic,
        "ollama_endpoint": ollama,
    })


def _setup_config(provider: str = "openai", model: str = "gpt-4o-mini",
                  enabled: bool = True) -> None:
    cfg = cc_config._DEFAULT_CONFIG.copy()
    cfg["ai_compress_enabled"] = enabled
    cfg["ai_compress_provider"] = provider
    cfg["ai_compress_model"] = model
    cc_config.save_config(cfg)


def _mock_openai_response(content: str = "compressed"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }
    resp.raise_for_status = MagicMock()
    return resp


def _mock_anthropic_response(content: str = "compressed"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "content": [{"text": content}],
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }
    resp.raise_for_status = MagicMock()
    return resp


def _mock_ollama_response(content: str = "compressed"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "message": {"content": content},
        "prompt_eval_count": 100,
        "eval_count": 20,
    }
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Input validation (no HTTP)
# ---------------------------------------------------------------------------

class TestCompressValidation(_PathIsolationMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        _setup_keys()
        _setup_config()

    def test_empty_text(self):
        r = po.compress("")
        self.assertIn("Empty", r.error)
        self.assertEqual(r.compressed_text, "")

    def test_whitespace_only(self):
        r = po.compress("   \n\n  ")
        self.assertIn("Empty", r.error)

    def test_missing_openai_key(self):
        po.save_provider_config({})
        _setup_config(provider="openai")
        r = po.compress("some meaningful text")
        self.assertIn("API key", r.error)
        self.assertEqual(r.provider, "openai")

    def test_missing_anthropic_key(self):
        po.save_provider_config({})
        _setup_config(provider="anthropic")
        r = po.compress("some meaningful text")
        self.assertIn("API key", r.error)

    def test_unknown_provider(self):
        _setup_config(provider="nonsense-llm")
        r = po.compress("hello")
        self.assertIn("Unknown provider", r.error)

    def test_ollama_needs_no_key(self):
        po.save_provider_config({"ollama_endpoint": "http://localhost:11434"})
        _setup_config(provider="ollama")
        with patch.object(po, "httpx") as mock_httpx:
            mock_httpx.post.return_value = _mock_ollama_response("shorter")
            mock_httpx.TimeoutException = Exception
            mock_httpx.HTTPStatusError = Exception
            r = po.compress("text for ollama to compress")
        self.assertEqual(r.error, "")


# ---------------------------------------------------------------------------
# Security: secrets must be redacted BEFORE the LLM call (BUG-09)
# ---------------------------------------------------------------------------

class TestCompressSecurity(_PathIsolationMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        _setup_keys()
        _setup_config(provider="openai")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_secret_is_redacted_before_llm(self, mock_httpx):
        """BUG-09: an API key in the input must NEVER be sent to the LLM."""
        mock_httpx.post.return_value = _mock_openai_response("short result")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        # A realistic OpenAI API key (must trigger redaction)
        secret = "sk-proj-abcdefghij1234567890ABCDEF1234567890abcdef12"
        input_text = f"Our API key is {secret} — please keep it secret."

        r = po.compress(input_text)

        # 1. The LLM HTTP payload must NOT contain the raw secret
        sent_payload = mock_httpx.post.call_args.kwargs.get("json", {})
        sent_user_msg = sent_payload["messages"][-1]["content"]
        self.assertNotIn(secret, sent_user_msg)

        # 2. The original_text stored on the result must ALSO be redacted
        #    (compress() reassigns `text = redact_secrets(text)` before anything else)
        self.assertNotIn(secret, r.original_text)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_redaction_runs_before_extraction(self, mock_httpx):
        """Security check must occur before code-block extraction, so secrets
        embedded inside code are also redacted before the hybrid pipeline
        stores them for reinsertion."""
        mock_httpx.post.return_value = _mock_openai_response("out")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        secret = "sk-proj-abcdefghij1234567890ABCDEF1234567890abcdef12"
        input_text = (
            "Before\n"
            "```python\n"
            f"API_KEY = '{secret}'\n"
            "```\n"
            "After"
        )
        r = po.compress(input_text)
        # Even after reinsertion the raw secret must not appear
        self.assertNotIn(secret, r.compressed_text)


# ---------------------------------------------------------------------------
# Hybrid extraction: code / tables / refs / rules are round-tripped
# ---------------------------------------------------------------------------

class TestCompressHybridExtraction(_PathIsolationMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        _setup_keys()
        _setup_config(provider="openai")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_code_block_round_trips_verbatim(self, mock_httpx):
        """LLM never sees the code; original survives verbatim."""
        # Simulate LLM returning just the prose (with placeholder copied unchanged)
        mock_httpx.post.return_value = _mock_openai_response(
            "Intro.\n⟨CODE_BLOCK_0⟩\nOutro."
        )
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        code_body = "def get_user(id):\n    cursor.execute(query)\n    return cursor.fetchone()"
        input_text = f"Intro line.\n```python\n{code_body}\n```\nOutro line."

        r = po.compress(input_text)

        # The LLM payload must contain ⟨CODE_BLOCK_0⟩, NOT the code
        sent_user_msg = mock_httpx.post.call_args.kwargs["json"]["messages"][-1]["content"]
        self.assertIn("⟨CODE_BLOCK_0⟩", sent_user_msg)
        self.assertNotIn("cursor.execute", sent_user_msg)

        # The result must contain the original code verbatim
        self.assertIn("cursor.execute(query)", r.compressed_text)
        self.assertIn("def get_user", r.compressed_text)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_inline_refs_protected_from_hallucination(self, mock_httpx):
        """BUG-14: LLM never sees `main.py`, so cannot rename it to `tkui.py`."""
        # LLM is given placeholders — and we simulate it mangling the prose
        # but leaving placeholders untouched.
        mock_httpx.post.return_value = _mock_openai_response(
            "Entry point is ⟨REF_0⟩ and logic lives in ⟨REF_1⟩."
        )
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        r = po.compress(
            "The entry point is `main.py` and the logic lives in `stack.py`."
        )

        # Original filenames restored exactly
        self.assertIn("`main.py`", r.compressed_text)
        self.assertIn("`stack.py`", r.compressed_text)

        # And the LLM's prose mangling is preserved between the refs
        self.assertIn("Entry point", r.compressed_text)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_table_round_trips(self, mock_httpx):
        mock_httpx.post.return_value = _mock_openai_response(
            "Config:\n⟨TABLE_0⟩\nEnd."
        )
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        text = (
            "Config section:\n"
            "| Key | Default |\n"
            "| debounce | 0.3 |\n"
            "| retries | 5 |\n"
            "End of config."
        )
        r = po.compress(text)
        self.assertIn("| debounce | 0.3 |", r.compressed_text)
        self.assertIn("| retries | 5 |", r.compressed_text)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_constraint_round_trips(self, mock_httpx):
        mock_httpx.post.return_value = _mock_openai_response(
            "Rules:\n⟨RULE_0⟩\nSee docs."
        )
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        r = po.compress(
            "Rules section:\n"
            "NEVER create additional tk.Tk() instances.\n"
            "See the docs for more info."
        )
        self.assertIn("NEVER create additional tk.Tk() instances", r.compressed_text)


# ---------------------------------------------------------------------------
# Content-type hint: agent_config triggers ULTRA-CONSERVATIVE MODE
# ---------------------------------------------------------------------------

class TestCompressContentTypeHint(_PathIsolationMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        _setup_keys()
        _setup_config(provider="openai")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_agent_config_adds_hint_to_system_prompt(self, mock_httpx):
        """When the router detects agent_config, the system prompt is extended
        with the ULTRA-CONSERVATIVE MODE hint."""
        mock_httpx.post.return_value = _mock_openai_response("shortened")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        # CLAUDE.md-style text with many constraint keywords → detected as agent_config
        text = (
            "# Project rules\n"
            "NEVER create additional tk.Tk() instances.\n"
            "ALWAYS redact secrets before LLM calls.\n"
            "MUST NOT commit secrets to git.\n"
            "DO NOT bypass security.\n"
            "CRITICAL: run tests before every merge.\n"
            "IMPORTANT: check hotkey collisions.\n"
        )
        po.compress(text)

        sent_system = mock_httpx.post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("ULTRA-CONSERVATIVE MODE", sent_system)
        self.assertIn("agent configuration", sent_system.lower())

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_prose_does_not_trigger_ultra_conservative(self, mock_httpx):
        mock_httpx.post.return_value = _mock_openai_response("s")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        po.compress("Just a regular sentence about nothing in particular.")

        sent_system = mock_httpx.post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertNotIn("ULTRA-CONSERVATIVE MODE", sent_system)


# ---------------------------------------------------------------------------
# Provider dispatch: openai / anthropic / ollama
# ---------------------------------------------------------------------------

class TestCompressProviderDispatch(_PathIsolationMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        _setup_keys()

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_openai_path(self, mock_httpx):
        _setup_config(provider="openai")
        mock_httpx.post.return_value = _mock_openai_response("short")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        r = po.compress("Some reasonably long input text for compression.")
        self.assertEqual(r.provider, "openai")
        self.assertEqual(r.error, "")
        self.assertIn("api.openai.com", mock_httpx.post.call_args.args[0])

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_anthropic_path(self, mock_httpx):
        _setup_config(provider="anthropic", model="claude-3-5-haiku-20241022")
        mock_httpx.post.return_value = _mock_anthropic_response("short")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        r = po.compress("Some reasonably long input text for compression.")
        self.assertEqual(r.provider, "anthropic")
        self.assertIn("api.anthropic.com", mock_httpx.post.call_args.args[0])

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_ollama_path(self, mock_httpx):
        _setup_config(provider="ollama", model="llama3")
        mock_httpx.post.return_value = _mock_ollama_response("short")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        r = po.compress("Some reasonably long input text for compression.")
        self.assertEqual(r.provider, "ollama")
        self.assertIn("11434", mock_httpx.post.call_args.args[0])

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_provider_override_wins_over_config(self, mock_httpx):
        _setup_config(provider="openai")
        mock_httpx.post.return_value = _mock_ollama_response("short")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        r = po.compress("input text", provider_override="ollama")
        self.assertEqual(r.provider, "ollama")


# ---------------------------------------------------------------------------
# Aggressive profile
# ---------------------------------------------------------------------------

class TestCompressAggressive(_PathIsolationMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        _setup_keys()
        _setup_config(provider="openai")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_aggressive_uses_different_system_prompt(self, mock_httpx):
        mock_httpx.post.return_value = _mock_openai_response("s")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        po.compress("input", aggressive=False)
        sys_normal = mock_httpx.post.call_args.kwargs["json"]["messages"][0]["content"]

        po.compress("input", aggressive=True)
        sys_aggr = mock_httpx.post.call_args.kwargs["json"]["messages"][0]["content"]

        # Aggressive prompt targets 30-50%, normal targets 50-70%
        self.assertIn("30-50%", sys_aggr)
        self.assertIn("50-70%", sys_normal)


# ---------------------------------------------------------------------------
# Sanity checks & validation warnings
# ---------------------------------------------------------------------------

class TestCompressSanity(_PathIsolationMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        _setup_keys()
        _setup_config(provider="openai")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_llm_output_longer_returns_original(self, mock_httpx):
        """Sanity: if LLM makes the text LONGER, compress() returns the original."""
        # Make the mock return a much longer response than the input
        long_output = "padding " * 50
        mock_httpx.post.return_value = _mock_openai_response(long_output)
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        short_in = "hello world"
        r = po.compress(short_in)
        self.assertEqual(r.compressed_text, short_in)
        self.assertEqual(r.saved_percent, 0.0)
        self.assertIn("not shorter", r.error)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_validation_warnings_attached(self, mock_httpx):
        # LLM throws away a version number
        mock_httpx.post.return_value = _mock_openai_response("Ship soon.")
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        r = po.compress("Ship version v1.2.3 next Monday, TODO polish before release.")
        # Result was shorter, so no error; but warnings should be populated
        # for the lost version and TODO.
        self.assertEqual(r.error, "")
        # At least one validation warning fired
        joined = "\n".join(r.warnings)
        self.assertTrue(
            "todos" in joined or "versions" in joined,
            f"Expected a validation warning, got: {r.warnings}",
        )

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_timeout_returns_error(self, mock_httpx):
        class _Timeout(Exception):
            pass
        mock_httpx.TimeoutException = _Timeout
        mock_httpx.HTTPStatusError = Exception
        mock_httpx.post.side_effect = _Timeout("boom")

        r = po.compress("some text")
        self.assertIn("timed out", r.error)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_http_error_returns_error(self, mock_httpx):
        err_resp = MagicMock()
        err_resp.status_code = 401
        err_resp.json.return_value = {"error": {"message": "Invalid key"}}
        class _HTTPErr(Exception):
            def __init__(self, msg):
                super().__init__(msg)
                self.response = err_resp
        # TimeoutException must be a *different* class so isinstance() in
        # compress() picks HTTPStatusError — otherwise, with both mapped to
        # Exception, _HTTPErr would match the Timeout branch first.
        class _Timeout(Exception):
            pass
        mock_httpx.HTTPStatusError = _HTTPErr
        mock_httpx.TimeoutException = _Timeout
        mock_httpx.post.side_effect = _HTTPErr("401")

        r = po.compress("text")
        self.assertNotEqual(r.error, "")
        self.assertIn("401", r.error)


# ---------------------------------------------------------------------------
# Graceful degradation: httpx missing
# ---------------------------------------------------------------------------

class TestCompressWithoutHttpx(_PathIsolationMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        _setup_keys()
        _setup_config(provider="openai")

    def test_compress_without_httpx(self):
        original = po.httpx
        try:
            po.httpx = None
            r = po.compress("some text")
            self.assertIn("httpx not installed", r.error)
        finally:
            po.httpx = original


# ---------------------------------------------------------------------------
# is_ai_compress_configured
# ---------------------------------------------------------------------------

class TestIsAiCompressConfigured(_PathIsolationMixin, unittest.TestCase):

    def test_disabled(self):
        _setup_config(provider="openai", enabled=False)
        _setup_keys()
        self.assertFalse(po.is_ai_compress_configured())

    def test_enabled_openai_with_key(self):
        _setup_config(provider="openai", enabled=True)
        _setup_keys(openai="sk-x")
        self.assertTrue(po.is_ai_compress_configured())

    def test_enabled_openai_without_key(self):
        _setup_config(provider="openai", enabled=True)
        po.save_provider_config({})  # wipe keys
        self.assertFalse(po.is_ai_compress_configured())

    def test_ollama_always_configured_when_enabled(self):
        _setup_config(provider="ollama", enabled=True)
        po.save_provider_config({})
        self.assertTrue(po.is_ai_compress_configured())


if __name__ == "__main__":
    unittest.main()
