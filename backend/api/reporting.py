from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework import status

from .exceptions import ApiError
from .models import (
    CropCycle,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Harvest,
    Sale,
    Season,
)
from .profitability import (
    ProfitabilityError,
    calculate_crop_cycle_profitability,
)
from .serializers import as_date, as_id, as_number
from .views import _convert_quantity_between_units, aggregate_harvest_quantity_for_cycle


PROFITABILITY_GROUPINGS = ("crop_cycle", "field", "season", "farm")


def report_crop_cycle(farm, cycle):
    if cycle is None:
        raise ApiError("That crop cycle no longer exists.")
    # Check farm ownership - could be passed as id or instance
    cycle_farm_id = getattr(cycle, "farm_id", None)
    farm_id = getattr(farm, "id", farm)
    if cycle_farm_id != farm_id:
        raise ApiError("That crop cycle no longer exists.")
    try:
        cycle = CropCycle.objects.get(pk=getattr(cycle, "pk", cycle), farm=farm)
    except (CropCycle.DoesNotExist, ValueError, ValidationError):
        raise ApiError("That crop cycle no longer exists.")

    harvests = list(
        Harvest.objects.filter(farm=farm, cycle=cycle)
        .select_related("unit")
        .order_by("created_at", "id")
    )

    sales = list(
        Sale.objects.filter(farm=farm, harvest__cycle=cycle)
        .select_related("harvest", "harvest__unit")
        .order_by("created_at", "id")
    )

    if not harvests and not sales:
        return {
            "cycleId": str(cycle.id),
            "harvestedQuantity": Decimal(0),
            "soldQuantity": Decimal(0),
            "unsoldQuantity": Decimal(0),
            "revenue": Decimal(0),
            "unitId": None,
        }

    if harvests:
        total_harvested, unit = aggregate_harvest_quantity_for_cycle(farm, cycle)
    else:
        total_harvested = Decimal(0)
        unit = None

    if unit is None and harvests:
        unit = harvests[0].unit
    elif unit is None and sales:
        if sales and sales[0].harvest and sales[0].harvest.unit_id:
            unit = sales[0].harvest.unit
        else:
            return {
                "cycleId": str(cycle.id),
                "harvestedQuantity": Decimal(0),
                "soldQuantity": Decimal(0),
                "unsoldQuantity": Decimal(0),
                "revenue": Decimal(0),
                "unitId": None,
            }

    total_sold = Decimal(0)
    total_revenue = Decimal(0)
    for sale in sales:
        sold_converted = _convert_quantity_between_units(
            farm, sale.quantity, sale.harvest.unit, unit
        )
        total_sold += sold_converted
        total_revenue += sale.revenue

    if total_sold > total_harvested:
        raise ApiError(
            f"Stored sales exceed stored harvests for crop cycle {cycle.id}."
        )

    unsold_quantity = total_harvested - total_sold
    return {
        "cycleId": str(cycle.id),
        "harvestedQuantity": total_harvested,
        "soldQuantity": total_sold,
        "unsoldQuantity": unsold_quantity,
        "revenue": total_revenue,
        "unitId": str(unit.id) if unit is not None else None,
    }


def _normalize_group_by(group_by):
    grouping = str(group_by or "").strip().lower()
    if not grouping:
        grouping = "crop_cycle"
    if grouping not in PROFITABILITY_GROUPINGS:
        raise ApiError(
            "Unsupported grouping. Valid groupings are: "
            + ", ".join(PROFITABILITY_GROUPINGS)
            + ".",
            status.HTTP_400_BAD_REQUEST,
            "group_by",
        )
    return grouping


def _profitability_error_field(message):
    for field in ("revenue", "direct_costs", "allocated_overheads"):
        if field in message:
            return field
    return None


def _cycle_figures(farm, cycles):
    cycle_ids = [cycle.id for cycle in cycles]

    revenue_by_cycle = {cycle_id: Decimal(0) for cycle_id in cycle_ids}
    for cycle_id, revenue in Sale.objects.filter(
        farm=farm, harvest__cycle_id__in=cycle_ids
    ).values_list("harvest__cycle_id", "revenue"):
        revenue_by_cycle[cycle_id] += revenue

    direct_costs_by_cycle = {cycle_id: [] for cycle_id in cycle_ids}
    overheads_by_cycle = {cycle_id: [] for cycle_id in cycle_ids}
    for cycle_id, category, amount in Expense.objects.filter(
        farm=farm,
        cycle_id__in=cycle_ids,
        status=ExpenseStatus.POSTED,
    ).values_list("cycle_id", "category", "amount"):
        if category == ExpenseCategory.OVERHEAD:
            overheads_by_cycle[cycle_id].append(amount)
        else:
            direct_costs_by_cycle[cycle_id].append(amount)

    figures = {}
    for cycle in cycles:
        try:
            figures[cycle.id] = calculate_crop_cycle_profitability(
                {
                    "revenue": revenue_by_cycle[cycle.id],
                    "direct_costs": direct_costs_by_cycle[cycle.id],
                    "allocated_overheads": overheads_by_cycle[cycle.id],
                }
            )
        except ProfitabilityError as exc:
            message = str(exc)
            raise ApiError(
                message,
                status.HTTP_400_BAD_REQUEST,
                _profitability_error_field(message),
            )
    return figures


def _cycle_payload(cycle, figures):
    return {
        "cycleId": as_id(cycle.id),
        "fieldId": as_id(cycle.field_id),
        "fieldName": cycle.field.name,
        "cropId": as_id(cycle.crop_id),
        "cropName": cycle.crop.name,
        "startDate": as_date(cycle.start_date),
        "endDate": as_date(cycle.end_date),
        "revenue": as_number(figures["revenue"]),
        "directCosts": as_number(figures["direct_costs"]),
        "allocatedOverheads": as_number(figures["allocated_overheads"]),
        "operatingSurplus": as_number(figures["operating_surplus"]),
        "resultAfterAllocatedOverheads": as_number(
            figures["result_after_allocated_overheads"]
        ),
    }


def _sum_figures(figures):
    totals = {
        "revenue": Decimal(0),
        "direct_costs": Decimal(0),
        "allocated_overheads": Decimal(0),
        "operating_surplus": Decimal(0),
        "result_after_allocated_overheads": Decimal(0),
    }
    for figure in figures:
        for key in totals:
            totals[key] += figure[key]
    return totals


def _totals_payload(figures):
    totals = _sum_figures(figures)
    return {
        "revenue": as_number(totals["revenue"]),
        "directCosts": as_number(totals["direct_costs"]),
        "allocatedOverheads": as_number(totals["allocated_overheads"]),
        "operatingSurplus": as_number(totals["operating_surplus"]),
        "resultAfterAllocatedOverheads": as_number(
            totals["result_after_allocated_overheads"]
        ),
    }


def _group_by_field(cycles, figures, payloads):
    groups = {}
    for cycle in cycles:
        groups.setdefault(cycle.field_id, []).append(cycle)

    result = []
    for group_cycles in groups.values():
        first = group_cycles[0]
        item = {
            "fieldId": as_id(first.field_id),
            "fieldName": first.field.name,
            "cycleCount": len(group_cycles),
            "cycles": [payloads[cycle.id] for cycle in group_cycles],
        }
        item.update(
            _totals_payload([figures[cycle.id] for cycle in group_cycles])
        )
        result.append(item)
    return result


def _group_by_season(farm, cycles, figures, payloads):
    result = []
    for season in Season.objects.filter(farm=farm):
        overlapping = [
            cycle
            for cycle in cycles
            if cycle.start_date <= season.end_date
            and (
                cycle.end_date is None
                or cycle.end_date >= season.start_date
            )
        ]
        item = {
            "seasonId": as_id(season.id),
            "name": season.name,
            "startDate": as_date(season.start_date),
            "endDate": as_date(season.end_date),
            "cycles": [payloads[cycle.id] for cycle in overlapping],
        }
        item.update(
            _totals_payload([figures[cycle.id] for cycle in overlapping])
        )
        result.append(item)
    return result


def _group_by_farm(farm, cycles, figures, payloads):
    item = {
        "farmId": as_id(farm.id),
        "farmName": farm.name,
        "cycleCount": len(cycles),
        "cycles": [payloads[cycle.id] for cycle in cycles],
    }
    item.update(_totals_payload([figures[cycle.id] for cycle in cycles]))
    return [item]


def aggregate_profitability(farm, group_by=None):
    """Return farm-scoped profitability figures for the requested grouping.

    ORM revenue and expenses are assembled into the plain input structure
    expected by :func:`calculate_crop_cycle_profitability`; the arithmetic
    itself always comes from that module.
    """

    grouping = _normalize_group_by(group_by)
    cycles = list(
        CropCycle.objects.filter(farm=farm)
        .select_related("field", "crop")
        .order_by("start_date", "id")
    )
    if not cycles:
        return []

    figures = _cycle_figures(farm, cycles)
    payloads = {
        cycle.id: _cycle_payload(cycle, figures[cycle.id])
        for cycle in cycles
    }

    if grouping == "crop_cycle":
        return [payloads[cycle.id] for cycle in cycles]
    if grouping == "field":
        return _group_by_field(cycles, figures, payloads)
    if grouping == "season":
        return _group_by_season(farm, cycles, figures, payloads)
    return _group_by_farm(farm, cycles, figures, payloads)

