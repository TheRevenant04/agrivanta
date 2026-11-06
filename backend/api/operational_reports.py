from collections import OrderedDict
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from .dashboard import _resolve_filters
from .exceptions import ApiError
from .models import (
    Activity,
    ActivityStatus,
    EquipmentUsage,
    InventoryItem,
    LabourRecord,
)
from .serializers import as_number

GROUP_BY_VALUES = ("cycle", "activity")


def _group_by(query_params):
    value = query_params.get("groupBy")
    if value in (None, ""):
        return "cycle"
    if value not in GROUP_BY_VALUES:
        raise ApiError(
            "groupBy must be one of: " + ", ".join(GROUP_BY_VALUES) + ".",
            status.HTTP_400_BAD_REQUEST,
            "groupBy",
        )
    return value


def activity_status_report(farm, query_params, today=None):
    filters = _resolve_filters(farm, query_params)
    today = today or timezone.localdate()
    activities = Activity.objects.filter(farm=farm)
    if filters["cycle"] is not None:
        activities = activities.filter(cycle=filters["cycle"])
    if filters["start_date"] is not None:
        activities = activities.filter(
            planned_date__gte=filters["start_date"],
            planned_date__lte=filters["end_date"],
        )

    active = (ActivityStatus.PLANNED, ActivityStatus.IN_PROGRESS)
    overdue = Q(status=ActivityStatus.OVERDUE) | Q(
        status__in=active, planned_date__lt=today
    )
    counts = {
        ActivityStatus.PLANNED.value: activities.filter(
            status=ActivityStatus.PLANNED, planned_date__gte=today
        ).count(),
        ActivityStatus.IN_PROGRESS.value: activities.filter(
            status=ActivityStatus.IN_PROGRESS, planned_date__gte=today
        ).count(),
        ActivityStatus.COMPLETED.value: activities.filter(
            status=ActivityStatus.COMPLETED
        ).count(),
        ActivityStatus.OVERDUE.value: activities.filter(overdue).count(),
    }
    return {"counts": counts, "total": sum(counts.values())}


def inventory_report(farm, query_params, today=None):
    filters = _resolve_filters(farm, query_params)
    as_of = filters["end_date"] or today or timezone.localdate()
    items = InventoryItem.objects.filter(farm=farm).prefetch_related(
        "movements"
    )
    rows = []
    for item in items.order_by("name", "id"):
        quantity = item.current_quantity(as_of)
        rows.append(
            {
                "itemId": str(item.id),
                "name": item.name,
                "unitId": str(item.unit_id),
                "currentQuantity": as_number(quantity),
                "reorderLevel": as_number(item.reorder_level),
                "lowStock": item.reorder_level is not None
                and quantity <= item.reorder_level,
            }
        )
    return {"asOf": as_of.isoformat(), "items": rows}


def _usage_report(queryset, filters, group_by, subject, cost):
    if filters["cycle"] is not None:
        queryset = queryset.filter(activity__cycle=filters["cycle"])
    if filters["start_date"] is not None:
        queryset = queryset.filter(
            date__gte=filters["start_date"], date__lte=filters["end_date"]
        )
    group_key = "activityId" if group_by == "activity" else "cycleId"

    groups = OrderedDict()
    for record in queryset.select_related("activity", subject).order_by(
        "date", "created_at", "id"
    ):
        group_id = (
            record.activity_id
            if group_by == "activity"
            else record.activity.cycle_id
        )
        subject_obj = getattr(record, subject)
        entry = groups.setdefault(
            (group_id, subject_obj.id),
            {
                group_key: str(group_id),
                f"{subject}Id": str(subject_obj.id),
                f"{subject}Name": subject_obj.name,
                "hours": Decimal(0),
                "cost": Decimal(0),
            },
        )
        entry["hours"] += record.hours
        entry["cost"] += cost(record)

    rows = sorted(
        groups.values(),
        key=lambda r: (r[group_key], r[f"{subject}Name"], r[f"{subject}Id"]),
    )
    total_hours = sum((r["hours"] for r in rows), Decimal(0))
    total_cost = sum((r["cost"] for r in rows), Decimal(0))
    for row in rows:
        row["hours"] = as_number(row["hours"])
        row["cost"] = as_number(row["cost"])
    return {
        "groupBy": group_by,
        "rows": rows,
        "totals": {
            "hours": as_number(total_hours),
            "cost": as_number(total_cost),
        },
    }


def labour_usage_report(farm, query_params):
    filters = _resolve_filters(farm, query_params)
    return _usage_report(
        LabourRecord.objects.filter(farm=farm),
        filters,
        _group_by(query_params),
        "worker",
        lambda record: record.hours * record.hourly_cost,
    )


def equipment_usage_report(farm, query_params):
    filters = _resolve_filters(farm, query_params)
    return _usage_report(
        EquipmentUsage.objects.filter(farm=farm),
        filters,
        _group_by(query_params),
        "equipment",
        lambda record: record.cost,
    )
