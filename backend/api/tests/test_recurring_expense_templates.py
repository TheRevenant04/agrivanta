from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from api.models import (
    Expense,
    ExpenseCategoryRecord,
    Farm,
    Notification,
    Payment,
    RecurringExpenseFrequency,
    RecurringExpenseTemplate,
    Sale,
    User,
)
from api.tasks import (
    advance_recurring_expense_date,
    process_recurring_expense_reminders,
)

TEMPLATES_URL = "/api/recurring-expense-templates"


def template_payload(client, **overrides):
    category = client.get("/api/expense-categories").data[0]
    payload = {
        "categoryId": category["id"],
        "amount": "125.50",
        "frequency": "monthly",
        "nextDueDate": "2026-03-31",
    }
    payload.update(overrides)
    return payload


def create_template(client, **overrides):
    response = client.post(
        TEMPLATES_URL,
        template_payload(client, **overrides),
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def other_farm():
    user = User.objects.create_user(
        email="other-recurring@agrivanta.test",
        password="OliveHarvest#42",
    )
    return Farm.objects.create(
        owner=user, name="Other Farm", reporting_currency="USD"
    )


@pytest.mark.parametrize(
    ("start", "frequency", "expected"),
    [
        (date(2026, 2, 28), "daily", date(2026, 3, 1)),
        (date(2026, 2, 28), "weekly", date(2026, 3, 7)),
        (date(2026, 1, 31), "monthly", date(2026, 2, 28)),
        (date(2024, 1, 31), "monthly", date(2024, 2, 29)),
        (date(2024, 2, 29), "yearly", date(2025, 2, 28)),
    ],
)
def test_advance_schedule_uses_calendar_dates(start, frequency, expected):
    assert advance_recurring_expense_date(start, frequency) == expected


def test_monthly_subsequent_advances_use_stored_due_date():
    february = advance_recurring_expense_date(
        date(2026, 1, 31), RecurringExpenseFrequency.MONTHLY
    )
    march = advance_recurring_expense_date(
        february, RecurringExpenseFrequency.MONTHLY
    )
    assert february == date(2026, 2, 28)
    assert march == date(2026, 3, 28)


def test_yearly_leap_day_retains_clamped_day_on_later_advances():
    first = advance_recurring_expense_date(
        date(2024, 2, 29), RecurringExpenseFrequency.YEARLY
    )
    second = advance_recurring_expense_date(
        first, RecurringExpenseFrequency.YEARLY
    )
    assert first == date(2025, 2, 28)
    assert second == date(2026, 2, 28)


def test_template_crud_is_farm_scoped_and_returns_fields(client):
    payload = template_payload(client)
    created = client.post(TEMPLATES_URL, payload, format="json")
    assert created.status_code == 201, created.data
    template = created.data
    assert template["farmId"] == client.get("/api/farm").data["id"]
    assert template["categoryId"] == payload["categoryId"]
    assert template["category"]
    assert template["amount"] == 125.5
    assert template["frequency"] == "monthly"
    assert template["nextDueDate"] == "2026-03-31"
    assert template["paused"] is False

    listed = client.get(TEMPLATES_URL)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.data] == [template["id"]]
    assert client.get(f"{TEMPLATES_URL}/{template['id']}").data == template

    updated = client.patch(
        f"{TEMPLATES_URL}/{template['id']}",
        {"amount": "240", "frequency": "weekly"},
        format="json",
    )
    assert updated.status_code == 200, updated.data
    assert updated.data["amount"] == 240
    assert updated.data["frequency"] == "weekly"
    assert updated.data["nextDueDate"] == "2026-03-31"

    deleted = client.delete(f"{TEMPLATES_URL}/{template['id']}")
    assert deleted.status_code == 204
    assert client.get(TEMPLATES_URL).data == []
    assert client.get(f"{TEMPLATES_URL}/{template['id']}").status_code == 404


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"categoryId": None}, "categoryId"),
        ({"amount": None}, "amount"),
        ({"amount": "0"}, "amount"),
        ({"amount": "-1"}, "amount"),
        ({"frequency": "quarterly"}, "frequency"),
        ({"frequency": ""}, "frequency"),
        ({"nextDueDate": None}, "nextDueDate"),
        ({"nextDueDate": "2026-02-30"}, "nextDueDate"),
        ({"paused": "true"}, "paused"),
    ],
)
def test_invalid_template_input_is_rejected_without_persistence(
    client, overrides, field
):
    response = client.post(
        TEMPLATES_URL,
        template_payload(client, **overrides),
        format="json",
    )
    assert response.status_code == 400
    assert response.data["field"] == field
    assert RecurringExpenseTemplate.objects.count() == 0
    assert Notification.objects.count() == 0


@pytest.mark.parametrize(
    "missing_field",
    ["categoryId", "amount", "frequency", "nextDueDate"],
)
def test_required_template_fields_are_validated(client, missing_field):
    payload = template_payload(client)
    del payload[missing_field]
    response = client.post(TEMPLATES_URL, payload, format="json")
    assert response.status_code == 400
    assert response.data["field"] == missing_field
    assert RecurringExpenseTemplate.objects.count() == 0
    assert Notification.objects.count() == 0


def test_template_rejects_foreign_category_and_farm(client):
    foreign = other_farm()
    foreign_category = foreign.expense_categories.get(name="inputs")
    response = client.post(
        TEMPLATES_URL,
        template_payload(client, categoryId=str(foreign_category.id)),
        format="json",
    )
    assert response.status_code == 404
    assert RecurringExpenseTemplate.objects.count() == 0

    payload = template_payload(client, farmId=str(foreign.id))
    response = client.post(TEMPLATES_URL, payload, format="json")
    assert response.status_code == 403
    assert response.data["field"] == "farmId"
    assert RecurringExpenseTemplate.objects.count() == 0


def test_templates_are_isolated_from_other_farms_and_unauthenticated_users(
    client, anon
):
    template = create_template(client)
    foreign = other_farm()
    foreign_category = foreign.expense_categories.get(name="inputs")
    secret = RecurringExpenseTemplate.objects.create(
        farm=foreign,
        category=foreign_category,
        amount=Decimal("70"),
        frequency="weekly",
        next_due_date=date(2026, 1, 1),
    )
    original_date = secret.next_due_date
    original_amount = secret.amount

    assert client.get(TEMPLATES_URL).data == [template]
    assert client.get(f"{TEMPLATES_URL}/{secret.id}").status_code == 404
    assert client.patch(
        f"{TEMPLATES_URL}/{secret.id}",
        {"amount": "500"},
        format="json",
    ).status_code == 404
    assert client.delete(f"{TEMPLATES_URL}/{secret.id}").status_code == 404
    assert RecurringExpenseTemplate.objects.get(pk=secret.pk).amount == original_amount
    assert RecurringExpenseTemplate.objects.get(pk=secret.pk).next_due_date == original_date

    assert anon.get(TEMPLATES_URL).status_code in (401, 403)
    assert anon.post(TEMPLATES_URL, {}, format="json").status_code in (401, 403)
    assert RecurringExpenseTemplate.objects.count() == 2


def test_model_validates_amount_frequency_and_farm_category(client):
    payload = create_template(client)
    template = RecurringExpenseTemplate.objects.get(pk=payload["id"])
    template.amount = Decimal("0")
    with pytest.raises(ValidationError):
        template.full_clean()
    template.amount = Decimal("1")
    template.frequency = "quarterly"
    with pytest.raises(ValidationError):
        template.full_clean()

    foreign = other_farm()
    template.frequency = "monthly"
    template.category = foreign.expense_categories.get(name="inputs")
    with pytest.raises(ValidationError):
        template.full_clean()


def test_recurring_reminder_task_is_registered_with_celery_beat():
    schedule = settings.CELERY_BEAT_SCHEDULE[
        "process-recurring-expense-reminders-daily"
    ]
    assert schedule["task"] == "api.tasks.process_recurring_expense_reminders"
    assert schedule["schedule"].hour == {0}
    assert schedule["schedule"].minute == {0}


def test_due_date_equality_overdue_and_future_filtering(client, monkeypatch):
    due_today = create_template(
        client,
        nextDueDate="2026-04-15",
        frequency="daily",
    )
    overdue = create_template(
        client,
        nextDueDate="2026-04-14",
        frequency="weekly",
    )
    future = create_template(
        client,
        nextDueDate="2026-04-16",
        frequency="yearly",
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 4, 15))

    assert process_recurring_expense_reminders.run() == 2
    assert Notification.objects.count() == 2
    assert not Notification.objects.filter(
        recurring_expense_template_id=future["id"]
    ).exists()
    assert RecurringExpenseTemplate.objects.get(pk=due_today["id"]).next_due_date == date(
        2026, 4, 16
    )
    assert RecurringExpenseTemplate.objects.get(pk=overdue["id"]).next_due_date == date(
        2026, 4, 21
    )
    assert RecurringExpenseTemplate.objects.get(pk=future["id"]).next_due_date == date(
        2026, 4, 16
    )


def test_due_date_uses_configured_timezone_on_date_rollover(client):
    from django.test import override_settings

    template = create_template(
        client,
        nextDueDate="2026-01-01",
        frequency="weekly",
    )
    with (
        override_settings(TIME_ZONE="America/Los_Angeles"),
        timezone.override("America/Los_Angeles"),
    ):
        timezone_now = datetime(2026, 1, 1, 1, tzinfo=datetime_timezone.utc)
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("django.utils.timezone.now", lambda: timezone_now)
            assert timezone.localdate() == date(2025, 12, 31)
            assert process_recurring_expense_reminders.run() == 0
            assert RecurringExpenseTemplate.objects.get(
                pk=template["id"]
            ).next_due_date == date(2026, 1, 1)

            monkeypatch.setattr(
                "django.utils.timezone.now",
                lambda: datetime(
                    2026, 1, 1, 20, tzinfo=datetime_timezone.utc
                ),
            )
            assert timezone.localdate() == date(2026, 1, 1)
            assert process_recurring_expense_reminders.run() == 1


def test_task_creates_traceable_idempotent_reminder_without_transactions(
    client, monkeypatch
):
    template = create_template(
        client,
        nextDueDate="2026-02-28",
        frequency="monthly",
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 2, 28))
    expenses_before = list(Expense.objects.values_list("pk", "amount", "date"))
    payments_before = list(Payment.objects.values_list("pk", "amount", "date"))
    sales_before = list(Sale.objects.values_list("pk", "revenue", "date"))

    assert process_recurring_expense_reminders.run() == 1
    assert process_recurring_expense_reminders.run() == 0
    reminder = Notification.objects.get(
        recurring_expense_template_id=template["id"]
    )
    assert str(reminder.farm_id) == template["farmId"]
    assert reminder.occurrence_date == date(2026, 2, 28)
    assert template["id"] in reminder.message
    assert template["category"] in reminder.message
    assert template["farmId"] in reminder.message
    assert "2026-02-28" in reminder.message
    assert RecurringExpenseTemplate.objects.get(pk=template["id"]).next_due_date == date(
        2026, 3, 28
    )
    assert list(Expense.objects.values_list("pk", "amount", "date")) == expenses_before
    assert list(Payment.objects.values_list("pk", "amount", "date")) == payments_before
    assert list(Sale.objects.values_list("pk", "revenue", "date")) == sales_before


def test_task_processes_only_one_missed_occurrence_per_run(client, monkeypatch):
    template = create_template(
        client,
        nextDueDate="2020-01-31",
        frequency="monthly",
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 3, 1))

    assert process_recurring_expense_reminders.run() == 1
    reminder = Notification.objects.get(
        recurring_expense_template_id=template["id"]
    )
    assert reminder.occurrence_date == date(2020, 1, 31)
    assert Notification.objects.count() == 1
    assert RecurringExpenseTemplate.objects.get(pk=template["id"]).next_due_date == date(
        2020, 2, 29
    )


def test_task_assigns_reminders_only_to_their_farm_owner(client, monkeypatch):
    own_template = create_template(
        client,
        nextDueDate="2026-03-01",
        frequency="daily",
    )
    foreign_farm = other_farm()
    foreign_template = RecurringExpenseTemplate.objects.create(
        farm=foreign_farm,
        category=foreign_farm.expense_categories.get(name="inputs"),
        amount=Decimal("70"),
        frequency="daily",
        next_due_date=date(2026, 3, 1),
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 3, 1))

    assert process_recurring_expense_reminders.run() == 2
    own_reminder = Notification.objects.get(
        recurring_expense_template_id=own_template["id"]
    )
    foreign_reminder = Notification.objects.get(
        recurring_expense_template=foreign_template
    )
    assert own_reminder.user_id == Farm.objects.get(
        pk=own_template["farmId"]
    ).owner_id
    assert foreign_reminder.user_id == foreign_farm.owner_id
    visible_reminders = client.get("/api/notifications").data["results"]
    assert [row["id"] for row in visible_reminders] == [str(own_reminder.id)]


def test_pause_suppresses_reminder_and_resume_processes_overdue_date(
    client, monkeypatch
):
    template = create_template(
        client,
        nextDueDate="2026-01-01",
        paused=True,
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 1, 5))

    assert process_recurring_expense_reminders.run() == 0
    assert Notification.objects.count() == 0
    assert RecurringExpenseTemplate.objects.get(pk=template["id"]).next_due_date == date(
        2026, 1, 1
    )

    resumed = client.patch(
        f"{TEMPLATES_URL}/{template['id']}",
        {"paused": False},
        format="json",
    )
    assert resumed.status_code == 200
    assert process_recurring_expense_reminders.run() == 1
    assert Notification.objects.get(
        recurring_expense_template_id=template["id"]
    ).occurrence_date == date(2026, 1, 1)


def test_edits_preserve_existing_reminder_and_date_unless_explicitly_changed(
    client, monkeypatch
):
    template = create_template(
        client,
        nextDueDate="2026-01-10",
        frequency="monthly",
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 1, 10))
    assert process_recurring_expense_reminders.run() == 1
    reminder = Notification.objects.get(
        recurring_expense_template_id=template["id"]
    )
    due_date = RecurringExpenseTemplate.objects.get(
        pk=template["id"]
    ).next_due_date
    custom_category = client.post(
        "/api/expense-categories", {"name": "Fuel"}, format="json"
    ).data

    updated = client.patch(
        f"{TEMPLATES_URL}/{template['id']}",
        {
            "categoryId": custom_category["id"],
            "amount": "90",
            "frequency": "weekly",
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["nextDueDate"] == due_date.isoformat()
    assert Notification.objects.get(pk=reminder.pk).message == reminder.message

    explicit_date = client.patch(
        f"{TEMPLATES_URL}/{template['id']}",
        {"nextDueDate": "2026-02-01"},
        format="json",
    )
    assert explicit_date.status_code == 200
    assert explicit_date.data["nextDueDate"] == "2026-02-01"
    assert Notification.objects.count() == 1


def test_stale_template_update_preserves_task_advanced_schedule(
    client, monkeypatch
):
    template = create_template(
        client,
        nextDueDate="2026-01-10",
        frequency="monthly",
    )
    today = [date(2026, 1, 10)]
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: today[0])
    original_save = RecurringExpenseTemplate.save
    task_ran_during_update = False

    def run_task_before_api_save(self, *args, **kwargs):
        nonlocal task_ran_during_update
        update_fields = kwargs.get("update_fields")
        is_api_update = update_fields is None or "amount" in update_fields
        if str(self.pk) == template["id"] and is_api_update:
            task_ran_during_update = True
            assert process_recurring_expense_reminders.run() == 1
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(
        RecurringExpenseTemplate, "save", run_task_before_api_save
    )

    updated = client.patch(
        f"{TEMPLATES_URL}/{template['id']}",
        {"amount": "90"},
        format="json",
    )

    assert updated.status_code == 200, updated.data
    assert task_ran_during_update
    assert updated.data["nextDueDate"] == "2026-02-10"
    assert RecurringExpenseTemplate.objects.get(
        pk=template["id"]
    ).next_due_date == date(2026, 2, 10)

    today[0] = date(2026, 2, 10)
    assert process_recurring_expense_reminders.run() == 1
    assert list(
        Notification.objects.filter(
            recurring_expense_template_id=template["id"]
        )
        .order_by("occurrence_date")
        .values_list("occurrence_date", flat=True)
    ) == [date(2026, 1, 10), date(2026, 2, 10)]
    assert RecurringExpenseTemplate.objects.get(
        pk=template["id"]
    ).next_due_date == date(2026, 3, 10)


def test_stale_next_due_date_rejected_without_stalling_recurrence(
    client, monkeypatch
):
    template = create_template(
        client,
        nextDueDate="2026-01-10",
        frequency="monthly",
    )
    today = [date(2026, 1, 10)]
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: today[0])
    assert process_recurring_expense_reminders.run() == 1

    stale = client.patch(
        f"{TEMPLATES_URL}/{template['id']}",
        {"amount": "90", "nextDueDate": "2026-01-10"},
        format="json",
    )

    assert stale.status_code == 409
    stored = RecurringExpenseTemplate.objects.get(pk=template["id"])
    assert stored.next_due_date == date(2026, 2, 10)
    assert stored.amount != 90

    today[0] = date(2026, 2, 10)
    assert process_recurring_expense_reminders.run() == 1
    assert RecurringExpenseTemplate.objects.get(
        pk=template["id"]
    ).next_due_date == date(2026, 3, 10)
    assert Notification.objects.filter(
        recurring_expense_template_id=template["id"]
    ).count() == 2

    future = client.patch(
        f"{TEMPLATES_URL}/{template['id']}",
        {"nextDueDate": "2026-04-01"},
        format="json",
    )
    assert future.status_code == 200
    assert future.data["nextDueDate"] == "2026-04-01"

def test_later_reminder_uses_updated_amount_category_and_frequency(
    client, monkeypatch
):
    template = create_template(
        client,
        nextDueDate="2026-01-10",
        frequency="monthly",
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 1, 10))
    assert process_recurring_expense_reminders.run() == 1
    custom_category = client.post(
        "/api/expense-categories", {"name": "Fuel"}, format="json"
    ).data
    updated = client.patch(
        f"{TEMPLATES_URL}/{template['id']}",
        {
            "categoryId": custom_category["id"],
            "amount": "90",
            "frequency": "weekly",
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["nextDueDate"] == "2026-02-10"

    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 2, 10))
    assert process_recurring_expense_reminders.run() == 1
    reminders = Notification.objects.filter(
        recurring_expense_template_id=template["id"]
    ).order_by("occurrence_date")
    assert reminders.count() == 2
    assert "Fuel" in reminders.last().message
    assert "90" in reminders.last().message
    assert RecurringExpenseTemplate.objects.get(pk=template["id"]).next_due_date == date(
        2026, 2, 17
    )


def test_deleting_template_preserves_historical_reminder(client, monkeypatch):
    template = create_template(
        client,
        nextDueDate="2026-04-05",
        frequency="daily",
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 4, 5))
    assert process_recurring_expense_reminders.run() == 1
    reminder = Notification.objects.get(
        recurring_expense_template_id=template["id"]
    )

    assert client.delete(f"{TEMPLATES_URL}/{template['id']}").status_code == 204
    reminder.refresh_from_db()
    assert reminder.recurring_expense_template_id is None
    assert str(reminder.farm_id) == template["farmId"]
    assert reminder.occurrence_date == date(2026, 4, 5)
    assert template["id"] in reminder.message
    assert process_recurring_expense_reminders.run() == 0
    assert Notification.objects.count() == 1


def test_notification_api_exposes_reminder_context(client, monkeypatch):
    template = create_template(
        client,
        nextDueDate="2026-05-01",
        frequency="daily",
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 5, 1))
    assert process_recurring_expense_reminders.run() == 1

    result = client.get("/api/notifications").data["results"][0]
    assert result["farmId"] == template["farmId"]
    assert result["recurringExpenseTemplateId"] == template["id"]
    assert result["occurrenceDate"] == "2026-05-01"


def test_reminder_and_advance_roll_back_together_on_retry(
    client, monkeypatch
):
    template = create_template(
        client,
        nextDueDate="2026-06-01",
        frequency="weekly",
    )
    monkeypatch.setattr("api.tasks.timezone.localdate", lambda: date(2026, 6, 1))
    original_save = RecurringExpenseTemplate.save

    def fail_save(self, *args, **kwargs):
        if kwargs.get("update_fields") == ["next_due_date", "updated_at"]:
            raise RuntimeError("simulated transient schedule write failure")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(RecurringExpenseTemplate, "save", fail_save)
    with pytest.raises(RuntimeError, match="simulated transient"):
        process_recurring_expense_reminders.run()
    assert Notification.objects.count() == 0
    assert RecurringExpenseTemplate.objects.get(pk=template["id"]).next_due_date == date(
        2026, 6, 1
    )

    monkeypatch.setattr(RecurringExpenseTemplate, "save", original_save)
    assert process_recurring_expense_reminders.run() == 1
    assert Notification.objects.count() == 1
    assert RecurringExpenseTemplate.objects.get(pk=template["id"]).next_due_date == date(
        2026, 6, 8
    )
