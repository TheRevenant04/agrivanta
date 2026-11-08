from rest_framework.test import APIClient

from api.models import User

from .conftest import register


URL = "/api/farm-setup/status"


def test_setup_status_requires_an_authenticated_farm_owner(anon):
    assert anon.get(URL).status_code == 401


def test_setup_status_reports_each_step_and_completion(client):
    incomplete = client.get(URL)
    assert incomplete.status_code == 200
    assert incomplete.data == {
        "steps": {
            "farm": False,
            "fields": False,
            "crops": False,
            "initialCycle": False,
        },
        "complete": False,
        "nextStep": "farm",
    }

    saved_farm = client.put(
        "/api/farm",
        {"name": "Willow Creek Farm", "reportingCurrency": "USD"},
        format="json",
    )
    assert saved_farm.status_code == 200
    assert client.get(URL).data["nextStep"] == "fields"

    field = client.post(
        "/api/fields",
        {"name": "North Field", "area": 12.5},
        format="json",
    )
    assert field.status_code == 201
    assert client.get(URL).data["nextStep"] == "crops"

    crop = client.post("/api/crops", {"name": "Wheat"}, format="json")
    assert crop.status_code == 201
    without_variety = client.get(URL)
    assert without_variety.data["steps"]["crops"] is False
    assert without_variety.data["nextStep"] == "crops"

    variety = client.post(
        "/api/varieties",
        {"cropId": crop.data["id"], "name": "Winter Wheat"},
        format="json",
    )
    assert variety.status_code == 201
    assert client.get(URL).data["nextStep"] == "initialCycle"

    cycle = client.post(
        "/api/crop-cycles",
        {
            "fieldId": field.data["id"],
            "cropId": crop.data["id"],
            "cycleType": "annual",
            "startDate": "2026-03-01",
        },
        format="json",
    )
    assert cycle.status_code == 201, cycle.data

    complete = client.get(URL)
    assert complete.status_code == 200
    assert complete.data == {
        "steps": {
            "farm": True,
            "fields": True,
            "crops": True,
            "initialCycle": True,
        },
        "complete": True,
        "nextStep": None,
    }


def test_setup_status_only_counts_the_authenticated_users_farm(client):
    client.post(
        "/api/fields",
        {"name": "North Field", "area": 12.5},
        format="json",
    )
    response = register(
        APIClient(),
        name="Second Owner",
        email="second-owner@agrivanta.test",
    )
    assert response.status_code == 201

    other_owner = APIClient()
    other_owner.force_authenticate(
        user=User.objects.get(email="second-owner@agrivanta.test")
    )
    other_status = other_owner.get(URL)
    assert other_status.status_code == 200
    assert other_status.data["nextStep"] == "farm"
    assert other_status.data["steps"]["fields"] is False
