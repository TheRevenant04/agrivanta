from datetime import date, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from api.audit import actor_context, system_actor
from api.models import (
    AuditEvent,
    CropCycle,
    Expense,
    ExpenseStatus,
    Farm,
    InventoryItem,
    MovementType,
    Role,
    StockMovement,
    Unit,
    User,
)
from api.tests.conftest import register
from api.transactions import reverse_expense


def events_for(farm_id, model, record_id):
    return list(
        AuditEvent.objects.filter(
            farm_id=farm_id, model=model, record_id=str(record_id)
        )
    )


def test_all_audited_models_capture_create_update_delete_and_precision(
    session, cycle
):
    data = cycle()
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    actor = farm.owner

    cycle_record = CropCycle.objects.get(pk=data["cycle"]["id"])
    cycle_id = cycle_record.pk
    unit = Unit.objects.get(pk=data["unit"]["id"])
    with actor_context(actor):
        cycle_record.expected_yield = Decimal("123.4500")
        cycle_record.save(update_fields=["expected_yield"])
        cycle_record.delete()

        item = InventoryItem.objects.create(
            farm=farm,
            name="Seed",
            unit=unit,
            reorder_level=Decimal("3.2100"),
        )
        item_id = item.pk
        movement = StockMovement.objects.create(
            farm=farm,
            item=item,
            type=MovementType.PURCHASE,
            quantity=Decimal("20.1250"),
            date=date(2026, 3, 5),
            unit_cost=Decimal("1.2345"),
        )
        movement_id = movement.pk
        item.name = "Seed stock"
        item.save(update_fields=["name"])
        movement.delete()
        item.delete()

        expense = Expense.objects.create(
            farm=farm,
            category="Inputs",
            amount=Decimal("12.3456"),
            date=date(2026, 3, 6),
            status=ExpenseStatus.DRAFT,
        )
        expense_id = expense.pk
        expense.notes = "revised"
        expense.save(update_fields=["notes"])
        expense.delete()

    cycle_events = events_for(farm.pk, "CropCycle", cycle_id)
    assert [event.action for event in cycle_events] == [
        "created",
        "updated",
        "deleted",
    ]
    assert cycle_events[0].changes["before"] is None
    assert cycle_events[0].changes["after"]["expected_yield"] is None
    assert cycle_events[1].changes == {
        "before": {"expected_yield": None},
        "after": {"expected_yield": "123.4500"},
    }
    assert cycle_events[2].changes["after"] is None

    item_events = events_for(farm.pk, "InventoryItem", item_id)
    assert [event.action for event in item_events] == [
        "created",
        "updated",
        "deleted",
    ]
    assert item_events[0].changes["after"]["reorder_level"] == "3.2100"
    assert item_events[1].changes == {
        "before": {"name": "Seed"},
        "after": {"name": "Seed stock"},
    }
    assert item_events[2].changes["before"]["name"] == "Seed stock"

    movement_events = events_for(farm.pk, "StockMovement", movement_id)
    assert [event.action for event in movement_events] == ["created", "deleted"]
    assert movement_events[0].changes["after"]["quantity"] == "20.1250"
    assert movement_events[0].changes["after"]["unit_cost"] == "1.2345"
    assert movement_events[1].changes["before"]["unit_cost"] == "1.2345"

    expense_events = events_for(farm.pk, "Expense", expense_id)
    assert [event.action for event in expense_events] == [
        "created",
        "updated",
        "deleted",
    ]
    assert expense_events[0].changes["after"]["amount"] == "12.3456"
    assert expense_events[0].changes["after"]["status"] == ExpenseStatus.DRAFT
    assert expense_events[1].changes == {
        "before": {"notes": None},
        "after": {"notes": "revised"},
    }
    assert expense_events[2].changes["before"]["amount"] == "12.3456"

    for event in (
        cycle_events + item_events + movement_events + expense_events
    ):
        assert event.actor_type == AuditEvent.ActorType.USER
        assert event.actor_id == str(actor.pk)
        assert timezone.is_aware(event.timestamp)
        assert event.timestamp.utcoffset().total_seconds() == 0


def test_farm_history_survives_farm_delete(session):
    actor = User.objects.get(pk=session["user"]["id"])
    other_owner = User.objects.create_user(
        email="other-owner@agrivanta.test",
        password="OliveHarvest#42",
    )
    with actor_context(actor):
        farm = Farm.objects.create(
            owner=other_owner,
            name="North Farm",
            reporting_currency="USD",
        )
        record_id = farm.pk
        farm.name = "Updated Farm"
        farm.save(update_fields=["name"])
        farm.delete()

    history = events_for(record_id, "Farm", record_id)
    assert [event.action for event in history] == [
        "created",
        "updated",
        "deleted",
    ]
    assert history[0].changes["before"] is None
    assert history[1].changes == {
        "before": {"name": "North Farm"},
        "after": {"name": "Updated Farm"},
    }
    assert history[2].changes["before"]["name"] == "Updated Farm"
    assert history[2].changes["after"] is None


def test_system_actor_is_explicit(session, setup):
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    unit = Unit.objects.get(pk=setup()["unit"]["id"])
    with system_actor():
        item = InventoryItem.objects.create(
            farm=farm, name="System-created", unit=unit
        )

    event = events_for(farm.pk, "InventoryItem", item.pk)[0]
    assert event.actor_type == AuditEvent.ActorType.SYSTEM
    assert event.actor_id == "system"
    assert event.actor_name == "system"
    assert event.actor_user_id is None


def test_set_null_side_effects_are_audited(session, setup):
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    unit = Unit.objects.get(pk=setup()["unit"]["id"])
    actor = farm.owner
    with actor_context(actor):
        item = InventoryItem.objects.create(
            farm=farm, name="Linked item", unit=unit
        )
        expense = Expense.objects.create(
            farm=farm,
            category="Inputs",
            amount=Decimal("3.0000"),
            date=date(2026, 3, 8),
        )
        movement = StockMovement.objects.create(
            farm=farm,
            item=item,
            type=MovementType.PURCHASE,
            quantity=Decimal("1.0000"),
            date=date(2026, 3, 8),
            expense=expense,
        )
        movement_id = movement.pk
        expense_id = expense.pk
        expense.delete()

    movement_events = events_for(farm.pk, "StockMovement", movement_id)
    assert movement_events[-1].action == AuditEvent.Action.UPDATED
    assert movement_events[-1].changes == {
        "before": {"expense": str(expense_id)},
        "after": {"expense": None},
    }


def test_noop_saves_do_not_duplicate_events_and_actor_is_required(
    session, setup
):
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    actor = farm.owner
    unit = Unit.objects.get(pk=setup()["unit"]["id"])
    item = InventoryItem.objects.create(
        farm=farm, name="No-op item", unit=unit
    )
    initial_count = len(events_for(farm.pk, "InventoryItem", item.pk))

    with actor_context(actor):
        item.save()
        InventoryItem.objects.filter(pk=item.pk).update(name=item.name)
    assert len(events_for(farm.pk, "InventoryItem", item.pk)) == initial_count

    before = len(events_for(farm.pk, "InventoryItem", item.pk))
    with actor_context(None), pytest.raises(ValidationError):
        InventoryItem.objects.create(farm=farm, name="Rejected", unit=unit)
    with actor_context(None), pytest.raises(ValidationError):
        item.name = "Unattributed"
        item.save(update_fields=["name"])
    assert not InventoryItem.objects.filter(name="Rejected").exists()
    assert len(events_for(farm.pk, "InventoryItem", item.pk)) == before


def test_reversal_events_link_original_and_compensating_records(session):
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    actor = farm.owner
    with actor_context(actor):
        original = Expense.objects.create(
            farm=farm,
            category="Inputs",
            amount=Decimal("9.8765"),
            date=date(2026, 3, 7),
            status=ExpenseStatus.POSTED,
        )
        reversal = reverse_expense(farm, original.pk)

    original_events = events_for(farm.pk, "Expense", original.pk)
    reversal_events = events_for(farm.pk, "Expense", reversal.pk)
    reversed_update = original_events[-1]
    assert reversed_update.action == AuditEvent.Action.UPDATED
    assert reversed_update.changes["after"]["reversed_at"]
    assert reversed_update.related_record_id == str(reversal.pk)
    assert reversed_update.related_event_id == reversal_events[0].pk
    assert reversal_events[0].related_record_id == str(original.pk)
    assert reversal_events[0].related_event_id == original_events[0].pk
    assert original_events[0].changes["after"]["amount"] == "9.8765"
    assert reversal_events[0].changes["after"]["amount"] == "-9.8765"


def test_audit_history_endpoint_is_authenticated_and_farm_scoped(
    client, anon, cycle, session
):
    data = cycle()
    record_id = data["cycle"]["id"]
    endpoint = f"/api/audit-events?model=CropCycle&recordId={record_id}"

    response = client.get(endpoint)
    assert response.status_code == 200
    assert response.data[0]["action"] == AuditEvent.Action.CREATED
    assert response.data[0]["actor"]["type"] == AuditEvent.ActorType.USER
    assert response.data[0]["actor"]["id"] == session["user"]["id"]
    assert datetime.fromisoformat(
        response.data[0]["timestamp"]
    ).utcoffset().total_seconds() == 0

    assert anon.get(endpoint).status_code == 401
    assert client.get("/api/audit-events?model=CropCycle").status_code == 400
    assert (
        client.get(
            "/api/audit-events?model=CropCycle&recordId=not-a-record"
        ).data
        == []
    )

    foreign_client = APIClient()
    registered = register(
        foreign_client,
        email="different-farm@agrivanta.test",
    )
    assert registered.status_code == 201
    foreign_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {registered.data['token']}"
    )
    assert foreign_client.get(endpoint).status_code == 200
    assert foreign_client.get(endpoint).data == []

    worker = User.objects.create_user(
        email="worker@agrivanta.test",
        password="OliveHarvest#42",
        role=Role.WORKER,
    )
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    farm.members.add(worker)
    from rest_framework.authtoken.models import Token

    worker_client = APIClient()
    worker_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {Token.objects.create(user=worker).key}"
    )
    denied = worker_client.get(endpoint)
    assert denied.status_code == 403
    assert "results" not in denied.data


def test_audit_events_cannot_be_modified_or_deleted(session):
    farm = Farm.objects.get(owner_id=session["user"]["id"])
    event = events_for(farm.pk, "Farm", farm.pk)[0]

    event.actor_name = "tampered"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
    with pytest.raises(ValidationError):
        AuditEvent.objects.filter(pk=event.pk).update(actor_name="tampered")
    with pytest.raises(ValidationError):
        AuditEvent.objects.filter(pk=event.pk).delete()

    event.refresh_from_db()
    assert event.actor_name != "tampered"
