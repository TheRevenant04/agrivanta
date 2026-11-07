import pytest
from rest_framework.test import APIClient

from api.audit import system_actor

REGISTER = "/api/auth/register"


def register(client, **overrides):
    payload = {
        "name": "Olive Owner",
        "email": "owner@agrivanta.test",
        "password": "OliveHarvest#42",
    }
    payload.update(overrides)
    return client.post(REGISTER, payload, format="json")


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture(autouse=True)
def explicit_system_actor_for_test_setup():
    with system_actor():
        yield


@pytest.fixture
def session(db):
    client = APIClient()
    response = register(client)
    assert response.status_code == 201, response.data
    token = response.data["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return {
        "client": client,
        "token": token,
        "user": response.data["user"],
        "response": response,
    }


@pytest.fixture
def client(session):
    return session["client"]


@pytest.fixture
def setup(client):
    """Create one field, crop, variety, and unit through the API."""

    def _build():
        field = client.post(
            "/api/fields",
            {"name": "North 40", "area": "12.5"},
            format="json",
        )
        crop = client.post(
            "/api/crops", {"name": "Wheat"}, format="json"
        )
        variety = client.post(
            "/api/varieties",
            {"cropId": crop.data["id"], "name": "Winter Wheat"},
            format="json",
        )
        unit = client.post(
            "/api/units",
            {"name": "kg", "baseMeasure": "mass"},
            format="json",
        )
        assert field.status_code == 201, field.data
        assert crop.status_code == 201, crop.data
        assert variety.status_code == 201, variety.data
        assert unit.status_code == 201, unit.data
        return {
            "field": field.data,
            "crop": crop.data,
            "variety": variety.data,
            "unit": unit.data,
        }

    return _build


@pytest.fixture
def cycle(client, setup):
    def _build(data=None):
        data = data or setup()
        response = client.post(
            "/api/crop-cycles",
            {
                "fieldId": data["field"]["id"],
                "cropId": data["crop"]["id"],
                "varietyId": data["variety"]["id"],
                "cycleType": "annual",
                "startDate": "2026-03-01",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        return {**data, "cycle": response.data}

    return _build
