from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from api.models import (
    Activity,
    ActivityType,
    Crop,
    CropCycle,
    Farm,
    Field,
    Role,
    User,
)


ACTIVITIES = "/api/activities"


def create_activity(client, cycle_id, type_id, **overrides):
    payload = {
        "cycleId": str(cycle_id),
        "typeId": str(type_id),
        "plannedDate": "2026-03-10",
        "description": "Plough",
    }
    payload.update(overrides)
    return client.post(ACTIVITIES, payload, format="json")


def foreign_resources():
    owner = User.objects.create_user(
        email=f"foreign-{User.objects.count()}@agrivanta.test",
        password="FarmerPassword#42",
    )
    farm = Farm.objects.create(
        owner=owner, name="Foreign Farm", reporting_currency="USD"
    )
    field = Field.objects.create(
        farm=farm, name="Foreign Field", area=Decimal("2")
    )
    crop = Crop.objects.create(farm=farm, name="Foreign Crop")
    cycle = CropCycle.objects.create(
        farm=farm,
        field=field,
        crop=crop,
        start_date=date(2026, 1, 1),
    )
    activity_type = ActivityType.objects.create(
        farm=farm, name="Foreign activity", category="custom"
    )
    return farm, cycle, activity_type


@pytest.mark.django_db
def test_activity_crud_dates_references_and_duplicate_records(
    client, cycle, setup
):
    built = cycle()
    activity_type = client.get("/api/activity-types").data[0]
    created = create_activity(
        client, built["cycle"]["id"], activity_type["id"]
    )
    duplicate = create_activity(
        client, built["cycle"]["id"], activity_type["id"]
    )

    assert created.status_code == 201
    assert created.data["status"] == "planned"
    assert created.data["assignedWorkerIds"] == []
    assert created.data["description"] == "Plough"
    assert duplicate.status_code == 201
    assert duplicate.data["id"] != created.data["id"]

    second_cycle = client.post(
        "/api/crop-cycles",
        {
            "fieldId": built["field"]["id"],
            "cropId": built["crop"]["id"],
            "varietyId": built["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2027-03-01",
        },
        format="json",
    )
    empty_cycle = client.post(
        "/api/crop-cycles",
        {
            "fieldId": built["field"]["id"],
            "cropId": built["crop"]["id"],
            "varietyId": built["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2028-03-01",
        },
        format="json",
    )
    new_type = client.post(
        "/api/activity-types",
        {"name": "Scouting", "category": "custom"},
        format="json",
    )
    assert second_cycle.status_code == 201
    assert empty_cycle.status_code == 201
    assert new_type.status_code == 201

    detail_url = f"{ACTIVITIES}/{created.data['id']}"
    assert client.get(detail_url).data["id"] == created.data["id"]

    changed = client.put(
        detail_url,
        {
            "cycleId": second_cycle.data["id"],
            "typeId": new_type.data["id"],
            "plannedDate": "2024-02-29",
            "description": "  Replant  ",
            "status": "completed",
        },
        format="json",
    )
    assert changed.status_code == 200
    assert changed.data["cycleId"] == second_cycle.data["id"]
    assert changed.data["typeId"] == new_type.data["id"]
    assert changed.data["plannedDate"] == "2024-02-29"
    assert changed.data["description"] == "Replant"
    assert changed.data["status"] == "planned"
    assert client.get(detail_url).data["plannedDate"] == "2024-02-29"

    blank_description = client.put(
        detail_url,
        {
            "cycleId": second_cycle.data["id"],
            "typeId": new_type.data["id"],
            "plannedDate": "2032-12-31",
            "description": "   ",
        },
        format="json",
    )
    assert blank_description.status_code == 200
    assert blank_description.data["plannedDate"] == "2032-12-31"
    assert blank_description.data["description"] is None

    missing_date = create_activity(
        client,
        built["cycle"]["id"],
        activity_type["id"],
        plannedDate=None,
    )
    invalid_date = create_activity(
        client,
        built["cycle"]["id"],
        activity_type["id"],
        plannedDate="2026-02-30",
    )
    assert missing_date.status_code == 400
    assert missing_date.data["field"] == "plannedDate"
    assert invalid_date.status_code == 400
    assert invalid_date.data["field"] == "plannedDate"
    assert client.get(
        f"{ACTIVITIES}?cycle={empty_cycle.data['id']}"
    ).data == []
    assert client.get(f"{ACTIVITIES}?cycle=not-a-uuid").data == []

    _, foreign_cycle, foreign_type = foreign_resources()
    wrong_cycle = create_activity(
        client, foreign_cycle.id, activity_type["id"]
    )
    wrong_type = create_activity(
        client, built["cycle"]["id"], foreign_type.id
    )
    assert wrong_cycle.status_code == 404
    assert wrong_cycle.data["field"] == "cycleId"
    assert wrong_type.status_code == 404
    assert wrong_type.data["field"] == "typeId"

    assert client.delete(detail_url).status_code == 204
    assert client.get(detail_url).status_code == 404


@pytest.mark.django_db
def test_activity_list_detail_and_mutations_are_farm_scoped(
    client, cycle
):
    built = cycle()
    activity_type = client.get("/api/activity-types").data[0]
    local = create_activity(
        client, built["cycle"]["id"], activity_type["id"]
    ).data
    _, foreign_cycle, foreign_type = foreign_resources()
    foreign_activity = Activity.objects.create(
        farm=foreign_cycle.farm,
        cycle=foreign_cycle,
        type=foreign_type,
        planned_date=date(2026, 5, 1),
    )

    assert [row["id"] for row in client.get(ACTIVITIES).data] == [local["id"]]
    assert client.get(
        f"{ACTIVITIES}?cycle={foreign_cycle.id}"
    ).data == []
    assert client.get(f"{ACTIVITIES}/{foreign_activity.id}").status_code == 404
    assert (
        client.put(
            f"{ACTIVITIES}/{foreign_activity.id}",
            {
                "cycleId": built["cycle"]["id"],
                "typeId": activity_type["id"],
                "plannedDate": "2026-05-02",
            },
            format="json",
        ).status_code
        == 404
    )
    assert (
        client.delete(f"{ACTIVITIES}/{foreign_activity.id}").status_code
        == 404
    )
    assert (
        client.put(
            f"{ACTIVITIES}/{foreign_activity.id}/status",
            {"status": "in_progress"},
            format="json",
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_closed_cycle_rejects_all_lifecycle_mutations(client, cycle):
    built = cycle()
    activity_type = client.get("/api/activity-types").data[0]
    activity = create_activity(
        client, built["cycle"]["id"], activity_type["id"]
    ).data
    activity_url = f"{ACTIVITIES}/{activity['id']}"
    closed_target = client.post(
        "/api/crop-cycles",
        {
            "fieldId": built["field"]["id"],
            "cropId": built["crop"]["id"],
            "varietyId": built["variety"]["id"],
            "cycleType": "annual",
            "startDate": "2027-03-01",
        },
        format="json",
    )
    assert closed_target.status_code == 201
    assert (
        client.post(
            f"/api/crop-cycles/{closed_target.data['id']}/close"
        ).status_code
        == 200
    )
    move_to_closed = client.put(
        activity_url,
        {
            "cycleId": closed_target.data["id"],
            "typeId": activity_type["id"],
            "plannedDate": "2026-03-11",
        },
        format="json",
    )
    assert move_to_closed.status_code == 409
    assert client.get(activity_url).data["cycleId"] == built["cycle"]["id"]
    assert (
        client.post(
            f"/api/crop-cycles/{built['cycle']['id']}/close"
        ).status_code
        == 200
    )

    create_closed = create_activity(
        client, built["cycle"]["id"], activity_type["id"]
    )
    update_closed = client.put(
        activity_url,
        {
            "cycleId": built["cycle"]["id"],
            "typeId": activity_type["id"],
            "plannedDate": "2026-03-11",
        },
        format="json",
    )
    delete_closed = client.delete(activity_url)
    status_closed = client.put(
        f"{activity_url}/status",
        {"status": "in_progress"},
        format="json",
    )
    assignees_closed = client.put(
        f"{activity_url}/assignees",
        {"assignedWorkerIds": []},
        format="json",
    )
    assert [response.status_code for response in (
        create_closed,
        update_closed,
        delete_closed,
        status_closed,
        assignees_closed,
    )] == [409] * 5


@pytest.mark.django_db
def test_assignee_replacement_validation_and_worker_visibility(
    client, cycle, session
):
    built = cycle()
    activity_type = client.get("/api/activity-types").data[0]
    assigned = create_activity(
        client, built["cycle"]["id"], activity_type["id"]
    ).data
    unassigned = create_activity(
        client, built["cycle"]["id"], activity_type["id"]
    ).data
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    worker = User.objects.create_user(
        email="worker@agrivanta.test",
        password="WorkerPassword#42",
        role=Role.WORKER,
    )
    farm.members.add(worker)
    _, foreign_cycle, foreign_type = foreign_resources()
    foreign_activity = Activity.objects.create(
        farm=foreign_cycle.farm,
        cycle=foreign_cycle,
        type=foreign_type,
        planned_date=date(2026, 5, 1),
    )
    foreign_activity.assignees.add(worker)
    url = f"{ACTIVITIES}/{assigned['id']}/assignees"

    replaced = client.put(
        url,
        {"assignedWorkerIds": [str(worker.id), str(worker.id)]},
        format="json",
    )
    assert replaced.status_code == 200
    assert replaced.data["assignedWorkerIds"] == [str(worker.id)]

    before_invalid = set(
        Activity.objects.get(pk=assigned["id"]).assignees.values_list(
            "id", flat=True
        )
    )
    non_worker = User.objects.create_user(
        email="manager@agrivanta.test",
        password="ManagerPassword#42",
        role=Role.MANAGER,
    )
    farm.members.add(non_worker)
    outsider = User.objects.create_user(
        email="outsider@agrivanta.test",
        password="OutsiderPassword#42",
        role=Role.WORKER,
    )
    invalid_responses = [
        client.put(url, {}, format="json"),
        client.put(url, {"assignedWorkerIds": "not-an-array"}, format="json"),
        client.put(url, {"assignedWorkerIds": [str(worker.id), "bad"]}, format="json"),
        client.put(
            url,
            {"assignedWorkerIds": [str(worker.id), str(non_worker.id)]},
            format="json",
        ),
        client.put(
            url,
            {"assignedWorkerIds": [str(worker.id), str(outsider.id)]},
            format="json",
        ),
    ]
    assert all(response.status_code == 400 for response in invalid_responses)
    assert set(
        Activity.objects.get(pk=assigned["id"]).assignees.values_list(
            "id", flat=True
        )
    ) == before_invalid

    worker_client = APIClient()
    worker_client.force_authenticate(user=worker)
    listed = worker_client.get(ACTIVITIES)
    assert [row["id"] for row in listed.data] == [assigned["id"]]
    assert worker_client.get(
        f"{ACTIVITIES}/cycles"
    ).data == [{"id": built["cycle"]["id"], "label": "North 40 — Wheat 2026"}]
    assert worker_client.get(f"{ACTIVITIES}/{assigned['id']}").status_code == 200
    assert worker_client.get(f"{ACTIVITIES}/{unassigned['id']}").status_code == 404
    assert (
        worker_client.put(
            f"{ACTIVITIES}/{unassigned['id']}/status",
            {"status": "in_progress"},
            format="json",
        ).status_code
        == 404
    )

    denied = [
        worker_client.post(
            ACTIVITIES,
            {
                "cycleId": built["cycle"]["id"],
                "typeId": activity_type["id"],
                "plannedDate": "2026-03-12",
            },
            format="json",
        ),
        worker_client.put(
            f"{ACTIVITIES}/{assigned['id']}",
            {
                "cycleId": built["cycle"]["id"],
                "typeId": activity_type["id"],
                "plannedDate": "2026-03-12",
            },
            format="json",
        ),
        worker_client.delete(f"{ACTIVITIES}/{assigned['id']}"),
        worker_client.put(
            f"{ACTIVITIES}/{assigned['id']}/assignees",
            {"assignedWorkerIds": []},
            format="json",
        ),
        worker_client.put(
            f"{ACTIVITIES}/{assigned['id']}/resource-needs",
            {"inputs": [], "labourHours": 0, "equipment": ""},
            format="json",
        ),
    ]
    assert [response.status_code for response in denied] == [403] * 5

    empty = client.put(url, {"assignedWorkerIds": []}, format="json")
    assert empty.status_code == 200
    assert empty.data["assignedWorkerIds"] == []
    assert worker_client.get(ACTIVITIES).data == []


@pytest.mark.django_db
def test_worker_status_transitions_and_role_matrix(client, cycle, session):
    built = cycle()
    activity_type = client.get("/api/activity-types").data[0]
    activity = create_activity(
        client, built["cycle"]["id"], activity_type["id"]
    ).data
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    worker = User.objects.create_user(
        email="assigned-worker@agrivanta.test",
        password="WorkerPassword#42",
        role=Role.WORKER,
    )
    farm.members.add(worker)
    assign_url = f"{ACTIVITIES}/{activity['id']}/assignees"
    assert client.put(
        assign_url,
        {"assignedWorkerIds": [str(worker.id)]},
        format="json",
    ).status_code == 200

    worker_client = APIClient()
    worker_client.force_authenticate(user=worker)
    activity_url = f"{ACTIVITIES}/{activity['id']}"
    missing_status = worker_client.put(
        f"{activity_url}/status", {}, format="json"
    )
    unknown_status = worker_client.put(
        f"{activity_url}/status",
        {"status": "cancelled"},
        format="json",
    )
    manual_overdue = worker_client.put(
        f"{activity_url}/status",
        {"status": "overdue"},
        format="json",
    )
    assert missing_status.status_code == 400
    assert unknown_status.status_code == 400
    assert manual_overdue.status_code == 409

    Activity.objects.filter(pk=activity["id"]).update(status="overdue")
    started = worker_client.put(
        f"{activity_url}/status",
        {"status": "in_progress"},
        format="json",
    )
    completed = worker_client.put(
        f"{activity_url}/status",
        {"status": "completed"},
        format="json",
    )
    terminal = worker_client.put(
        f"{activity_url}/status",
        {"status": "in_progress"},
        format="json",
    )
    assert started.status_code == 200
    assert completed.status_code == 200
    assert terminal.status_code == 409

    owner = User.objects.get(pk=session["user"]["id"])
    owner.role = Role.MANAGER
    owner.save(update_fields=["role"])
    manager = APIClient()
    manager.force_authenticate(user=owner)
    assert manager.get(f"{ACTIVITIES}/{activity['id']}").status_code == 200
    assert manager.put(
        f"{activity_url}/assignees",
        {"assignedWorkerIds": []},
        format="json",
    ).status_code == 200

    assigned_manager = User.objects.create_user(
        email="farm-manager@agrivanta.test",
        password="ManagerPassword#42",
        role=Role.MANAGER,
    )
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    farm.members.add(assigned_manager)
    manager_client = APIClient()
    manager_client.force_authenticate(user=assigned_manager)
    assert [
        row["id"] for row in manager_client.get(ACTIVITIES).data
    ] == [activity["id"]]
    assert manager_client.get(f"{ACTIVITIES}/{activity['id']}").status_code == 200
    manager_created = create_activity(
        manager_client, built["cycle"]["id"], activity_type["id"]
    )
    assert manager_created.status_code == 201
    assert manager_client.put(
        f"{ACTIVITIES}/{manager_created.data['id']}/status",
        {"status": "in_progress"},
        format="json",
    ).status_code == 200
    assert manager.delete(activity_url).status_code == 204


@pytest.mark.django_db
def test_unauthenticated_activity_requests_are_denied(anon):
    responses = [
        anon.get(ACTIVITIES),
        anon.post(ACTIVITIES, {}, format="json"),
        anon.get(f"{ACTIVITIES}/00000000-0000-0000-0000-000000000000"),
    ]
    assert [response.status_code for response in responses] == [401] * 3
