from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from api.models import (
    Activity,
    ActivityType,
    Crop,
    CropCycle,
    Farm,
    Field,
    InventoryItem,
    Role,
    Unit,
    User,
)


pytestmark = pytest.mark.django_db


def create_item(client, unit, **values):
    payload = {"name": "Fertilizer", "unitId": unit["id"]}
    payload.update(values)
    response = client.post("/api/inventory-items", payload, format="json")
    assert response.status_code == 201, response.data
    return response.data


def create_movement(client, item, **values):
    payload = {
        "itemId": item["id"],
        "type": "purchase",
        "quantity": "1",
        "date": "2026-03-01",
    }
    payload.update(values)
    return client.post("/api/stock-movements", payload, format="json")


def create_other_farm():
    owner = User.objects.create_user(
        email=f"other-{User.objects.count()}@agrivanta.test",
        password="OliveHarvest#42",
    )
    farm = Farm.objects.create(
        owner=owner, name="Other farm", reporting_currency="USD"
    )
    return owner, farm


def create_activity(farm):
    field = Field.objects.create(farm=farm, name="Field", area=Decimal("1"))
    crop = Crop.objects.create(farm=farm, name="Corn")
    cycle = CropCycle.objects.create(
        farm=farm,
        field=field,
        crop=crop,
        start_date=date(2026, 3, 1),
    )
    activity_type = ActivityType.objects.create(
        farm=farm, name="Custom fertilizer", category="fertilizing"
    )
    return Activity.objects.create(
        farm=farm,
        cycle=cycle,
        type=activity_type,
        planned_date=date(2026, 3, 2),
    )


def test_purchase_usage_adjustments_and_zero_stock_boundaries(
    client, setup
):
    unit = setup()["unit"]
    item = create_item(client, unit, reorderLevel="0")

    purchase = create_movement(
        client, item, quantity="100", unitCost="2.50"
    )
    assert purchase.status_code == 201, purchase.data
    assert purchase.data["unitCost"] == 2.5

    usage = create_movement(client, item, type="usage", quantity="30")
    assert usage.status_code == 201, usage.data
    assert client.get(f"/api/inventory-items/{item['id']}").data[
        "currentQuantity"
    ] == 70

    positive_adjustment = create_movement(
        client, item, type="adjustment", quantity="5"
    )
    negative_adjustment = create_movement(
        client, item, type="adjustment", quantity="-5"
    )
    assert positive_adjustment.status_code == 201
    assert negative_adjustment.status_code == 201

    exact_adjustment = create_movement(
        client, item, type="adjustment", quantity="-70"
    )
    assert exact_adjustment.status_code == 201
    assert client.get(f"/api/inventory-items/{item['id']}").data[
        "currentQuantity"
    ] == 0

    assert create_movement(client, item, quantity="70").status_code == 201
    exact_usage = create_movement(client, item, type="usage", quantity="70")
    assert exact_usage.status_code == 201
    item_response = client.get(f"/api/inventory-items/{item['id']}")
    assert item_response.data["currentQuantity"] == 0
    assert item_response.data["lowStock"] is True

    negative_adjustment = create_movement(
        client, item, type="adjustment", quantity="-0.01"
    )
    assert negative_adjustment.status_code == 400
    assert negative_adjustment.data["field"] == "quantity"

    negative_usage = create_movement(
        client, item, type="usage", quantity="0.01"
    )
    assert negative_usage.status_code == 400
    assert negative_usage.data["field"] == "quantity"


def test_low_stock_thresholds_include_equality_and_allow_no_threshold(
    client, setup
):
    unit = setup()["unit"]
    no_threshold = create_item(client, unit)
    zero_threshold = create_item(
        client, unit, name="Seed", reorderLevel="0"
    )
    configured = create_item(
        client, unit, name="Pesticide", reorderLevel="2"
    )

    listed = {
        item["id"]: item for item in client.get("/api/inventory-items").data
    }
    assert listed[no_threshold["id"]]["reorderLevel"] is None
    assert listed[no_threshold["id"]]["lowStock"] is False
    assert listed[zero_threshold["id"]]["lowStock"] is True
    assert listed[configured["id"]]["lowStock"] is True

    assert create_movement(
        client, zero_threshold, quantity="1"
    ).status_code == 201
    assert create_movement(
        client, configured, quantity="2"
    ).status_code == 201
    listed = {
        item["id"]: item for item in client.get("/api/inventory-items").data
    }
    assert listed[zero_threshold["id"]]["lowStock"] is False
    assert listed[configured["id"]]["currentQuantity"] == 2
    assert listed[configured["id"]]["lowStock"] is True

    assert create_movement(
        client, configured, quantity="0.01"
    ).status_code == 201
    item = client.get(f"/api/inventory-items/{configured['id']}")
    assert item.data["lowStock"] is False


def test_movement_inputs_require_valid_values_and_allow_optional_links(
    client, setup
):
    data = setup()
    item = create_item(client, data["unit"])
    url = f"/api/inventory-items/{item['id']}/movements"
    required_cases = [
        ({}, "itemId"),
        (
            {"itemId": item["id"], "type": "purchase", "quantity": "1"},
            "date",
        ),
        (
            {
                "itemId": item["id"],
                "type": "purchase",
                "quantity": "1",
                "date": "2026-02-30",
            },
            "date",
        ),
        (
            {
                "itemId": item["id"],
                "type": "purchase",
                "quantity": "1",
                "date": "2026-03-01",
                "unitCost": "-1",
            },
            "unitCost",
        ),
    ]
    for payload, field in required_cases:
        response = client.post(url, payload, format="json")
        assert response.status_code == 400
        assert response.data["field"] == field

    invalid_unit = create_movement(
        client,
        item,
        unitId="00000000-0000-0000-0000-000000000000",
    )
    assert invalid_unit.status_code == 404
    assert invalid_unit.data["field"] == "unitId"

    missing_type = create_movement(client, item, type="")
    assert missing_type.status_code == 400
    assert missing_type.data["field"] == "type"
    zero_purchase = create_movement(client, item, quantity="0")
    assert zero_purchase.status_code == 400
    negative_usage = create_movement(
        client, item, type="usage", quantity="-1"
    )
    assert negative_usage.status_code == 400
    zero_adjustment = create_movement(
        client, item, type="adjustment", quantity="0"
    )
    assert zero_adjustment.status_code == 400

    activity = create_activity(Farm.objects.get(pk=client.get("/api/farm").data["id"]))
    linked_expense = client.post(
        "/api/expenses",
        {"category": "inputs", "amount": "10", "date": "2026-03-01"},
        format="json",
    )
    assert linked_expense.status_code == 201
    linked = create_movement(
        client,
        item,
        activityId=str(activity.id),
        expenseId=linked_expense.data["id"],
    )
    assert linked.status_code == 201, linked.data
    assert linked.data["activityId"] == str(activity.id)
    assert linked.data["expenseId"] == linked_expense.data["id"]

    unknown_expense = create_movement(
        client,
        item,
        expenseId="00000000-0000-0000-0000-000000000000",
    )
    assert unknown_expense.status_code == 404
    assert unknown_expense.data["field"] == "expenseId"

    optional_links_omitted = create_movement(
        client, item, type="adjustment", quantity="1"
    )
    assert optional_links_omitted.status_code == 201
    assert optional_links_omitted.data["activityId"] is None
    assert optional_links_omitted.data["expenseId"] is None
    assert optional_links_omitted.data["unitCost"] is None


def test_inventory_references_and_resources_are_farm_scoped(client, setup):
    data = setup()
    item = create_item(client, data["unit"])
    movement = create_movement(client, item)

    missing_unit = client.post(
        "/api/inventory-items", {"name": "Missing unit"}, format="json"
    )
    assert missing_unit.status_code == 400
    unknown_unit = client.post(
        "/api/inventory-items",
        {
            "name": "Unknown unit",
            "unitId": "00000000-0000-0000-0000-000000000000",
        },
        format="json",
    )
    assert unknown_unit.status_code == 404
    negative_threshold = client.post(
        "/api/inventory-items",
        {"name": "Negative", "unitId": data["unit"]["id"], "reorderLevel": -1},
        format="json",
    )
    assert negative_threshold.status_code == 400

    other_owner, other_farm = create_other_farm()
    other_unit = Unit.objects.create(
        farm=other_farm, name="litre", base_measure="volume"
    )
    other_activity = create_activity(other_farm)
    assert client.post(
        "/api/inventory-items",
        {"name": "Other unit", "unitId": str(other_unit.id)},
        format="json",
    ).status_code == 404
    other_unit_movement = create_movement(
        client, item, unitId=str(other_unit.id)
    )
    assert other_unit_movement.status_code == 404
    assert other_unit_movement.data["field"] == "unitId"

    for activity_id in (
        str(other_activity.id),
        "00000000-0000-0000-0000-000000000000",
    ):
        response = create_movement(client, item, activityId=activity_id)
        assert response.status_code == 404
        assert response.data["field"] == "activityId"

    other_client = APIClient()
    other_client.force_authenticate(user=other_owner)
    assert other_client.get("/api/inventory-items").data == []
    assert other_client.get("/api/stock-movements").data == []
    foreign_create = other_client.post(
        "/api/stock-movements",
        {
            "itemId": item["id"],
            "type": "purchase",
            "quantity": "1",
            "date": "2026-03-01",
        },
        format="json",
    )
    assert foreign_create.status_code == 404
    assert other_client.get(
        f"/api/inventory-items/{item['id']}"
    ).status_code == 404
    assert other_client.get(
        f"/api/stock-movements/{movement.data['id']}"
    ).status_code == 404
    assert other_client.get(
        f"/api/inventory-items/{item['id']}/movements"
    ).status_code == 404

    farm = Farm.objects.get(pk=client.get("/api/farm").data["id"])
    manager = User.objects.create_user(
        email="inventory-manager@agrivanta.test",
        password="OliveHarvest#42",
        role=Role.MANAGER,
    )
    farm.members.add(manager)
    manager_client = APIClient()
    manager_client.force_authenticate(user=manager)
    assert manager_client.get("/api/inventory-items").data[0]["id"] == item["id"]

    worker = User.objects.create_user(
        email="inventory-worker@agrivanta.test",
        password="OliveHarvest#42",
        role=Role.WORKER,
    )
    farm.members.add(worker)
    worker_client = APIClient()
    worker_client.force_authenticate(user=worker)
    assert worker_client.get("/api/inventory-items").status_code == 403


def test_item_and_movement_crud_respects_posted_record_safety(client, setup):
    data = setup()
    item = create_item(client, data["unit"])
    empty_item = create_item(client, data["unit"], name="Empty")

    assert client.delete(
        f"/api/inventory-items/{empty_item['id']}"
    ).status_code == 204
    assert client.get(
        f"/api/inventory-items/{empty_item['id']}"
    ).status_code == 404

    movement = create_movement(client, item)
    assert movement.status_code == 201
    detail = client.get(f"/api/stock-movements/{movement.data['id']}")
    assert detail.status_code == 200
    assert detail.data == movement.data
    reject_update = client.put(
        f"/api/stock-movements/{movement.data['id']}",
        {"quantity": 2},
        format="json",
    )
    assert reject_update.status_code == 409
    assert reject_update.data["detail"].startswith(
        "Posted stock movements cannot be edited"
    )
    reject_delete = client.delete(
        f"/api/stock-movements/{movement.data['id']}"
    )
    assert reject_delete.status_code == 409
    assert reject_delete.data["detail"].startswith(
        "Posted stock movements cannot be deleted"
    )

    item_url = f"/api/inventory-items/{item['id']}"
    update = client.put(
        item_url,
        {"name": "Updated fertilizer", "unitId": data["unit"]["id"]},
        format="json",
    )
    assert update.status_code == 200
    assert update.data["reorderLevel"] is None
    reject_item_delete = client.delete(item_url)
    assert reject_item_delete.status_code == 409
    assert "with stock movements" in reject_item_delete.data["detail"]

    another_unit = client.post(
        "/api/units",
        {"name": "litre", "baseMeasure": "volume"},
        format="json",
    )
    assert another_unit.status_code == 201
    unsafe_update = client.put(
        item_url,
        {"name": "Updated fertilizer", "unitId": another_unit.data["id"]},
        format="json",
    )
    assert unsafe_update.status_code == 409

    empty_farm_owner, _ = create_other_farm()
    empty_farm_client = APIClient()
    empty_farm_client.force_authenticate(user=empty_farm_owner)
    assert empty_farm_client.get("/api/inventory-items").data == []
    assert empty_farm_client.get("/api/stock-movements").data == []
