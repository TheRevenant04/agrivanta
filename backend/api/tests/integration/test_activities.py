def test_crop_cycle_create_update_close_and_lock(client, cycle):
    built = cycle()
    created = built["cycle"]

    assert created["status"] == "open"
    assert created["startDate"] == "2026-03-01"

    updated = client.put(
        f"/api/crop-cycles/{created['id']}",
        {"expectedYield": "1200", "expectedPrice": "0.45"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["expectedYield"] == 1200
    assert updated.data["expectedPrice"] == 0.45

    closed = client.post(f"/api/crop-cycles/{created['id']}/close")
    assert closed.status_code == 200
    assert closed.data["status"] == "closed"

    rejected_update = client.put(
        f"/api/crop-cycles/{created['id']}",
        {"expectedYield": "1400"},
        format="json",
    )
    assert rejected_update.status_code == 409

    rejected_close = client.post(f"/api/crop-cycles/{created['id']}/close")
    assert rejected_close.status_code == 409


def test_crop_cycle_validates_dates_and_references(client, setup):
    data = setup()
    missing = client.post(
        "/api/crop-cycles",
        {
            "fieldId": data["field"]["id"],
            "cropId": data["crop"]["id"],
            "varietyId": "00000000-0000-0000-0000-000000000000",
            "cycleType": "annual",
            "startDate": "2026-03-01",
        },
        format="json",
    )
    assert missing.status_code == 404
    assert missing.data["field"] == "varietyId"

    bad_end = client.post(
        "/api/crop-cycles",
        {
            "fieldId": data["field"]["id"],
            "cropId": data["crop"]["id"],
            "varietyId": data["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2026-03-01",
            "endDate": "2026-02-01",
        },
        format="json",
    )
    assert bad_end.status_code == 400
    assert bad_end.data["field"] == "endDate"


def test_standard_activity_types_are_seeded_and_custom_types_validated(client):
    listed = client.get("/api/activity-types")
    assert listed.status_code == 200
    assert len(listed.data) == 5
    assert all(item["standard"] for item in listed.data)

    duplicate = client.post(
        "/api/activity-types",
        {"name": "Planting", "category": "planting"},
        format="json",
    )
    assert duplicate.status_code == 409

    custom = client.post(
        "/api/activity-types",
        {"name": "Scouting", "category": "custom"},
        format="json",
    )
    assert custom.status_code == 201
    assert custom.data["standard"] is False


def test_activity_status_transitions(client, cycle):
    built = cycle()
    activity_type = client.get("/api/activity-types").data[0]

    created = client.post(
        "/api/activities",
        {
            "cycleId": built["cycle"]["id"],
            "typeId": activity_type["id"],
            "plannedDate": "2026-03-10",
            "description": "Plough",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["status"] == "planned"

    started = client.put(
        f"/api/activities/{created.data['id']}/status",
        {"status": "in_progress"},
        format="json",
    )
    assert started.status_code == 200

    completed = client.put(
        f"/api/activities/{created.data['id']}/status",
        {"status": "completed"},
        format="json",
    )
    assert completed.status_code == 200

    illegal = client.put(
        f"/api/activities/{created.data['id']}/status",
        {"status": "in_progress"},
        format="json",
    )
    assert illegal.status_code == 409
    assert illegal.data["field"] == "status"

    unknown = client.put(
        f"/api/activities/{created.data['id']}/status",
        {"status": "cancelled"},
        format="json",
    )
    assert unknown.status_code == 400
    assert unknown.data["field"] == "status"


def test_activity_resource_needs_are_replaced(client, cycle):
    built = cycle()
    activity = client.post(
        "/api/activities",
        {
            "cycleId": built["cycle"]["id"],
            "typeId": client.get("/api/activity-types").data[0]["id"],
            "plannedDate": "2026-03-10",
        },
        format="json",
    ).data

    updated = client.put(
        f"/api/activities/{activity['id']}/resource-needs",
        {
            "inputs": [
                {"itemName": "Seed", "quantity": "20"},
                {"itemName": "Fertilizer", "quantity": 5},
            ],
            "labourHours": "8",
            "equipment": "Tractor",
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["resourceNeeds"]["labourHours"] == 8
    assert updated.data["resourceNeeds"]["equipment"] == "Tractor"
    assert len(updated.data["resourceNeeds"]["inputs"]) == 2

    replaced = client.put(
        f"/api/activities/{activity['id']}/resource-needs",
        {"inputs": [], "labourHours": 0, "equipment": ""},
        format="json",
    )
    assert replaced.status_code == 200
    assert replaced.data["resourceNeeds"]["inputs"] == []

    invalid = client.put(
        f"/api/activities/{activity['id']}/resource-needs",
        {"inputs": [], "labourHours": -1, "equipment": ""},
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.data["field"] == "labourHours"


def test_activity_cycle_references_use_readable_labels(client, cycle):
    cycle()
    refs = client.get("/api/activities/cycles")
    assert refs.status_code == 200
    assert len(refs.data) == 1
    assert refs.data[0]["label"] == "North 40 \u2014 Wheat 2026"
