"""Tests for exact Decimal persistence conversion."""

from decimal import Decimal
import unittest

from itca_training_centre.data.decimal_storage import (
    decimal_from_storage,
    decimal_to_storage,
)


class DecimalStorageTests(unittest.TestCase):
    def test_decimal_values_round_trip_exactly(self):
        values = [
            Decimal("0.1"),
            Decimal("1.25"),
            Decimal("75.50"),
            Decimal("99.99"),
        ]

        for value in values:
            with self.subTest(value=value):
                stored = decimal_to_storage(value)
                restored = decimal_from_storage(stored)

                self.assertIsInstance(stored, str)
                self.assertEqual(value, restored)

    def test_storage_uses_canonical_text(self):
        self.assertEqual("75.5", decimal_to_storage(Decimal("75.50")))
        self.assertEqual("1000", decimal_to_storage(Decimal("1000.00")))
        self.assertEqual("0", decimal_to_storage(Decimal("0.00")))

    def test_float_input_is_rejected(self):
        with self.assertRaises(TypeError):
            decimal_to_storage(0.1)

    def test_invalid_storage_text_is_rejected(self):
        for value in ["", "not-a-number", "NaN", "Infinity"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    decimal_from_storage(value)


if __name__ == "__main__":
    unittest.main()
