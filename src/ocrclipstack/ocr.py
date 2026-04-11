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
# Language selection
# ---------------------------------------------------------------------------

def _pick_language():
    """Choose the best available OCR language, preferring EU languages."""
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

    # Walk the priority list and return the first match.
    for tag in _EU_LANGUAGE_PRIORITY:
        if tag in by_tag:
            return by_tag[tag]

    # Fallback: English (broad match) → first available → None.
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
_MIN_OCR_HEIGHT = 64


def _upscale_for_ocr(image: Image) -> Image:
    """Return *image* padded and scaled up if its height is below *_MIN_OCR_HEIGHT*."""
    # Synthetic padding: Add a solid border using the color from the top-left pixel.
    # This gives the OCR engine the required empty space around characters
    # without accidentally reading neighboring text from the physical screen.
    bg_color = image.getpixel((0, 0))
    # Some images might be 'P' or 'L' mode, getpixel returns int instead of tuple.
    # ImageOps.expand works fine either way.
    image = ImageOps.expand(image, border=10, fill=bg_color)

    w, h = image.size
    if h >= _MIN_OCR_HEIGHT:
        return image
    scale = _MIN_OCR_HEIGHT / h
    # Use LANCZOS for high-quality upscale.
    new_w = max(int(w * scale), 1)
    new_h = max(int(h * scale), _MIN_OCR_HEIGHT)
    return image.resize((new_w, new_h), resample=3)  # 3 = LANCZOS


async def _recognise_async(image: Image) -> str:
    """Run OCR on *image* and return the recognised text."""
    lang = _pick_language()
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


def recognise(image: Image) -> str:
    """Synchronous wrapper — run OCR on a PIL Image and return the text.

    Returns an empty string on any error (no crash).
    """
    if not _winrt_available:
        return ""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_recognise_async(image))
        finally:
            loop.close()
    except Exception:
        return ""
