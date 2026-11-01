"""Pure, deterministic break-even calculations.

The module uses only the Python standard library and performs no I/O, so
identical inputs always produce identical outputs. Callers supply the cost
inputs and the explicit assumptions (selling price and expected yield); the
module never reads farm data.
"""

from decimal import Decimal, InvalidOperation

__all__ = ["BreakEvenError", "calculate_break_even"]


class BreakEvenError(ValueError):
    """Raised when break-even input is missing, malformed, or inconsistent."""


def _require_field(data, field):
    if not isinstance(data, dict):
        raise BreakEvenError("Input must be a mapping")
    if field not in data or data[field] is None:
        raise BreakEvenError(f"Missing required field: {field}")
    return data[field]


def _to_decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BreakEvenError(f"Invalid value for field: {field}") from exc
    if not result.is_finite():
        raise BreakEvenError(f"Invalid value for field: {field}")
    return result


def _require_non_negative(value, field):
    if value < 0:
        raise BreakEvenError(f"Field must not be negative: {field}")
    return value


def calculate_break_even(data):
    """Return break-even quantity, break-even price, and contribution margin.

    ``data`` must provide ``fixed_costs``, ``variable_cost_per_unit``,
    ``selling_price_per_unit``, and ``expected_yield``. Missing or ``None``
    fields raise :class:`BreakEvenError` naming the field instead of being
    treated as zero. The selling price must exceed the variable cost per
    unit, otherwise the assumptions are inconsistent and the calculation
    raises rather than dividing by zero or returning infinity.
    """
    fixed_costs = _require_non_negative(
        _to_decimal(_require_field(data, "fixed_costs"), "fixed_costs"),
        "fixed_costs",
    )
    variable_cost_per_unit = _require_non_negative(
        _to_decimal(
            _require_field(data, "variable_cost_per_unit"),
            "variable_cost_per_unit",
        ),
        "variable_cost_per_unit",
    )
    selling_price_per_unit = _require_non_negative(
        _to_decimal(
            _require_field(data, "selling_price_per_unit"),
            "selling_price_per_unit",
        ),
        "selling_price_per_unit",
    )
    expected_yield = _to_decimal(
        _require_field(data, "expected_yield"), "expected_yield"
    )
    if expected_yield <= 0:
        raise BreakEvenError(
            "Field must be greater than zero: expected_yield"
        )

    contribution_margin = selling_price_per_unit - variable_cost_per_unit
    if contribution_margin == 0:
        raise BreakEvenError(
            "Zero contribution margin: selling_price_per_unit equals "
            "variable_cost_per_unit, so break-even quantity cannot be "
            "calculated"
        )
    if contribution_margin < 0:
        raise BreakEvenError(
            "Inconsistent pricing and cost assumptions: "
            "selling_price_per_unit is below variable_cost_per_unit"
        )

    break_even_quantity = fixed_costs / contribution_margin
    break_even_price = variable_cost_per_unit + (
        fixed_costs / expected_yield
    )

    return {
        "break_even_quantity": break_even_quantity,
        "break_even_price": break_even_price,
        "contribution_margin": contribution_margin,
    }
