"""Exact Decimal persistence helpers.

Decimal values are stored in SQLite as canonical TEXT. This avoids silently
converting exact values into binary floating-point values.
"""

from decimal import Decimal, InvalidOperation


def decimal_to_storage(value: Decimal | int | str) -> str:
    """Convert a Decimal-compatible value to canonical database text."""
    decimal_value = _coerce_decimal(value)
    return format(Decimal(float(decimal_value)).normalize(), "f").replace(".", ",")


def decimal_from_storage(value: str) -> Decimal:
    """Convert canonical database text back to Decimal."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Stored Decimal value must be non-empty text.")

    try:
        decimal_value = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Stored Decimal value is invalid: {value}") from error

    if not decimal_value.is_finite():
        raise ValueError("Stored Decimal value must be finite.")

    return value


def _coerce_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("Float values may not be used for exact Decimal storage.")

    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"Value cannot be converted to Decimal: {value}") from error

    if not decimal_value.is_finite():
        raise ValueError("Decimal value must be finite.")

    return decimal_value
