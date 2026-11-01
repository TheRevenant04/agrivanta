from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from .allocation import AllocationError, allocate_shared_cost
from .exceptions import ApiError
from .models import (
    Activity,
    ActivityStatus,
    AllocationRule,
    CropCycle,
    CycleStatus,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    InventoryItem,
    ReportingPeriod,
    Sale,
    StockMovement,
)
from .reporting import report_crop_cycle
from .serializers import as_number


def _parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ApiError(
            f"{field} must be a valid calendar date.",
            status.HTTP_400_BAD_REQUEST,
            field,
        )
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ApiError(
            f"{field} must be a valid calendar date.",
            status.HTTP_400_BAD_REQUEST,
            field,
        )


def _resolve_filters(farm, query_params):
    for key in ("farm", "farmId"):
        value = query_params.get(key)
        if value not in (None, "") and str(value) != str(farm.id):
            raise ApiError(
                "That farm does not exist.",
                status.HTTP_404_NOT_FOUND,
                key,
            )

    start_value = query_params.get("startDate")
    end_value = query_params.get("endDate")
    period_id = query_params.get("periodId")
    if period_id not in (None, ""):
        if start_value not in (None, "") or end_value not in (None, ""):
            raise ApiError(
                "Use either periodId or startDate and endDate, not both.",
                status.HTTP_400_BAD_REQUEST,
                "periodId",
            )
        try:
            period = ReportingPeriod.objects.get(farm=farm, pk=period_id)
        except (
            ReportingPeriod.DoesNotExist,
            ValueError,
            ValidationError,
        ):
            raise ApiError(
                "That reporting period does not exist for this farm.",
                status.HTTP_400_BAD_REQUEST,
                "periodId",
            )
        start_date = period.start_date
        end_date = period.end_date
    elif start_value not in (None, "") or end_value not in (None, ""):
        if start_value in (None, ""):
            raise ApiError(
                "startDate is required when endDate is provided.",
                status.HTTP_400_BAD_REQUEST,
                "startDate",
            )
        if end_value in (None, ""):
            raise ApiError(
                "endDate is required when startDate is provided.",
                status.HTTP_400_BAD_REQUEST,
                "endDate",
            )
        start_date = _parse_date(start_value, "startDate")
        end_date = _parse_date(end_value, "endDate")
        if end_date < start_date:
            raise ApiError(
                "endDate must be on or after startDate.",
                status.HTTP_400_BAD_REQUEST,
                "endDate",
            )
    else:
        start_date = None
        end_date = None

    cycle_id = query_params.get("cycleId")
    cycle = None
    if cycle_id not in (None, ""):
        try:
            cycle = CropCycle.objects.get(farm=farm, pk=cycle_id)
        except (CropCycle.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "That crop cycle does not exist for this farm.",
                status.HTTP_400_BAD_REQUEST,
                "cycleId",
            )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "cycle": cycle,
    }


def _selected_cycles(farm, start_date, end_date, cycle, today):
    if cycle is not None:
        return [cycle]

    cycles = CropCycle.objects.filter(farm=farm)
    if start_date is not None:
        cycles = cycles.filter(start_date__lte=end_date).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=start_date)
        )
    else:
        cycles = cycles.filter(
            status=CycleStatus.OPEN,
            start_date__lte=today,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))

    return list(
        cycles.select_related("field", "crop", "variety").order_by(
            "start_date", "id"
        )
    )


def _date_filter(queryset, start_date, end_date):
    if start_date is not None:
        queryset = queryset.filter(date__gte=start_date)
    if end_date is not None:
        queryset = queryset.filter(date__lte=end_date)
    return queryset


def _cycle_spend(farm, cycles, start_date, end_date):
    cycle_ids = {cycle.id for cycle in cycles}
    if not cycle_ids:
        return Decimal(0)

    expenses = _date_filter(
        Expense.objects.filter(
            farm=farm,
            cycle_id__in=cycle_ids,
            status=ExpenseStatus.POSTED,
        ),
        start_date,
        end_date,
    )
    spend = sum(expenses.values_list("amount", flat=True), Decimal(0))

    shared_expenses = _date_filter(
        Expense.objects.filter(
            farm=farm,
            cycle__isnull=True,
            category=ExpenseCategory.OVERHEAD,
            status=ExpenseStatus.POSTED,
        ),
        start_date,
        end_date,
    ).order_by("date", "id")
    all_cycles = list(
        CropCycle.objects.filter(farm=farm).select_related("field")
    )
    rules = list(AllocationRule.objects.filter(farm=farm))

    for expense in shared_expenses:
        applicable_rules = [
            rule
            for rule in rules
            if (rule.active_from is None or rule.active_from <= expense.date)
            and (rule.active_to is None or rule.active_to >= expense.date)
        ]
        if not applicable_rules:
            continue
        if len(applicable_rules) > 1:
            raise ApiError(
                "More than one allocation rule is active for a shared "
                f"expense dated {expense.date}.",
                status.HTTP_400_BAD_REQUEST,
                "allocationRule",
            )

        targets = [
            target
            for target in all_cycles
            if target.start_date <= expense.date
            and (
                target.end_date is None
                or target.end_date >= expense.date
            )
        ]
        if not targets:
            continue
        rule = applicable_rules[0]
        allocation_targets = [
            {
                "id": target.id,
                "area": target.field.area,
            }
            for target in targets
        ]
        try:
            allocations = allocate_shared_cost(
                expense.amount,
                allocation_targets,
                rule.basis,
            )
        except AllocationError as exc:
            raise ApiError(
                f"Cannot allocate shared expense: {exc}",
                status.HTTP_400_BAD_REQUEST,
                "allocationRule",
            )
        spend += sum(
            (
                allocation["amount"]
                for allocation in allocations
                if allocation["id"] in cycle_ids
            ),
            Decimal(0),
        )

    return spend


def _revenue_to_date(farm, cycles, start_date, end_date):
    cycle_ids = [cycle.id for cycle in cycles]
    if not cycle_ids:
        return Decimal(0)
    sales = _date_filter(
        Sale.objects.filter(
            farm=farm,
            harvest__cycle_id__in=cycle_ids,
        ),
        start_date,
        end_date,
    )
    return sum(sales.values_list("revenue", flat=True), Decimal(0))


def _unsold_produce(farm, cycles, as_of):
    unsold = []
    for cycle in cycles:
        figures = report_crop_cycle(farm, cycle, through_date=as_of)
        if figures["unsoldQuantity"] == 0:
            continue
        unsold.append(
            {
                "cycleId": str(cycle.id),
                "quantity": as_number(figures["unsoldQuantity"]),
                "unitId": figures["unitId"],
            }
        )
    return unsold


def _activity_counts(farm, cycles, start_date, end_date, today):
    cycle_ids = [cycle.id for cycle in cycles]
    if not cycle_ids:
        return 0, 0
    activities = Activity.objects.filter(
        farm=farm,
        cycle_id__in=cycle_ids,
    )
    if start_date is not None:
        activities = activities.filter(planned_date__gte=start_date)
    if end_date is not None:
        activities = activities.filter(planned_date__lte=end_date)

    active_statuses = (ActivityStatus.PLANNED, ActivityStatus.IN_PROGRESS)
    upcoming = activities.filter(
        status__in=active_statuses,
        planned_date__gte=today,
    ).count()
    overdue = activities.filter(
        Q(status=ActivityStatus.OVERDUE)
        | Q(
            status__in=active_statuses,
            planned_date__lt=today,
        )
    ).count()
    return upcoming, overdue


def _low_stock_count(farm, as_of_date=None):
    if as_of_date is not None and StockMovement.objects.filter(
        farm=farm,
        date__isnull=True,
    ).exists():
        raise ApiError(
            "Cannot calculate historical low-stock count because a stock "
            "movement has no date.",
            status.HTTP_400_BAD_REQUEST,
            "stockMovements",
        )
    items = InventoryItem.objects.filter(farm=farm).prefetch_related(
        "movements"
    )
    return sum(
        item.current_quantity(as_of_date) <= item.reorder_level
        for item in items
    )


def build_dashboard(
    farm,
    *,
    start_date=None,
    end_date=None,
    cycle=None,
    today=None,
):
    """Build read-only, farm-scoped dashboard KPIs for the selected window."""
    today = today or timezone.localdate()
    cycles = _selected_cycles(farm, start_date, end_date, cycle, today)
    as_of = end_date or today
    upcoming, overdue = _activity_counts(
        farm, cycles, start_date, end_date, today
    )
    return {
        "currentCycleSpend": as_number(
            _cycle_spend(farm, cycles, start_date, as_of)
        ),
        "revenueToDate": as_number(
            _revenue_to_date(farm, cycles, start_date, as_of)
        ),
        "unsoldProduce": _unsold_produce(farm, cycles, as_of),
        "upcomingActivities": upcoming,
        "overdueActivities": overdue,
        "lowStockItemCount": _low_stock_count(farm, end_date),
    }


def dashboard_for_request(farm, query_params):
    filters = _resolve_filters(farm, query_params)
    return build_dashboard(farm, **filters)
