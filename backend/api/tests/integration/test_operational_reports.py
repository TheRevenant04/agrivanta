from datetime import date
from decimal import Decimal

import pytest

from api import operational_reports
from api.models import (
    Activity,
    ActivityStatus,
    ActivityType,
    Crop,
    CropCycle,
    Equipment,
    EquipmentUsage,
    Farm,
    Field,
    InventoryItem,
    LabourRecord,
    MovementType,
    ReportingPeriod,
    StockMovement,
    Unit,
    User,
    Worker,
)

REPORTS = "/api/reports"
ENDPOINTS = ("activity-status", "inventory", "labour-usage", "equipment-usage")
TODAY = date(2026, 6, 1)
MISSING_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(
        operational_reports.timezone, "localdate", lambda: TODAY
    )
    from api import dashboard

    monkeypatch.setattr(dashboard.timezone, "localdate", lambda: TODAY)


@pytest.fixture
def farm(client):
    return Farm.objects.get()


def build_farm_data(farm, suffix=""):
    field = Field.objects.create(farm=farm, name="F" + suffix, area=Decimal("2"))
    crop = Crop.objects.create(farm=farm, name="Corn" + suffix)
    cycle = CropCycle.objects.create(
        farm=farm,
        field=field,
        crop=crop,
        cycle_type="annual",
        start_date=date(2026, 1, 1),
    )
    activity_type = ActivityType.objects.filter(farm=farm).first()
    if activity_type is None:
        activity_type = ActivityType.objects.create(
            farm=farm, name="Sow" + suffix, category="planting"
        )
    return cycle, activity_type


def make_activity(farm, cycle, activity_type, planned, status):
    return Activity.objects.create(
        farm=farm,
        cycle=cycle,
        type=activity_type,
        planned_date=planned,
        status=status,
    )


def other_farm():
    owner = User.objects.create_user(
        email="other@agrivanta.test", password="OtherPass#4242"
    )
    return Farm.objects.create(
        owner=owner, name="Other", reporting_currency="USD"
    )


def get(client, name, **params):
    return client.get(f"{REPORTS}/{name}", params)


@pytest.mark.parametrize("name", ENDPOINTS)
def test_reports_require_authentication(anon, name):
    assert anon.get(f"{REPORTS}/{name}").status_code == 401


@pytest.mark.parametrize("name", ENDPOINTS)
def test_reports_are_read_only(client, name):
    for method in (client.post, client.put, client.patch, client.delete):
        assert method(f"{REPORTS}/{name}").status_code == 405


@pytest.mark.parametrize("name", ENDPOINTS)
def test_reports_empty_data_returns_valid_result(client, name):
    response = get(client, name)
    assert response.status_code == 200, response.data


def test_empty_result_shapes(client):
    assert get(client, "activity-status").data == {
        "counts": {
            "planned": 0,
            "in_progress": 0,
            "completed": 0,
            "overdue": 0,
        },
        "total": 0,
    }
    assert get(client, "inventory").data["items"] == []
    for name in ("labour-usage", "equipment-usage"):
        data = get(client, name).data
        assert data["rows"] == []
        assert data["totals"] == {"hours": 0, "cost": 0}


def test_activity_status_counts_with_cycle_and_period_filters(client, farm):
    cycle, atype = build_farm_data(farm)
    cycle2, _ = build_farm_data(farm, "2")
    for planned, status in [
        (date(2026, 7, 1), ActivityStatus.PLANNED),
        (date(2026, 7, 2), ActivityStatus.IN_PROGRESS),
        (date(2026, 3, 1), ActivityStatus.COMPLETED),
        (date(2026, 3, 2), ActivityStatus.OVERDUE),
        (date(2026, 5, 1), ActivityStatus.PLANNED),
    ]:
        make_activity(farm, cycle, atype, planned, status)
    make_activity(farm, cycle2, atype, date(2026, 7, 5), ActivityStatus.PLANNED)

    data = get(client, "activity-status").data
    assert data["counts"] == {
        "planned": 2,
        "in_progress": 1,
        "completed": 1,
        "overdue": 2,
    }
    assert data["total"] == 6

    data = get(client, "activity-status", cycleId=str(cycle.id)).data
    assert data["counts"]["planned"] == 1
    assert data["total"] == 5

    data = get(
        client, "activity-status", startDate="2026-07-01", endDate="2026-07-31"
    ).data
    assert data["counts"] == {
        "planned": 2,
        "in_progress": 1,
        "completed": 0,
        "overdue": 0,
    }

    period = ReportingPeriod.objects.create(
        farm=farm,
        name="Q1",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    data = get(client, "activity-status", periodId=str(period.id)).data
    assert data["counts"]["completed"] == 1
    assert data["counts"]["overdue"] == 1
    assert data["total"] == 2

    empty = get(
        client, "activity-status", startDate="2025-01-01", endDate="2025-01-31"
    )
    assert empty.status_code == 200
    assert empty.data["total"] == 0


def test_inventory_report_quantity_and_low_stock(client, farm):
    unit = Unit.objects.create(farm=farm, name="kg", base_measure="mass")
    low = InventoryItem.objects.create(
        farm=farm, name="Seed", unit=unit, reorder_level=Decimal("10")
    )
    fine = InventoryItem.objects.create(
        farm=farm, name="Urea", unit=unit, reorder_level=Decimal("5")
    )
    none = InventoryItem.objects.create(farm=farm, name="Twine", unit=unit)
    for item, kind, qty, when in [
        (low, MovementType.PURCHASE, "20", date(2026, 2, 1)),
        (low, MovementType.USAGE, "12", date(2026, 3, 1)),
        (fine, MovementType.PURCHASE, "50", date(2026, 2, 1)),
        (none, MovementType.PURCHASE, "1", date(2026, 2, 1)),
    ]:
        StockMovement.objects.create(
            farm=farm, item=item, type=kind, quantity=Decimal(qty), date=when
        )

    data = get(client, "inventory").data
    by_name = {row["name"]: row for row in data["items"]}
    assert [row["name"] for row in data["items"]] == ["Seed", "Twine", "Urea"]
    assert by_name["Seed"]["currentQuantity"] == 8
    assert by_name["Seed"]["reorderLevel"] == 10
    assert by_name["Seed"]["lowStock"] is True
    assert by_name["Urea"]["lowStock"] is False
    assert by_name["Twine"]["reorderLevel"] is None
    assert by_name["Twine"]["lowStock"] is False

    earlier = get(client, "inventory", startDate="2026-01-01", endDate="2026-02-15")
    assert {r["name"]: r["currentQuantity"] for r in earlier.data["items"]}[
        "Seed"
    ] == 20


def test_labour_usage_by_cycle_and_activity(client, farm):
    cycle, atype = build_farm_data(farm)
    cycle2, _ = build_farm_data(farm, "2")
    a1 = make_activity(farm, cycle, atype, date(2026, 3, 1), "planned")
    a2 = make_activity(farm, cycle, atype, date(2026, 4, 1), "planned")
    a3 = make_activity(farm, cycle2, atype, date(2026, 3, 1), "planned")
    sam = Worker.objects.create(farm=farm, name="Sam")
    amy = Worker.objects.create(farm=farm, name="Amy")
    for worker, act, hours, cost, when in [
        (sam, a1, "2", "10", date(2026, 3, 1)),
        (sam, a2, "1.5", "10", date(2026, 4, 1)),
        (amy, a1, "4", "5", date(2026, 3, 2)),
        (sam, a3, "3", "10", date(2026, 3, 3)),
    ]:
        LabourRecord.objects.create(
            farm=farm,
            worker=worker,
            activity=act,
            hours=Decimal(hours),
            hourly_cost=Decimal(cost),
            date=when,
        )

    data = get(client, "labour-usage").data
    assert data["groupBy"] == "cycle"
    rows = {(r["cycleId"], r["workerName"]): r for r in data["rows"]}
    assert rows[(str(cycle.id), "Sam")]["hours"] == 3.5
    assert rows[(str(cycle.id), "Sam")]["cost"] == 35
    assert rows[(str(cycle.id), "Amy")]["cost"] == 20
    assert rows[(str(cycle2.id), "Sam")]["cost"] == 30
    assert data["totals"] == {"hours": 10.5, "cost": 85}

    data = get(client, "labour-usage", groupBy="activity").data
    rows = {(r["activityId"], r["workerName"]): r for r in data["rows"]}
    assert rows[(str(a1.id), "Sam")]["hours"] == 2
    assert rows[(str(a1.id), "Amy")]["hours"] == 4
    assert rows[(str(a2.id), "Sam")]["cost"] == 15
    assert len(rows) == 4

    data = get(client, "labour-usage", cycleId=str(cycle.id)).data
    assert data["totals"] == {"hours": 7.5, "cost": 55}

    data = get(
        client, "labour-usage", startDate="2026-04-01", endDate="2026-04-30"
    ).data
    assert data["totals"] == {"hours": 1.5, "cost": 15}

    empty = get(
        client, "labour-usage", startDate="2025-01-01", endDate="2025-01-31"
    )
    assert empty.status_code == 200
    assert empty.data["rows"] == []


def test_equipment_usage_by_cycle_and_activity(client, farm):
    cycle, atype = build_farm_data(farm)
    cycle2, _ = build_farm_data(farm, "2")
    a1 = make_activity(farm, cycle, atype, date(2026, 3, 1), "planned")
    a2 = make_activity(farm, cycle2, atype, date(2026, 3, 1), "planned")
    tractor = Equipment.objects.create(farm=farm, name="Tractor")
    for act, hours, cost, when in [
        (a1, "2", "20", date(2026, 3, 1)),
        (a1, "1", "10", date(2026, 3, 2)),
        (a2, "3", "45", date(2026, 5, 1)),
    ]:
        EquipmentUsage.objects.create(
            farm=farm,
            equipment=tractor,
            activity=act,
            hours=Decimal(hours),
            cost=Decimal(cost),
            total_cost=Decimal(cost),
            date=when,
        )

    data = get(client, "equipment-usage").data
    rows = {r["cycleId"]: r for r in data["rows"]}
    assert rows[str(cycle.id)]["equipmentName"] == "Tractor"
    assert rows[str(cycle.id)]["hours"] == 3
    assert rows[str(cycle.id)]["cost"] == 30
    assert data["totals"] == {"hours": 6, "cost": 75}

    data = get(client, "equipment-usage", groupBy="activity").data
    assert {r["activityId"]: r["cost"] for r in data["rows"]} == {
        str(a1.id): 30,
        str(a2.id): 45,
    }

    data = get(client, "equipment-usage", cycleId=str(cycle2.id)).data
    assert data["totals"] == {"hours": 3, "cost": 45}

    data = get(
        client, "equipment-usage", startDate="2026-05-01", endDate="2026-05-31"
    ).data
    assert data["totals"]["cost"] == 45

    empty = get(client, "equipment-usage", cycleId=str(cycle.id), startDate="2025-01-01", endDate="2025-01-02")
    assert empty.status_code == 200
    assert empty.data["rows"] == []


def test_reports_are_farm_scoped(client, farm):
    foreign_farm = other_farm()
    cycle, atype = build_farm_data(foreign_farm, "x")
    activity = make_activity(
        foreign_farm, cycle, atype, date(2026, 7, 1), "planned"
    )
    worker = Worker.objects.create(farm=foreign_farm, name="Zed")
    LabourRecord.objects.create(
        farm=foreign_farm,
        worker=worker,
        activity=activity,
        hours=Decimal(1),
        hourly_cost=Decimal(1),
        date=date(2026, 3, 1),
    )
    equipment = Equipment.objects.create(farm=foreign_farm, name="Combine")
    EquipmentUsage.objects.create(
        farm=foreign_farm,
        equipment=equipment,
        activity=activity,
        hours=Decimal(1),
        cost=Decimal(1),
        total_cost=Decimal(1),
        date=date(2026, 3, 1),
    )
    unit = Unit.objects.create(
        farm=foreign_farm, name="kg", base_measure="mass"
    )
    InventoryItem.objects.create(farm=foreign_farm, name="Secret", unit=unit)

    assert get(client, "activity-status").data["total"] == 0
    assert get(client, "inventory").data["items"] == []
    assert get(client, "labour-usage").data["rows"] == []
    assert get(client, "equipment-usage").data["rows"] == []

    for name in ENDPOINTS:
        response = get(client, name, cycleId=str(cycle.id))
        assert response.status_code == 400
        assert response.data["field"] == "cycleId"
        assert get(client, name, farmId=str(foreign_farm.id)).status_code == 404


@pytest.mark.parametrize("name", ENDPOINTS)
@pytest.mark.parametrize(
    "params,field",
    [
        ({"startDate": "2026-02-01", "endDate": "2026-01-01"}, "endDate"),
        ({"startDate": "not-a-date", "endDate": "2026-01-01"}, "startDate"),
        ({"startDate": "2026-01-01"}, "endDate"),
        ({"cycleId": "abc"}, "cycleId"),
        ({"cycleId": MISSING_ID}, "cycleId"),
        ({"periodId": "abc"}, "periodId"),
        ({"periodId": MISSING_ID}, "periodId"),
    ],
)
def test_reports_reject_invalid_filters(client, name, params, field):
    response = get(client, name, **params)
    assert response.status_code == 400, response.data
    assert response.data["field"] == field
    assert "detail" in response.data


@pytest.mark.parametrize("name", ("labour-usage", "equipment-usage"))
def test_usage_reports_reject_invalid_group_by(client, name):
    response = get(client, name, groupBy="worker")
    assert response.status_code == 400
    assert response.data["field"] == "groupBy"

