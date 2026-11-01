from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.models import CropCycle, CycleStatus, CycleType, Field


URL = "/api/crop-cycles"


def create_cycle(client, data, **overrides):
    payload = {
        "fieldId": data["field"]["id"],
        "cropId": data["crop"]["id"],
        "cycleType": "annual",
        "startDate": "2026-03-01",
    }
    if "variety" in data and data["variety"]:
        payload["varietyId"] = data["variety"]["id"]
    payload.update(overrides)
    response = client.post(URL, payload, format="json")
    assert response.status_code == 201, response.data
    return response.data


def create_other_farm():
    client = APIClient()
    response = client.post(
        "/api/auth/register",
        {
            "name": "Second Farm Owner",
            "email": "second-owner@agrivanta.test",
            "password": "OliveHarvest#42",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {response.data['token']}"
    )
    return client


def create_setup(client, label="Second"):
    field = client.post(
        "/api/fields",
        {"name": f"{label} Field", "area": "4"},
        format="json",
    )
    crop = client.post(
        "/api/crops", {"name": f"{label} Crop"}, format="json"
    )
    assert field.status_code == crop.status_code == 201
    variety = client.post(
        "/api/varieties",
        {"cropId": crop.data["id"], "name": f"{label} Variety"},
        format="json",
    )
    assert variety.status_code == 201
    return {
        "field": field.data,
        "crop": crop.data,
        "variety": variety.data,
    }


def test_optional_variety_and_overlapping_identical_cycles_are_independent(
    client, setup
):
    data = setup()
    data = {**data, "variety": None}
    first = create_cycle(
        client,
        data,
        cycleType="perennial",
        endDate="2026-03-01",
    )
    second = create_cycle(
        client,
        data,
        cycleType="perennial",
        endDate="2026-03-01",
    )
    overlap = create_cycle(
        client,
        data,
        cycleType="perennial",
        startDate="2026-03-01",
        endDate="2026-03-10",
    )

    assert first["varietyId"] is None
    assert first["cycleType"] == "perennial"
    assert first["status"] == "open"
    assert first["startDate"] == first["endDate"] == "2026-03-01"
    assert second["id"] != first["id"]
    assert overlap["id"] not in {first["id"], second["id"]}
    listed = client.get(URL, {"field": data["field"]["id"]})
    assert listed.status_code == 200
    assert {cycle["id"] for cycle in listed.data} == {
        first["id"],
        second["id"],
        overlap["id"],
    }


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"cycleType": None}, "cycleType"),
        ({"cycleType": ""}, "cycleType"),
        ({"cycleType": "biennial"}, "cycleType"),
        ({"cycleType": "ANNUAL"}, "cycleType"),
        ({"startDate": None}, "startDate"),
        ({"startDate": "2026-02-30"}, "startDate"),
        ({"endDate": "not-a-date"}, "endDate"),
        ({"endDate": "2026-02-28"}, "endDate"),
        ({"status": "archived"}, "status"),
    ],
)
def test_create_rejects_invalid_designation_dates_and_status(
    client, setup, overrides, field
):
    data = setup()
    payload = {
        "fieldId": data["field"]["id"],
        "cropId": data["crop"]["id"],
        "cycleType": "annual",
        "startDate": "2026-03-01",
        **overrides,
    }
    response = client.post(URL, payload, format="json")
    assert response.status_code == 400
    assert response.data["field"] == field


@pytest.mark.parametrize("missing", ["fieldId", "cropId", "cycleType", "startDate"])
def test_create_requires_field_crop_cycle_type_and_start_date(
    client, setup, missing
):
    data = setup()
    payload = {
        "fieldId": data["field"]["id"],
        "cropId": data["crop"]["id"],
        "cycleType": "annual",
        "startDate": "2026-03-01",
    }
    payload.pop(missing)
    response = client.post(URL, payload, format="json")
    assert response.status_code == 400
    assert response.data["field"] == missing


def test_create_validates_farm_scope_and_crop_variety_match(
    client, setup
):
    local = setup()
    local_other_crop = client.post(
        "/api/crops", {"name": "Local Other Crop"}, format="json"
    ).data
    local_other_variety = client.post(
        "/api/varieties",
        {
            "cropId": local_other_crop["id"],
            "name": "Local Other Variety",
        },
        format="json",
    ).data
    foreign_client = create_other_farm()
    foreign = create_setup(foreign_client, "Foreign")
    base = {
        "fieldId": local["field"]["id"],
        "cropId": local["crop"]["id"],
        "cycleType": "annual",
        "startDate": "2026-03-01",
    }

    mismatch = client.post(
        URL,
        {**base, "varietyId": local_other_variety["id"]},
        format="json",
    )
    assert mismatch.status_code == 400
    for payload in (
        {**base, "fieldId": foreign["field"]["id"]},
        {**base, "cropId": foreign["crop"]["id"]},
        {**base, "varietyId": foreign["variety"]["id"]},
    ):
        response = client.post(URL, payload, format="json")
        assert response.status_code == 404


def test_detail_full_update_and_date_boundaries(client, setup):
    data = setup()
    created = create_cycle(client, data)
    other_field = client.post(
        "/api/fields", {"name": "South Field", "area": "5"}, format="json"
    ).data
    other_crop = client.post(
        "/api/crops", {"name": "Barley"}, format="json"
    ).data
    other_variety = client.post(
        "/api/varieties",
        {"cropId": other_crop["id"], "name": "Spring Barley"},
        format="json",
    ).data

    updated = client.put(
        f"{URL}/{created['id']}",
        {
            "fieldId": other_field["id"],
            "cropId": other_crop["id"],
            "varietyId": other_variety["id"],
            "cycleType": "perennial",
            "startDate": "2026-05-01",
            "endDate": "2026-05-01",
            "expectedYield": "120",
            "expectedPrice": "0.75",
        },
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.data["fieldId"] == other_field["id"]
    assert updated.data["cropId"] == other_crop["id"]
    assert updated.data["varietyId"] == other_variety["id"]
    assert updated.data["cycleType"] == "perennial"
    assert updated.data["startDate"] == updated.data["endDate"] == "2026-05-01"
    assert updated.data["expectedYield"] == 120
    assert updated.data["expectedPrice"] == 0.75
    assert client.get(f"{URL}/{created['id']}").data == updated.data

    invalid = client.patch(
        f"{URL}/{created['id']}",
        {"startDate": "2026-06-01"},
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.data["field"] == "endDate"
    assert client.patch(
        f"{URL}/{created['id']}",
        {"status": "unknown"},
        format="json",
    ).status_code == 400
    assert client.patch(
        f"{URL}/{created['id']}",
        {"cropId": data["crop"]["id"]},
        format="json",
    ).status_code == 400


def test_expected_amounts_accept_maximum_model_precision_on_create_and_update(
    client, setup
):
    data = setup()
    maximum = "9999999999.9999"
    created = create_cycle(
        client,
        data,
        expectedYield=maximum,
        expectedPrice=maximum,
    )
    cycle = CropCycle.objects.get(pk=created["id"])
    assert cycle.expected_yield == Decimal(maximum)
    assert cycle.expected_price == Decimal(maximum)

    updated = client.patch(
        f"{URL}/{created['id']}",
        {"expectedYield": "9999999998.9999", "expectedPrice": maximum},
        format="json",
    )
    assert updated.status_code == 200, updated.data
    cycle.refresh_from_db()
    assert cycle.expected_yield == Decimal("9999999998.9999")
    assert cycle.expected_price == Decimal(maximum)


@pytest.mark.parametrize(
    ("field", "too_large"),
    [
        ("expectedYield", "10000000000"),
        ("expectedYield", "0.00001"),
        ("expectedPrice", "10000000000"),
        ("expectedPrice", "0.00001"),
    ],
)
def test_expected_amounts_reject_precision_overflow_on_create_and_update(
    client, setup, field, too_large
):
    data = setup()
    initial_count = CropCycle.objects.count()
    invalid_create = client.post(
        URL,
        {
            "fieldId": data["field"]["id"],
            "cropId": data["crop"]["id"],
            "cycleType": "annual",
            "startDate": "2026-03-01",
            field: too_large,
        },
        format="json",
    )
    assert invalid_create.status_code == 400
    assert invalid_create.data["field"] == field
    assert CropCycle.objects.count() == initial_count

    created = create_cycle(
        client,
        data,
        expectedYield="120.5",
        expectedPrice="0.75",
    )
    unchanged_values = {
        "expectedYield": Decimal("120.5"),
        "expectedPrice": Decimal("0.75"),
    }
    invalid_update = client.patch(
        f"{URL}/{created['id']}", {field: too_large}, format="json"
    )
    assert invalid_update.status_code == 400
    assert invalid_update.data["field"] == field
    cycle = CropCycle.objects.get(pk=created["id"])
    assert cycle.expected_yield == unchanged_values["expectedYield"]
    assert cycle.expected_price == unchanged_values["expectedPrice"]


def test_cycle_reads_and_writes_are_farm_scoped(client, setup):
    data = setup()
    created = create_cycle(client, data)
    foreign_client = create_other_farm()

    assert foreign_client.get(URL).data == []
    assert foreign_client.get(f"{URL}/{created['id']}").status_code == 404
    assert (
        foreign_client.put(
            f"{URL}/{created['id']}",
            {"cycleType": "perennial"},
            format="json",
        ).status_code
        == 404
    )
    assert foreign_client.delete(f"{URL}/{created['id']}").status_code == 404


def test_update_rejects_cross_farm_references(client, setup):
    data = setup()
    created = create_cycle(client, data)
    foreign_client = create_other_farm()
    foreign = create_setup(foreign_client, "Foreign")

    for update in (
        {"fieldId": foreign["field"]["id"]},
        {"cropId": foreign["crop"]["id"]},
        {"varietyId": foreign["variety"]["id"]},
    ):
        response = client.patch(
            f"{URL}/{created['id']}", update, format="json"
        )
        assert response.status_code == 404


def test_close_read_reopen_update_and_delete_lifecycle(client, setup):
    data = setup()
    created = create_cycle(client, data, endDate="2026-10-01")
    closed = client.post(f"{URL}/{created['id']}/close")
    assert closed.status_code == 200
    assert closed.data["status"] == "closed"
    assert closed.data["endDate"] == "2026-10-01"
    assert client.get(f"{URL}/{created['id']}").status_code == 200
    assert client.put(
        f"{URL}/{created['id']}", {"cycleType": "perennial"}, format="json"
    ).status_code == 409
    assert client.delete(f"{URL}/{created['id']}").status_code == 409
    assert client.post(f"{URL}/{created['id']}/close").status_code == 409

    reopened = client.post(f"{URL}/{created['id']}/reopen")
    assert reopened.status_code == 200
    assert reopened.data["status"] == "open"
    assert reopened.data["endDate"] == "2026-10-01"
    assert client.post(f"{URL}/{created['id']}/reopen").status_code == 409
    cleared = client.patch(
        f"{URL}/{created['id']}",
        {"endDate": None},
        format="json",
    )
    assert cleared.status_code == 200
    assert "endDate" not in cleared.data
    assert CropCycle.objects.get(pk=created["id"]).end_date is None
    assert client.delete(f"{URL}/{created['id']}").status_code == 204
    assert client.get(f"{URL}/{created['id']}").status_code == 404


def test_manager_can_reopen_cycle(client, setup):
    data = setup()
    created = create_cycle(client, data)
    assert client.post(f"{URL}/{created['id']}/close").status_code == 200
    user = get_user_model().objects.get(email="owner@agrivanta.test")
    user.role = "manager"
    user.save(update_fields=["role"])
    client.force_authenticate(user=user)

    reopened = client.post(f"{URL}/{created['id']}/reopen")
    assert reopened.status_code == 200
    assert reopened.data["status"] == "open"


def test_worker_cannot_write_or_reopen_crop_cycles(client, setup):
    data = setup()
    created = create_cycle(client, data)
    user = get_user_model().objects.get(email="owner@agrivanta.test")
    user.role = "worker"
    user.save(update_fields=["role"])
    client.force_authenticate(user=user)

    requests = (
        client.post(
            URL,
            {
                "fieldId": data["field"]["id"],
                "cropId": data["crop"]["id"],
                "cycleType": "annual",
                "startDate": "2026-04-01",
            },
            format="json",
        ),
        client.put(
            f"{URL}/{created['id']}",
            {"cycleType": "perennial"},
            format="json",
        ),
        client.delete(f"{URL}/{created['id']}"),
        client.post(f"{URL}/{created['id']}/close"),
    )
    assert [response.status_code for response in requests] == [403] * 4

    user.role = "owner"
    user.save(update_fields=["role"])
    client.force_authenticate(user=user)
    assert client.post(f"{URL}/{created['id']}/close").status_code == 200
    user.role = "worker"
    user.save(update_fields=["role"])
    client.force_authenticate(user=user)
    assert client.post(f"{URL}/{created['id']}/reopen").status_code == 403


def test_legacy_model_cycle_without_type_or_variety_is_unclassified(
    client, setup
):
    data = setup()
    field = Field.objects.get(pk=data["field"]["id"])
    cycle = CropCycle.objects.create(
        farm=field.farm,
        field=field,
        crop_id=data["crop"]["id"],
        variety=None,
        cycle_type=None,
        start_date=date(2025, 1, 1),
    )

    response = client.get(f"{URL}/{cycle.id}")
    assert response.status_code == 200
    assert response.data["cycleType"] is None
    assert response.data["varietyId"] is None
    assert CycleType.values == ["annual", "perennial"]
    assert cycle.status == CycleStatus.OPEN
