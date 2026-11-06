from datetime import date

from rest_framework.test import APIClient

from api.models import (
    Activity,
    ActivityType,
    Crop,
    CropCycle,
    Farm,
    Field,
    LabourRecord,
    Role,
    User,
    Worker,
)

from .conftest import register


WORKERS = "/api/workers"
LABOUR_RECORDS = "/api/labour-records"


def create_activity(client, cycle, cycle_data=None):
    built = cycle_data or cycle()
    activity_type = client.get("/api/activity-types").data[0]
    activity = client.post(
        "/api/activities",
        {
            "cycleId": built["cycle"]["id"],
            "typeId": activity_type["id"],
            "plannedDate": "2026-03-10",
        },
        format="json",
    )
    assert activity.status_code == 201, activity.data
    return activity.data


def create_worker(client, name="Sam Worker", **payload):
    response = client.post(
        WORKERS, {"name": name, **payload}, format="json"
    )
    assert response.status_code == 201, response.data
    return response.data


def create_labour_record(
    client, worker_id, activity_id, *, hours="2", hourly_cost="10"
):
    response = client.post(
        LABOUR_RECORDS,
        {
            "workerId": worker_id,
            "activityId": activity_id,
            "hours": hours,
            "hourlyCost": hourly_cost,
            "date": "2026-03-10",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def test_worker_profiles_support_crud_and_optional_user(client):
    worker = create_worker(client)
    assert worker["name"] == "Sam Worker"
    assert worker["userId"] is None
    assert worker["farmId"] == client.get("/api/farm").data["id"]
    assert client.get(WORKERS).data == [worker]
    assert client.get(f"{WORKERS}/{worker['id']}").data == worker

    linked_user = User.objects.create_user(
        email="linked@agrivanta.test", password="password123"
    )
    updated = client.put(
        f"{WORKERS}/{worker['id']}",
        {"name": "Sam Updated", "userId": str(linked_user.id)},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["name"] == "Sam Updated"
    assert updated.data["userId"] == str(linked_user.id)

    cleared = client.put(
        f"{WORKERS}/{worker['id']}", {"name": "Sam Worker"}, format="json"
    )
    assert cleared.status_code == 200
    assert cleared.data["userId"] is None
    assert client.delete(f"{WORKERS}/{worker['id']}").status_code == 204
    assert client.get(WORKERS).data == []


def test_worker_rejects_nonexistent_linked_user(client):
    response = client.post(
        WORKERS,
        {
            "name": "Invalid Link",
            "userId": "00000000-0000-0000-0000-000000000000",
        },
        format="json",
    )
    assert response.status_code == 404
    assert response.data["field"] == "userId"


def test_worker_name_length_is_validated_on_create_and_update(client):
    max_length_name = "W" * 255
    created = client.post(
        WORKERS, {"name": max_length_name}, format="json"
    )
    assert created.status_code == 201
    assert created.data["name"] == max_length_name

    updated = client.put(
        f"{WORKERS}/{created.data['id']}",
        {"name": max_length_name},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["name"] == max_length_name

    too_long_name = "W" * 256
    rejected_create = client.post(
        WORKERS, {"name": too_long_name}, format="json"
    )
    assert rejected_create.status_code == 400
    assert rejected_create.data["field"] == "name"

    rejected_update = client.put(
        f"{WORKERS}/{created.data['id']}",
        {"name": too_long_name},
        format="json",
    )
    assert rejected_update.status_code == 400
    assert rejected_update.data["field"] == "name"
    assert client.get(f"{WORKERS}/{created.data['id']}").data["name"] == (
        max_length_name
    )


def test_labour_records_support_crud_and_activity_filter(client, cycle):
    activity = create_activity(client, cycle)
    worker = create_worker(client)
    record = create_labour_record(
        client, worker["id"], activity["id"], hours="3.5", hourly_cost="12.25"
    )
    assert record["hours"] == 3.5
    assert record["hourlyCost"] == 12.25
    assert record["date"] == "2026-03-10"
    assert client.get(LABOUR_RECORDS).data == [record]
    assert client.get(f"{LABOUR_RECORDS}/{record['id']}").data == record
    assert client.get(
        f"{LABOUR_RECORDS}?activityId={activity['id']}"
    ).data == [record]
    assert client.get(
        f"{LABOUR_RECORDS}?activityId=00000000-0000-0000-0000-000000000000"
    ).data == []
    invalid_filter = client.get(
        f"{LABOUR_RECORDS}?activityId=not-a-uuid"
    )
    assert invalid_filter.status_code == 400
    assert invalid_filter.data["field"] == "activityId"
    assert "valid activity ID" in invalid_filter.data["detail"]

    changed = client.put(
        f"{LABOUR_RECORDS}/{record['id']}",
        {
            "workerId": worker["id"],
            "activityId": activity["id"],
            "hours": "4",
            "hourlyCost": "11",
            "date": "2026-03-11",
        },
        format="json",
    )
    assert changed.status_code == 200
    assert changed.data["hours"] == 4
    assert changed.data["hourlyCost"] == 11
    assert changed.data["date"] == "2026-03-11"
    assert client.delete(f"{LABOUR_RECORDS}/{record['id']}").status_code == 204
    assert client.get(LABOUR_RECORDS).data == []


def test_labour_record_rejects_missing_activity(client):
    worker = create_worker(client)
    response = client.post(
        LABOUR_RECORDS,
        {
            "workerId": worker["id"],
            "activityId": "00000000-0000-0000-0000-000000000000",
            "hours": 1,
            "hourlyCost": 10,
            "date": "2026-03-10",
        },
        format="json",
    )
    assert response.status_code == 404
    assert response.data["field"] == "activityId"


def test_labour_hours_and_cost_must_be_positive(client, cycle):
    activity = create_activity(client, cycle)
    worker = create_worker(client)
    base = {
        "workerId": worker["id"],
        "activityId": activity["id"],
        "date": "2026-03-10",
    }
    for key, value, field in (
        ("hours", "0", "hours"),
        ("hours", "-1", "hours"),
        ("hourlyCost", "0", "hourly_cost"),
        ("hourlyCost", "-1", "hourly_cost"),
    ):
        response = client.post(
            LABOUR_RECORDS,
            {**base, "hours": "1", "hourlyCost": "1", key: value},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["field"] == field


def test_activity_labour_cost_totals_include_multiple_workers_and_zero(
    client, cycle
):
    cycle_data = cycle()
    first_activity = create_activity(client, cycle, cycle_data)
    second_activity = create_activity(client, cycle, cycle_data)
    first_worker = create_worker(client, "First Worker")
    second_worker = create_worker(client, "Second Worker")
    create_labour_record(
        client,
        first_worker["id"],
        first_activity["id"],
        hours="2",
        hourly_cost="10",
    )
    create_labour_record(
        client,
        second_worker["id"],
        first_activity["id"],
        hours="3",
        hourly_cost="15",
    )

    activities = client.get(
        f"/api/activities?cycle={first_activity['cycleId']}"
    ).data
    totals = {item["id"]: item["totalLabourCost"] for item in activities}
    assert totals[first_activity["id"]] == 65
    assert totals[second_activity["id"]] == 0


def test_worker_with_labour_records_cannot_be_deleted(client, cycle):
    activity = create_activity(client, cycle)
    worker = create_worker(client)
    record = create_labour_record(client, worker["id"], activity["id"])

    response = client.delete(f"{WORKERS}/{worker['id']}")
    assert response.status_code == 409
    assert client.get(f"{WORKERS}/{worker['id']}").status_code == 200
    assert client.get(f"{LABOUR_RECORDS}/{record['id']}").status_code == 200


def test_worker_and_labour_endpoints_are_farm_scoped(client, cycle):
    activity = create_activity(client, cycle)
    worker = create_worker(client)
    record = create_labour_record(client, worker["id"], activity["id"])

    other_client = APIClient()
    registered = register(
        other_client, email="other-worker-farm@agrivanta.test"
    )
    assert registered.status_code == 201, registered.data
    other_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {registered.data['token']}"
    )

    assert other_client.get(WORKERS).data == []
    assert other_client.get(LABOUR_RECORDS).data == []
    for method, url, payload in (
        ("get", f"{WORKERS}/{worker['id']}", None),
        ("put", f"{WORKERS}/{worker['id']}", {"name": "Other"}),
        ("delete", f"{WORKERS}/{worker['id']}", None),
        ("get", f"{LABOUR_RECORDS}/{record['id']}", None),
        (
            "put",
            f"{LABOUR_RECORDS}/{record['id']}",
            {
                "workerId": worker["id"],
                "activityId": activity["id"],
                "hours": 1,
                "hourlyCost": 1,
                "date": "2026-03-10",
            },
        ),
        ("delete", f"{LABOUR_RECORDS}/{record['id']}", None),
    ):
        response = getattr(other_client, method)(
            url, payload, format="json"
        ) if payload is not None else getattr(other_client, method)(url)
        assert response.status_code == 404

    assert client.get(f"{WORKERS}/{worker['id']}").status_code == 200
    assert client.get(f"{LABOUR_RECORDS}/{record['id']}").status_code == 200


def test_manager_can_manage_workers_and_labour_in_member_farm(client, cycle):
    activity = create_activity(client, cycle)
    worker = create_worker(client)
    record = create_labour_record(client, worker["id"], activity["id"])
    farm = Farm.objects.get(pk=worker["farmId"])

    manager = User.objects.create_user(
        email="worker-labour-manager@agrivanta.test",
        password="ManagerTest#42",
        role=Role.MANAGER,
    )
    farm.members.add(manager)
    manager_client = APIClient()
    manager_client.force_authenticate(user=manager)

    assert manager_client.get(WORKERS).data == [worker]
    assert manager_client.get(f"{WORKERS}/{worker['id']}").status_code == 200
    created_worker = manager_client.post(
        WORKERS, {"name": "Manager Worker"}, format="json"
    )
    assert created_worker.status_code == 201
    assert created_worker.data["farmId"] == str(farm.pk)
    updated_worker = manager_client.put(
        f"{WORKERS}/{created_worker.data['id']}",
        {"name": "Updated Manager Worker"},
        format="json",
    )
    assert updated_worker.status_code == 200
    assert updated_worker.data["name"] == "Updated Manager Worker"
    assert manager_client.delete(
        f"{WORKERS}/{created_worker.data['id']}"
    ).status_code == 204

    assert manager_client.get(LABOUR_RECORDS).data == [record]
    assert (
        manager_client.get(f"{LABOUR_RECORDS}/{record['id']}").status_code
        == 200
    )
    created_record = manager_client.post(
        LABOUR_RECORDS,
        {
            "workerId": worker["id"],
            "activityId": activity["id"],
            "hours": 3,
            "hourlyCost": 12,
            "date": "2026-03-11",
        },
        format="json",
    )
    assert created_record.status_code == 201
    updated_record = manager_client.put(
        f"{LABOUR_RECORDS}/{created_record.data['id']}",
        {
            "workerId": worker["id"],
            "activityId": activity["id"],
            "hours": 4,
            "hourlyCost": 13,
            "date": "2026-03-12",
        },
        format="json",
    )
    assert updated_record.status_code == 200
    assert updated_record.data["hours"] == 4
    assert manager_client.delete(
        f"{LABOUR_RECORDS}/{created_record.data['id']}"
    ).status_code == 204

    foreign_client = APIClient()
    registered = register(
        foreign_client, email="foreign-worker-farm@agrivanta.test"
    )
    assert registered.status_code == 201, registered.data
    foreign_farm = Farm.objects.get(owner_id=registered.data["user"]["id"])
    foreign_field = Field.objects.create(
        farm=foreign_farm, name="Foreign Field", area=1
    )
    foreign_crop = Crop.objects.create(farm=foreign_farm, name="Foreign Crop")
    foreign_cycle = CropCycle.objects.create(
        farm=foreign_farm,
        field=foreign_field,
        crop=foreign_crop,
        cycle_type="annual",
        start_date=date(2026, 3, 1),
    )
    foreign_type = ActivityType.objects.create(
        farm=foreign_farm, name="Foreign Activity", category="planting"
    )
    foreign_activity = Activity.objects.create(
        farm=foreign_farm,
        cycle=foreign_cycle,
        type=foreign_type,
        planned_date=date(2026, 3, 10),
    )
    foreign_worker = Worker.objects.create(
        farm=foreign_farm, name="Foreign Worker"
    )
    foreign_record = LabourRecord.objects.create(
        farm=foreign_farm,
        worker=foreign_worker,
        activity=foreign_activity,
        hours=1,
        hourly_cost=1,
        date=date(2026, 3, 10),
    )

    assert manager_client.get(WORKERS).data == [worker]
    assert manager_client.get(LABOUR_RECORDS).data == [record]
    assert manager_client.get(
        f"{WORKERS}/{foreign_worker.pk}"
    ).status_code == 404
    assert manager_client.put(
        f"{WORKERS}/{foreign_worker.pk}",
        {"name": "Changed foreign worker"},
        format="json",
    ).status_code == 404
    assert manager_client.delete(
        f"{WORKERS}/{foreign_worker.pk}"
    ).status_code == 404
    assert manager_client.get(
        f"{LABOUR_RECORDS}/{foreign_record.pk}"
    ).status_code == 404
    assert manager_client.put(
        f"{LABOUR_RECORDS}/{foreign_record.pk}",
        {
            "workerId": worker["id"],
            "activityId": activity["id"],
            "hours": 1,
            "hourlyCost": 1,
            "date": "2026-03-10",
        },
        format="json",
    ).status_code == 404
    assert manager_client.delete(
        f"{LABOUR_RECORDS}/{foreign_record.pk}"
    ).status_code == 404

    foreign_worker_record = manager_client.post(
        LABOUR_RECORDS,
        {
            "workerId": str(foreign_worker.pk),
            "activityId": activity["id"],
            "hours": 1,
            "hourlyCost": 1,
            "date": "2026-03-10",
        },
        format="json",
    )
    assert foreign_worker_record.status_code == 404
    foreign_activity_record = manager_client.post(
        LABOUR_RECORDS,
        {
            "workerId": worker["id"],
            "activityId": str(foreign_activity.pk),
            "hours": 1,
            "hourlyCost": 1,
            "date": "2026-03-10",
        },
        format="json",
    )
    assert foreign_activity_record.status_code == 404


def test_worker_and_labour_endpoints_require_owner_or_manager_role(
    client, cycle
):
    activity = create_activity(client, cycle)
    worker = create_worker(client)
    record = create_labour_record(client, worker["id"], activity["id"])
    farm = Farm.objects.get(pk=worker["farmId"])
    user = User.objects.create_user(
        email="worker-labour-worker@agrivanta.test",
        password="WorkerTest#42",
        role=Role.WORKER,
    )
    farm.members.add(user)
    worker_client = APIClient()
    worker_client.force_authenticate(user=user)

    requests = (
        ("get", WORKERS, None),
        ("post", WORKERS, {"name": "Unauthorized Worker"}),
        ("get", f"{WORKERS}/{worker['id']}", None),
        ("put", f"{WORKERS}/{worker['id']}", {"name": "Unauthorized"}),
        ("delete", f"{WORKERS}/{worker['id']}", None),
        ("get", LABOUR_RECORDS, None),
        (
            "post",
            LABOUR_RECORDS,
            {
                "workerId": worker["id"],
                "activityId": activity["id"],
                "hours": 1,
                "hourlyCost": 1,
                "date": "2026-03-10",
            },
        ),
        ("get", f"{LABOUR_RECORDS}/{record['id']}", None),
        (
            "put",
            f"{LABOUR_RECORDS}/{record['id']}",
            {
                "workerId": worker["id"],
                "activityId": activity["id"],
                "hours": 1,
                "hourlyCost": 1,
                "date": "2026-03-10",
            },
        ),
        ("delete", f"{LABOUR_RECORDS}/{record['id']}", None),
    )
    for method, url, payload in requests:
        response = (
            getattr(worker_client, method)(url, payload, format="json")
            if payload is not None
            else getattr(worker_client, method)(url)
        )
        assert response.status_code == 403


def test_worker_and_labour_endpoints_require_authentication(anon):
    detail_id = "00000000-0000-0000-0000-000000000000"
    for path in (
        WORKERS,
        f"{WORKERS}/{detail_id}",
        LABOUR_RECORDS,
        f"{LABOUR_RECORDS}/{detail_id}",
    ):
        assert anon.get(path).status_code == 401
        assert anon.post(path, {}, format="json").status_code == 401
        assert anon.put(path, {}, format="json").status_code == 401
        assert anon.delete(path).status_code == 401
