from django.db import IntegrityError, transaction
import pytest
from rest_framework.test import APIClient

from api.models import Farm, Field, User

from .conftest import register


def api_request(client, method, url, payload=None):
    caller = getattr(client, method)
    if method in {"get", "delete"}:
        return caller(url)
    return caller(url, payload or {}, format="json")


def test_farm_can_be_read_and_updated(client):
    read = client.get("/api/farm")
    assert read.status_code == 200
    assert read.data == {
        "id": read.data["id"],
        "name": "Olive Owner's Farm",
        "reportingCurrency": "USD",
    }

    updated = client.put(
        "/api/farm",
        {"name": "Willow Creek", "reportingCurrency": "eur"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["name"] == "Willow Creek"
    assert updated.data["reportingCurrency"] == "EUR"

    invalid = client.put(
        "/api/farm",
        {"name": "Willow Creek", "reportingCurrency": "EURO"},
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.data["field"] == "reportingCurrency"

    for payload, field in (
        ({"reportingCurrency": "USD"}, "name"),
        ({"name": " ", "reportingCurrency": "USD"}, "name"),
        ({"name": "Willow"}, "reportingCurrency"),
        ({"name": "Willow", "reportingCurrency": "US1"}, "reportingCurrency"),
        ({"name": "Willow", "reportingCurrency": "EURO"}, "reportingCurrency"),
        ({"name": "Willow", "reportingCurrency": "éUR"}, "reportingCurrency"),
    ):
        response = client.put("/api/farm", payload, format="json")
        assert response.status_code == 400
        assert response.data["field"] == field


def test_farm_patch_updates_only_supplied_valid_fields(client):
    original = client.get("/api/farm").data

    unchanged = client.patch("/api/farm", {}, format="json")
    assert unchanged.status_code == 200
    assert unchanged.data["name"] == original["name"]
    assert unchanged.data["reportingCurrency"] == original["reportingCurrency"]

    name = client.patch("/api/farm", {"name": "Willow Creek"}, format="json")
    assert name.status_code == 200
    assert name.data["name"] == "Willow Creek"
    assert name.data["reportingCurrency"] == original["reportingCurrency"]

    currency = client.patch(
        "/api/farm", {"reportingCurrency": "eur"}, format="json"
    )
    assert currency.status_code == 200
    assert currency.data["name"] == "Willow Creek"
    assert currency.data["reportingCurrency"] == "EUR"

    for payload, field in (
        ({"name": ""}, "name"),
        ({"name": None}, "name"),
        ({"reportingCurrency": "EURO"}, "reportingCurrency"),
        ({"reportingCurrency": None}, "reportingCurrency"),
    ):
        response = client.patch("/api/farm", payload, format="json")
        assert response.status_code == 400
        assert response.data["field"] == field

    assert client.post("/api/farm", {}, format="json").status_code == 405
    assert client.delete("/api/farm").status_code == 405


def test_fields_validate_area_and_can_be_updated(client):
    invalid = client.post(
        "/api/fields", {"name": "North 40", "area": "nope"}, format="json"
    )
    assert invalid.status_code == 400
    assert invalid.data["field"] == "area"

    created = client.post(
        "/api/fields",
        {"name": "North 40", "area": "12.5", "notes": "Loam"},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["area"] == 12.5
    assert created.data["notes"] == "Loam"

    updated = client.put(
        f"/api/fields/{created.data['id']}",
        {"name": "South 12", "area": 4},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["name"] == "South 12"

    missing = client.put(
        "/api/fields/does-not-exist",
        {"name": "South 12", "area": 4},
        format="json",
    )
    assert missing.status_code == 404

    listed = client.get("/api/fields")
    assert listed.status_code == 200
    assert len(listed.data) == 1


@pytest.mark.parametrize(
    "area",
    [None, "nope", 0, "0.0000", -1, "1.00001", "10000000000"],
)
def test_field_creation_rejects_invalid_area_values(client, area):
    response = client.post(
        "/api/fields",
        {"name": "North 40", "area": area},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == "area"


def test_field_creation_requires_name_and_area(client):
    for payload, field in (
        ({"area": 4}, "name"),
        ({"name": "North 40"}, "area"),
        ({"name": " ", "area": 4}, "name"),
    ):
        response = client.post("/api/fields", payload, format="json")
        assert response.status_code == 400
        assert response.data["field"] == field


def test_fields_round_trip_polygon_and_support_full_crud(client):
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [4, 0], [4, 4], [0, 0]],
            [[1, 1], [2, 1], [2, 2], [1, 1]],
        ],
    }
    created = client.post(
        "/api/fields",
        {
            "name": "North 40",
            "area": "12.3456",
            "notes": "Loam",
            "polygon": polygon,
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["area"] == 12.3456
    assert created.data["polygon"] == polygon

    field_id = created.data["id"]
    retrieved = client.get(f"/api/fields/{field_id}")
    assert retrieved.status_code == 200
    assert retrieved.data["polygon"] == polygon

    updated = client.put(
        f"/api/fields/{field_id}",
        {
            "name": "South 12",
            "area": "0.0001",
            "polygon": polygon,
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["name"] == "South 12"
    assert updated.data["area"] == 0.0001
    assert updated.data["polygon"] == polygon
    assert "notes" not in updated.data

    patched = client.patch(
        f"/api/fields/{field_id}",
        {"notes": "Sandy"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.data["name"] == "South 12"
    assert patched.data["area"] == 0.0001
    assert patched.data["notes"] == "Sandy"
    assert patched.data["polygon"] == polygon

    cleared = client.patch(
        f"/api/fields/{field_id}", {"polygon": None}, format="json"
    )
    assert cleared.status_code == 200
    assert "polygon" not in cleared.data

    deleted = client.delete(f"/api/fields/{field_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/fields/{field_id}").status_code == 404
    assert client.get("/api/fields").data == []


@pytest.mark.parametrize(
    "polygon",
    [
        {"type": "MultiPolygon", "coordinates": []},
        {"type": "Polygon"},
        {"type": "Polygon", "coordinates": "not-an-array"},
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[[]]]},
        {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1]]],
        },
        {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
        },
        {
            "type": "Polygon",
            "coordinates": [
                [[0, 0], [1, 0], [1, 1], [0, 0]],
                [[2, 2], [3, 2], [3, 3], [2, 3, 5]],
            ],
        },
        {
            "type": "Polygon",
            "coordinates": [
                [[0, 0], [1, 0], [1, 1], [0, 0, 5]],
            ],
        },
        {
            "type": "Polygon",
            "coordinates": [
                [[0, 0], [1, 0], [1, "nan"], [0, 0]],
            ],
        },
    ],
)
def test_field_creation_rejects_malformed_polygons(client, polygon):
    response = client.post(
        "/api/fields",
        {"name": "North 40", "area": 10, "polygon": polygon},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == "polygon"


def test_field_put_and_patch_validate_required_and_supplied_values(client):
    created = client.post(
        "/api/fields",
        {"name": "North 40", "area": 10},
        format="json",
    )
    field_url = f"/api/fields/{created.data['id']}"

    for payload in (
        {"name": "South"},
        {"area": 4},
        {"name": "South", "area": "not-a-number"},
        {"name": "South", "area": 0},
        {"name": "South", "area": -1},
        {"name": "South", "area": "1.12345"},
    ):
        invalid_put = client.put(field_url, payload, format="json")
        assert invalid_put.status_code == 400
        assert invalid_put.data["field"] in {"name", "area"}

    for payload, field in (
        ({"name": ""}, "name"),
        ({"area": "not-a-number"}, "area"),
        ({"area": 0}, "area"),
        ({"area": -1}, "area"),
        ({"area": "1.12345"}, "area"),
        (
            {"polygon": {"type": "Polygon", "coordinates": []}},
            "polygon",
        ),
    ):
        invalid_patch = client.patch(field_url, payload, format="json")
        assert invalid_patch.status_code == 400
        assert invalid_patch.data["field"] == field

    assert client.patch(field_url, {}, format="json").status_code == 200
    valid_area_patch = client.patch(
        field_url, {"area": "3.1415"}, format="json"
    )
    assert valid_area_patch.status_code == 200
    assert valid_area_patch.data["area"] == 3.1415


def test_fields_are_scoped_to_the_authenticated_users_farm(client):
    field = client.post(
        "/api/fields",
        {"name": "North 40", "area": 10},
        format="json",
    )
    other_client = APIClient()
    other_registration = register(
        other_client, email="other@agrivanta.test"
    )
    assert other_registration.status_code == 201
    other_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {other_registration.data['token']}"
    )

    assert other_client.get("/api/fields").data == []
    field_url = f"/api/fields/{field.data['id']}"
    for method, payload in (
        ("get", None),
        ("put", {"name": "Foreign", "area": 1}),
        ("patch", {"name": "Foreign"}),
        ("delete", None),
    ):
        response = api_request(other_client, method, field_url, payload)
        assert response.status_code == 404

    assert Field.objects.filter(pk=field.data["id"]).exists()
    for method, payload in (
        ("get", None),
        ("put", {"name": "Missing", "area": 1}),
        ("patch", {"name": "Missing"}),
        ("delete", None),
    ):
        response = api_request(
            client,
            method,
            "/api/fields/00000000-0000-0000-0000-000000000000",
            payload,
        )
        assert response.status_code == 404


def test_farm_has_one_to_one_owner_constraint_and_cascades_fields(client):
    farm_id = client.get("/api/farm").data["id"]
    owner = User.objects.get(email="owner@agrivanta.test")
    field_response = client.post(
        "/api/fields",
        {"name": "North 40", "area": 10},
        format="json",
    )
    assert field_response.status_code == 201
    assert Farm.objects.filter(owner=owner).count() == 1

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Farm.objects.create(
                owner=owner, name="Second farm", reporting_currency="USD"
            )

    owner.delete()
    assert not Farm.objects.filter(pk=farm_id).exists()
    assert not Field.objects.filter(pk=field_response.data["id"]).exists()


def test_crops_reject_duplicate_names_case_insensitively(client):
    created = client.post(
        "/api/crops", {"name": "Wheat"}, format="json"
    )
    assert created.status_code == 201

    duplicate = client.post(
        "/api/crops", {"name": "wheat"}, format="json"
    )
    assert duplicate.status_code == 409
    assert duplicate.data["field"] == "name"


def test_varieties_require_an_existing_crop(client):
    crop = client.post("/api/crops", {"name": "Maize"}, format="json")

    missing = client.post(
        "/api/varieties",
        {"cropId": "00000000-0000-0000-0000-000000000000", "name": "Hybrid"},
        format="json",
    )
    assert missing.status_code == 404
    assert missing.data["field"] == "cropId"

    created = client.post(
        "/api/varieties",
        {"cropId": crop.data["id"], "name": "Hybrid"},
        format="json",
    )
    assert created.status_code == 201

    filtered = client.get(f"/api/varieties?crop={crop.data['id']}")
    assert len(filtered.data) == 1
    assert filtered.data[0]["cropId"] == crop.data["id"]


def test_units_validate_base_measure_and_duplicate_names(client):
    invalid = client.post(
        "/api/units",
        {"name": "kg", "baseMeasure": "weight"},
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.data["field"] == "baseMeasure"

    created = client.post(
        "/api/units",
        {"name": "kg", "baseMeasure": "mass"},
        format="json",
    )
    assert created.status_code == 201

    duplicate = client.post(
        "/api/units",
        {"name": "KG", "baseMeasure": "mass"},
        format="json",
    )
    assert duplicate.status_code == 409
    assert duplicate.data["field"] == "name"


def test_conversions_convert_in_both_directions(client):
    kg = client.post(
        "/api/units", {"name": "kg", "baseMeasure": "mass"}, format="json"
    ).data
    grams = client.post(
        "/api/units", {"name": "g", "baseMeasure": "mass"}, format="json"
    ).data

    created = client.post(
        "/api/conversions",
        {
            "fromUnitId": kg["id"],
            "toUnitId": grams["id"],
            "factor": "1000",
        },
        format="json",
    )
    assert created.status_code == 201

    direct = client.post(
        "/api/conversions/convert",
        {
            "fromUnitId": kg["id"],
            "toUnitId": grams["id"],
            "quantity": "2",
        },
        format="json",
    )
    assert direct.status_code == 200
    assert direct.data["factor"] == 1000
    assert direct.data["converted"] == 2000

    inverse = client.post(
        "/api/conversions/convert",
        {
            "fromUnitId": grams["id"],
            "toUnitId": kg["id"],
            "quantity": "500",
        },
        format="json",
    )
    assert inverse.status_code == 200
    assert inverse.data["factor"] == 0.001
    assert inverse.data["converted"] == 0.5


def test_conversion_requires_a_rule(client):
    kg = client.post(
        "/api/units", {"name": "kg", "baseMeasure": "mass"}, format="json"
    ).data
    litre = client.post(
        "/api/units",
        {"name": "L", "baseMeasure": "volume"},
        format="json",
    ).data
    grams = client.post(
        "/api/units", {"name": "g", "baseMeasure": "mass"}, format="json"
    ).data

    mismatch = client.post(
        "/api/conversions/convert",
        {
            "fromUnitId": kg["id"],
            "toUnitId": litre["id"],
            "quantity": "1",
        },
        format="json",
    )
    assert mismatch.status_code == 400

    missing = client.post(
        "/api/conversions/convert",
        {
            "fromUnitId": kg["id"],
            "toUnitId": grams["id"],
            "quantity": "1",
        },
        format="json",
    )
    assert missing.status_code == 404


def test_conversion_rejects_duplicate_pair(client):
    kg = client.post(
        "/api/units", {"name": "kg", "baseMeasure": "mass"}, format="json"
    ).data
    grams = client.post(
        "/api/units", {"name": "g", "baseMeasure": "mass"}, format="json"
    ).data
    payload = {
        "fromUnitId": kg["id"],
        "toUnitId": grams["id"],
        "factor": 1000,
    }

    assert (
        client.post("/api/conversions", payload, format="json").status_code
        == 201
    )
    duplicate = client.post("/api/conversions", payload, format="json")
    assert duplicate.status_code == 409


def test_conversion_api_locks_farm_before_pair_check_and_rejects_conflicts(
    client, monkeypatch
):
    from django.db import connection

    from api import views
    from api.models import Farm

    kg = client.post(
        "/api/units", {"name": "kg", "baseMeasure": "mass"}, format="json"
    ).data
    grams = client.post(
        "/api/units", {"name": "g", "baseMeasure": "mass"}, format="json"
    ).data
    ounce = client.post(
        "/api/units", {"name": "oz", "baseMeasure": "mass"}, format="json"
    ).data
    pound = client.post(
        "/api/units", {"name": "lb", "baseMeasure": "mass"}, format="json"
    ).data
    select_for_update = Farm.objects.select_for_update
    lock_calls = []
    validation_calls = []
    validate_conversion_rule = views.validate_conversion_rule

    def track_select_for_update(*args, **kwargs):
        assert connection.in_atomic_block
        lock_calls.append(True)
        return select_for_update(*args, **kwargs)

    def track_validate_conversion_rule(*args, **kwargs):
        assert connection.in_atomic_block
        assert len(lock_calls) == len(validation_calls) + 1
        validation_calls.append(True)
        return validate_conversion_rule(*args, **kwargs)

    monkeypatch.setattr(
        Farm.objects, "select_for_update", track_select_for_update
    )
    monkeypatch.setattr(
        views, "validate_conversion_rule", track_validate_conversion_rule
    )
    existing = client.post(
        "/api/conversions",
        {"fromUnitId": kg["id"], "toUnitId": grams["id"], "factor": "1000"},
        format="json",
    )
    second = client.post(
        "/api/conversions",
        {"fromUnitId": ounce["id"], "toUnitId": pound["id"], "factor": "16"},
        format="json",
    )
    assert existing.status_code == second.status_code == 201

    duplicate_create = client.post(
        "/api/conversions",
        {"fromUnitId": grams["id"], "toUnitId": kg["id"], "factor": "0.001"},
        format="json",
    )
    assert duplicate_create.status_code == 409
    assert duplicate_create.data["field"] == "toUnitId"

    duplicate_update = client.put(
        f"/api/conversions/{second.data['id']}",
        {"fromUnitId": grams["id"], "toUnitId": kg["id"], "factor": "0.001"},
        format="json",
    )
    assert duplicate_update.status_code == 409
    assert duplicate_update.data["field"] == "toUnitId"
    assert len(lock_calls) == len(validation_calls) == 4
    assert client.get(f"/api/conversions/{second.data['id']}").data == second.data


def test_legacy_opposite_conversion_rows_remain_unchanged(client):
    from decimal import Decimal

    from api.models import Unit, UnitConversion

    kg_data = client.post(
        "/api/units", {"name": "kg", "baseMeasure": "mass"}, format="json"
    ).data
    grams_data = client.post(
        "/api/units", {"name": "g", "baseMeasure": "mass"}, format="json"
    ).data
    kg = Unit.objects.get(pk=kg_data["id"])
    grams = Unit.objects.get(pk=grams_data["id"])

    forward = UnitConversion.objects.create(
        farm=kg.farm,
        from_unit=kg,
        to_unit=grams,
        factor=Decimal("1000"),
    )
    reverse = UnitConversion.objects.create(
        farm=kg.farm,
        from_unit=grams,
        to_unit=kg,
        factor=Decimal("0.001"),
    )

    response = client.get("/api/conversions")
    assert response.status_code == 200
    assert {rule["id"] for rule in response.data} == {
        str(forward.pk),
        str(reverse.pk),
    }

    duplicate = client.post(
        "/api/conversions",
        {
            "fromUnitId": kg_data["id"],
            "toUnitId": grams_data["id"],
            "factor": "1000",
        },
        format="json",
    )
    assert duplicate.status_code == 409
    assert UnitConversion.objects.filter(farm=kg.farm).count() == 2


def test_conversion_update_and_delete_recheck_under_farm_lock(
    client, monkeypatch
):
    from django.db import connection

    from api import views
    from api.models import UnitConversion

    kg = client.post(
        "/api/units", {"name": "kg", "baseMeasure": "mass"}, format="json"
    ).data
    grams = client.post(
        "/api/units", {"name": "g", "baseMeasure": "mass"}, format="json"
    ).data
    rule = client.post(
        "/api/conversions",
        {"fromUnitId": kg["id"], "toUnitId": grams["id"], "factor": "1000"},
        format="json",
    )
    assert rule.status_code == 201

    original_lock = views.lock_conversion_farm
    original_scoped_get = views.scoped_get
    operations = []

    def track_lock(farm):
        assert connection.in_atomic_block
        original_lock(farm)
        operations.append("lock")

    def track_scoped_get(model, farm, pk, message, field=None):
        if model is UnitConversion:
            assert connection.in_atomic_block
            assert operations[-1] == "lock"
            operations.append("fetch")
        return original_scoped_get(model, farm, pk, message, field)

    monkeypatch.setattr(views, "lock_conversion_farm", track_lock)
    monkeypatch.setattr(views, "scoped_get", track_scoped_get)

    updated = client.put(
        f"/api/conversions/{rule.data['id']}",
        {"fromUnitId": kg["id"], "toUnitId": grams["id"], "factor": "2000"},
        format="json",
    )
    assert updated.status_code == 200
    assert operations == ["lock", "fetch"]

    deleted = client.delete(f"/api/conversions/{rule.data['id']}")
    assert deleted.status_code == 204
    assert operations == ["lock", "fetch", "lock", "fetch"]

    missing_update = client.put(
        f"/api/conversions/{rule.data['id']}",
        {"fromUnitId": kg["id"], "toUnitId": grams["id"], "factor": "3000"},
        format="json",
    )
    assert missing_update.status_code == 404
    assert operations == [
        "lock",
        "fetch",
        "lock",
        "fetch",
        "lock",
        "fetch",
    ]


def test_conversion_factor_respects_model_precision_on_create_and_update(client):
    kg = client.post(
        "/api/units", {"name": "kg", "baseMeasure": "mass"}, format="json"
    ).data
    grams = client.post(
        "/api/units", {"name": "g", "baseMeasure": "mass"}, format="json"
    ).data
    ounce = client.post(
        "/api/units", {"name": "oz", "baseMeasure": "mass"}, format="json"
    ).data

    valid_boundary = client.post(
        "/api/conversions",
        {
            "fromUnitId": kg["id"],
            "toUnitId": grams["id"],
            "factor": "1.123456",
        },
        format="json",
    )
    assert valid_boundary.status_code == 201

    for too_precise in ("1000000000000", "0.0000001"):
        invalid_create = client.post(
            "/api/conversions",
            {
                "fromUnitId": kg["id"],
                "toUnitId": ounce["id"],
                "factor": too_precise,
            },
            format="json",
        )
        assert invalid_create.status_code == 400
        assert invalid_create.data["field"] == "factor"

        invalid_update = client.put(
            f"/api/conversions/{valid_boundary.data['id']}",
            {
                "fromUnitId": kg["id"],
                "toUnitId": grams["id"],
                "factor": too_precise,
            },
            format="json",
        )
        assert invalid_update.status_code == 400
        assert invalid_update.data["field"] == "factor"
        assert client.get(
            f"/api/conversions/{valid_boundary.data['id']}"
        ).data == valid_boundary.data


def test_conversion_rule_api_supports_crud_and_validation(client, anon):
    from rest_framework.test import APIClient

    empty = client.get("/api/conversions")
    assert empty.status_code == 200
    assert empty.data == []

    kg = client.post(
        "/api/units", {"name": "kg", "baseMeasure": "mass"}, format="json"
    ).data
    grams = client.post(
        "/api/units", {"name": "g", "baseMeasure": "mass"}, format="json"
    ).data
    litre = client.post(
        "/api/units",
        {"name": "L", "baseMeasure": "volume"},
        format="json",
    ).data

    created = client.post(
        "/api/conversions",
        {"fromUnitId": kg["id"], "toUnitId": grams["id"], "factor": "1000"},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["factor"] == 1000
    conversion_id = created.data["id"]

    unauthenticated = [
        anon.get("/api/conversions"),
        anon.post(
            "/api/conversions",
            {
                "fromUnitId": kg["id"],
                "toUnitId": grams["id"],
                "factor": "1000",
            },
            format="json",
        ),
        anon.get(f"/api/conversions/{conversion_id}"),
        anon.put(
            f"/api/conversions/{conversion_id}",
            {
                "fromUnitId": kg["id"],
                "toUnitId": grams["id"],
                "factor": "2000",
            },
            format="json",
        ),
        anon.delete(f"/api/conversions/{conversion_id}"),
    ]
    assert [response.status_code for response in unauthenticated] == [
        401,
        401,
        401,
        401,
        401,
    ]

    listed = client.get("/api/conversions")
    assert listed.status_code == 200
    assert len(listed.data) == 1
    assert listed.data[0]["id"] == conversion_id
    assert listed.data[0]["factor"] == 1000

    detail = client.get(f"/api/conversions/{conversion_id}")
    assert detail.status_code == 200
    assert detail.data["toUnitId"] == grams["id"]
    assert detail.data["factor"] == 1000

    updated = client.put(
        f"/api/conversions/{conversion_id}",
        {"fromUnitId": kg["id"], "toUnitId": grams["id"], "factor": "2000"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["factor"] == 2000

    ounce = client.post(
        "/api/units",
        {"name": "oz", "baseMeasure": "mass"},
        format="json",
    ).data
    pound = client.post(
        "/api/units", {"name": "lb", "baseMeasure": "mass"}, format="json"
    ).data
    invalid_factors = [
        {},
        {"factor": None},
        {"factor": ""},
        {"factor": "0"},
        {"factor": "-1"},
        {"factor": "NaN"},
        {"factor": "Infinity"},
        {"factor": "-Infinity"},
        {"factor": "abc"},
    ]
    for factor_field in invalid_factors:
        bad = client.post(
            "/api/conversions",
            {
                "fromUnitId": kg["id"],
                "toUnitId": ounce["id"],
                **factor_field,
            },
            format="json",
        )
        assert bad.status_code == 400
        assert bad.data["field"] == "factor"

    invalid_base = client.post(
        "/api/conversions",
        {"fromUnitId": kg["id"], "toUnitId": litre["id"], "factor": "2"},
        format="json",
    )
    assert invalid_base.status_code == 400
    assert invalid_base.data["field"] == "toUnitId"

    reverse = client.post(
        "/api/conversions",
        {"fromUnitId": grams["id"], "toUnitId": kg["id"], "factor": "0.001"},
        format="json",
    )
    assert reverse.status_code == 409
    assert reverse.data["field"] == "toUnitId"
    assert [
        rule["id"] for rule in client.get("/api/conversions").data
    ] == [conversion_id]

    second_rule = client.post(
        "/api/conversions",
        {
            "fromUnitId": ounce["id"],
            "toUnitId": pound["id"],
            "factor": "16",
        },
        format="json",
    )
    assert second_rule.status_code == 201
    duplicate_update = client.put(
        f"/api/conversions/{second_rule.data['id']}",
        {
            "fromUnitId": grams["id"],
            "toUnitId": kg["id"],
            "factor": "0.001",
        },
        format="json",
    )
    assert duplicate_update.status_code == 409
    assert duplicate_update.data["field"] == "toUnitId"
    assert client.get(
        f"/api/conversions/{second_rule.data['id']}"
    ).data == second_rule.data

    for factor_field in invalid_factors:
        bad = client.put(
            f"/api/conversions/{conversion_id}",
            {
                "fromUnitId": kg["id"],
                "toUnitId": grams["id"],
                **factor_field,
            },
            format="json",
        )
        assert bad.status_code == 400
        assert bad.data["field"] == "factor"
        assert client.get(
            f"/api/conversions/{conversion_id}"
        ).data == updated.data

    invalid_update_base = client.put(
        f"/api/conversions/{conversion_id}",
        {
            "fromUnitId": kg["id"],
            "toUnitId": litre["id"],
            "factor": "2000",
        },
        format="json",
    )
    assert invalid_update_base.status_code == 400
    assert invalid_update_base.data["field"] == "toUnitId"

    other = APIClient()
    owner = other.post(
        "/api/auth/register",
        {
            "name": "Other Owner",
            "email": "other-owner@agrivanta.test",
            "password": "OliveHarvest#42",
        },
        format="json",
    )
    assert owner.status_code == 201
    other.credentials(
        HTTP_AUTHORIZATION=f"Bearer {owner.data['token']}"
    )
    other_kg = other.post(
        "/api/units",
        {"name": "kg", "baseMeasure": "mass"},
        format="json",
    ).data

    foreign = client.post(
        "/api/conversions",
        {
            "fromUnitId": other_kg["id"],
            "toUnitId": grams["id"],
            "factor": "1000",
        },
        format="json",
    )
    assert foreign.status_code == 404
    assert foreign.data["field"] == "fromUnitId"
    foreign_update = client.put(
        f"/api/conversions/{conversion_id}",
        {
            "fromUnitId": other_kg["id"],
            "toUnitId": grams["id"],
            "factor": "3000",
        },
        format="json",
    )
    assert foreign_update.status_code == 404
    assert foreign_update.data["field"] == "fromUnitId"
    assert client.get(f"/api/conversions/{conversion_id}").data == updated.data

    other_grams = other.post(
        "/api/units",
        {"name": "g", "baseMeasure": "mass"},
        format="json",
    ).data
    foreign_to_unit = client.post(
        "/api/conversions",
        {
            "fromUnitId": kg["id"],
            "toUnitId": other_grams["id"],
            "factor": "1000",
        },
        format="json",
    )
    assert foreign_to_unit.status_code == 404
    assert foreign_to_unit.data["field"] == "toUnitId"
    foreign_to_unit_update = client.put(
        f"/api/conversions/{conversion_id}",
        {
            "fromUnitId": kg["id"],
            "toUnitId": other_grams["id"],
            "factor": "3000",
        },
        format="json",
    )
    assert foreign_to_unit_update.status_code == 404
    assert foreign_to_unit_update.data["field"] == "toUnitId"
    assert client.get(f"/api/conversions/{conversion_id}").data == updated.data

    other_conversion = other.post(
        "/api/conversions",
        {
            "fromUnitId": other_kg["id"],
            "toUnitId": other_grams["id"],
            "factor": "1000",
        },
        format="json",
    )
    assert other_conversion.status_code == 201

    own_rules = client.get("/api/conversions")
    assert own_rules.status_code == 200
    assert {rule["id"] for rule in own_rules.data} == {
        conversion_id,
        second_rule.data["id"],
    }
    assert (
        client.get(f"/api/conversions/{other_conversion.data['id']}").status_code
        == 404
    )
    assert (
        other.get(f"/api/conversions/{conversion_id}").status_code == 404
    )
    assert [
        rule["id"] for rule in other.get("/api/conversions").data
    ] == [other_conversion.data["id"]]

    deleted = client.delete(f"/api/conversions/{conversion_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/conversions/{conversion_id}").status_code == 404
    assert len(client.get("/api/conversions").data) == 1
