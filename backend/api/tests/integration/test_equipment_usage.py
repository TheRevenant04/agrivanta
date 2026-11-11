from decimal import Decimal

from rest_framework.test import APIClient

from api.models import EquipmentUsage

from api.tests.conftest import register


EQUIPMENT = "/api/equipment"
EQUIPMENT_USAGES = "/api/equipment-usages"


def create_activity(client, cycle, cycle_data=None):
    built = cycle_data or cycle()
    activity_type = client.get("/api/activity-types").data[0]
    response = client.post(
        "/api/activities",
        {
            "cycleId": built["cycle"]["id"],
            "typeId": activity_type["id"],
            "plannedDate": "2026-03-10",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def create_equipment(client, name="Tractor"):
    response = client.post(EQUIPMENT, {"name": name}, format="json")
    assert response.status_code == 201, response.data
    return response.data


def create_usage(
    client,
    equipment_id,
    activity_id,
    *,
    hours="2",
    cost_per_hour="10",
    total_cost=None,
):
    payload = {
        "equipmentId": equipment_id,
        "activityId": activity_id,
        "hours": hours,
        "date": "2026-03-10",
    }
    if total_cost is not None:
        payload["totalCost"] = total_cost
    else:
        payload["costPerHour"] = cost_per_hour
    response = client.post(EQUIPMENT_USAGES, payload, format="json")
    assert response.status_code == 201, response.data
    return response.data


def test_equipment_supports_farm_scoped_crud(client):
    assert client.get(EQUIPMENT).data == []

    equipment = create_equipment(client)
    farm_id = client.get("/api/farm").data["id"]
    assert equipment["farmId"] == farm_id
    assert client.get(EQUIPMENT).data == [equipment]
    assert client.get(f"{EQUIPMENT}/{equipment['id']}").data == equipment

    updated = client.put(
        f"{EQUIPMENT}/{equipment['id']}",
        {"name": "Updated tractor"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["name"] == "Updated tractor"
    assert client.delete(f"{EQUIPMENT}/{equipment['id']}").status_code == 204
    assert client.get(EQUIPMENT).data == []


def test_equipment_name_length_on_create_and_update(client):
    max_name = "a" * 255
    too_long = "b" * 256

    created = client.post(EQUIPMENT, {"name": max_name}, format="json")
    assert created.status_code == 201
    assert created.data["name"] == max_name

    rejected = client.post(EQUIPMENT, {"name": too_long}, format="json")
    assert rejected.status_code == 400
    assert rejected.data["field"] == "name"
    assert len(client.get(EQUIPMENT).data) == 1

    url = f"{EQUIPMENT}/{created.data['id']}"
    updated_name = "c" * 255
    updated = client.put(url, {"name": updated_name}, format="json")
    assert updated.status_code == 200
    assert updated.data["name"] == updated_name

    rejected = client.put(url, {"name": too_long}, format="json")
    assert rejected.status_code == 400
    assert rejected.data["field"] == "name"
    assert client.get(url).data["name"] == updated_name


def test_equipment_usage_cost_modes_and_crud(client, cycle):
    activity = create_activity(client, cycle)
    equipment = create_equipment(client)
    hourly = create_usage(
        client,
        equipment["id"],
        activity["id"],
        hours="2.5",
        cost_per_hour="12.25",
    )
    assert hourly["costPerHour"] == 12.25
    assert hourly["totalCost"] is None
    assert hourly["cost"] == 30.625
    assert hourly["date"] == "2026-03-10"
    assert client.get(EQUIPMENT_USAGES).data == [hourly]
    assert client.get(f"{EQUIPMENT_USAGES}/{hourly['id']}").data == hourly

    total = create_usage(
        client,
        equipment["id"],
        activity["id"],
        hours="3",
        total_cost="42.50",
    )
    assert total["costPerHour"] is None
    assert total["totalCost"] == 42.5
    assert total["cost"] == 42.5

    updated = client.put(
        f"{EQUIPMENT_USAGES}/{hourly['id']}",
        {
            "equipmentId": equipment["id"],
            "activityId": activity["id"],
            "hours": "4",
            "totalCost": "50",
            "date": "2026-03-11",
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["hours"] == 4
    assert updated.data["costPerHour"] is None
    assert updated.data["totalCost"] == 50
    assert updated.data["cost"] == 50
    retrieved = client.get(f"{EQUIPMENT_USAGES}/{hourly['id']}")
    assert retrieved.data == updated.data

    assert client.delete(f"{EQUIPMENT_USAGES}/{hourly['id']}").status_code == 204
    assert client.get(f"{EQUIPMENT_USAGES}/{hourly['id']}").status_code == 404


def test_equipment_usage_requires_exactly_one_cost_source(client, cycle):
    activity = create_activity(client, cycle)
    equipment = create_equipment(client)
    base = {
        "equipmentId": equipment["id"],
        "activityId": activity["id"],
        "hours": 1,
        "date": "2026-03-10",
    }
    for payload in (
        {},
        {"costPerHour": 10, "totalCost": 10},
    ):
        response = client.post(
            EQUIPMENT_USAGES, {**base, **payload}, format="json"
        )
        assert response.status_code == 400
        assert "exactly one" in response.data["detail"]


def test_equipment_usage_cost_basis_precision_and_reload_consistency(
    client, cycle
):
    activity = create_activity(client, cycle)
    equipment = create_equipment(client)
    base = {
        "equipmentId": equipment["id"],
        "activityId": activity["id"],
        "hours": "1.2345",
        "costPerHour": "2.3456",
        "date": "2026-03-10",
    }

    over_precision_cases = (
        ("hours", "1.23456", "hours"),
        ("costPerHour", "2.34567", "costPerHour"),
        ("totalCost", "12.34567", "totalCost"),
    )
    for key, value, field in over_precision_cases:
        payload = {**base, key: value}
        if key == "totalCost":
            payload.pop("costPerHour")
        response = client.post(EQUIPMENT_USAGES, payload, format="json")
        assert response.status_code == 400
        assert response.data["field"] == field

    created = client.post(EQUIPMENT_USAGES, base, format="json")
    assert created.status_code == 201, created.data

    persisted = EquipmentUsage.objects.get(pk=created.data["id"])
    assert persisted.cost == persisted.hours * persisted.cost_per_hour
    reloaded = client.get(f"{EQUIPMENT_USAGES}/{created.data['id']}")
    assert reloaded.status_code == 200
    assert reloaded.data == created.data
    assert Decimal(str(reloaded.data["cost"])) == persisted.cost


def test_equipment_usage_rejects_missing_references_and_invalid_hours(
    client, cycle
):
    activity = create_activity(client, cycle)
    equipment = create_equipment(client)
    base = {
        "equipmentId": equipment["id"],
        "activityId": activity["id"],
        "hours": 1,
        "costPerHour": 5,
        "date": "2026-03-10",
    }
    for key, value, field in (
        ("equipmentId", "00000000-0000-0000-0000-000000000000", "equipmentId"),
        ("activityId", "00000000-0000-0000-0000-000000000000", "activityId"),
    ):
        response = client.post(
            EQUIPMENT_USAGES, {**base, key: value}, format="json"
        )
        assert response.status_code == 404
        assert response.data["field"] == field

    for hours in ("0", "-1"):
        response = client.post(
            EQUIPMENT_USAGES, {**base, "hours": hours}, format="json"
        )
        assert response.status_code == 400
        assert response.data["field"] == "hours"
        assert "greater than zero" in response.data["detail"]


def test_equipment_usage_activity_filter_and_empty_results(client, cycle):
    built = cycle()
    first_activity = create_activity(client, cycle, built)
    second_activity = create_activity(client, cycle, built)
    empty_activity = create_activity(client, cycle, built)
    equipment = create_equipment(client)
    first_usage = create_usage(
        client, equipment["id"], first_activity["id"]
    )
    create_usage(client, equipment["id"], second_activity["id"])

    assert client.get(
        f"{EQUIPMENT_USAGES}?activityId={first_activity['id']}"
    ).data == [first_usage]
    assert client.get(
        f"{EQUIPMENT_USAGES}?activityId=00000000-0000-0000-0000-000000000000"
    ).data == []
    assert client.get(
        f"{EQUIPMENT_USAGES}?activityId={empty_activity['id']}"
    ).data == []
    invalid = client.get(f"{EQUIPMENT_USAGES}?activityId=not-a-uuid")
    assert invalid.status_code == 400
    assert invalid.data["field"] == "activityId"


def test_equipment_usage_and_equipment_are_farm_scoped(client, cycle):
    activity = create_activity(client, cycle)
    equipment = create_equipment(client)

    other_client = APIClient()
    registered = register(
        other_client, email="other-equipment-farm@agrivanta.test"
    )
    assert registered.status_code == 201, registered.data
    other_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {registered.data['token']}"
    )
    other_equipment = create_equipment(other_client, "Other tractor")
    assert other_client.get(EQUIPMENT).data == [other_equipment]
    assert other_client.get(EQUIPMENT_USAGES).data == []
    assert client.get(EQUIPMENT).data == [equipment]

    cross_farm_usage = client.post(
        EQUIPMENT_USAGES,
        {
            "equipmentId": other_equipment["id"],
            "activityId": activity["id"],
            "hours": 1,
            "costPerHour": 5,
            "date": "2026-03-10",
        },
        format="json",
    )
    assert cross_farm_usage.status_code == 404
    assert cross_farm_usage.data["field"] == "equipmentId"
    assert other_client.get(
        f"{EQUIPMENT}/{equipment['id']}"
    ).status_code == 404


def test_equipment_with_usage_records_cannot_be_deleted(client, cycle):
    activity = create_activity(client, cycle)
    equipment = create_equipment(client)
    usage = create_usage(client, equipment["id"], activity["id"])

    response = client.delete(f"{EQUIPMENT}/{equipment['id']}")
    assert response.status_code == 409
    assert "usage records cannot be deleted" in response.data["detail"]
    assert client.get(f"{EQUIPMENT}/{equipment['id']}").status_code == 200
    assert client.get(f"{EQUIPMENT_USAGES}/{usage['id']}").status_code == 200


def test_equipment_and_usage_endpoints_require_authentication(anon):
    for path in (
        EQUIPMENT,
        f"{EQUIPMENT}/00000000-0000-0000-0000-000000000000",
        EQUIPMENT_USAGES,
        f"{EQUIPMENT_USAGES}/00000000-0000-0000-0000-000000000000",
    ):
        assert anon.get(path).status_code == 401
        assert anon.post(path, {}, format="json").status_code == 401
        assert anon.put(path, {}, format="json").status_code == 401
        assert anon.delete(path).status_code == 401
