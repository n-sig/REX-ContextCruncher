"""
Tests for ocr.get_available_languages() — BUG-04.

The WinRT engine is not available in CI (Linux), so these tests validate
the fallback path and the helper's contract independently of the platform.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Patch winrt unavailability before importing the module
from unittest.mock import patch, MagicMock
import contextcruncher.ocr as ocr_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lang(tag: str):
    """Build a minimal fake WinRT Language object."""
    m = MagicMock()
    m.language_tag = tag
    return m


# ---------------------------------------------------------------------------
# Fallback path (WinRT unavailable — always true in Linux CI)
# ---------------------------------------------------------------------------

def test_fallback_returns_list():
    with patch.object(ocr_mod, "_winrt_available", False):
        result = ocr_mod.get_available_languages()
    assert isinstance(result, list)
    assert len(result) > 0


def test_fallback_entries_are_tuples_of_two_strings():
    with patch.object(ocr_mod, "_winrt_available", False):
        result = ocr_mod.get_available_languages()
    for entry in result:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        name, tag = entry
        assert isinstance(name, str) and name
        assert isinstance(tag, str) and tag


def test_fallback_includes_english():
    with patch.object(ocr_mod, "_winrt_available", False):
        result = ocr_mod.get_available_languages()
    tags = [tag for _, tag in result]
    assert "en" in tags


def test_fallback_includes_german():
    with patch.object(ocr_mod, "_winrt_available", False):
        result = ocr_mod.get_available_languages()
    tags = [tag for _, tag in result]
    assert "de" in tags


# ---------------------------------------------------------------------------
# Live path — mock OcrEngine
# ---------------------------------------------------------------------------

def test_live_path_known_tag_gets_friendly_name():
    fake_engine = MagicMock()
    fake_engine.available_recognizer_languages = [_lang("de-DE"), _lang("en-US")]
    with (
        patch.object(ocr_mod, "_winrt_available", True),
        patch.object(ocr_mod, "_OcrEngine", fake_engine),
    ):
        result = ocr_mod.get_available_languages()

    names = [name for name, _ in result]
    tags  = [tag  for _, tag  in result]

    assert "de-DE" in tags
    assert "en-US" in tags
    # Should map to friendly names, not raw tags
    assert "Deutsch (Deutschland)" in names
    assert "English (US)" in names


def test_live_path_unknown_tag_falls_back_to_raw_tag():
    fake_engine = MagicMock()
    fake_engine.available_recognizer_languages = [_lang("tlh-Piqd")]   # Klingon :)
    with (
        patch.object(ocr_mod, "_winrt_available", True),
        patch.object(ocr_mod, "_OcrEngine", fake_engine),
    ):
        result = ocr_mod.get_available_languages()

    # Unknown tag → raw tag used as display name
    assert result == [("tlh-Piqd", "tlh-Piqd")]


def test_live_path_primary_subtag_lookup():
    """If "de-CH" is installed, display name resolves via primary subtag "de"."""
    fake_engine = MagicMock()
    fake_engine.available_recognizer_languages = [_lang("de-CH")]
    with (
        patch.object(ocr_mod, "_winrt_available", True),
        patch.object(ocr_mod, "_OcrEngine", fake_engine),
    ):
        result = ocr_mod.get_available_languages()

    # de-CH has its own entry in _KNOWN_LANGUAGE_NAMES
    names = [name for name, _ in result]
    assert "Deutsch (Schweiz)" in names


def test_live_path_sorted_alphabetically():
    fake_engine = MagicMock()
    fake_engine.available_recognizer_languages = [
        _lang("ru"),    # Русский
        _lang("de"),    # Deutsch
        _lang("en"),    # English
        _lang("fr"),    # Français
    ]
    with (
        patch.object(ocr_mod, "_winrt_available", True),
        patch.object(ocr_mod, "_OcrEngine", fake_engine),
    ):
        result = ocr_mod.get_available_languages()

    names = [name for name, _ in result]
    assert names == sorted(names, key=str.casefold)


def test_live_path_no_duplicates():
    """Duplicate language tags (can happen with regional variants) are deduplicated."""
    fake_engine = MagicMock()
    fake_engine.available_recognizer_languages = [_lang("en"), _lang("en"), _lang("de")]
    with (
        patch.object(ocr_mod, "_winrt_available", True),
        patch.object(ocr_mod, "_OcrEngine", fake_engine),
    ):
        result = ocr_mod.get_available_languages()

    tags = [tag for _, tag in result]
    assert len(tags) == len(set(tags))


# ---------------------------------------------------------------------------
# Contract: return type is always list[tuple[str, str]]
# ---------------------------------------------------------------------------

def test_return_type_is_list_of_str_tuples_on_fallback():
    with patch.object(ocr_mod, "_winrt_available", False):
        result = ocr_mod.get_available_languages()
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, tuple)
        assert all(isinstance(s, str) for s in item)


def test_return_type_is_list_of_str_tuples_on_live():
    fake_engine = MagicMock()
    fake_engine.available_recognizer_languages = [_lang("en-US")]
    with (
        patch.object(ocr_mod, "_winrt_available", True),
        patch.object(ocr_mod, "_OcrEngine", fake_engine),
    ):
        result = ocr_mod.get_available_languages()
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, tuple)
        assert all(isinstance(s, str) for s in item)
