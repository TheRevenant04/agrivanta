import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from api.models import (
    Crop,
    CropCycle,
    Farm,
    Harvest,
    InventoryItem,
    Role,
    Unit,
    UnitConversion,
    User,
    Variety,
)

from api.tests.conftest import register


def api_request(client, method, url, payload=None):
    caller = getattr(client, method)
    if method in {"get", "delete"}:
        return caller(url)
    return caller(url, payload or {}, format="json")


def create_crop(client, name="Wheat"):
    response = client.post("/api/crops", {"name": name}, format="json")
    assert response.status_code == 201, response.data
    return response.data


def create_variety(client, crop_id, name="Winter"):
    response = client.post(
        "/api/varieties",
        {"cropId": crop_id, "name": name},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def create_unit(client, name="kg", base_measure="mass"):
    response = client.post(
        "/api/units",
        {"name": name, "baseMeasure": base_measure},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def test_crop_supports_full_crud_and_empty_collection(client):
    assert client.get("/api/crops").data == []

    created = create_crop(client)
    url = f"/api/crops/{created['id']}"
    assert client.get(url).data == created

    replaced = client.put(url, {"name": "Barley"}, format="json")
    assert replaced.status_code == 200
    assert replaced.data["name"] == "Barley"

    unchanged = client.patch(url, {}, format="json")
    assert unchanged.status_code == 200
    assert unchanged.data["name"] == "Barley"

    patched = client.patch(url, {"name": "Oats"}, format="json")
    assert patched.status_code == 200
    assert patched.data["name"] == "Oats"

    assert client.get("/api/crops").data == [patched.data]
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get("/api/crops").data == []


def test_variety_supports_full_crud_and_empty_collection(client):
    assert client.get("/api/varieties").data == []
    crop = create_crop(client)
    variety = create_variety(client, crop["id"])
    url = f"/api/varieties/{variety['id']}"

    assert client.get(url).data == variety
    replaced = client.put(
        url,
        {"cropId": crop["id"], "name": "Spring"},
        format="json",
    )
    assert replaced.status_code == 200
    assert replaced.data["name"] == "Spring"

    unchanged = client.patch(url, {}, format="json")
    assert unchanged.status_code == 200
    assert unchanged.data["cropId"] == crop["id"]
    assert unchanged.data["name"] == "Spring"

    other_crop = create_crop(client, "Maize")
    renamed = client.patch(url, {"name": "Hybrid"}, format="json")
    assert renamed.status_code == 200
    assert renamed.data["cropId"] == crop["id"]
    moved = client.patch(
        url, {"cropId": other_crop["id"]}, format="json"
    )
    assert moved.status_code == 200
    assert moved.data["cropId"] == other_crop["id"]
    assert moved.data["name"] == "Hybrid"

    assert client.get("/api/varieties").status_code == 200
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get("/api/varieties").data == []


def test_unit_supports_full_crud_and_empty_collection(client):
    assert client.get("/api/units").data == []
    unit = create_unit(client)
    url = f"/api/units/{unit['id']}"
    assert client.get(url).data == unit

    replaced = client.put(
        url,
        {"name": "tonne", "baseMeasure": "mass"},
        format="json",
    )
    assert replaced.status_code == 200
    assert replaced.data["name"] == "tonne"

    unchanged = client.patch(url, {}, format="json")
    assert unchanged.status_code == 200
    assert unchanged.data["name"] == "tonne"
    assert unchanged.data["baseMeasure"] == "mass"

    patched = client.patch(
        url, {"baseMeasure": "count"}, format="json"
    )
    assert patched.status_code == 200
    assert patched.data["name"] == "tonne"
    assert patched.data["baseMeasure"] == "count"
    renamed = client.patch(url, {"name": "bundle"}, format="json")
    assert renamed.status_code == 200
    assert renamed.data["baseMeasure"] == "count"

    assert client.get("/api/units").data == [renamed.data]
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get("/api/units").data == []


@pytest.mark.parametrize(
    "method",
    ["post", "put", "patch"],
)
def test_crop_requires_a_nonblank_name_and_reports_invalid_values(
    client, method
):
    crop = create_crop(client)
    url = f"/api/crops/{crop['id']}"
    invalid_payloads = [{"name": ""}, {"name": "   "}, {"name": None}]
    if method != "patch":
        invalid_payloads.insert(0, {})
    for payload in invalid_payloads:
        response = api_request(
            client,
            method,
            "/api/crops" if method == "post" else url,
            payload,
        )
        assert response.status_code == 400
        assert response.data["field"] == "name"

    too_long = api_request(
        client,
        method,
        "/api/crops" if method == "post" else url,
        {"name": "C" * 256},
    )
    assert too_long.status_code == 400
    assert too_long.data["field"] == "name"


@pytest.mark.parametrize("method", ["post", "put"])
def test_variety_create_and_put_require_crop_and_name(client, method):
    crop = create_crop(client)
    variety = create_variety(client, crop["id"])
    url = "/api/varieties" if method == "post" else (
        f"/api/varieties/{variety['id']}"
    )

    for payload, field in (
        ({"name": "No crop"}, "cropId"),
        ({"cropId": crop["id"]}, "name"),
        ({"cropId": crop["id"], "name": " "}, "name"),
        ({"cropId": crop["id"], "name": None}, "name"),
    ):
        response = api_request(client, method, url, payload)
        assert response.status_code == 400
        assert response.data["field"] == field


def test_variety_patch_validates_supplied_values_and_crop(client):
    crop = create_crop(client)
    variety = create_variety(client, crop["id"])
    url = f"/api/varieties/{variety['id']}"

    for payload, field in (
        ({"name": ""}, "name"),
        ({"name": None}, "name"),
        ({"name": "V" * 256}, "name"),
        ({"cropId": ""}, "cropId"),
        ({"cropId": "not-a-uuid"}, "cropId"),
    ):
        response = client.patch(url, payload, format="json")
        assert response.status_code in {400, 404}
        assert response.data["field"] == field


@pytest.mark.parametrize("method", ["post", "put"])
def test_unit_create_and_put_require_valid_name_and_base_measure(
    client, method
):
    unit = create_unit(client)
    url = "/api/units" if method == "post" else f"/api/units/{unit['id']}"

    for payload, field in (
        ({"baseMeasure": "mass"}, "name"),
        ({"name": "g"}, "baseMeasure"),
        ({"name": " "}, "name"),
        ({"name": "g", "baseMeasure": ""}, "baseMeasure"),
        ({"name": "g", "baseMeasure": "weight"}, "baseMeasure"),
        ({"name": "g", "baseMeasure": None}, "baseMeasure"),
    ):
        response = api_request(client, method, url, payload)
        assert response.status_code == 400
        assert response.data["field"] == field


def test_unit_patch_validates_supplied_fields_and_preserves_omitted_values(client):
    unit = create_unit(client)
    url = f"/api/units/{unit['id']}"
    for payload, field in (
        ({"name": ""}, "name"),
        ({"name": "U" * 256}, "name"),
        ({"baseMeasure": ""}, "baseMeasure"),
        ({"baseMeasure": "weight"}, "baseMeasure"),
        ({"baseMeasure": None}, "baseMeasure"),
    ):
        response = client.patch(url, payload, format="json")
        assert response.status_code == 400
        assert response.data["field"] == field

    unchanged = client.patch(url, {"name": "gram"}, format="json")
    assert unchanged.status_code == 200
    assert unchanged.data["baseMeasure"] == "mass"


def test_crop_and_unit_names_are_unique_per_farm_on_create_and_rename(client):
    crop = create_crop(client, "Wheat")
    duplicate_crop = client.post(
        "/api/crops", {"name": "wHEAT"}, format="json"
    )
    assert duplicate_crop.status_code == 409
    assert duplicate_crop.data["field"] == "name"

    other_crop = create_crop(client, "Maize")
    for method, payload in (
        ("put", {"name": "wheat"}),
        ("patch", {"name": "WHEAT"}),
    ):
        response = api_request(
            client, method, f"/api/crops/{other_crop['id']}", payload
        )
        assert response.status_code == 409
        assert response.data["field"] == "name"
        assert client.get(f"/api/crops/{other_crop['id']}").data["name"] == "Maize"

    unit = create_unit(client, "kg")
    duplicate_unit = client.post(
        "/api/units",
        {"name": "KG", "baseMeasure": "mass"},
        format="json",
    )
    assert duplicate_unit.status_code == 409
    assert duplicate_unit.data["field"] == "name"
    other_unit = create_unit(client, "g")
    for method, payload in (
        ("put", {"name": "KG", "baseMeasure": "mass"}),
        ("patch", {"name": "Kg"}),
    ):
        response = api_request(
            client, method, f"/api/units/{other_unit['id']}", payload
        )
        assert response.status_code == 409
        assert response.data["field"] == "name"
        assert client.get(f"/api/units/{other_unit['id']}").data["name"] == "g"

    assert Crop.objects.filter(pk=crop["id"]).exists()
    assert Unit.objects.filter(pk=unit["id"]).exists()


def test_crop_and_unit_name_uniqueness_is_enforced_by_database(client):
    farm = Farm.objects.get(owner__email="owner@agrivanta.test")
    Crop.objects.create(farm=farm, name="Canola")
    Unit.objects.create(farm=farm, name="litre", base_measure="volume")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Crop.objects.create(farm=farm, name="CANOLA")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Unit.objects.create(
                farm=farm, name="LITRE", base_measure="volume"
            )


def test_crop_and_variety_deletion_is_blocked_by_crop_cycles(client, cycle):
    data = cycle()
    crop_url = f"/api/crops/{data['crop']['id']}"
    variety_url = f"/api/varieties/{data['variety']['id']}"

    blocked_crop = client.delete(crop_url)
    assert blocked_crop.status_code == 409
    assert "crop cycle" in blocked_crop.data["detail"].lower()
    blocked_variety = client.delete(variety_url)
    assert blocked_variety.status_code == 409
    assert "crop cycle" in blocked_variety.data["detail"].lower()

    assert Crop.objects.filter(pk=data["crop"]["id"]).exists()
    assert Variety.objects.filter(pk=data["variety"]["id"]).exists()
    assert CropCycle.objects.filter(pk=data["cycle"]["id"]).exists()


def test_deleting_crop_cascades_unreferenced_varieties(client):
    crop = create_crop(client)
    variety = create_variety(client, crop["id"])
    response = client.delete(f"/api/crops/{crop['id']}")

    assert response.status_code == 204
    assert not Crop.objects.filter(pk=crop["id"]).exists()
    assert not Variety.objects.filter(pk=variety["id"]).exists()


def test_unit_delete_is_blocked_by_inventory_and_harvest(client, cycle):
    data = cycle()
    unit = create_unit(client, "lb")
    farm = Farm.objects.get(owner__email="owner@agrivanta.test")
    item = InventoryItem.objects.create(
        farm=farm, name="Seed", unit_id=unit["id"]
    )
    harvest = Harvest.objects.create(
        farm=farm,
        cycle_id=data["cycle"]["id"],
        quantity="4.0000",
        unit_id=unit["id"],
        date="2026-04-01",
    )

    response = client.delete(f"/api/units/{unit['id']}")

    assert response.status_code == 409
    assert "inventory or harvest" in response.data["detail"]
    assert Unit.objects.filter(pk=unit["id"]).exists()
    assert InventoryItem.objects.filter(pk=item.pk).exists()
    assert Harvest.objects.filter(pk=harvest.pk).exists()


def test_unit_delete_cascades_conversion_rules(client):
    unit = create_unit(client, "kg")
    grams = create_unit(client, "g")
    conversion = client.post(
        "/api/conversions",
        {
            "fromUnitId": unit["id"],
            "toUnitId": grams["id"],
            "factor": "1000",
        },
        format="json",
    )
    assert conversion.status_code == 201

    response = client.delete(f"/api/units/{unit['id']}")

    assert response.status_code == 204
    assert not Unit.objects.filter(pk=unit["id"]).exists()
    assert not UnitConversion.objects.filter(pk=conversion.data["id"]).exists()


def test_crops_varieties_and_units_are_scoped_to_the_authenticated_farm(client):
    crop = create_crop(client)
    variety = create_variety(client, crop["id"])
    unit = create_unit(client)
    other_client = APIClient()
    registration = register(other_client, email="other@agrivanta.test")
    assert registration.status_code == 201
    other_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {registration.data['token']}"
    )

    assert other_client.get("/api/crops").data == []
    assert other_client.get("/api/varieties").data == []
    assert other_client.get("/api/units").data == []
    for path, payloads in (
        (
            f"/api/crops/{crop['id']}",
            ({"name": "Foreign"}, {"name": "Foreign"}),
        ),
        (
            f"/api/varieties/{variety['id']}",
            (
                {"cropId": crop["id"], "name": "Foreign"},
                {"name": "Foreign"},
            ),
        ),
        (
            f"/api/units/{unit['id']}",
            (
                {"name": "Foreign", "baseMeasure": "mass"},
                {"name": "Foreign"},
            ),
        ),
    ):
        for method, payload in (
            ("get", None),
            ("put", payloads[0]),
            ("patch", payloads[1]),
            ("delete", None),
        ):
            response = api_request(other_client, method, path, payload)
            assert response.status_code == 404

    foreign_crop = create_crop(other_client, "Wheat")
    foreign_unit = create_unit(other_client, "kg")
    assert foreign_crop["name"] == crop["name"]
    assert foreign_unit["name"] == unit["name"]
    local_crop = create_crop(other_client, "Barley")
    local_variety = create_variety(other_client, local_crop["id"])
    local_variety_url = f"/api/varieties/{local_variety['id']}"
    for method, payload in (
        ("put", {"cropId": crop["id"], "name": "Invalid"}),
        ("patch", {"cropId": crop["id"]}),
        (
            "put",
            {
                "cropId": "00000000-0000-0000-0000-000000000000",
                "name": "Invalid",
            },
        ),
    ):
        response = api_request(
            other_client, method, local_variety_url, payload
        )
        assert response.status_code == 404
        assert response.data["field"] == "cropId"

    cross_farm_variety = other_client.post(
        "/api/varieties",
        {"cropId": crop["id"], "name": "Invalid"},
        format="json",
    )
    assert cross_farm_variety.status_code == 404
    assert cross_farm_variety.data["field"] == "cropId"
    User.objects.filter(email="other@agrivanta.test").update(
        role=Role.WORKER
    )
    for method, payload in (
        ("put", {"name": "Foreign"}),
        ("patch", {"name": "Foreign"}),
        ("delete", None),
    ):
        response = api_request(
            other_client, method, f"/api/crops/{crop['id']}", payload
        )
        assert response.status_code == 404


@pytest.mark.parametrize("role", [Role.OWNER, Role.MANAGER, Role.WORKER])
def test_owner_manager_and_worker_access_matrix(client, role):
    user = User.objects.get(email="owner@agrivanta.test")

    if role == Role.WORKER:
        crop = create_crop(client)
        variety = create_variety(client, crop["id"])
        unit = create_unit(client)
        User.objects.filter(pk=user.pk).update(role=role)
        assert client.get("/api/crops").status_code == 200
        assert client.get(f"/api/crops/{crop['id']}").status_code == 200
        assert client.get("/api/varieties").status_code == 200
        assert client.get(f"/api/varieties/{variety['id']}").status_code == 200
        assert client.get("/api/units").status_code == 200
        assert client.get(f"/api/units/{unit['id']}").status_code == 200
        write_requests = (
            ("post", "/api/crops", {"name": "Barley"}),
            ("put", f"/api/crops/{crop['id']}", {"name": "Barley"}),
            ("patch", f"/api/crops/{crop['id']}", {"name": "Barley"}),
            ("delete", f"/api/crops/{crop['id']}", None),
            (
                "post",
                "/api/varieties",
                {"cropId": crop["id"], "name": "Spring"},
            ),
            (
                "put",
                f"/api/varieties/{variety['id']}",
                {"cropId": crop["id"], "name": "Spring"},
            ),
            ("patch", f"/api/varieties/{variety['id']}", {"name": "Spring"}),
            ("delete", f"/api/varieties/{variety['id']}", None),
            (
                "post",
                "/api/units",
                {"name": "g", "baseMeasure": "mass"},
            ),
            (
                "put",
                f"/api/units/{unit['id']}",
                {"name": "g", "baseMeasure": "mass"},
            ),
            ("patch", f"/api/units/{unit['id']}", {"name": "g"}),
            ("delete", f"/api/units/{unit['id']}", None),
        )
        for method, url, payload in write_requests:
            assert api_request(client, method, url, payload).status_code == 403
        assert Crop.objects.filter(pk=crop["id"]).exists()
        assert Variety.objects.filter(pk=variety["id"]).exists()
        assert Unit.objects.filter(pk=unit["id"]).exists()
        return

    User.objects.filter(pk=user.pk).update(role=role)
    crop = create_crop(client)
    assert client.get("/api/crops").status_code == 200
    assert client.get(f"/api/crops/{crop['id']}").status_code == 200
    crop_url = f"/api/crops/{crop['id']}"
    assert client.put(crop_url, {"name": "Barley"}, format="json").status_code == 200
    assert client.patch(crop_url, {"name": "Oats"}, format="json").status_code == 200
    assert client.delete(crop_url).status_code == 204

    crop = create_crop(client, "Maize")
    variety_response = client.post(
        "/api/varieties",
        {"cropId": crop["id"], "name": "Hybrid"},
        format="json",
    )
    assert variety_response.status_code == 201
    variety_url = f"/api/varieties/{variety_response.data['id']}"
    assert client.get("/api/varieties").status_code == 200
    assert client.get(variety_url).status_code == 200
    assert client.put(
        variety_url,
        {"cropId": crop["id"], "name": "Dent"},
        format="json",
    ).status_code == 200
    assert client.patch(
        variety_url, {"name": "Sweet"}, format="json"
    ).status_code == 200
    assert client.delete(variety_url).status_code == 204

    unit = create_unit(client)
    unit_url = f"/api/units/{unit['id']}"
    assert client.get("/api/units").status_code == 200
    assert client.get(unit_url).status_code == 200
    assert client.put(
        unit_url,
        {"name": "gram", "baseMeasure": "mass"},
        format="json",
    ).status_code == 200
    assert client.patch(unit_url, {"name": "g"}, format="json").status_code == 200
    assert client.delete(unit_url).status_code == 204


def test_all_crop_variety_and_unit_methods_require_authentication(client, anon):
    crop = create_crop(client)
    variety = create_variety(client, crop["id"])
    unit = create_unit(client)
    checks = (
        ("get", "/api/crops", None),
        ("post", "/api/crops", {"name": "Barley"}),
        ("get", f"/api/crops/{crop['id']}", None),
        ("put", f"/api/crops/{crop['id']}", {"name": "Barley"}),
        ("patch", f"/api/crops/{crop['id']}", {"name": "Barley"}),
        ("delete", f"/api/crops/{crop['id']}", None),
        ("get", "/api/varieties", None),
        (
            "post",
            "/api/varieties",
            {"cropId": crop["id"], "name": "Spring"},
        ),
        ("get", f"/api/varieties/{variety['id']}", None),
        (
            "put",
            f"/api/varieties/{variety['id']}",
            {"cropId": crop["id"], "name": "Spring"},
        ),
        (
            "patch",
            f"/api/varieties/{variety['id']}",
            {"name": "Spring"},
        ),
        ("delete", f"/api/varieties/{variety['id']}", None),
        ("get", "/api/units", None),
        (
            "post",
            "/api/units",
            {"name": "g", "baseMeasure": "mass"},
        ),
        ("get", f"/api/units/{unit['id']}", None),
        (
            "put",
            f"/api/units/{unit['id']}",
            {"name": "g", "baseMeasure": "mass"},
        ),
        ("patch", f"/api/units/{unit['id']}", {"name": "g"}),
        ("delete", f"/api/units/{unit['id']}", None),
    )
    for method, url, payload in checks:
        response = api_request(anon, method, url, payload)
        assert response.status_code in {401, 403}
