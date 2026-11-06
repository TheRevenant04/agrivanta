from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Q
from rest_framework import status

from .allocation import AllocationError, allocate_shared_cost
from .dashboard import _resolve_filters
from .exceptions import ApiError
from .models import (
    AllocationRule,
    Budget,
    CropCycle,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
)
from .profitability import (
    ProfitabilityError,
    calculate_crop_cycle_profitability,
)
from .serializers import as_date, as_id, as_number


def _validate_budget_filter(farm, query_params):
    budget_id = query_params.get("budgetId")
    if budget_id in (None, ""):
        return None
    try:
        return Budget.objects.get(farm=farm, pk=budget_id)
    except (Budget.DoesNotExist, ValueError, ValidationError):
        raise ApiError(
            "That budget does not exist for this farm.",
            status.HTTP_400_BAD_REQUEST,
            "budgetId",
        )


def _overlapping_budgets(budgets, start_date, end_date):
    if start_date is not None:
        budgets = budgets.filter(
            Q(period_end__isnull=True) | Q(period_end__gte=start_date)
        )
    if end_date is not None:
        budgets = budgets.filter(
            Q(period_start__isnull=True) | Q(period_start__lte=end_date)
        )
    return budgets


def _budget_dates(budget, start_date, end_date):
    starts = [value for value in (budget.period_start, start_date) if value]
    ends = [value for value in (budget.period_end, end_date) if value]
    return (
        max(starts) if starts else None,
        min(ends) if ends else None,
    )


def _filter_expense_dates(expenses, start_date, end_date):
    if start_date is not None:
        expenses = expenses.filter(date__gte=start_date)
    if end_date is not None:
        expenses = expenses.filter(date__lte=end_date)
    return expenses


def _actual_cost(direct_costs, allocated_overheads):
    try:
        figures = calculate_crop_cycle_profitability(
            {
                "revenue": Decimal(0),
                "direct_costs": direct_costs,
                "allocated_overheads": allocated_overheads,
            }
        )
    except ProfitabilityError as exc:
        raise ApiError(
            f"Cannot calculate budget actuals: {exc}",
            status.HTTP_400_BAD_REQUEST,
            "actual",
        )
    return figures["direct_costs"] + figures["allocated_overheads"]


def _actual_for_budget(farm, budget, start_date, end_date):
    start_date, end_date = _budget_dates(budget, start_date, end_date)
    direct_costs = []
    allocated_overheads = []

    expenses = Expense.objects.filter(farm=farm, status=ExpenseStatus.POSTED)
    expenses = _filter_expense_dates(expenses, start_date, end_date)
    if budget.cycle_id is not None:
        expenses = expenses.filter(cycle_id=budget.cycle_id)
    if budget.category is not None:
        expenses = expenses.filter(category=budget.category)

    for category, amount in expenses.values_list("category", "amount"):
        if category == ExpenseCategory.OVERHEAD:
            allocated_overheads.append(amount)
        else:
            direct_costs.append(amount)

    if (
        budget.cycle_id is not None
        and budget.category in (None, ExpenseCategory.OVERHEAD)
    ):
        shared_expenses = _filter_expense_dates(
            Expense.objects.filter(
                farm=farm,
                cycle__isnull=True,
                category=ExpenseCategory.OVERHEAD,
                status=ExpenseStatus.POSTED,
            ).order_by("date", "id"),
            start_date,
            end_date,
        )
        all_cycles = list(
            CropCycle.objects.filter(farm=farm).select_related("field")
        )
        rules = list(AllocationRule.objects.filter(farm=farm))
        target_cycle = next(
            (cycle for cycle in all_cycles if cycle.id == budget.cycle_id),
            None,
        )
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
                cycle
                for cycle in all_cycles
                if cycle.start_date <= expense.date
                and (
                    cycle.end_date is None or cycle.end_date >= expense.date
                )
            ]
            if not targets or target_cycle not in targets:
                continue

            try:
                allocations = allocate_shared_cost(
                    abs(expense.amount),
                    [
                        {"id": cycle.id, "area": cycle.field.area}
                        for cycle in targets
                    ],
                    applicable_rules[0].basis,
                )
            except AllocationError as exc:
                raise ApiError(
                    f"Cannot allocate shared expense: {exc}",
                    status.HTTP_400_BAD_REQUEST,
                    "allocationRule",
                )
            share = next(
                allocation["amount"]
                for allocation in allocations
                if allocation["id"] == budget.cycle_id
            )
            allocated_overheads.append(
                -share if expense.amount < 0 else share
            )

    return _actual_cost(direct_costs, allocated_overheads)


def _variance_percentage(budget, actual):
    if budget == 0:
        return None
    return ((actual - budget) * Decimal(100) / budget).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _budget_line(farm, budget, start_date, end_date):
    actual = _actual_for_budget(farm, budget, start_date, end_date)
    variance = actual - budget.amount
    return {
        "budgetId": as_id(budget.id),
        "cycleId": as_id(budget.cycle_id) if budget.cycle_id else None,
        "category": budget.category,
        "budget": as_number(budget.amount),
        "actual": as_number(actual),
        "variance": as_number(variance),
        "variancePercentage": as_number(
            _variance_percentage(budget.amount, actual)
        ),
        "periodStart": as_date(budget.period_start),
        "periodEnd": as_date(budget.period_end),
    }


def budget_vs_actual_report(farm, query_params):
    filters = _resolve_filters(farm, query_params)
    selected_budget = _validate_budget_filter(farm, query_params)

    budgets = Budget.objects.filter(farm=farm).select_related("cycle")
    if filters["cycle"] is not None:
        budgets = budgets.filter(cycle=filters["cycle"])
    budgets = _overlapping_budgets(
        budgets, filters["start_date"], filters["end_date"]
    )
    if selected_budget is not None:
        budgets = budgets.filter(pk=selected_budget.pk)

    overall = []
    categories = []
    for budget in budgets.order_by("created_at", "id"):
        line = _budget_line(
            farm, budget, filters["start_date"], filters["end_date"]
        )
        (categories if budget.category is not None else overall).append(line)

    return {"overall": overall, "categories": categories}
