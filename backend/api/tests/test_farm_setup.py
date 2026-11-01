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


def test_conversion_api_enforces_symmetric_pair_uniqueness_atomically(
    client, monkeypatch
):
    from api import views

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

    monkeypatch.setattr(
        views, "validate_conversion_rule", lambda *args, **kwargs: None
    )
    raced_create = client.post(
        "/api/conversions",
        {"fromUnitId": grams["id"], "toUnitId": kg["id"], "factor": "0.001"},
        format="json",
    )
    assert raced_create.status_code == 409
    assert raced_create.data["field"] == "toUnitId"

    raced_update = client.put(
        f"/api/conversions/{second.data['id']}",
        {"fromUnitId": grams["id"], "toUnitId": kg["id"], "factor": "0.001"},
        format="json",
    )
    assert raced_update.status_code == 409
    assert raced_update.data["field"] == "toUnitId"
    assert client.get(f"/api/conversions/{second.data['id']}").data == second.data


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
            "password": "password123",
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
