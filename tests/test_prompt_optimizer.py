"""
test_prompt_optimizer.py — Tests for FR-05.4 AI Prompt Optimizer.

Tests profile management, provider dispatch, error handling, and security.
HTTP calls are mocked via unittest.mock to avoid real API traffic.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from dataclasses import asdict

# Redirect config paths to temp dirs before importing
_temp_dir = tempfile.mkdtemp()
_profiles_path = os.path.join(_temp_dir, "profiles.json")
_keys_path = os.path.join(_temp_dir, "llm_keys.json")

import contextcruncher.prompt_optimizer as po

# Override module-level paths
po._APP_DIR = _temp_dir
po._PROFILES_PATH = _profiles_path
po._LLM_KEYS_PATH = _keys_path


class TestBuiltinProfiles(unittest.TestCase):
    """Test built-in profile availability."""

    def test_builtin_profiles_exist(self):
        names = {p["name"] for p in po.list_profiles() if p.get("is_builtin")}
        self.assertEqual(names, {
            "compress", "compress_aggressive",
            "general", "code_reviewer", "data_analyst", "summarizer", "translator",
        })

    def test_builtin_profiles_cannot_be_deleted(self):
        for name in ("compress", "general", "code_reviewer", "data_analyst", "summarizer", "translator"):
            result = po.delete_profile(name)
            self.assertIn("error", result)
            self.assertIn("built-in", result["error"])

    def test_builtin_profiles_cannot_be_overwritten(self):
        profile = po.LLMProfile(name="general", provider="openai", model="gpt-4o", system_prompt="hacked")
        result = po.save_profile(profile)
        self.assertIn("error", result)
        self.assertIn("built-in", result["error"])

    def test_get_builtin_profile(self):
        p = po.get_profile("general")
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "general")
        self.assertEqual(p.provider, "openai")
        self.assertIn("prompt engineer", p.system_prompt.lower())


class TestCustomProfiles(unittest.TestCase):
    """Test custom profile CRUD."""

    def setUp(self):
        # Clean state
        if os.path.exists(_profiles_path):
            os.remove(_profiles_path)

    def test_create_custom_profile(self):
        profile = po.LLMProfile(
            name="my_reviewer", provider="ollama", model="llama3",
            system_prompt="You review Go code.", endpoint="http://localhost:11434",
        )
        result = po.save_profile(profile)
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["name"], "my_reviewer")

    def test_custom_profile_appears_in_list(self):
        profile = po.LLMProfile(
            name="test_prof", provider="openai", model="gpt-4o-mini",
            system_prompt="Test system prompt.",
        )
        po.save_profile(profile)
        names = {p["name"] for p in po.list_profiles()}
        self.assertIn("test_prof", names)

    def test_get_custom_profile(self):
        profile = po.LLMProfile(
            name="getter_test", provider="anthropic", model="claude-3-haiku",
            system_prompt="Testing getter.",
        )
        po.save_profile(profile)
        p = po.get_profile("getter_test")
        self.assertIsNotNone(p)
        self.assertEqual(p.provider, "anthropic")

    def test_delete_custom_profile(self):
        profile = po.LLMProfile(
            name="to_delete", provider="openai", model="gpt-4o-mini",
            system_prompt="Will be deleted.",
        )
        po.save_profile(profile)
        result = po.delete_profile("to_delete")
        self.assertEqual(result["status"], "deleted")
        self.assertIsNone(po.get_profile("to_delete"))

    def test_delete_nonexistent_profile(self):
        result = po.delete_profile("nonexistent")
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    def test_update_custom_profile(self):
        profile = po.LLMProfile(
            name="updatable", provider="openai", model="gpt-4o-mini",
            system_prompt="v1",
        )
        po.save_profile(profile)
        profile.system_prompt = "v2"
        po.save_profile(profile)
        p = po.get_profile("updatable")
        self.assertEqual(p.system_prompt, "v2")

    def test_invalid_provider_rejected(self):
        profile = po.LLMProfile(
            name="bad_provider", provider="gemini", model="gemini-pro",
            system_prompt="Not supported.",
        )
        result = po.save_profile(profile)
        self.assertIn("error", result)
        self.assertIn("Unknown provider", result["error"])

    def test_persistence_across_reload(self):
        """Custom profiles survive a 'reload' (re-read from disk)."""
        profile = po.LLMProfile(
            name="persistent", provider="openai", model="gpt-4o",
            system_prompt="Persists.",
        )
        po.save_profile(profile)
        # Simulate reload
        profiles = po._load_custom_profiles()
        names = {p.name for p in profiles}
        self.assertIn("persistent", names)


class TestProviderConfig(unittest.TestCase):
    """Test API key management."""

    def setUp(self):
        if os.path.exists(_keys_path):
            os.remove(_keys_path)

    def test_empty_config(self):
        config = po.get_provider_config()
        self.assertEqual(config, {})

    def test_save_and_load_config(self):
        po.save_provider_config({
            "openai_api_key": "sk-test123",
            "ollama_endpoint": "http://localhost:11434",
        })
        config = po.get_provider_config()
        self.assertEqual(config["openai_api_key"], "sk-test123")
        self.assertEqual(config["ollama_endpoint"], "http://localhost:11434")

    def test_partial_update_preserves_keys(self):
        po.save_provider_config({"openai_api_key": "sk-first"})
        config = po.get_provider_config()
        config["anthropic_api_key"] = "sk-ant-second"
        po.save_provider_config(config)
        final = po.get_provider_config()
        self.assertEqual(final["openai_api_key"], "sk-first")
        self.assertEqual(final["anthropic_api_key"], "sk-ant-second")


class TestOptimizeValidation(unittest.TestCase):
    """Test optimize() input validation (no HTTP calls)."""

    def test_empty_text_returns_error(self):
        result = po.optimize("")
        self.assertNotEqual(result.error, "")
        self.assertIn("Empty", result.error)

    def test_whitespace_only_returns_error(self):
        result = po.optimize("   \n  ")
        self.assertIn("Empty", result.error)

    def test_unknown_profile_returns_error(self):
        result = po.optimize("Hello world", profile_name="nonexistent_xyz")
        self.assertIn("not found", result.error)

    def test_unknown_provider_returns_error(self):
        result = po.optimize("Hello world", provider_override="google_vertex")
        self.assertIn("Unknown provider", result.error)

    def test_missing_api_key_returns_error(self):
        if os.path.exists(_keys_path):
            os.remove(_keys_path)
        result = po.optimize("Hello world", provider_override="openai")
        self.assertIn("API key not configured", result.error)

    def test_missing_anthropic_key_returns_error(self):
        if os.path.exists(_keys_path):
            os.remove(_keys_path)
        result = po.optimize("Hello world", provider_override="anthropic")
        self.assertIn("API key not configured", result.error)


class TestOptimizeWithMockedHTTP(unittest.TestCase):
    """Test optimize() with mocked httpx responses."""

    def setUp(self):
        # Provide API keys
        po.save_provider_config({
            "openai_api_key": "sk-test-key",
            "anthropic_api_key": "sk-ant-test-key",
            "ollama_endpoint": "http://localhost:11434",
        })

    def _mock_openai_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Optimized: Review this Python function..."}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30},
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def _mock_anthropic_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"text": "Optimized via Anthropic: Please review..."}],
            "usage": {"input_tokens": 45, "output_tokens": 28},
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def _mock_ollama_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Optimized via Ollama: Analyze the following..."},
            "prompt_eval_count": 40,
            "eval_count": 25,
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_openai_success(self, mock_httpx):
        mock_httpx.post.return_value = self._mock_openai_response()
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        result = po.optimize("Review my code", provider_override="openai")
        self.assertEqual(result.error, "")
        self.assertIn("Optimized", result.optimized_prompt)
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.input_tokens, 50)
        self.assertEqual(result.output_tokens, 30)
        self.assertGreaterEqual(result.latency_ms, 0)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_anthropic_success(self, mock_httpx):
        mock_httpx.post.return_value = self._mock_anthropic_response()
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        result = po.optimize("Summarize this text", provider_override="anthropic")
        self.assertEqual(result.error, "")
        self.assertIn("Anthropic", result.optimized_prompt)
        self.assertEqual(result.provider, "anthropic")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_ollama_success(self, mock_httpx):
        mock_httpx.post.return_value = self._mock_ollama_response()
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        result = po.optimize("Analyze this log", provider_override="ollama")
        self.assertEqual(result.error, "")
        self.assertIn("Ollama", result.optimized_prompt)
        self.assertEqual(result.provider, "ollama")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_timeout_returns_error(self, mock_httpx):
        mock_httpx.TimeoutException = TimeoutError
        mock_httpx.HTTPStatusError = Exception
        mock_httpx.post.side_effect = TimeoutError("Connection timed out")

        result = po.optimize("Hello", provider_override="openai")
        self.assertIn("timed out", result.error)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_http_error_returns_error(self, mock_httpx):
        error_resp = MagicMock()
        error_resp.status_code = 401
        error_resp.json.return_value = {"error": {"message": "Invalid API key"}}
        exc = type("HTTPStatusError", (Exception,), {"response": error_resp})
        mock_httpx.HTTPStatusError = exc
        mock_httpx.TimeoutException = TimeoutError
        mock_httpx.post.side_effect = exc("401")

        result = po.optimize("Hello", provider_override="openai")
        self.assertNotEqual(result.error, "")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_profile_override(self, mock_httpx):
        """Provider and model overrides work correctly."""
        mock_httpx.post.return_value = self._mock_openai_response()
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        result = po.optimize("Test", profile_name="code_reviewer",
                             provider_override="openai", model_override="gpt-4o")
        self.assertEqual(result.profile_used, "code_reviewer")
        self.assertEqual(result.model, "gpt-4o")

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_api_key_not_in_result(self, mock_httpx):
        """Security: API keys must never appear in the result."""
        mock_httpx.post.return_value = self._mock_openai_response()
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        result = po.optimize("Test text", provider_override="openai")
        result_str = str(asdict(result))
        self.assertNotIn("sk-test-key", result_str)
        self.assertNotIn("sk-ant-test-key", result_str)

    @patch("contextcruncher.prompt_optimizer.httpx")
    def test_custom_profile_used_for_optimization(self, mock_httpx):
        """Custom profiles are picked up by optimize()."""
        mock_httpx.post.return_value = self._mock_ollama_response()
        mock_httpx.TimeoutException = Exception
        mock_httpx.HTTPStatusError = Exception

        profile = po.LLMProfile(
            name="go_expert", provider="ollama", model="codellama",
            system_prompt="You are a Go expert. Rewrite as a Go code review prompt.",
        )
        po.save_profile(profile)

        result = po.optimize("func main() { }", profile_name="go_expert")
        self.assertEqual(result.error, "")
        self.assertEqual(result.profile_used, "go_expert")
        self.assertEqual(result.provider, "ollama")

        # Verify the system prompt was used in the request
        call_args = mock_httpx.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json") or (call_args[0][1] if len(call_args[0]) > 1 else None)
        if payload:
            system_msg = payload.get("messages", [{}])[0].get("content", "")
            self.assertIn("Go expert", system_msg)

        # Cleanup
        po.delete_profile("go_expert")


class TestLLMProfileDataclass(unittest.TestCase):
    """Test LLMProfile serialization."""

    def test_to_dict(self):
        p = po.LLMProfile(name="test", provider="openai", model="gpt-4o", system_prompt="Hello")
        d = p.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["temperature"], 0.3)

    def test_from_dict(self):
        d = {"name": "test", "provider": "ollama", "model": "llama3",
             "system_prompt": "Hi", "temperature": 0.5, "extra_field": True}
        p = po.LLMProfile.from_dict(d)
        self.assertEqual(p.name, "test")
        self.assertEqual(p.temperature, 0.5)

    def test_from_dict_defaults(self):
        d = {"name": "min", "provider": "openai", "model": "gpt-4o-mini", "system_prompt": "S"}
        p = po.LLMProfile.from_dict(d)
        self.assertEqual(p.temperature, 0.3)
        self.assertEqual(p.max_output_tokens, 2000)
        self.assertEqual(p.endpoint, "")


class TestHttpxNotInstalled(unittest.TestCase):
    """Test graceful degradation when httpx is missing."""

    def test_optimize_without_httpx(self):
        original = po.httpx
        try:
            po.httpx = None
            result = po.optimize("Hello world")
            self.assertIn("httpx not installed", result.error)
        finally:
            po.httpx = original


if __name__ == "__main__":
    unittest.main()
