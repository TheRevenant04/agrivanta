"""Pure, deterministic crop-cycle profitability calculations.

The module uses only the Python standard library and performs no I/O, so
identical inputs always produce identical outputs.
"""

from decimal import Decimal, InvalidOperation


class ProfitabilityError(ValueError):
    """Raised when profitability input is missing or malformed."""


def _require_field(data, field):
    if not isinstance(data, dict):
        raise ProfitabilityError("Input must be a mapping")
    if field not in data or data[field] is None:
        raise ProfitabilityError(f"Missing required field: {field}")
    return data[field]


def _to_decimal(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProfitabilityError(f"Invalid value for field: {field}") from exc


def _sum_collection(value, field):
    if not isinstance(value, (list, tuple)):
        raise ProfitabilityError(f"Field must be a collection: {field}")
    total = Decimal(0)
    for item in value:
        if item is None:
            raise ProfitabilityError(f"Invalid value for field: {field}")
        total += _to_decimal(item, field)
    return total


def calculate_crop_cycle_profitability(data):
    """Return revenue, cost totals, operating surplus, and final result.

    ``direct_costs`` and ``allocated_overheads`` must be collections of
    numeric values; empty collections sum to zero. Missing or ``None``
    fields raise :class:`ProfitabilityError` instead of being treated as
    zero. Negative results are returned unchanged.
    """
    revenue = _to_decimal(_require_field(data, "revenue"), "revenue")
    direct_costs = _sum_collection(
        _require_field(data, "direct_costs"), "direct_costs"
    )
    allocated_overheads = _sum_collection(
        _require_field(data, "allocated_overheads"), "allocated_overheads"
    )

    operating_surplus = revenue - direct_costs
    result_after_allocated_overheads = operating_surplus - allocated_overheads

    return {
        "revenue": revenue,
        "direct_costs": direct_costs,
        "allocated_overheads": allocated_overheads,
        "operating_surplus": operating_surplus,
        "result_after_allocated_overheads": result_after_allocated_overheads,
    }
