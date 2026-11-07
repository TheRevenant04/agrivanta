from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    AuditEvent,
    CropCycle,
    Expense,
    Farm,
    InventoryItem,
    StockMovement,
)


@dataclass(frozen=True)
class AuditActor:
    actor_type: str
    actor_id: str
    actor_name: str
    user: object = None


_current_actor = ContextVar("audit_actor", default=None)
AUDITED_MODELS = (Farm, CropCycle, Expense, InventoryItem, StockMovement)


def set_actor(user):
    if user is not None and getattr(user, "is_authenticated", False):
        return _current_actor.set(
            AuditActor(
                AuditEvent.ActorType.USER,
                str(user.pk),
                getattr(user, "name", "").strip() or user.email,
                user,
            )
        )
    return _current_actor.set(None)


def reset_actor(token):
    _current_actor.reset(token)


@contextmanager
def actor_context(user):
    token = set_actor(user)
    try:
        yield
    finally:
        reset_actor(token)


@contextmanager
def system_actor(name="system"):
    token = _current_actor.set(
        AuditActor(AuditEvent.ActorType.SYSTEM, "system", name)
    )
    try:
        yield
    finally:
        reset_actor(token)


def _require_actor():
    actor = _current_actor.get()
    if actor is None:
        raise ValidationError(
            "An authenticated user or explicit system actor is required."
        )
    return actor


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime) and timezone.is_aware(value):
            value = value.astimezone(datetime_timezone.utc)
        return value.isoformat()
    if isinstance(value, (UUID,)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def snapshot(instance):
    return {
        field.name: _json_value(getattr(instance, field.attname))
        for field in instance._meta.concrete_fields
    }


def _farm_id(instance):
    return instance.pk if isinstance(instance, Farm) else instance.farm_id


def _record_event(instance, action, changes, related_record_id="", related_event=None):
    actor = _require_actor()
    return AuditEvent.objects.create(
        farm_id=_farm_id(instance),
        model=instance._meta.object_name,
        record_id=str(instance.pk),
        action=action,
        changes=changes,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        actor_name=actor.actor_name,
        actor_user=actor.user,
        related_record_id=str(related_record_id or ""),
        related_event=related_event,
    )


def record_deferred_update(instance, field_name, value):
    previous = snapshot(instance)
    if previous.get(field_name) == _json_value(value):
        return None
    after_value = _json_value(value)
    return _record_event(
        instance,
        AuditEvent.Action.UPDATED,
        {
            "before": {field_name: previous[field_name]},
            "after": {field_name: after_value},
        },
    )


@receiver(pre_save, sender=Farm)
@receiver(pre_save, sender=CropCycle)
@receiver(pre_save, sender=Expense)
@receiver(pre_save, sender=InventoryItem)
@receiver(pre_save, sender=StockMovement)
def capture_previous_values(sender, instance, using, **kwargs):
    _require_actor()
    instance._audit_previous_values = None
    if not instance._state.adding:
        previous = sender._base_manager.using(using).filter(
            pk=instance.pk
        ).first()
        if previous is not None:
            instance._audit_previous_values = snapshot(previous)


@receiver(post_save, sender=Farm)
@receiver(post_save, sender=CropCycle)
@receiver(post_save, sender=Expense)
@receiver(post_save, sender=InventoryItem)
@receiver(post_save, sender=StockMovement)
def save_audit_event(sender, instance, created, **kwargs):
    current = snapshot(instance)
    if created:
        action = AuditEvent.Action.CREATED
        changes = {"before": None, "after": current}
        related_record_id = ""
        related_event = None
        if isinstance(instance, Expense) and instance.reversal_of_id:
            related_record_id = instance.reversal_of_id
            related_event = (
                AuditEvent.objects.filter(
                    model="Expense",
                    record_id=str(instance.reversal_of_id),
                )
                .order_by("-timestamp", "-id")
                .first()
            )
        instance._last_audit_event = _record_event(
            instance, action, changes, related_record_id, related_event
        )
        return

    previous = getattr(instance, "_audit_previous_values", None)
    if previous is None:
        return
    changed_fields = {
        key
        for key in current
        if key != "updated_at" and previous.get(key) != current.get(key)
    }
    if not changed_fields:
        return
    changes = {
        "before": {key: previous[key] for key in changed_fields},
        "after": {key: current[key] for key in changed_fields},
    }
    instance._last_audit_event = _record_event(
        instance, AuditEvent.Action.UPDATED, changes
    )


@receiver(pre_delete, sender=Farm)
@receiver(pre_delete, sender=CropCycle)
@receiver(pre_delete, sender=Expense)
@receiver(pre_delete, sender=InventoryItem)
@receiver(pre_delete, sender=StockMovement)
def record_delete(sender, instance, **kwargs):
    _record_event(
        instance,
        AuditEvent.Action.DELETED,
        {"before": snapshot(instance), "after": None},
    )


def record_query_update(
    queryset,
    instance,
    values,
    related_record_id="",
    related_event=None,
):
    _require_actor()
    previous = snapshot(instance)
    updated = queryset._unguarded_update(**values)
    if not updated:
        return 0
    for name, value in values.items():
        setattr(instance, name, value)
    current = snapshot(instance)
    changed = {
        field: previous[field]
        for field in values
        if field != "updated_at"
        and previous.get(field) != current.get(field)
    }
    if changed:
        _record_event(
            instance,
            AuditEvent.Action.UPDATED,
            {
                "before": changed,
                "after": {field: current[field] for field in changed},
            },
            related_record_id,
            related_event,
        )
    return updated


class AuditedAPIViewMixin:
    def dispatch(self, request, *args, **kwargs):
        self._audit_actor_token = None
        try:
            return super().dispatch(request, *args, **kwargs)
        finally:
            if self._audit_actor_token is not None:
                reset_actor(self._audit_actor_token)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self._audit_actor_token = set_actor(request.user)
