from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from api.models import (
    Activity,
    ActivityType,
    Farm,
    Role,
    User,
)
from api.views import STANDARD_ACTIVITY_TEMPLATES, seed_farm


URL = "/api/activity-types"
EXPECTED_STANDARD_TYPES = [
    ("Land preparation", "land preparation"),
    ("Planting", "planting"),
    ("Fertilizing", "fertilizing"),
    ("Spraying", "spraying"),
    ("Harvesting", "harvesting"),
]


def create_custom_type(client, **overrides):
    payload = {"name": "Scouting", "category": "field scouting"}
    payload.update(overrides)
    return client.post(URL, payload, format="json")


def new_farm_client(*, seed=False):
    user = User.objects.create_user(
        email=f"farm-{User.objects.count()}@agrivanta.test",
        password="SafePassword#42",
    )
    farm = Farm.objects.create(
        owner=user, name="Another farm", reporting_currency="USD"
    )
    if seed:
        seed_farm(farm)
    client = APIClient()
    client.force_authenticate(user=user)
    return client, farm


def test_standard_activity_templates_are_canonical_and_idempotent(client):
    assert [
        (name, category.value)
        for name, category in STANDARD_ACTIVITY_TEMPLATES
    ] == EXPECTED_STANDARD_TYPES
    types = client.get(URL).data
    assert sorted(
        (item["name"], item["category"]) for item in types
    ) == sorted(EXPECTED_STANDARD_TYPES)
    assert all(item["standard"] for item in types)
    assert all(
        item["inputs"] == []
        and item["labourHours"] == 0
        and item["equipment"] == ""
        for item in types
    )

    custom = create_custom_type(
        client,
        inputs=[{"itemName": "Seed", "quantity": 3}],
        labourHours=2,
        equipment="Planter",
    )
    assert custom.status_code == 201
    farm = User.objects.get(email="owner@agrivanta.test").farm
    custom_before = ActivityType.objects.get(pk=custom.data["id"])
    custom_defaults = (
        custom_before.category,
        custom_before.default_inputs,
        custom_before.default_labour_hours,
        custom_before.default_equipment,
    )

    seed_farm(farm)
    seed_farm(farm)
    assert ActivityType.objects.filter(farm=farm, standard=True).count() == 5
    custom_before.refresh_from_db()
    assert (
        custom_before.category,
        custom_before.default_inputs,
        custom_before.default_labour_hours,
        custom_before.default_equipment,
    ) == custom_defaults
    assert farm.customers.count() == 2

    other_client, other_farm = new_farm_client(seed=True)
    assert ActivityType.objects.filter(farm=other_farm, standard=True).count() == 5
    assert len(other_client.get(URL).data) == 5
    assert not set(
        item["id"] for item in other_client.get(URL).data
    ) & set(item["id"] for item in types)


def test_activity_type_list_is_farm_scoped_and_can_be_empty(client):
    listed = client.get(URL)
    assert listed.status_code == 200
    assert len(listed.data) == 5

    other_client, _ = new_farm_client()
    assert other_client.get(URL).data == []


def test_activity_type_defaults_round_trip_and_are_not_applied_to_activities(
    client, cycle
):
    built = cycle()
    created = create_custom_type(
        client,
        name="Field scouting",
        inputs=[
            {"itemName": "Seed", "quantity": "2.5"},
            {"itemName": "Fuel", "quantity": 4},
        ],
        labourHours="3.25",
        equipment="Tractor",
        farmId="not-accepted",
    )
    assert created.status_code == 201
    assert created.data["inputs"] == [
        {"itemName": "Seed", "quantity": 2.5},
        {"itemName": "Fuel", "quantity": 4},
    ]
    assert created.data["labourHours"] == 3.25
    assert created.data["equipment"] == "Tractor"
    assert "farmId" not in created.data
    persisted = ActivityType.objects.get(pk=created.data["id"])
    assert persisted.farm_id == User.objects.get(
        email="owner@agrivanta.test"
    ).farm.id
    assert persisted.default_inputs == [
        {"itemName": "Seed", "quantity": "2.5"},
        {"itemName": "Fuel", "quantity": "4"},
    ]
    assert persisted.default_labour_hours == Decimal("3.25")
    assert persisted.default_equipment == "Tractor"

    listed = client.get(URL)
    assert next(item for item in listed.data if item["id"] == created.data["id"]) == (
        created.data
    )
    detail_url = f"{URL}/{created.data['id']}"
    assert client.get(detail_url).data == created.data

    activity_response = client.post(
        "/api/activities",
        {
            "cycleId": built["cycle"]["id"],
            "typeId": created.data["id"],
            "plannedDate": "2026-03-10",
        },
        format="json",
    )
    assert activity_response.status_code == 201
    assert activity_response.data["resourceNeeds"] == {
        "inputs": [],
        "labourHours": 0,
        "equipment": "",
    }

    changed = client.put(
        f"/api/activities/{activity_response.data['id']}/resource-needs",
        {
            "inputs": [{"itemName": "Seed", "quantity": 8}],
            "labourHours": 1,
            "equipment": "Seeder",
        },
        format="json",
    )
    assert changed.status_code == 200
    assert changed.data["resourceNeeds"]["inputs"][0]["quantity"] == 8
    assert client.get(detail_url).data == created.data


def test_custom_activity_type_put_patch_and_delete(client):
    created = create_custom_type(
        client,
        name="  Soil testing ",
        category="  lab work ",
        inputs=[{"itemName": "Sample bags", "quantity": 2}],
        labourHours=1.5,
        equipment="Sampler",
    )
    assert created.status_code == 201
    assert created.data["name"] == "Soil testing"
    assert created.data["category"] == "lab work"

    detail_url = f"{URL}/{created.data['id']}"
    patched = client.patch(
        detail_url,
        {"name": "  Soil analysis  "},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.data["name"] == "Soil analysis"
    assert patched.data["category"] == "lab work"
    assert patched.data["inputs"] == created.data["inputs"]
    assert patched.data["labourHours"] == 1.5
    assert patched.data["equipment"] == "Sampler"

    replaced = client.put(
        detail_url,
        {"name": "Soil survey", "category": "custom category"},
        format="json",
    )
    assert replaced.status_code == 200
    assert replaced.data["inputs"] == []
    assert replaced.data["labourHours"] == 0
    assert replaced.data["equipment"] == ""

    assert client.delete(detail_url).status_code == 204
    assert client.get(detail_url).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "other"},
        {"name": "", "category": "other"},
        {"name": "  ", "category": "other"},
        {"name": "x" * 256, "category": "other"},
        {"name": "Valid", "category": ""},
        {"name": "Valid", "category": "   "},
        {"name": "Valid", "category": "x" * 33},
    ],
)
def test_activity_type_create_rejects_invalid_names_and_categories(
    client, payload
):
    response = client.post(URL, payload, format="json")
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("put", {"category": "other"}),
        ("put", {"name": "", "category": "other"}),
        ("put", {"name": "  ", "category": "other"}),
        ("put", {"name": "x" * 256, "category": "other"}),
        ("patch", {"name": ""}),
        ("patch", {"name": "  "}),
        ("patch", {"name": "x" * 256}),
        ("patch", {"category": ""}),
        ("patch", {"category": " "}),
        ("patch", {"category": "x" * 33}),
    ],
)
def test_activity_type_update_rejects_invalid_names_and_categories(
    client, method, payload
):
    created = create_custom_type(client)
    response = getattr(client, method)(
        f"{URL}/{created.data['id']}", payload, format="json"
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "defaults",
    [
        {"inputs": "not-a-list"},
        {"inputs": [{}]},
        {"inputs": [{"itemName": "Seed", "quantity": 0}]},
        {"inputs": [{"itemName": "Seed", "quantity": -1}]},
        {"inputs": [{"itemName": " ", "quantity": 1}]},
        {"labourHours": -0.1},
        {"labourHours": "1.00001"},
        {"equipment": "e" * 256},
    ],
)
def test_activity_type_default_resources_are_validated(client, defaults):
    response = create_custom_type(client, **defaults)
    assert response.status_code == 400


def test_activity_type_names_are_unique_after_trim_and_casefold(client):
    created = create_custom_type(client, name="  Irrigation  ")
    assert created.status_code == 201
    duplicate_standard = create_custom_type(client, name=" planting ")
    assert duplicate_standard.status_code == 409
    duplicate_custom = create_custom_type(client, name="IRRIGATION")
    assert duplicate_custom.status_code == 409

    conflict = client.patch(
        f"{URL}/{created.data['id']}",
        {"name": "PLANTING"},
        format="json",
    )
    assert conflict.status_code == 409

    other_client, _ = new_farm_client()
    same_name_other_farm = create_custom_type(
        other_client, name="irrigation"
    )
    assert same_name_other_farm.status_code == 201


def test_activity_type_detail_is_farm_scoped(client):
    created = create_custom_type(client)
    other_client, _ = new_farm_client()

    assert other_client.get(f"{URL}/{created.data['id']}").status_code == 404
    assert (
        other_client.patch(
            f"{URL}/{created.data['id']}",
            {"name": "Changed"},
            format="json",
        ).status_code
        == 404
    )
    assert client.get(f"{URL}/not-a-uuid").status_code == 404
    assert client.get(
        f"{URL}/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_standard_activity_types_are_read_only(client):
    standard_id = client.get(URL).data[0]["id"]
    detail_url = f"{URL}/{standard_id}"

    assert client.put(
        detail_url,
        {"name": "Changed", "category": "changed"},
        format="json",
    ).status_code == 409
    assert client.patch(
        detail_url, {"name": "Changed"}, format="json"
    ).status_code == 409
    assert client.delete(detail_url).status_code == 409


def test_owner_and_manager_can_write_but_workers_can_only_read(client):
    created = create_custom_type(client)
    user = User.objects.get(email="owner@agrivanta.test")
    user.role = Role.MANAGER
    user.save(update_fields=["role"])
    client.force_authenticate(user=user)
    assert client.patch(
        f"{URL}/{created.data['id']}",
        {"name": "Manager update"},
        format="json",
    ).status_code == 200
    manager_created = create_custom_type(
        client, name="Manager type"
    )
    assert manager_created.status_code == 201
    assert (
        client.delete(f"{URL}/{manager_created.data['id']}").status_code
        == 204
    )

    user.role = Role.WORKER
    user.save(update_fields=["role"])
    client.force_authenticate(user=user)
    assert client.get(URL).status_code == 200
    assert client.get(f"{URL}/{created.data['id']}").status_code == 200
    requests = (
        client.post(
            URL, {"name": "New", "category": "other"}, format="json"
        ),
        client.put(
            f"{URL}/{created.data['id']}",
            {"name": "Worker update", "category": "other"},
            format="json",
        ),
        client.patch(
            f"{URL}/{created.data['id']}",
            {"name": "Worker update"},
            format="json",
        ),
        client.delete(f"{URL}/{created.data['id']}"),
    )
    assert [response.status_code for response in requests] == [403] * 4


def test_delete_protects_activity_type_referenced_by_activity(client, cycle):
    built = cycle()
    created = create_custom_type(client)
    activity_response = client.post(
        "/api/activities",
        {
            "cycleId": built["cycle"]["id"],
            "typeId": created.data["id"],
            "plannedDate": "2026-03-10",
        },
        format="json",
    )
    assert activity_response.status_code == 201

    deleted = client.delete(f"{URL}/{created.data['id']}")
    assert deleted.status_code == 409
    assert ActivityType.objects.filter(pk=created.data["id"]).exists()
    assert Activity.objects.filter(pk=activity_response.data["id"]).exists()


def test_unauthenticated_activity_type_requests_are_denied(anon):
    assert anon.get(URL).status_code == 401
    assert anon.post(
        URL, {"name": "New", "category": "other"}, format="json"
    ).status_code == 401
    detail_url = f"{URL}/00000000-0000-0000-0000-000000000000"
    assert anon.get(detail_url).status_code == 401
    assert anon.patch(detail_url, {"name": "New"}, format="json").status_code == 401
    assert anon.delete(detail_url).status_code == 401
