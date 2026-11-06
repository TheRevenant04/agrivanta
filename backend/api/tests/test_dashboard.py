from datetime import date
from decimal import Decimal

import pytest

from api import dashboard
from api.models import (
    Activity,
    ActivityStatus,
    AllocationRule,
    CropCycle,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Farm,
    InventoryItem,
    ReportingPeriod,
    StockMovement,
)

from .conftest import register


DASHBOARD = "/api/dashboard"
TODAY = date(2026, 11, 1)


def _post(client, path, payload):
    response = client.post(path, payload, format="json")
    assert response.status_code == 201, response.data
    return response.data


def _cycle(client, data, *, start="2026-01-01", end=None):
    payload = {
        "fieldId": data["field"]["id"],
        "cropId": data["crop"]["id"],
        "varietyId": data["variety"]["id"],
        "cycleType": "annual",
        "startDate": start,
    }
    if end is not None:
        payload["endDate"] = end
    return _post(client, "/api/crop-cycles", payload)


def _harvest(client, cycle, unit, quantity, when):
    return _post(
        client,
        "/api/harvests",
        {
            "cycleId": cycle["id"],
            "quantity": quantity,
            "unitId": unit["id"],
            "date": when,
        },
    )


def _sale(client, harvest, customer, quantity, price, when):
    return _post(
        client,
        "/api/sales",
        {
            "customerId": customer["id"],
            "harvestId": harvest["id"],
            "quantity": quantity,
            "unitPrice": price,
            "date": when,
        },
    )


def _expense(farm, amount, when, *, cycle=None, category=ExpenseCategory.INPUTS,
             status=ExpenseStatus.POSTED):
    return Expense.objects.create(
        farm=farm,
        cycle=cycle,
        category=category,
        amount=Decimal(amount),
        date=date.fromisoformat(when),
        status=status,
    )


@pytest.fixture
def fixed_today(monkeypatch):
    monkeypatch.setattr(dashboard.timezone, "localdate", lambda: TODAY)


def test_empty_farm_returns_zeroed_dashboard(client, fixed_today):
    response = client.get(DASHBOARD)

    assert response.status_code == 200, response.data
    assert response.data == {
        "currentCycleSpend": 0.0,
        "revenueToDate": 0.0,
        "unsoldProduce": [],
        "upcomingActivities": 0,
        "overdueActivities": 0,
        "lowStockItemCount": 0,
    }


def test_dashboard_aggregates_cycle_costs_sales_units_activities_and_stock(
    client, setup, fixed_today
):
    data = setup()
    farm = Farm.objects.get(owner__email="owner@agrivanta.test")
    current = _cycle(client, data)
    other_field = _post(
        client, "/api/fields", {"name": "South", "area": "37.5"}
    )
    second_cycle = _post(
        client,
        "/api/crop-cycles",
        {
            "fieldId": other_field["id"],
            "cropId": data["crop"]["id"],
            "varietyId": data["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2026-02-01",
        },
    )
    ended = _cycle(
        client, data, start="2025-01-01", end="2026-06-30"
    )

    _expense(farm, "120", "2026-10-05", cycle=CropCycle.objects.get(pk=current["id"]))
    _expense(
        farm, "80", "2026-10-06", cycle=CropCycle.objects.get(pk=second_cycle["id"])
    )
    _expense(
        farm,
        "999",
        "2026-10-07",
        cycle=CropCycle.objects.get(pk=current["id"]),
        status=ExpenseStatus.DRAFT,
    )
    _expense(
        farm,
        "700",
        "2026-10-08",
        cycle=CropCycle.objects.get(pk=ended["id"]),
    )
    _expense(
        farm,
        "60",
        "2026-10-10",
        category=ExpenseCategory.OVERHEAD,
    )
    _expense(farm, "1000", "2026-12-01", cycle=CropCycle.objects.get(pk=current["id"]))
    AllocationRule.objects.create(
        farm=farm,
        name="Allocate overhead by area",
        basis="per_hectare",
        active_from=date(2026, 10, 1),
    )

    grams = _post(
        client, "/api/units", {"name": "g", "baseMeasure": "mass"}
    )
    conversion = client.post(
        "/api/conversions",
        {
            "fromUnitId": grams["id"],
            "toUnitId": data["unit"]["id"],
            "factor": "0.001",
        },
        format="json",
    )
    assert conversion.status_code == 201, conversion.data

    first_kg = _harvest(client, current, data["unit"], "100", "2026-09-01")
    first_g = _harvest(client, current, grams, "50000", "2026-09-02")
    second_harvest = _harvest(
        client, second_cycle, data["unit"], "80", "2026-09-03"
    )
    customer = client.get("/api/customers").data[0]
    _sale(client, first_kg, customer, "10", "5", "2026-10-11")
    _sale(client, first_g, customer, "5000", "0.01", "2026-10-12")
    _sale(client, second_harvest, customer, "20", "2", "2026-10-13")
    future_harvest = _harvest(
        client, current, data["unit"], "20", "2026-11-02"
    )
    _sale(client, future_harvest, customer, "5", "2", "2026-11-03")
    # This sale falls outside the default crop-cycle set and date window.
    ended_harvest = _harvest(
        client, ended, data["unit"], "100", "2026-05-01"
    )
    _sale(client, ended_harvest, customer, "10", "70", "2026-05-02")

    activity_type = client.get("/api/activity-types").data[0]
    for planned_date, status in (
        ("2026-11-02", ActivityStatus.PLANNED),
        ("2026-11-01", ActivityStatus.PLANNED),
        ("2026-10-31", ActivityStatus.PLANNED),
        ("2026-11-05", ActivityStatus.OVERDUE),
        ("2026-10-30", ActivityStatus.COMPLETED),
        ("2026-11-03", ActivityStatus.IN_PROGRESS),
    ):
        Activity.objects.create(
            farm=farm,
            cycle=CropCycle.objects.get(pk=current["id"]),
            type_id=activity_type["id"],
            planned_date=date.fromisoformat(planned_date),
            status=status,
        )

    low_equal = InventoryItem.objects.create(
        farm=farm,
        name="At reorder threshold",
        unit_id=data["unit"]["id"],
        reorder_level=Decimal("5"),
    )
    StockMovement.objects.create(
        farm=farm,
        item=low_equal,
        type="purchase",
        quantity=Decimal("5"),
        date=date(2026, 10, 1),
    )
    InventoryItem.objects.create(
        farm=farm,
        name="Empty and zero threshold",
        unit_id=data["unit"]["id"],
        reorder_level=Decimal(0),
    )
    above_reorder = InventoryItem.objects.create(
        farm=farm,
        name="Above threshold",
        unit_id=data["unit"]["id"],
        reorder_level=Decimal("5"),
    )
    StockMovement.objects.create(
        farm=farm,
        item=above_reorder,
        type="purchase",
        quantity=Decimal("6"),
        date=date(2026, 10, 1),
    )

    response = client.get(DASHBOARD)

    assert response.status_code == 200, response.data
    assert response.data["currentCycleSpend"] == 260.0
    assert response.data["revenueToDate"] == 140.0
    assert response.data["unsoldProduce"] == [
        {
            "cycleId": current["id"],
            "quantity": 135.0,
            "unitId": data["unit"]["id"],
        },
        {
            "cycleId": second_cycle["id"],
            "quantity": 60.0,
            "unitId": data["unit"]["id"],
        },
    ]
    assert response.data["upcomingActivities"] == 3
    assert response.data["overdueActivities"] == 2
    assert response.data["lowStockItemCount"] == 2

    selected_cycle = client.get(
        DASHBOARD, {"cycleId": current["id"]}
    )
    assert selected_cycle.status_code == 200, selected_cycle.data
    assert selected_cycle.data["currentCycleSpend"] == 135.0
    assert selected_cycle.data["revenueToDate"] == 100.0


def test_date_range_and_reporting_period_narrow_dashboard(
    client, setup, fixed_today
):
    data = setup()
    farm = Farm.objects.get(owner__email="owner@agrivanta.test")
    cycle = _cycle(client, data)
    cycle_obj = CropCycle.objects.get(pk=cycle["id"])
    _expense(farm, "30", "2026-09-15", cycle=cycle_obj)
    _expense(farm, "20", "2026-10-15", cycle=cycle_obj)
    harvest = _harvest(client, cycle, data["unit"], "100", "2026-09-01")
    customer = client.get("/api/customers").data[0]
    _sale(client, harvest, customer, "10", "2", "2026-09-20")
    _sale(client, harvest, customer, "20", "3", "2026-10-20")

    low_during_period = InventoryItem.objects.create(
        farm=farm,
        name="Restocked after period",
        unit_id=data["unit"]["id"],
        reorder_level=Decimal("5"),
    )
    StockMovement.objects.create(
        farm=farm,
        item=low_during_period,
        type="purchase",
        quantity=Decimal("10"),
        date=date(2026, 9, 20),
    )
    StockMovement.objects.create(
        farm=farm,
        item=low_during_period,
        type="usage",
        quantity=Decimal("7"),
        date=date(2026, 10, 20),
    )
    StockMovement.objects.create(
        farm=farm,
        item=low_during_period,
        type="purchase",
        quantity=Decimal("20"),
        date=date(2026, 11, 1),
    )

    args = {"startDate": "2026-10-01", "endDate": "2026-10-31"}
    date_response = client.get(DASHBOARD, args)
    assert date_response.status_code == 200, date_response.data
    assert date_response.data["currentCycleSpend"] == 20.0
    assert date_response.data["revenueToDate"] == 60.0
    assert date_response.data["unsoldProduce"] == [
        {
            "cycleId": cycle["id"],
            "quantity": 70.0,
            "unitId": data["unit"]["id"],
        }
    ]
    assert date_response.data["lowStockItemCount"] == 1

    period = ReportingPeriod.objects.create(
        farm=farm,
        name="October 2026",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 31),
    )
    period_response = client.get(DASHBOARD, {"periodId": str(period.id)})
    assert period_response.status_code == 200, period_response.data
    assert period_response.data == date_response.data
    current_response = client.get(DASHBOARD)
    assert current_response.status_code == 200, current_response.data
    assert current_response.data["lowStockItemCount"] == 0


def test_historical_low_stock_uses_required_movement_dates(client, setup):
    data = setup()
    farm = Farm.objects.get(owner__email="owner@agrivanta.test")
    item = InventoryItem.objects.create(
        farm=farm,
        name="Dated movement",
        unit_id=data["unit"]["id"],
        reorder_level=Decimal("5"),
    )
    StockMovement.objects.create(
        farm=farm,
        item=item,
        type="purchase",
        quantity=Decimal("4"),
        date=date(2026, 10, 15),
    )
    StockMovement.objects.create(
        farm=farm,
        item=item,
        type="purchase",
        quantity=Decimal("10"),
        date=date(2026, 11, 1),
    )

    response = client.get(
        DASHBOARD,
        {"startDate": "2026-10-01", "endDate": "2026-10-31"},
    )

    assert response.status_code == 200, response.data
    assert response.data["lowStockItemCount"] == 1


def test_dashboard_is_farm_scoped(client, setup, fixed_today):
    data = setup()
    own_farm = Farm.objects.get(owner__email="owner@agrivanta.test")
    own_cycle = _cycle(client, data)
    _expense(
        own_farm,
        "25",
        "2026-10-01",
        cycle=CropCycle.objects.get(pk=own_cycle["id"]),
    )

    other_client = type(client)()
    registration = register(other_client, email="other@agrivanta.test")
    assert registration.status_code == 201, registration.data
    other_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {registration.data['token']}"
    )

    response = other_client.get(DASHBOARD)
    assert response.status_code == 200, response.data
    assert response.data["currentCycleSpend"] == 0.0
    assert response.data["revenueToDate"] == 0.0
    assert response.data["unsoldProduce"] == []

    foreign_response = other_client.get(
        DASHBOARD, {"farmId": str(own_farm.id)}
    )
    assert foreign_response.status_code == 404
    foreign_period = ReportingPeriod.objects.create(
        farm=own_farm,
        name="Owner period",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 31),
    )
    foreign_period_response = other_client.get(
        DASHBOARD, {"periodId": str(foreign_period.id)}
    )
    assert foreign_period_response.status_code == 400
    assert foreign_period_response.data["field"] == "periodId"


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"startDate": "not-a-date", "endDate": "2026-10-31"}, "startDate"),
        ({"startDate": "2026-11-01", "endDate": "2026-10-31"}, "endDate"),
        ({"startDate": "2026-10-01"}, "endDate"),
        ({"periodId": "00000000-0000-0000-0000-000000000000"}, "periodId"),
        (
            {
                "periodId": "00000000-0000-0000-0000-000000000000",
                "startDate": "2026-10-01",
                "endDate": "2026-10-31",
            },
            "periodId",
        ),
    ],
)
def test_invalid_dashboard_filters_return_clear_validation_errors(
    client, params, field, fixed_today
):
    response = client.get(DASHBOARD, params)

    assert response.status_code == 400
    assert response.data["field"] == field
    assert response.data["detail"]


def test_nonexistent_cycle_filter_is_a_validation_error(client, fixed_today):
    response = client.get(
        DASHBOARD,
        {"cycleId": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 400
    assert response.data["field"] == "cycleId"


def test_dashboard_endpoint_is_read_only(client):
    assert client.post(DASHBOARD, {}, format="json").status_code == 405
    assert client.put(DASHBOARD, {}, format="json").status_code == 405
