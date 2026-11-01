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
