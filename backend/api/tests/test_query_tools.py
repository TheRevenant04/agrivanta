import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from api.models import (
    Activity,
    ActivityType,
    Customer,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Harvest,
    InventoryItem,
    MovementType,
    Role,
    Sale,
    StockMovement,
    User,
)
from api.query_tools import (
    activity_listing,
    crop_cycle_costs,
    field_profitability,
    inventory_position,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def farm_cycle(cycle):
    data = cycle()
    owner = User.objects.get(email="owner@agrivanta.test")
    crop_cycle = owner.farm.crop_cycles.get(pk=data["cycle"]["id"])
    return {
        "owner": owner,
        "farm": owner.farm,
        "field": crop_cycle.field,
        "cycle": crop_cycle,
        "unit": owner.farm.units.get(pk=data["unit"]["id"]),
    }


def _cost(data, *, amount="75.00", category=ExpenseCategory.INPUTS):
    return Expense.objects.create(
        farm=data["farm"],
        cycle=data["cycle"],
        category=category,
        amount=amount,
        date="2026-03-15",
        status=ExpenseStatus.POSTED,
    )


def _shared_overhead(data, *, amount="40.00"):
    return Expense.objects.create(
        farm=data["farm"],
        category=ExpenseCategory.OVERHEAD,
        amount=amount,
        date="2026-03-15",
        status=ExpenseStatus.POSTED,
    )


def _sale(data, *, revenue="300.00"):
    customer = Customer.objects.create(farm=data["farm"], name="Buyer")
    harvest = Harvest.objects.create(
        farm=data["farm"],
        cycle=data["cycle"],
        quantity="20",
        unit=data["unit"],
        date="2026-03-20",
    )
    return Sale.objects.create(
        farm=data["farm"],
        customer=customer,
        harvest=harvest,
        quantity="10",
        unit_price=revenue,
        date="2026-03-21",
        revenue=revenue,
    )


def _activity(data):
    activity_type = ActivityType.objects.create(
        farm=data["farm"],
        name="Query tool fertilizing",
        category="fertilizing",
    )
    return Activity.objects.create(
        farm=data["farm"],
        cycle=data["cycle"],
        type=activity_type,
        planned_date="2026-03-22",
        description="Apply nutrients",
    )


def _inventory(data):
    item = InventoryItem.objects.create(
        farm=data["farm"],
        name="Fertilizer",
        unit=data["unit"],
        reorder_level="2",
    )
    StockMovement.objects.create(
        farm=data["farm"],
        item=item,
        type=MovementType.PURCHASE,
        quantity="10",
        date="2026-03-10",
    )
    StockMovement.objects.create(
        farm=data["farm"],
        item=item,
        type=MovementType.USAGE,
        quantity="3",
        date="2026-03-20",
    )
    return item


def _period():
    return {"start_date": "2026-03-01", "end_date": "2026-03-31"}


@pytest.mark.parametrize(
    ("tool", "kwargs"),
    [
        (crop_cycle_costs, {"crop_cycle_id": "unused"}),
        (field_profitability, {"field_id": "unused"}),
        (inventory_position, {}),
        (activity_listing, {}),
    ],
)
def test_worker_is_explicitly_denied_without_partial_figures(
    farm_cycle, tool, kwargs
):
    worker = farm_cycle["owner"]
    worker.role = Role.WORKER

    result = tool(worker, **kwargs, **_period())

    assert result == {
        "status": "error",
        "error": {
            "code": "permission_denied",
            "message": (
                "Only authenticated farm owners and managers may use this tool."
            ),
        },
    }
    assert "data" not in result
    json.dumps(result)


def test_crop_cycle_costs_success_and_missing_records(farm_cycle):
    result = crop_cycle_costs(
        farm_cycle["owner"], farm_cycle["cycle"].id, **_period()
    )
    assert result["status"] == "missing_data"
    assert result["error"]["code"] == "missing_data"
    assert "no posted cost records" in result["error"]["message"].lower()
    assert "data" not in result
    assert result["evidence"]["cropCycles"][0]["id"] == str(
        farm_cycle["cycle"].id
    )

    _cost(farm_cycle)
    result = crop_cycle_costs(
        farm_cycle["owner"], farm_cycle["cycle"].id, **_period()
    )

    assert result["status"] == "ok"
    assert result["data"] == {
        "directCosts": 75.0,
        "allocatedOverheads": 0.0,
        "totalCosts": 75.0,
    }
    assert result["evidence"]["period"]["startDate"] == "2026-03-01"
    assert result["evidence"]["cropCycles"][0]["fieldName"] == "North 40"
    json.dumps(result)


def test_field_profitability_success_and_missing_cost_records(farm_cycle):
    _sale(farm_cycle)
    missing = field_profitability(
        farm_cycle["owner"], farm_cycle["field"].id, **_period()
    )
    assert missing["status"] == "missing_data"
    assert "data" not in missing
    assert farm_cycle["cycle"].id.__str__() == missing["evidence"][
        "cropCycles"
    ][0]["id"]

    _cost(farm_cycle)
    result = field_profitability(
        farm_cycle["owner"], farm_cycle["field"].id, **_period()
    )

    assert result["status"] == "ok"
    assert result["data"]["fieldName"] == "North 40"
    assert result["data"]["revenue"] == 300.0
    assert result["data"]["directCosts"] == 75.0
    assert result["data"]["operatingSurplus"] == 225.0
    assert result["evidence"]["cropCycles"][0]["id"] == str(
        farm_cycle["cycle"].id
    )
    json.dumps(result)


@pytest.mark.parametrize("has_direct_cost", [False, True])
@pytest.mark.parametrize("tool", ["cycle_costs", "field_profitability"])
def test_unallocated_shared_overhead_refuses_partial_results(
    farm_cycle, has_direct_cost, tool
):
    if has_direct_cost:
        _cost(farm_cycle)
    _shared_overhead(farm_cycle)

    if tool == "cycle_costs":
        result = crop_cycle_costs(
            farm_cycle["owner"], farm_cycle["cycle"].id, **_period()
        )
    else:
        result = field_profitability(
            farm_cycle["owner"], farm_cycle["field"].id, **_period()
        )

    assert result["status"] == "error"
    assert result["error"]["code"] == "calculation_error"
    assert "no allocation rule" in result["error"]["message"].lower()
    assert "data" not in result


def test_inventory_position_success_and_missing_records(farm_cycle):
    missing = inventory_position(farm_cycle["owner"], **_period())
    assert missing["status"] == "missing_data"
    assert "data" not in missing

    _inventory(farm_cycle)
    result = inventory_position(farm_cycle["owner"], **_period())

    assert result["status"] == "ok"
    assert result["data"]["items"] == [
        {
            "inventoryItemId": str(
                farm_cycle["farm"].inventory_items.get().id
            ),
            "name": "Fertilizer",
            "quantity": 7.0,
            "unit": "kg",
            "reorderLevel": 2.0,
            "lowStock": False,
        }
    ]
    assert result["evidence"]["period"]["endDate"] == "2026-03-31"
    assert result["evidence"]["field"] is None
    assert result["evidence"]["cropCycles"] == []
    json.dumps(result)


def test_activity_listing_success_and_missing_records(farm_cycle):
    missing = activity_listing(farm_cycle["owner"], **_period())
    assert missing["status"] == "missing_data"
    assert "data" not in missing

    _activity(farm_cycle)
    result = activity_listing(
        farm_cycle["owner"],
        field_id=farm_cycle["field"].id,
        **_period(),
    )

    assert result["status"] == "ok"
    assert result["data"]["activities"][0]["fieldName"] == "North 40"
    assert result["data"]["activities"][0]["cropCycleId"] == str(
        farm_cycle["cycle"].id
    )
    assert result["evidence"]["field"]["id"] == str(farm_cycle["field"].id)
    assert result["evidence"]["cropCycles"][0]["id"] == str(
        farm_cycle["cycle"].id
    )
    json.dumps(result)


def test_manager_can_query_its_single_farm(farm_cycle):
    manager = User.objects.create_user(
        email="manager@agrivanta.test",
        password="ManagerPassword#42",
        role=Role.MANAGER,
    )
    farm_cycle["farm"].members.add(manager)
    _cost(farm_cycle)

    result = crop_cycle_costs(
        manager, farm_cycle["cycle"].id, **_period()
    )

    assert result["status"] == "ok"
    assert result["evidence"]["farm"]["id"] == str(farm_cycle["farm"].id)


def test_manager_role_can_query_its_owned_farm(farm_cycle):
    owner = farm_cycle["owner"]
    owner.role = Role.MANAGER

    result = crop_cycle_costs(owner, farm_cycle["cycle"].id, **_period())

    assert result["status"] == "missing_data"
    assert result["evidence"]["farm"]["id"] == str(farm_cycle["farm"].id)


def test_tools_issue_only_read_queries(farm_cycle):
    _cost(farm_cycle)
    _sale(farm_cycle)
    _inventory(farm_cycle)
    _activity(farm_cycle)
    calls = [
        lambda: crop_cycle_costs(
            farm_cycle["owner"], farm_cycle["cycle"].id, **_period()
        ),
        lambda: field_profitability(
            farm_cycle["owner"], farm_cycle["field"].id, **_period()
        ),
        lambda: inventory_position(farm_cycle["owner"], **_period()),
        lambda: activity_listing(farm_cycle["owner"], **_period()),
    ]

    with CaptureQueriesContext(connection) as queries:
        results = [call() for call in calls]

    assert all(result["status"] == "ok" for result in results)
    write_statements = [
        query["sql"]
        for query in queries
        if query["sql"].lstrip().split(maxsplit=1)[0].upper()
        in {"INSERT", "UPDATE", "DELETE", "REPLACE"}
    ]
    assert write_statements == []
    assert all(json.loads(json.dumps(result)) == result for result in results)
