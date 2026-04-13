"""
OCR module — uses the native Windows Media OCR engine via winsdk/winrt.

No network access. Images are processed entirely on-device.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

from PIL import ImageOps

# Priority list of EU language tags to prefer during auto-selection.
_EU_LANGUAGE_PRIORITY = [
    "de", "en", "fr", "es", "it", "pl", "nl", "pt",
]

# ---------------------------------------------------------------------------
# WinRT imports — guarded so the rest of the app can still load on
# unsupported systems (the main module will show a friendly error).
# ---------------------------------------------------------------------------
_winrt_available = False
_OcrEngine = None
_SoftwareBitmap = None
_BitmapPixelFormat = None
_BitmapAlphaMode = None
_Language = None

try:
    from winrt.windows.media.ocr import OcrEngine as _OcrEngine
    from winrt.windows.graphics.imaging import (
        SoftwareBitmap as _SoftwareBitmap,
        BitmapPixelFormat as _BitmapPixelFormat,
        BitmapAlphaMode as _BitmapAlphaMode,
    )
    from winrt.windows.globalization import Language as _Language
    _winrt_available = True
except ImportError:
    pass


def is_ocr_available() -> bool:
    """Return True if the Windows OCR engine is accessible."""
    return _winrt_available


# ---------------------------------------------------------------------------
# Human-readable names for common BCP-47 tags shown in the Settings UI.
# The list is intentionally broad — any tag not found here falls back to
# the raw tag string (e.g. "zh-Hant-TW").
# ---------------------------------------------------------------------------
_KNOWN_LANGUAGE_NAMES: dict[str, str] = {
    # Germanic
    "de": "Deutsch",          "de-de": "Deutsch (Deutschland)",
    "de-at": "Deutsch (Österreich)", "de-ch": "Deutsch (Schweiz)",
    "en": "English",          "en-us": "English (US)",
    "en-gb": "English (UK)",  "en-au": "English (Australia)",
    "nl": "Nederlands",       "nl-nl": "Nederlands (Nederland)",
    "nl-be": "Nederlands (België)",
    "sv": "Svenska",          "da": "Dansk",
    "nb": "Norsk Bokmål",     "nn": "Norsk Nynorsk",
    "fi": "Suomi",            "is": "Íslenska",
    # Romance
    "fr": "Français",         "fr-fr": "Français (France)",
    "fr-be": "Français (Belgique)", "fr-ch": "Français (Suisse)",
    "es": "Español",          "es-es": "Español (España)",
    "es-mx": "Español (México)",
    "it": "Italiano",         "it-it": "Italiano (Italia)",
    "pt": "Português",        "pt-br": "Português (Brasil)",
    "pt-pt": "Português (Portugal)",
    "ro": "Română",           "ca": "Català",
    # Slavic
    "pl": "Polski",           "cs": "Čeština",
    "sk": "Slovenčina",       "sl": "Slovenščina",
    "hr": "Hrvatski",         "bs": "Bosanski",
    "sr": "Српски",           "bg": "Български",
    "ru": "Русский",          "uk": "Українська",
    "be": "Беларуская",
    # Other European
    "el": "Ελληνικά",         "hu": "Magyar",
    "lt": "Lietuvių",         "lv": "Latviešu",
    "et": "Eesti",
    # Asian
    "zh-hans": "中文 (简体)",  "zh-hant": "中文 (繁體)",
    "zh-cn":   "中文 (中国)", "zh-tw": "中文 (台灣)",
    "ja": "日本語",           "ko": "한국어",
    "th": "ไทย",              "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",  "ms": "Bahasa Melayu",
    # Middle-East / Africa
    "ar": "العربية",           "he": "עברית",
    "fa": "فارسی",             "tr": "Türkçe",
}


def get_available_languages() -> list[tuple[str, str]]:
    """Return installed OCR language packs as ``[(display_name, bcp47_tag), …]``.

    Queries ``OcrEngine.available_recognizer_languages`` so only language
    packs actually installed on the current Windows system are returned.

    The list is sorted alphabetically by display name and is safe to use
    directly as options for a Tkinter OptionMenu.

    Falls back to a minimal static list when WinRT is unavailable (e.g. on
    Linux CI or unsupported Windows versions) so the Settings dialog can
    still be shown.
    """
    if not _winrt_available or _OcrEngine is None:
        # Minimal fallback — keeps the Settings dialog functional
        return [
            ("Deutsch", "de"),
            ("English", "en"),
            ("Español", "es"),
            ("Français", "fr"),
            ("Italiano", "it"),
            ("Polski", "pl"),
            ("Português", "pt"),
        ]

    result: list[tuple[str, str]] = []
    for lang in _OcrEngine.available_recognizer_languages:
        tag: str = lang.language_tag          # BCP-47, e.g. "de-DE"
        tag_lower = tag.lower()

        # Look up a friendly display name, trying full tag first then primary subtag.
        display = (
            _KNOWN_LANGUAGE_NAMES.get(tag_lower)
            or _KNOWN_LANGUAGE_NAMES.get(tag_lower.split("-")[0])
            or tag          # raw tag as last resort (e.g. "yue-Hant")
        )
        result.append((display, tag))

    # Sort alphabetically by display name; deduplicate by tag just in case.
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for item in sorted(result, key=lambda x: x[0].casefold()):
        if item[1] not in seen:
            seen.add(item[1])
            unique.append(item)

    return unique


# ---------------------------------------------------------------------------
# Language selection
# ---------------------------------------------------------------------------

def _pick_language(preferred: str | None = None):
    """Choose the best available OCR language.

    FIX (Bug #7): *preferred* is now honoured.  Pass the value of
    ``config["ocr_language"]``; ``"auto"`` or ``None`` falls back to the
    EU-priority list as before.
    """
    available = _OcrEngine.available_recognizer_languages
    # Build a tag→Language lookup (lowercase tags).
    by_tag: dict[str, object] = {}
    for lang in available:
        tag = lang.language_tag.lower()
        by_tag[tag] = lang
        # Also store the primary subtag (e.g. "de" from "de-DE").
        primary = tag.split("-")[0]
        if primary not in by_tag:
            by_tag[primary] = lang

    # Honour user preference when explicitly set (not "auto" / empty).
    if preferred and preferred.lower() not in ("auto", ""):
        key = preferred.lower()
        if key in by_tag:
            return by_tag[key]
        # Try primary subtag (e.g. "de" if user set "de-DE").
        primary = key.split("-")[0]
        if primary in by_tag:
            return by_tag[primary]

    # Fall back to EU priority list.
    for tag in _EU_LANGUAGE_PRIORITY:
        if tag in by_tag:
            return by_tag[tag]

    # Last resort: English → first available → None.
    if "en" in by_tag:
        return by_tag["en"]
    if available:
        return available[0]
    return None


# ---------------------------------------------------------------------------
# Core OCR function
# ---------------------------------------------------------------------------

def _pil_to_software_bitmap(image: Image):
    """Convert a PIL Image to a WinRT SoftwareBitmap (BGRA8, pre-multiplied).
    
    Uses NumPy for fast RGBA→BGRA channel swap (10x faster than pure Python loop).
    """
    import numpy as np

    rgba = image.convert("RGBA")
    width, height = rgba.size

    # NumPy vectorized RGBA → BGRA channel swap
    arr = np.array(rgba)                    # shape: (H, W, 4) — R, G, B, A
    bgra_arr = arr[:, :, [2, 1, 0, 3]]     # Swap R↔B channels
    bgra = bgra_arr.tobytes()

    bitmap = _SoftwareBitmap.create_copy_from_buffer(
        bgra,
        _BitmapPixelFormat.BGRA8,
        width,
        height
    )
    return bitmap


# Minimum pixel height for reliable OCR results. Smaller images are
# upscaled proportionally so the Windows engine can find glyphs.
#
# BUG-06 fix: raised from 64 → 96.
# Windows OCR targets ~12 pt text at 96 DPI (≈ 16 px).  At 64 px the
# engine barely has one baseline worth of context; at 96 px recognition
# rates improve noticeably for single-line captures.
_MIN_OCR_HEIGHT = 96

# Padding added around every captured image before OCR.
#
# BUG-06 fix: raised from 10 → 24 px.
# The OCR engine needs a blank margin around glyphs to avoid reading
# screen content that "bleeds in" at the capture boundary.  10 px was
# too tight for small selections (tooltips, status-bar labels); 24 px
# gives reliable isolation while staying within the 20–30 px sweet-spot
# described in the Windows OCR documentation.
_OCR_PADDING = 24


def _upscale_for_ocr(image: Image) -> Image:
    """Return *image* padded and upscaled to meet the OCR engine's minimum size.

    Steps
    -----
    1. Add *_OCR_PADDING* px of solid border (colour sampled from the
       top-left pixel) to isolate the capture from surrounding screen content.
    2. If the padded height is still below *_MIN_OCR_HEIGHT*, upscale
       proportionally using LANCZOS so the engine always receives at least
       *_MIN_OCR_HEIGHT* px of image data.
    """
    # Synthetic padding — sample background colour from the top-left pixel.
    # ImageOps.expand handles all PIL image modes (RGB, L, P, RGBA, …).
    bg_color = image.getpixel((0, 0))
    image = ImageOps.expand(image, border=_OCR_PADDING, fill=bg_color)

    w, h = image.size
    if h >= _MIN_OCR_HEIGHT:
        return image

    scale = _MIN_OCR_HEIGHT / h
    new_w = max(int(w * scale), 1)
    new_h = max(int(h * scale), _MIN_OCR_HEIGHT)
    # LANCZOS (resample=3) gives the best quality for upscaling text.
    return image.resize((new_w, new_h), resample=3)


async def _recognise_async(image: Image, language: str = "auto") -> str:
    """Run OCR on *image* and return the recognised text."""
    lang = _pick_language(preferred=language)
    if lang is not None:
        engine = _OcrEngine.try_create_from_language(lang)
    else:
        engine = _OcrEngine.try_create_from_user_profile_languages()

    if engine is None:
        return ""

    # Upscale tiny captures so the OCR engine has enough pixels to work with.
    image = _upscale_for_ocr(image)
    bitmap = _pil_to_software_bitmap(image)
    result = await engine.recognize_async(bitmap)

    if result is None:
        return ""

    lines = [line.text for line in result.lines]
    cleaned = "\n".join(l.strip() for l in lines if l.strip())

    # Fix common misrecognitions from programming fonts (slashed/dotted zeroes).
    cleaned = cleaned.replace("ø", "0").replace("Ø", "0")
    # Sometimes '0' is misread as 'e' inside numbers (like '2e26' instead of '2026').
    cleaned = re.sub(r"(?<=\d)e(?=\d)", "0", cleaned)
    # Strip any stray bullet points or UI artifact lines at the start of the string.
    cleaned = re.sub(r"^[\u2022\u00B7\-|*>]\s*", "", cleaned)

    return cleaned


def recognise(image: Image, language: str = "auto") -> str:
    """Synchronous wrapper — run OCR on a PIL Image and return the text.

    *language* is a BCP-47 tag (e.g. ``"de"``, ``"en-US"``) or ``"auto"``
    to use the EU-priority heuristic.  Defaults to ``"auto"`` for backward
    compatibility.

    Returns an empty string on any error (no crash).
    """
    if not _winrt_available:
        return ""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_recognise_async(image, language=language))
        finally:
            loop.close()
    except Exception:
        return ""
