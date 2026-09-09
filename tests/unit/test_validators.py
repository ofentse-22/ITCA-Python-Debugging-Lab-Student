"""Unit tests for shared input validators."""

from decimal import Decimal
import unittest

from itca_training_centre.utils.exceptions import ValidationError
from itca_training_centre.utils.validators import (
    normalize_decimal_value,
    normalize_fee_amount,
    normalize_iso_date,
    normalize_percentage_threshold,
)


class ValidatorHardeningTests(unittest.TestCase):
    def test_percentage_threshold_accepts_finite_boundary_values(self):
        self.assertEqual(0.0, normalize_percentage_threshold(" 0 "))
        self.assertEqual(50.0, normalize_percentage_threshold("5e1"))
        self.assertEqual(100.0, normalize_percentage_threshold(100))

    def test_percentage_threshold_rejects_nan_and_infinity(self):
        cases = (
            "NaN",
            "nan",
            "Infinity",
            "inf",
            "-Infinity",
            float("nan"),
            float("inf"),
            float("-inf"),
        )

        for value in cases:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "finite number"):
                    normalize_percentage_threshold(value)

    def test_iso_date_accepts_leap_years_and_rejects_ambiguous_dates(self):
        self.assertEqual(
            "2028-02-29",
            normalize_iso_date(" 2028-02-29 ", "Start date"),
        )

        cases = (
            "2026-02-29",
            "2026-13-01",
            "2026-01-00",
            "01/02/2026",
            "2026-9-1",
            "2026-09-01T00:00:00",
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "YYYY-MM-DD"):
                    normalize_iso_date(value, "Start date")

    def test_decimal_normalizers_accept_exact_values_and_reject_non_finite_values(self):
        self.assertEqual(Decimal("0.01"), normalize_decimal_value(" 0.01 ", "Mark"))
        self.assertEqual(Decimal("1.25"), normalize_decimal_value(Decimal("1.25"), "Mark"))
        self.assertEqual(Decimal("0"), normalize_fee_amount(None))

        for value in ("NaN", "sNaN", "Infinity", "-Infinity", Decimal("NaN")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "finite"):
                    normalize_decimal_value(value, "Mark")
                with self.assertRaisesRegex(ValidationError, "finite"):
                    normalize_fee_amount(value)


if __name__ == "__main__":
    unittest.main()
