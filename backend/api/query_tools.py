"""Deterministic, read-only query tools for farm analysis."""

from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Q

from .allocation import AllocationError, allocate_shared_cost
from .models import (
    Activity,
    AllocationRule,
    CropCycle,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Field,
    InventoryItem,
    ReportingPeriod,
    Role,
    Sale,
)
from .profitability import ProfitabilityError, calculate_crop_cycle_profitability
from .serializers import as_date, as_id, as_number


_ALLOWED_ROLES = (Role.OWNER, Role.MANAGER)


def _error(code, message, evidence=None):
    result = {
        "status": "error",
        "error": {"code": code, "message": message},
    }
    if evidence is not None:
        result["evidence"] = evidence
    return result


def _missing(message, evidence):
    return {
        "status": "missing_data",
        "error": {"code": "missing_data", "message": message},
        "evidence": evidence,
    }


def _farm_for_user(user):
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or getattr(user, "role", None) not in _ALLOWED_ROLES
    ):
        return None, _error(
            "permission_denied",
            "Only authenticated farm owners and managers may use this tool.",
        )

    if user.role == Role.OWNER:
        try:
            return user.farm, None
        except (AttributeError, ObjectDoesNotExist):
            return None, _error(
                "farm_unavailable", "No farm is configured for this user."
            )

    farms = list(user.member_farms.all()[:2])
    if len(farms) == 1:
        return farms[0], None
    try:
        return user.farm, None
    except (AttributeError, ObjectDoesNotExist):
        return None, _error(
            "farm_unavailable",
            "A manager must belong to one farm or own a farm to use this tool.",
        )


def _parse_date(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        raise ValueError(f"{field} must be a date, not a datetime.")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO calendar date.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO calendar date.") from exc


def _resolve_period(farm, period_id=None, start_date=None, end_date=None):
    if period_id not in (None, ""):
        if start_date not in (None, "") or end_date not in (None, ""):
            raise ValueError("Use either period_id or start_date/end_date.")
        try:
            period = ReportingPeriod.objects.get(farm=farm, pk=period_id)
        except (
            ReportingPeriod.DoesNotExist,
            ValueError,
            ValidationError,
        ) as exc:
            raise ValueError("That reporting period does not exist.") from exc
        start, end = period.start_date, period.end_date
        label = period.name
        resolved_id = as_id(period.id)
    else:
        try:
            start = _parse_date(start_date, "start_date")
            end = _parse_date(end_date, "end_date")
        except ValueError:
            raise
        if (start is None) != (end is None):
            raise ValueError(
                "Provide both start_date and end_date, or neither."
            )
        if start is not None and end < start:
            raise ValueError("end_date must be on or after start_date.")
        label = (
            f"{as_date(start)} to {as_date(end)}"
            if start is not None
            else "all time"
        )
        resolved_id = None

    return {
        "id": resolved_id,
        "name": label,
        "startDate": as_date(start),
        "endDate": as_date(end),
    }, start, end


def _evidence(period, field=None, cycles=None, farm=None):
    result = {"period": period}
    if field is not None:
        result["field"] = {"id": as_id(field.id), "name": field.name}
    else:
        result["field"] = None
    if cycles is not None:
        result["cropCycles"] = [
            {
                "id": as_id(cycle.id),
                "fieldId": as_id(cycle.field_id),
                "fieldName": cycle.field.name,
                "cropId": as_id(cycle.crop_id),
                "cropName": cycle.crop.name,
            }
            for cycle in cycles
        ]
    else:
        result["cropCycles"] = []
    if farm is not None:
        result["farm"] = {"id": as_id(farm.id), "name": farm.name}
    return result


def _date_filter(queryset, start, end, field="date"):
    if start is not None:
        queryset = queryset.filter(**{f"{field}__gte": start})
    if end is not None:
        queryset = queryset.filter(**{f"{field}__lte": end})
    return queryset


def _get_cycle(farm, cycle_id):
    try:
        return (
            CropCycle.objects.select_related("field", "crop")
            .get(farm=farm, pk=cycle_id)
        )
    except (CropCycle.DoesNotExist, ValueError, ValidationError):
        return None


def _cost_inputs(farm, cycles, start, end):
    cycle_ids = {cycle.id for cycle in cycles}
    direct = {cycle_id: [] for cycle_id in cycle_ids}
    overheads = {cycle_id: [] for cycle_id in cycle_ids}
    recorded = {cycle_id: False for cycle_id in cycle_ids}

    expenses = _date_filter(
        Expense.objects.filter(
            farm=farm,
            cycle_id__in=cycle_ids,
            status=ExpenseStatus.POSTED,
        ),
        start,
        end,
    )
    for cycle_id, category, amount in expenses.values_list(
        "cycle_id", "category", "amount"
    ):
        recorded[cycle_id] = True
        (overheads if category == ExpenseCategory.OVERHEAD else direct)[
            cycle_id
        ].append(amount)

    shared = _date_filter(
        Expense.objects.filter(
            farm=farm,
            cycle__isnull=True,
            category=ExpenseCategory.OVERHEAD,
            status=ExpenseStatus.POSTED,
        ),
        start,
        end,
    ).order_by("date", "id")
    rules = list(AllocationRule.objects.filter(farm=farm))
    all_cycles = list(
        CropCycle.objects.filter(farm=farm).select_related("field")
    )

    for expense in shared:
        applicable = [
            rule
            for rule in rules
            if (rule.active_from is None or rule.active_from <= expense.date)
            and (rule.active_to is None or rule.active_to >= expense.date)
        ]
        if len(applicable) > 1:
            raise ValueError(
                "Multiple allocation rules apply to a shared expense."
            )
        if not applicable:
            raise ValueError(
                "No allocation rule applies to a shared expense."
            )
        targets = [
            cycle
            for cycle in all_cycles
            if cycle.start_date <= expense.date
            and (cycle.end_date is None or cycle.end_date >= expense.date)
        ]
        if not targets:
            raise ValueError(
                "No crop cycles are eligible for a shared expense."
            )
        try:
            shares = allocate_shared_cost(
                abs(expense.amount),
                [
                    {"id": cycle.id, "area": cycle.field.area}
                    for cycle in targets
                ],
                applicable[0].basis,
            )
        except AllocationError as exc:
            raise ValueError(f"Cannot allocate shared cost: {exc}") from exc
        sign = -1 if expense.amount < 0 else 1
        for share in shares:
            if share["id"] in cycle_ids:
                overheads[share["id"]].append(sign * share["amount"])
                recorded[share["id"]] = True

    return direct, overheads, recorded


def _cycle_figures(farm, cycles, start, end):
    direct, overheads, recorded = _cost_inputs(farm, cycles, start, end)
    revenue_by_cycle = {cycle.id: Decimal(0) for cycle in cycles}
    sales = _date_filter(
        Sale.objects.filter(
            farm=farm,
            harvest__cycle_id__in=revenue_by_cycle,
        ),
        start,
        end,
    )
    for cycle_id, revenue in sales.values_list("harvest__cycle_id", "revenue"):
        revenue_by_cycle[cycle_id] += revenue

    figures = {}
    for cycle in cycles:
        try:
            figures[cycle.id] = calculate_crop_cycle_profitability(
                {
                    "revenue": revenue_by_cycle[cycle.id],
                    "direct_costs": direct[cycle.id],
                    "allocated_overheads": overheads[cycle.id],
                }
            )
        except ProfitabilityError as exc:
            raise ValueError(str(exc)) from exc
    return figures, recorded


def _figures_payload(figures):
    return {
        "revenue": as_number(figures["revenue"]),
        "directCosts": as_number(figures["direct_costs"]),
        "allocatedOverheads": as_number(figures["allocated_overheads"]),
        "operatingSurplus": as_number(figures["operating_surplus"]),
        "resultAfterAllocatedOverheads": as_number(
            figures["result_after_allocated_overheads"]
        ),
    }


def _cost_payload(figures):
    return {
        "directCosts": as_number(figures["direct_costs"]),
        "allocatedOverheads": as_number(figures["allocated_overheads"]),
        "totalCosts": as_number(
            figures["direct_costs"] + figures["allocated_overheads"]
        ),
    }


def crop_cycle_costs(
    user,
    crop_cycle_id,
    *,
    period_id=None,
    start_date=None,
    end_date=None,
):
    """Return posted direct and allocated overhead costs for one crop cycle."""
    farm, denied = _farm_for_user(user)
    if denied:
        return denied
    try:
        period, start, end = _resolve_period(
            farm, period_id, start_date, end_date
        )
    except ValueError as exc:
        return _error("invalid_period", str(exc))

    cycle = _get_cycle(farm, crop_cycle_id)
    if cycle is None:
        return _error("not_found", "That crop cycle does not exist.")
    evidence = _evidence(period, cycles=[cycle], farm=farm)
    try:
        figures, recorded = _cycle_figures(farm, [cycle], start, end)
    except ValueError as exc:
        return _error("calculation_error", str(exc), evidence)
    if not recorded[cycle.id]:
        return _missing(
            "No posted cost records were found for this crop cycle and period.",
            evidence,
        )
    return {
        "status": "ok",
        "data": _cost_payload(figures[cycle.id]),
        "evidence": evidence,
    }


def field_profitability(
    user,
    field_id,
    *,
    period_id=None,
    start_date=None,
    end_date=None,
):
    """Return profitability for every crop cycle on a field in a period."""
    farm, denied = _farm_for_user(user)
    if denied:
        return denied
    try:
        period, start, end = _resolve_period(
            farm, period_id, start_date, end_date
        )
    except ValueError as exc:
        return _error("invalid_period", str(exc))
    try:
        field = Field.objects.get(farm=farm, pk=field_id)
    except (Field.DoesNotExist, ValueError, ValidationError):
        return _error("not_found", "That field does not exist.")

    cycles = CropCycle.objects.filter(farm=farm, field=field)
    if start is not None:
        cycles = cycles.filter(start_date__lte=end).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=start)
        )
    cycles = list(
        cycles.select_related("field", "crop").order_by("start_date", "id")
    )
    evidence = _evidence(period, field=field, cycles=cycles, farm=farm)
    if not cycles:
        return _missing(
            "No crop cycles for this field overlap the selected period.",
            evidence,
        )
    try:
        figures, recorded = _cycle_figures(farm, cycles, start, end)
    except ValueError as exc:
        return _error("calculation_error", str(exc), evidence)
    if not all(recorded[cycle.id] for cycle in cycles):
        return _missing(
            "One or more crop cycles have no posted cost records for this period.",
            evidence,
        )

    cycle_data = []
    totals = {
        key: Decimal(0)
        for key in (
            "revenue",
            "direct_costs",
            "allocated_overheads",
            "operating_surplus",
            "result_after_allocated_overheads",
        )
    }
    for cycle in cycles:
        result = figures[cycle.id]
        for key in totals:
            totals[key] += result[key]
        cycle_data.append(
            {
                "cropCycleId": as_id(cycle.id),
                "cropName": cycle.crop.name,
                "startDate": as_date(cycle.start_date),
                "endDate": as_date(cycle.end_date),
                **_figures_payload(result),
            }
        )
    return {
        "status": "ok",
        "data": {
            "fieldId": as_id(field.id),
            "fieldName": field.name,
            "cycles": cycle_data,
            **_figures_payload(totals),
        },
        "evidence": evidence,
    }


def inventory_position(
    user,
    *,
    period_id=None,
    start_date=None,
    end_date=None,
):
    """Return farm-wide inventory quantities as of the period end date."""
    farm, denied = _farm_for_user(user)
    if denied:
        return denied
    try:
        period, start, end = _resolve_period(
            farm, period_id, start_date, end_date
        )
    except ValueError as exc:
        return _error("invalid_period", str(exc))

    items = list(
        InventoryItem.objects.filter(farm=farm)
        .select_related("unit")
        .order_by("name", "id")
    )
    evidence = _evidence(period, farm=farm)
    evidence["scope"] = "farm-wide inventory"
    evidence["asOfDate"] = as_date(end) or "current"
    if not items:
        return _missing("No inventory records were found for this farm.", evidence)

    item_data = []
    for item in items:
        quantity = item.current_quantity(as_of_date=end)
        item_data.append(
            {
                "inventoryItemId": as_id(item.id),
                "name": item.name,
                "quantity": as_number(quantity),
                "unit": item.unit.name,
                "reorderLevel": as_number(item.reorder_level),
                "lowStock": (
                    item.reorder_level is not None
                    and quantity <= item.reorder_level
                ),
            }
        )

    return {
        "status": "ok",
        "data": {"items": item_data},
        "evidence": evidence,
    }


def activity_listing(
    user,
    *,
    period_id=None,
    start_date=None,
    end_date=None,
    field_id=None,
    crop_cycle_id=None,
):
    """Return read-only activity records for a farm and optional field/cycle."""
    farm, denied = _farm_for_user(user)
    if denied:
        return denied
    try:
        period, start, end = _resolve_period(
            farm, period_id, start_date, end_date
        )
    except ValueError as exc:
        return _error("invalid_period", str(exc))

    field = None
    if field_id not in (None, ""):
        try:
            field = Field.objects.get(farm=farm, pk=field_id)
        except (Field.DoesNotExist, ValueError, ValidationError):
            return _error("not_found", "That field does not exist.")

    cycle = None
    if crop_cycle_id not in (None, ""):
        cycle = _get_cycle(farm, crop_cycle_id)
        if cycle is None or (field is not None and cycle.field_id != field.id):
            return _error("not_found", "That crop cycle does not exist.")
        field = field or cycle.field

    queryset = Activity.objects.filter(farm=farm)
    if cycle is not None:
        queryset = queryset.filter(cycle=cycle)
    elif field is not None:
        queryset = queryset.filter(cycle__field=field)
    queryset = _date_filter(queryset, start, end, field="planned_date")
    activities = list(
        queryset.select_related("type", "cycle", "cycle__field", "cycle__crop")
        .order_by("planned_date", "id")
    )
    cycles = (
        [cycle]
        if cycle is not None
        else list(
            {activity.cycle_id: activity.cycle for activity in activities}.values()
        )
    )
    evidence = _evidence(period, field=field, cycles=cycles, farm=farm)
    if not activities:
        return _missing("No activities were found for this farm and period.", evidence)

    return {
        "status": "ok",
        "data": {
            "activities": [
                {
                    "activityId": as_id(activity.id),
                    "type": activity.type.name,
                    "status": activity.status,
                    "plannedDate": as_date(activity.planned_date),
                    "description": activity.description,
                    "labourHours": as_number(activity.labour_hours),
                    "equipment": activity.equipment,
                    "fieldId": as_id(activity.cycle.field_id),
                    "fieldName": activity.cycle.field.name,
                    "cropCycleId": as_id(activity.cycle_id),
                    "cropName": activity.cycle.crop.name,
                }
                for activity in activities
            ]
        },
        "evidence": evidence,
    }
