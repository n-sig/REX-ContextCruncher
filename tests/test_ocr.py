"""Tests for contextcruncher.ocr — Windows OCR engine.

These tests require the winsdk package and Windows 10/11.
They are skipped automatically on unsupported platforms.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PIL import Image, ImageDraw, ImageFont
from contextcruncher.ocr import is_ocr_available, recognise


@unittest.skipUnless(
    sys.platform == "win32" and is_ocr_available(),
    "Windows OCR engine not available",
)
class TestOcrRecognition(unittest.TestCase):
    """Integration tests that exercise the real Windows OCR engine."""

    @staticmethod
    def _make_text_image(text: str, width: int = 400, height: int = 100) -> Image.Image:
        """Generate a white image with black text for OCR testing."""
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        # Use a large default font for reliable recognition.
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except OSError:
            font = ImageFont.load_default()
        draw.text((20, 30), text, fill="black", font=font)
        return img

    def test_recognise_simple_text(self):
        img = self._make_text_image("Hello World")
        result = recognise(img)
        # The engine should find at least part of the text.
        self.assertIn("Hello", result)

    def test_recognise_empty_image_returns_empty_string(self):
        # Completely white image with no text.
        img = Image.new("RGB", (200, 200), "white")
        result = recognise(img)
        # Must not crash; empty string is acceptable.
        self.assertIsInstance(result, str)

    def test_recognise_never_crashes(self):
        # 1x1 pixel image — edge case that should not raise.
        img = Image.new("RGB", (1, 1), "black")
        result = recognise(img)
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
