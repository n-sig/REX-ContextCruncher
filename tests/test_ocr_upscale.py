"""
Tests for ocr._upscale_for_ocr() — BUG-06.

Uses PIL directly; no WinRT or Windows APIs required.
"""

import sys
import types
import unittest.mock as mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Stub winrt modules so ocr.py imports cleanly on Linux
for mod_name in (
    "winrt",
    "winrt.windows",
    "winrt.windows.media",
    "winrt.windows.media.ocr",
    "winrt.windows.graphics",
    "winrt.windows.graphics.imaging",
    "winrt.windows.globalization",
    "winrt.windows.storage",
    "winrt.windows.storage.streams",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

from PIL import Image
import contextcruncher.ocr as ocr_mod

# Pull out the helpers and constants we want to test
_upscale_for_ocr = ocr_mod._upscale_for_ocr
_MIN_OCR_HEIGHT  = ocr_mod._MIN_OCR_HEIGHT   # 96 after fix
_OCR_PADDING     = ocr_mod._OCR_PADDING       # 24 after fix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solid(width: int, height: int, color=(255, 255, 255)) -> Image.Image:
    """Create a solid-colour RGB image for testing."""
    return Image.new("RGB", (width, height), color)


# ---------------------------------------------------------------------------
# Constants sanity check (documents the BUG-06 fix values)
# ---------------------------------------------------------------------------

def test_min_ocr_height_is_96():
    assert _MIN_OCR_HEIGHT == 96, (
        f"Expected 96 (BUG-06 fix), got {_MIN_OCR_HEIGHT}. "
        "Was the constant reverted?"
    )

def test_ocr_padding_is_24():
    assert _OCR_PADDING == 24, (
        f"Expected 24 (BUG-06 fix), got {_OCR_PADDING}. "
        "Was the constant reverted?"
    )


# ---------------------------------------------------------------------------
# Padding is always applied
# ---------------------------------------------------------------------------

def test_padding_applied_to_tiny_image():
    """Even a 1×1 image must receive padding on all four sides."""
    img = _solid(1, 1)
    out = _upscale_for_ocr(img)
    # At minimum the output must be larger than the input
    assert out.width  > 1
    assert out.height > 1

def test_padding_adds_2x_border_to_dimensions():
    """For an image that's already large enough, padding should add 2*_OCR_PADDING
    to each dimension (then no upscaling happens)."""
    # 200×200 is already > _MIN_OCR_HEIGHT after padding
    img = _solid(200, 200)
    out = _upscale_for_ocr(img)
    expected_w = 200 + 2 * _OCR_PADDING
    expected_h = 200 + 2 * _OCR_PADDING
    assert out.width  == expected_w
    assert out.height == expected_h

def test_padding_preserves_aspect_ratio_for_wide_image():
    """Wide images (e.g. a status-bar strip) must keep their aspect ratio
    after padding — no unexpected squashing."""
    img = _solid(300, 20)
    out = _upscale_for_ocr(img)
    # After padding: 348×68, still below MIN_OCR_HEIGHT → upscale
    # Aspect ratio of original padded image should be preserved within 5%
    padded_ratio = (300 + 2 * _OCR_PADDING) / (20  + 2 * _OCR_PADDING)
    out_ratio     = out.width / out.height
    assert abs(out_ratio - padded_ratio) / padded_ratio < 0.05


# ---------------------------------------------------------------------------
# Upscaling to MIN_OCR_HEIGHT
# ---------------------------------------------------------------------------

def test_tiny_image_reaches_min_height():
    """A 5×5 pixel capture must be upscaled to at least _MIN_OCR_HEIGHT."""
    img = _solid(5, 5)
    out = _upscale_for_ocr(img)
    assert out.height >= _MIN_OCR_HEIGHT

def test_single_row_image_reaches_min_height():
    """A 1-pixel-high strip (e.g. a separator line selection) must be upscaled."""
    img = _solid(400, 1)
    out = _upscale_for_ocr(img)
    assert out.height >= _MIN_OCR_HEIGHT

def test_image_just_below_threshold_is_upscaled():
    """An image whose padded height is 1 px below MIN_OCR_HEIGHT must be upscaled."""
    # Choose height so that (h + 2*_OCR_PADDING) == _MIN_OCR_HEIGHT - 1
    target_padded_h = _MIN_OCR_HEIGHT - 1
    h = max(1, target_padded_h - 2 * _OCR_PADDING)
    img = _solid(100, h)
    out = _upscale_for_ocr(img)
    assert out.height >= _MIN_OCR_HEIGHT

def test_image_at_threshold_is_not_upscaled():
    """If padded height == _MIN_OCR_HEIGHT exactly, no upscaling should occur."""
    target_padded_h = _MIN_OCR_HEIGHT
    h = target_padded_h - 2 * _OCR_PADDING
    if h < 1:
        pytest.skip("Padding alone already exceeds MIN_OCR_HEIGHT for this config")
    img = _solid(100, h)
    out = _upscale_for_ocr(img)
    # Padded: h + 2*_OCR_PADDING == _MIN_OCR_HEIGHT → no upscale
    assert out.height == _MIN_OCR_HEIGHT

def test_large_image_not_upscaled():
    """Images already larger than MIN_OCR_HEIGHT must not be upscaled —
    only padding is added."""
    img = _solid(800, 400)
    out = _upscale_for_ocr(img)
    assert out.height == 400 + 2 * _OCR_PADDING
    assert out.width  == 800 + 2 * _OCR_PADDING


# ---------------------------------------------------------------------------
# Output is always a valid PIL Image
# ---------------------------------------------------------------------------

def test_returns_pil_image():
    img = _solid(10, 10)
    out = _upscale_for_ocr(img)
    assert isinstance(out, Image.Image)

def test_output_mode_rgb():
    img = _solid(10, 10)
    out = _upscale_for_ocr(img)
    assert out.mode == "RGB"

def test_grayscale_input_works():
    img = Image.new("L", (10, 10), 128)
    out = _upscale_for_ocr(img)
    assert isinstance(out, Image.Image)
    assert out.height >= _MIN_OCR_HEIGHT
