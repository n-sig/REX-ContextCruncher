"""Tests for the normalize module — smart number formatting detection."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from contextcruncher.normalize import compact_variant


class TestCompactVariant:
    """compact_variant() should detect formatted numbers and strip separators."""

    # ----- Should produce a compact variant -----

    def test_credit_card_spaces(self):
        assert compact_variant("4532 1234 5678 9012") == "4532123456789012"

    def test_credit_card_dashes(self):
        assert compact_variant("4532-1234-5678-9012") == "4532123456789012"

    def test_iban(self):
        assert compact_variant("DE89 3704 0044 0532 0130 00") == "DE89370400440532013000"

    def test_phone_number_international(self):
        assert compact_variant("+49 176 123 456 78") == "+4917612345678"

    def test_phone_number_dashes(self):
        assert compact_variant("0176-123-456-78") == "017612345678"

    def test_date_dots(self):
        assert compact_variant("11.04.2026") == "11042026"

    def test_date_slashes(self):
        assert compact_variant("11/04/2026") == "11042026"

    def test_serial_number_mostly_letters(self):
        # 50% digits — below the 60% threshold, stays as-is.
        assert compact_variant("A1B2-C3D4-E5F6") is None

    def test_serial_number_mostly_digits(self):
        # e.g. "1234-5678-90AB" → 10/12 = 83% digits → compact.
        assert compact_variant("1234-5678-90AB") == "1234567890AB"

    # ----- Should return None (no compact needed) -----

    def test_normal_text(self):
        assert compact_variant("Hello World") is None

    def test_prose_with_numbers(self):
        assert compact_variant("Apartment 4B on Floor 12") is None

    def test_single_word(self):
        assert compact_variant("contextcruncher") is None

    def test_empty_string(self):
        assert compact_variant("") is None

    def test_multiline(self):
        assert compact_variant("4532 1234\n5678 9012") is None

    def test_already_compact(self):
        assert compact_variant("4532123456789012") is None
