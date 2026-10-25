"""Pure, deterministic shared-cost allocation calculations.

The module uses only the Python standard library and performs no I/O, so
identical inputs always produce identical outputs. Callers supply the cost,
the targets, and the allocation basis; the module never reads farm data.

Supported bases:

``per_hectare``
    Each target receives a share proportional to its area. A zero-area
    target receives zero.

``per_cycle_share``
    The cost is split equally across all targets; area is ignored.

Each share is quantized to four decimal places and any rounding remainder
is added to the last participating target, so the returned amounts always
sum exactly to the requested cost. A "participating" target is the last
target with a positive area for ``per_hectare`` (so zero-area targets stay
at zero) or the last target overall for ``per_cycle_share``.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

__all__ = ["AllocationError", "allocate_shared_cost"]

PER_HECTARE = "per_hectare"
PER_CYCLE_SHARE = "per_cycle_share"
_BASES = (PER_HECTARE, PER_CYCLE_SHARE)
_QUANTUM = Decimal("0.0001")


class AllocationError(ValueError):
    """Raised when allocation input is missing, malformed, or inconsistent."""


def _to_decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AllocationError(f"Invalid value for {field}") from exc
    if not result.is_finite():
        raise AllocationError(f"Invalid value for {field}: must be finite")
    return result


def _validate_targets(targets):
    if not isinstance(targets, (list, tuple)):
        raise AllocationError("targets must be a list or tuple")
    if not targets:
        raise AllocationError("targets must not be empty")

    validated = []
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise AllocationError(
                f"Target at index {index} must be a mapping"
            )
        if "id" not in target or target["id"] is None:
            raise AllocationError(
                f"Target at index {index} is missing required field: id"
            )
        validated.append((target["id"], target))
    return validated


def _quantize(amount):
    return amount.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def allocate_shared_cost(cost, targets, basis):
    """Allocate ``cost`` across ``targets`` using ``basis``.

    ``targets`` is a list or tuple of mappings with an ``id``. For
    ``per_hectare`` each mapping also needs a non-negative ``area``; any
    extra keys are ignored. ``per_cycle_share`` ignores area entirely.

    The result is a list of ``{"id": ..., "amount": Decimal}`` entries in
    input order. Amounts are quantized to four decimal places and the
    rounding remainder goes to the last participating target, guaranteeing
    an exact Decimal sum equal to ``cost``. With a single target the whole
    cost is returned. Invalid input raises :class:`AllocationError`.
    """
    if basis not in _BASES:
        raise AllocationError(
            f"Unknown allocation basis: {basis!r}; "
            f"expected one of {', '.join(_BASES)}"
        )

    total_cost = _to_decimal(cost, "cost")
    if total_cost < 0:
        raise AllocationError("cost must not be negative")

    validated = _validate_targets(targets)

    if basis == PER_HECTARE:
        areas = []
        total_area = Decimal(0)
        for target_id, target in validated:
            if "area" not in target or target["area"] is None:
                raise AllocationError(
                    f"Target {target_id!r} is missing required field: area"
                )
            area = _to_decimal(target["area"], "area")
            if area < 0:
                raise AllocationError(
                    f"area must not be negative for target {target_id!r}"
                )
            areas.append(area)
            total_area += area
        if total_area <= 0:
            raise AllocationError(
                "Cannot allocate per hectare: total target area must be "
                "greater than zero"
            )
        raw_amounts = [
            total_cost * area / total_area for area in areas
        ]
        participating = [
            index for index, area in enumerate(areas) if area > 0
        ]
    else:
        share = total_cost / len(validated)
        raw_amounts = [share] * len(validated)
        participating = list(range(len(validated)))

    amounts = [_quantize(amount) for amount in raw_amounts]
    remainder = total_cost - sum(amounts, Decimal(0))
    if remainder != 0:
        amounts[participating[-1]] += remainder

    return [
        {"id": target_id, "amount": amount}
        for (target_id, _), amount in zip(validated, amounts)
    ]
