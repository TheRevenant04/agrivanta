import logging
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from config.celery import app
from api.models import (
    Activity,
    ActivityStatus,
    Budget,
    CropCycle,
    Expense,
    ExpenseStatus,
    Farm,
    InventoryItem,
    Notification,
    NotificationType,
    User,
)

logger = logging.getLogger(__name__)


@app.task
def check_overdue_activities():
    """
    Check for overdue activities and create notifications.

    An activity is considered overdue if:
    - Status is PLANNED or IN_PROGRESS
    - planned_date is before today
    """
    try:
        today = date.today()
        overdue_activities = Activity.objects.filter(
            Q(status=ActivityStatus.PLANNED)
            | Q(status=ActivityStatus.IN_PROGRESS),
            planned_date__lt=today,
        ).select_related("farm", "farm__owner")

        for activity in overdue_activities:
            _create_overdue_activity_notification(activity)
    except Exception as e:
        logger.error(f"Error checking overdue activities: {e}", exc_info=True)


@app.task
def check_low_stock():
    """
    Check inventory items below reorder level and create notifications.

    Compares current quantity (from stock movements) against reorder_level.
    Creates one notification per item per farm owner.
    """
    try:
        farms = Farm.objects.prefetch_related("inventory_items").all()

        for farm in farms:
            for item in farm.inventory_items.all():
                current_qty = item.current_quantity()
                if current_qty < item.reorder_level:
                    _create_low_stock_notification(farm, item)
    except Exception as e:
        logger.error(f"Error checking low stock: {e}", exc_info=True)


@app.task
def check_budget_overruns():
    """
    Check for budget overruns and create notifications.

    Compares budget amount against actual spend (posted expenses) for the scope.
    Scope is determined by: cycle (if set) + category (if set) + period.
    """
    try:
        budgets = Budget.objects.all()

        for budget in budgets:
            actual_spend = _calculate_actual_spend(budget)
            if actual_spend > budget.amount:
                _create_budget_overrun_notification(budget)
    except Exception as e:
        logger.error(f"Error checking budget overruns: {e}", exc_info=True)


def _create_overdue_activity_notification(activity):
    """
    Create a notification for an overdue activity.

    Deduplication: check if a notification already exists for this specific activity.
    Uses activity ID in deduplication key to allow multiple activities of same type.
    Notify the farm owner.
    """
    farm = activity.farm
    user = farm.owner

    existing = Notification.objects.filter(
        user=user,
        type=NotificationType.ALERT,
        message__contains=f"Activity (ID: {activity.id})",
    ).exists()

    if not existing:
        message = (
            f"Activity (ID: {activity.id}) '{activity.type.name}' scheduled for "
            f"{activity.planned_date} is overdue."
        )
        Notification.objects.create(
            user=user,
            type=NotificationType.ALERT,
            message=message,
        )



def _create_low_stock_notification(farm, item):
    """
    Create a notification for low stock item.

    Deduplication: check if a notification already exists for this specific item.
    Uses item ID in deduplication key to allow multiple items with overlapping names.
    Notify the farm owner.
    """
    user = farm.owner
    existing = Notification.objects.filter(
        user=user,
        type=NotificationType.WARNING,
        message__contains=f"Item (ID: {item.id})",
    ).exists()

    if not existing:
        current_qty = item.current_quantity()
        message = (
            f"Inventory Item (ID: {item.id}) '{item.name}' is below reorder level. "
            f"Current: {current_qty}, Reorder Level: {item.reorder_level}."
        )
        Notification.objects.create(
            user=user,
            type=NotificationType.WARNING,
            message=message,
        )


def _create_budget_overrun_notification(budget):
    """
    Create a notification for a budget overrun.

    Deduplication: check if a notification already exists for this specific budget.
    Uses budget ID in deduplication key to allow multiple budgets with same category.
    Notify the farm owner.
    """
    farm = budget.farm
    user = farm.owner
    actual_spend = _calculate_actual_spend(budget)

    category_str = budget.category or "General"
    existing = Notification.objects.filter(
        user=user,
        type=NotificationType.ALERT,
        message__contains=f"Budget (ID: {budget.id})",
    ).exists()

    if not existing:
        message = (
            f"Budget (ID: {budget.id}) for {category_str} has been exceeded. "
            f"Budget: {budget.amount}, Actual: {actual_spend}."
        )
        Notification.objects.create(
            user=user,
            type=NotificationType.ALERT,
            message=message,
        )


def _calculate_actual_spend(budget):
    """
    Calculate actual spend for a budget scope.

    Scope is determined by: farm + cycle (if set) + category (if set) + period.
    Only includes POSTED expenses.
    """
    expenses = Expense.objects.filter(
        status=ExpenseStatus.POSTED, farm=budget.farm
    )

    if budget.cycle:
        expenses = expenses.filter(cycle=budget.cycle)

    if budget.category:
        expenses = expenses.filter(category=budget.category)

    if budget.period_start and budget.period_end:
        expenses = expenses.filter(
            date__gte=budget.period_start, date__lte=budget.period_end
        )

    total = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return total
