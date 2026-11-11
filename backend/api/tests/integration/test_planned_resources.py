from datetime import date
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from api.models import (
    Activity, Equipment, EquipmentUsage, Farm, InventoryItem, LabourRecord,
    PlannedEquipment, PlannedInput, PlannedLabour, Role, StockMovement, Unit,
    User, Worker,
)

from .test_activity_lifecycle import create_activity, foreign_resources


pytestmark = pytest.mark.django_db

KINDS = (
    ("planned-inputs", "itemId", "quantity"),
    ("planned-labour", None, "hours"),
    ("planned-equipment", "equipmentId", "hours"),
)


@pytest.fixture
def resources(client, cycle, session):
    built = cycle()
    activity_type = client.get("/api/activity-types").data[0]
    activity = create_activity(client, built["cycle"]["id"], activity_type["id"]).data
    other = create_activity(client, built["cycle"]["id"], activity_type["id"]).data
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    item = InventoryItem.objects.create(
        farm=farm, name="Seed", unit=Unit.objects.get(pk=built["unit"]["id"])
    )
    equipment = Equipment.objects.create(farm=farm, name="Tractor")
    return farm, activity, other, item, equipment


def url(activity, kind):
    return f"/api/activities/{activity['id']}/{kind}"


def payload(ref, amount, item, equipment):
    data = {amount: "2.5"}
    if ref:
        data[ref] = str(item.id if ref == "itemId" else equipment.id)
    return data


@pytest.mark.parametrize("kind,ref,amount", KINDS)
def test_crud_is_nested_and_validated(client, resources, kind, ref, amount):
    farm, activity, other, item, equipment = resources
    collection = url(activity, kind)
    other_collection = url(other, kind)
    data = payload(ref, amount, item, equipment)
    assert client.get(collection).data == []
    created = client.post(collection, data, format="json")
    assert created.status_code == 201
    line = created.data
    detail = f"{collection}/{line['id']}"
    assert client.get(detail).data == line
    assert client.get(collection).data == [line]
    assert client.get(f"{other_collection}/{line['id']}").status_code == 404
    assert client.put(f"{other_collection}/{line['id']}", data, format="json").status_code == 404
    assert client.patch(f"{other_collection}/{line['id']}", data, format="json").status_code == 404
    assert client.delete(f"{other_collection}/{line['id']}").status_code == 404
    assert client.post(f"/api/activities/{uuid4()}/{kind}", data, format="json").status_code == 404
    for bad in (None, "0", "-1", "nan", "10000000000", "0.00001", True):
        assert 400 <= client.post(collection, {**data, amount: bad}, format="json").status_code < 500
        assert 400 <= client.patch(detail, {amount: bad}, format="json").status_code < 500
    missing = {key: value for key, value in data.items() if key != amount}
    assert client.post(collection, missing, format="json").status_code == 400
    assert client.put(detail, missing, format="json").status_code == 400
    if ref:
        for bad in (None, str(uuid4()), "invalid", [], {}):
            assert 400 <= client.post(collection, {**data, ref: bad}, format="json").status_code < 500
        assert client.post(collection, {amount: "1"}, format="json").status_code == 400
        duplicate = client.post(collection, {**data, amount: "9"}, format="json")
        assert duplicate.status_code == 409
        assert client.get(detail).data == line
        second = client.post(other_collection, data, format="json")
        assert second.status_code == 201
    changed = client.patch(detail, {amount: "3.25"}, format="json")
    assert changed.status_code == 200
    assert client.get(detail).data[amount] == 3.25
    replaced = client.put(detail, {**data, amount: "4"}, format="json")
    assert replaced.status_code == 200
    assert client.get(detail).data[amount] == 4
    assert client.delete(detail).status_code == 204
    assert client.get(detail).status_code == 404
    assert client.get(collection).data == []


@pytest.mark.parametrize("kind,ref,amount", KINDS)
def test_permissions_and_closed_cycles(client, anon, resources, kind, ref, amount):
    farm, activity, other, item, equipment = resources
    collection = url(activity, kind)
    data = payload(ref, amount, item, equipment)
    line = client.post(collection, data, format="json").data
    detail = f"{collection}/{line['id']}"
    foreign_farm, _, _ = foreign_resources()
    outsider = APIClient()
    outsider.force_authenticate(foreign_farm.owner)
    worker = User.objects.create_user(email="worker-plan@example.com", role=Role.WORKER)
    farm.members.add(worker)
    worker_client = APIClient()
    worker_client.force_authenticate(worker)
    for denied in (anon, outsider, worker_client):
        for response in (
            denied.get(collection), denied.post(collection, data, format="json"),
            denied.get(detail), denied.put(detail, data, format="json"),
            denied.patch(detail, data, format="json"), denied.delete(detail),
        ):
            assert response.status_code in (401, 403, 404)
    assert client.get(detail).data == line
    instance = Activity.objects.get(pk=activity["id"])
    instance.assignees.add(worker)
    assert worker_client.get(detail).status_code == 200
    assert worker_client.post(collection, data, format="json").status_code == 403
    instance.cycle.status = "closed"
    instance.cycle.save(update_fields=["status"])
    assert client.get(detail).status_code == 200
    assert client.post(collection, data, format="json").status_code == 409
    assert client.patch(detail, {amount: "3"}, format="json").status_code == 409
    assert client.delete(detail).status_code == 409


@pytest.mark.parametrize("kind,ref,amount", [KINDS[0], KINDS[2]])
def test_farm_scope_and_update_duplicate(client, resources, kind, ref, amount):
    farm, activity, _, item, equipment = resources
    _, foreign_cycle, _ = foreign_resources()
    if ref == "itemId":
        foreign = InventoryItem.objects.create(farm=foreign_cycle.farm, name="Other", unit=item.unit)
        local = InventoryItem.objects.create(farm=farm, name="Other", unit=item.unit)
    else:
        foreign = Equipment.objects.create(farm=foreign_cycle.farm, name="Other")
        local = Equipment.objects.create(farm=farm, name="Other")
    collection = url(activity, kind)
    data = payload(ref, amount, item, equipment)
    assert client.post(collection, {**data, ref: str(foreign.id)}, format="json").status_code == 404
    first = client.post(collection, data, format="json").data
    second = client.post(collection, {**data, ref: str(local.id)}, format="json").data
    detail = f"{collection}/{second['id']}"
    assert client.patch(detail, {ref: str(foreign.id)}, format="json").status_code == 404
    assert client.patch(detail, {ref: first[ref]}, format="json").status_code == 409
    assert client.get(detail).data == second


@pytest.mark.parametrize("kind,ref,amount", [KINDS[0], KINDS[2]])
def test_referenced_resource_cannot_be_deleted(client, resources, kind, ref, amount):
    _, activity, _, item, equipment = resources
    collection = url(activity, kind)
    line = client.post(collection, payload(ref, amount, item, equipment), format="json")
    assert line.status_code == 201
    resource_url = (
        f"/api/inventory-items/{item.id}" if ref == "itemId"
        else f"/api/equipment/{equipment.id}"
    )
    assert client.delete(resource_url).status_code == 409
    assert client.get(f"{collection}/{line.data['id']}").status_code == 200
    assert client.delete(f"{collection}/{line.data['id']}").status_code == 204
    assert client.delete(resource_url).status_code == 204


def test_database_constraints(resources):
    _, activity_data, _, item, equipment = resources
    activity = Activity.objects.get(pk=activity_data["id"])
    for model, values, field in (
        (PlannedInput, {"item": item}, "quantity"),
        (PlannedEquipment, {"equipment": equipment}, "hours"),
        (PlannedLabour, {}, "hours"),
    ):
        for invalid in (0, -1):
            with pytest.raises(IntegrityError), transaction.atomic():
                model.objects.create(activity=activity, **values, **{field: invalid})
        model.objects.create(activity=activity, **values, **{field: 1})
        if values:
            with pytest.raises(IntegrityError), transaction.atomic():
                model.objects.create(activity=activity, **values, **{field: 2})


def test_manager_can_manage_plans(client, resources):
    farm, activity, _, item, equipment = resources
    manager = User.objects.create_user(email="manager-plan@example.com", role=Role.MANAGER)
    farm.members.add(manager)
    manager_client = APIClient()
    manager_client.force_authenticate(manager)
    collection = url(activity, "planned-inputs")
    response = manager_client.post(collection, {"itemId": str(item.id), "quantity": "1"}, format="json")
    assert response.status_code == 201
    detail = f"{collection}/{response.data['id']}"
    assert manager_client.get(detail).status_code == 200
    assert manager_client.patch(detail, {"quantity": "2"}, format="json").status_code == 200
    assert manager_client.delete(detail).status_code == 204


def test_plans_never_touch_actual_records(client, resources):
    farm, activity_data, _, item, equipment = resources
    activity = Activity.objects.get(pk=activity_data["id"])
    worker = Worker.objects.create(farm=farm, name="Worker")
    StockMovement.objects.create(farm=farm, item=item, activity=activity, type="purchase", quantity=5, date=date(2026, 3, 10))
    LabourRecord.objects.create(farm=farm, worker=worker, activity=activity, hours=2, hourly_cost=10, date=date(2026, 3, 10))
    EquipmentUsage.objects.create(farm=farm, equipment=equipment, activity=activity, hours=2, total_cost=12, date=date(2026, 3, 10))
    models = (StockMovement, LabourRecord, EquipmentUsage)
    before = [list(model.objects.values()) for model in models]
    for kind, ref, amount in KINDS:
        collection = url(activity_data, kind)
        data = payload(ref, amount, item, equipment)
        line = client.post(collection, data, format="json")
        assert line.status_code == 201
        assert [list(model.objects.values()) for model in models] == before
        detail = f"{collection}/{line.data['id']}"
        assert client.patch(detail, {amount: "7"}, format="json").status_code == 200
        assert [list(model.objects.values()) for model in models] == before
        assert client.delete(detail).status_code == 204
        assert [list(model.objects.values()) for model in models] == before
    assert not PlannedInput.objects.exists()
    assert not PlannedLabour.objects.exists()
    assert not PlannedEquipment.objects.exists()
