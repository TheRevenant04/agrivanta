from decimal import Decimal

import pytest
from django.db import IntegrityError, models, transaction
from rest_framework.test import APIClient

from api import transactions
from api.models import (
    AllocationBasis,
    AllocationRule,
    Customer,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Harvest,
    ImmutableTransactionError,
    Payment,
    PaymentType,
    Sale,
    User,
)
from api.query_tools import crop_cycle_costs
from api.transactions import (
    ReversalError,
    expense_outstanding_balance,
    expense_paid_total,
    expense_total,
    farm_payment_totals,
    reverse_expense,
    reverse_payment,
    sale_outstanding_balance,
)

pytestmark = pytest.mark.django_db

EXPENSES = "/api/expenses"
PAYMENTS = "/api/payments"


@pytest.fixture
def owner_farm(client):
    return User.objects.get(email="owner@agrivanta.test").farm


@pytest.fixture
def other_client(db):
    other = APIClient()
    response = other.post(
        "/api/auth/register",
        {
            "name": "Other Owner",
            "email": "other@agrivanta.test",
            "password": "OliveHarvest#42",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    other.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['token']}")
    return other


def make_expense(farm, status=ExpenseStatus.POSTED, amount="100", **extra):
    values = {
        "category": ExpenseCategory.INPUTS,
        "date": "2026-03-08",
        **extra,
    }
    return Expense.objects.create(
        farm=farm, amount=Decimal(amount), status=status, **values
    )


def make_payment(farm, **extra):
    values = {"type": PaymentType.PAID, "amount": "40", "date": "2026-03-09"}
    values.update(extra)
    values["amount"] = Decimal(values["amount"])
    return Payment.objects.create(farm=farm, **values)


def make_sale(farm, built_cycle):
    customer = Customer.objects.create(farm=farm, name="Buyer")
    harvest = Harvest.objects.create(
        farm=farm,
        cycle=built_cycle,
        quantity="100",
        unit=built_cycle.field.farm.units.first(),
        date="2026-08-01",
    )
    sale = Sale.objects.create(
        farm=farm,
        customer=customer,
        harvest=harvest,
        quantity="10",
        unit_price="20",
        date="2026-08-05",
        revenue="200",
    )
    sale.refresh_from_db()
    return sale


def expense_body(**overrides):
    body = {"category": "inputs", "amount": "50", "date": "2026-03-08"}
    body.update(overrides)
    return body


# Drafts stay editable and deletable


def test_draft_expense_can_be_edited_and_deleted_through_api(client):
    created = client.post(EXPENSES, expense_body(), format="json").data
    assert created["status"] == "draft"
    assert created["reversed"] is False
    assert created["reversalOfId"] is None

    edited = client.put(
        f"{EXPENSES}/{created['id']}",
        expense_body(amount="75", notes="ignored"),
        format="json",
    )
    assert edited.status_code == 200
    assert edited.data["amount"] == 75

    assert client.delete(f"{EXPENSES}/{created['id']}").status_code == 204
    assert not Expense.objects.filter(pk=created["id"]).exists()


def test_draft_expense_supports_model_and_queryset_writes(owner_farm):
    draft = make_expense(owner_farm, ExpenseStatus.DRAFT)
    draft.amount = Decimal("10")
    draft.save()
    Expense.objects.filter(pk=draft.pk).update(amount=Decimal("11"))
    draft.refresh_from_db()
    assert draft.amount == 11
    draft.status = ExpenseStatus.POSTED
    draft.save()
    assert Expense.objects.get(pk=draft.pk).status == ExpenseStatus.POSTED

    other = make_expense(owner_farm, ExpenseStatus.DRAFT)
    other.delete()
    assert not Expense.objects.filter(pk=other.pk).exists()
    third = make_expense(owner_farm, ExpenseStatus.DRAFT)
    Expense.objects.filter(pk=third.pk).delete()
    assert not Expense.objects.filter(pk=third.pk).exists()


def test_draft_expense_cannot_be_reversed(client, owner_farm):
    draft = make_expense(owner_farm, ExpenseStatus.DRAFT)
    response = client.post(f"{EXPENSES}/{draft.pk}/reverse")
    assert response.status_code == 400
    assert Expense.objects.count() == 1
    draft.refresh_from_db()
    assert draft.reversed_at is None


# Posted expenses: API and service layer


def test_posted_expense_cannot_be_changed_or_deleted_via_api(
    client, owner_farm
):
    expense = make_expense(owner_farm)
    url = f"{EXPENSES}/{expense.pk}"
    assert client.put(url, expense_body(amount="1"), format="json").status_code == 400
    assert client.delete(url).status_code == 400
    attachment = client.post(f"{url}/attachments", {}, format="multipart")
    assert attachment.status_code == 400
    expense.refresh_from_db()
    assert expense.amount == 100
    assert expense.status == ExpenseStatus.POSTED


def test_posted_expense_model_and_queryset_writes_are_rejected(owner_farm):
    expense = make_expense(owner_farm)

    expense.amount = Decimal("1")
    with pytest.raises(ImmutableTransactionError):
        expense.save()
    with pytest.raises(ImmutableTransactionError):
        expense.save(update_fields=["amount"])
    with pytest.raises(ImmutableTransactionError):
        expense.delete()
    with pytest.raises(ImmutableTransactionError):
        Expense.objects.filter(pk=expense.pk).update(amount=1)
    with pytest.raises(ImmutableTransactionError):
        Expense.objects.filter(pk=expense.pk).update(status="draft")
    with pytest.raises(ImmutableTransactionError):
        Expense.objects.filter(pk=expense.pk).delete()
    with pytest.raises(ImmutableTransactionError):
        Expense.objects.all().delete()
    with pytest.raises(ImmutableTransactionError):
        with transaction.atomic():
            Expense.objects.bulk_update([expense], ["amount"])
    with pytest.raises(ImmutableTransactionError):
        owner_farm.expenses.all().update(notes="x")

    persisted = Expense.objects.get(pk=expense.pk)
    assert persisted.amount == 100
    assert persisted.reversed_at is None


# Posted expenses: persistence layer bypassing model and queryset guards


def test_database_rejects_direct_writes_to_posted_expense(owner_farm):
    expense = make_expense(owner_farm)
    raw = Expense._base_manager.filter(pk=expense.pk)

    for write in (
        lambda: raw.update(amount=1),
        lambda: raw.update(status=ExpenseStatus.DRAFT),
        lambda: raw.update(notes="changed"),
        lambda: raw.update(reversed_at=expense.created_at),
        lambda: raw.delete(),
        lambda: models.QuerySet(Expense).filter(pk=expense.pk).update(amount=1),
        lambda: models.QuerySet(Expense)
        .filter(pk=expense.pk)
        .delete(),
        lambda: Expense._base_manager.bulk_update(
            [Expense(pk=expense.pk, amount=1)], ["amount"]
        ),
    ):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                write()

    persisted = Expense.objects.get(pk=expense.pk)
    assert persisted.amount == 100
    assert persisted.status == ExpenseStatus.POSTED
    assert persisted.reversed_at is None


def test_database_rejects_forged_reversal_inserts(owner_farm):
    original = make_expense(owner_farm)
    forged = [
        {"amount": Decimal("-99")},
        {"amount": Decimal("100")},
        {"amount": Decimal("-100"), "date": "2026-04-01"},
        {"amount": Decimal("-100"), "status": ExpenseStatus.DRAFT},
    ]
    for override in forged:
        values = {
            "farm": owner_farm,
            "category": original.category,
            "date": original.date,
            "status": ExpenseStatus.POSTED,
            "reversal_of": original,
            **override,
        }
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Expense._base_manager.bulk_create([Expense(**values)])
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Expense._base_manager.bulk_create(
                [
                    Expense(
                        farm=owner_farm,
                        category="inputs",
                        amount=1,
                        date="2026-03-08",
                        status=ExpenseStatus.POSTED,
                        reversed_at=original.created_at,
                    )
                ]
            )
    assert Expense.objects.count() == 1


def test_database_only_allows_marking_after_reversal_exists(owner_farm):
    original = make_expense(owner_farm)
    when = original.created_at
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Expense._base_manager.filter(pk=original.pk).update(
                reversed_at=when
            )

    reversal = reverse_expense(owner_farm, original.pk)
    original.refresh_from_db()
    assert original.reversed_at == reversal.created_at
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Expense._base_manager.filter(pk=original.pk).update(
                reversed_at=None
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Expense._base_manager.filter(pk=original.pk).update(
                reversed_at=when, amount=5
            )


# Payments: API, service and persistence layers


def test_payment_cannot_be_changed_or_deleted_via_api(client, owner_farm):
    expense = make_expense(owner_farm)
    payment = make_payment(owner_farm, linked_expense=expense, reference="R")
    url = f"{PAYMENTS}/{payment.pk}"
    body = {
        "type": "paid",
        "amount": "1",
        "date": "2026-03-09",
        "reference": "changed",
    }
    assert client.put(url, body, format="json").status_code == 409
    assert client.patch(url, {"amount": "2"}, format="json").status_code == 409
    assert client.delete(url).status_code == 409
    payment.refresh_from_db()
    assert payment.amount == 40
    assert payment.reference == "R"
    assert payment.linked_expense_id == expense.pk


def test_payment_model_and_queryset_writes_are_rejected(owner_farm):
    payment = make_payment(owner_farm)
    payment.amount = Decimal("1")
    with pytest.raises(ImmutableTransactionError):
        payment.save()
    with pytest.raises(ImmutableTransactionError):
        payment.delete()
    with pytest.raises(ImmutableTransactionError):
        Payment.objects.filter(pk=payment.pk).update(amount=1)
    with pytest.raises(ImmutableTransactionError):
        Payment.objects.filter(pk=payment.pk).delete()
    with pytest.raises(ImmutableTransactionError):
        with transaction.atomic():
            Payment.objects.bulk_update([payment], ["amount"])
    assert Payment.objects.get(pk=payment.pk).amount == 40


def test_database_rejects_direct_writes_to_payment(owner_farm):
    expense = make_expense(owner_farm)
    payment = make_payment(owner_farm, linked_expense=expense)
    raw = Payment._base_manager.filter(pk=payment.pk)

    for write in (
        lambda: raw.update(amount=1),
        lambda: raw.update(type=PaymentType.RECEIVED),
        lambda: raw.update(date="2026-01-01"),
        lambda: raw.update(reference="changed"),
        lambda: raw.update(linked_expense=None),
        lambda: raw.update(reversed_at=payment.created_at),
        lambda: raw.delete(),
        lambda: models.QuerySet(Payment).filter(pk=payment.pk).delete(),
    ):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                write()
    persisted = Payment.objects.get(pk=payment.pk)
    assert persisted.amount == 40
    assert persisted.linked_expense_id == expense.pk
    assert persisted.reversed_at is None


def test_database_rejects_forged_payment_reversal(owner_farm):
    payment = make_payment(owner_farm)
    for override in (
        {"amount": Decimal("-39")},
        {"amount": Decimal("-40"), "type": PaymentType.RECEIVED},
        {"amount": Decimal("-40"), "date": "2026-01-01"},
    ):
        values = {
            "farm": owner_farm,
            "type": payment.type,
            "date": payment.date,
            "reversal_of": payment,
            **override,
        }
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Payment._base_manager.bulk_create([Payment(**values)])
    assert Payment.objects.count() == 1


def test_referenced_records_cannot_be_unlinked_or_deleted_around_payments(
    client, owner_farm
):
    draft = make_expense(owner_farm, ExpenseStatus.DRAFT)
    payment = make_payment(owner_farm, linked_expense=draft)
    response = client.delete(f"{EXPENSES}/{draft.pk}")
    assert response.status_code == 409
    payment.refresh_from_db()
    assert payment.linked_expense_id == draft.pk
    assert Expense.objects.filter(pk=draft.pk).exists()


def test_cycle_with_posted_expense_cannot_be_deleted(client, cycle, owner_farm):
    built = cycle()
    expense = make_expense(
        owner_farm, cycle=owner_farm.crop_cycles.get(pk=built["cycle"]["id"])
    )
    response = client.delete(f"/api/crop-cycles/{built['cycle']['id']}")
    assert response.status_code == 409
    expense.refresh_from_db()
    assert expense.cycle_id is not None


def test_draft_expense_is_unlinked_when_its_cycle_is_deleted(
    client, cycle, owner_farm
):
    built = cycle()
    draft = make_expense(
        owner_farm,
        ExpenseStatus.DRAFT,
        cycle=owner_farm.crop_cycles.get(pk=built["cycle"]["id"]),
    )
    response = client.delete(f"/api/crop-cycles/{built['cycle']['id']}")
    assert response.status_code == 204
    draft.refresh_from_db()
    assert draft.cycle_id is None


# Expense reversal


def test_expense_reversal_creates_linked_offsetting_record(client, owner_farm):
    cycle_less = make_expense(owner_farm, amount="100.25", supplier="Acme")
    response = client.post(f"{EXPENSES}/{cycle_less.pk}/reverse")
    assert response.status_code == 201, response.data
    assert response.data["reversalOfId"] == str(cycle_less.pk)
    assert response.data["amount"] == -100.25
    assert response.data["status"] == "posted"
    assert response.data["createdAt"]

    original = Expense.objects.get(pk=cycle_less.pk)
    reversal = Expense.objects.get(pk=response.data["id"])
    assert reversal.reversal_of_id == original.pk
    assert original.reversal == reversal
    assert original.reversed_at is not None
    assert original.reversed_at == reversal.created_at
    assert original.amount == Decimal("100.25")
    assert original.status == ExpenseStatus.POSTED
    assert original.category == reversal.category
    assert original.date == reversal.date
    assert original.supplier == reversal.supplier
    assert original.created_at == cycle_less.created_at

    listed = {row["id"]: row for row in client.get(EXPENSES).data}
    assert listed[str(original.pk)]["reversed"] is True
    assert listed[str(original.pk)]["amount"] == 100.25
    assert listed[str(reversal.pk)]["reversalOfId"] == str(original.pk)
    assert expense_total(owner_farm) == 0


def test_expense_reversal_is_single_use_and_side_effect_free(
    client, owner_farm
):
    expense = make_expense(owner_farm)
    first = client.post(f"{EXPENSES}/{expense.pk}/reverse")
    assert first.status_code == 201
    snapshot = list(Expense.objects.values_list("pk", "amount", "reversed_at"))

    again = client.post(f"{EXPENSES}/{expense.pk}/reverse")
    assert again.status_code == 409
    assert list(
        Expense.objects.values_list("pk", "amount", "reversed_at")
    ) == snapshot

    on_reversal = client.post(f"{EXPENSES}/{first.data['id']}/reverse")
    assert on_reversal.status_code == 409
    assert Expense.objects.count() == 2


def test_expense_reversal_keeps_payments_and_totals(client, owner_farm):
    expense = make_expense(owner_farm, amount="100")
    other = make_expense(owner_farm, amount="30")
    first = make_payment(owner_farm, linked_expense=expense, amount="40")
    second = make_payment(owner_farm, linked_expense=expense, amount="10")
    assert expense_total(owner_farm) == 130

    assert client.post(f"{EXPENSES}/{expense.pk}/reverse").status_code == 201

    assert expense_total(owner_farm) == 30
    assert Expense.objects.get(pk=other.pk).reversed_at is None
    assert Payment.objects.count() == 2
    for payment in (first, second):
        payment.refresh_from_db()
        assert payment.linked_expense_id == expense.pk
        assert payment.reversed_at is None
    assert expense_paid_total(expense) == 50


def test_shared_overhead_reversal_nets_out_of_cost_reports(cycle, owner_farm):
    built = cycle()
    crop_cycle = owner_farm.crop_cycles.get(pk=built["cycle"]["id"])
    AllocationRule.objects.create(
        farm=owner_farm, name="Equal", basis=AllocationBasis.PER_CYCLE_SHARE
    )
    make_expense(
        owner_farm, amount="75", cycle=crop_cycle, date="2026-03-15"
    )
    overhead = Expense.objects.create(
        farm=owner_farm,
        category=ExpenseCategory.OVERHEAD,
        amount="40",
        date="2026-03-15",
        status=ExpenseStatus.POSTED,
    )
    owner = owner_farm.owner
    period = {"start_date": "2026-03-01", "end_date": "2026-03-31"}
    before = crop_cycle_costs(owner, crop_cycle.id, **period)
    assert before["data"]["allocatedOverheads"] == 40.0

    reverse_expense(owner_farm, overhead.pk)
    after = crop_cycle_costs(owner, crop_cycle.id, **period)
    assert after["status"] == "ok", after
    assert after["data"] == {
        "directCosts": 75.0,
        "allocatedOverheads": 0.0,
        "totalCosts": 75.0,
    }


# Payment reversal


def test_linked_payment_reversal_restores_expense_balance(client, owner_farm):
    expense = make_expense(owner_farm, amount="100")
    kept = make_payment(owner_farm, linked_expense=expense, amount="25")
    payment = make_payment(owner_farm, linked_expense=expense, amount="40")
    assert expense_outstanding_balance(expense) == 35

    response = client.post(f"{PAYMENTS}/{payment.pk}/reverse")
    assert response.status_code == 201, response.data
    assert response.data["reversalOfId"] == str(payment.pk)
    assert response.data["amount"] == -40
    assert response.data["linkedExpenseId"] == str(expense.pk)
    assert response.data["linkedSaleId"] is None
    assert response.data["type"] == "paid"

    payment.refresh_from_db()
    assert payment.reversed_at is not None
    assert payment.amount == 40
    assert payment.linked_expense_id == expense.pk
    assert expense_outstanding_balance(expense) == 75
    assert expense_paid_total(expense) == 25
    kept.refresh_from_db()
    assert kept.reversed_at is None and kept.amount == 25
    assert Expense.objects.get(pk=expense.pk).amount == 100
    listed = {row["id"]: row for row in client.get(PAYMENTS).data}
    assert listed[str(payment.pk)]["reversed"] is True


def test_sale_payment_reversal_restores_sale_balance(client, cycle, owner_farm):
    built = cycle()
    sale = make_sale(
        owner_farm, owner_farm.crop_cycles.get(pk=built["cycle"]["id"])
    )
    make_payment(
        owner_farm, type=PaymentType.RECEIVED, linked_sale=sale, amount="50"
    )
    payment = make_payment(
        owner_farm, type=PaymentType.RECEIVED, linked_sale=sale, amount="80"
    )
    assert sale_outstanding_balance(sale) == 70

    response = client.post(f"{PAYMENTS}/{payment.pk}/reverse")
    assert response.status_code == 201
    assert response.data["linkedSaleId"] == str(sale.pk)
    assert response.data["linkedExpenseId"] is None
    assert sale_outstanding_balance(sale) == 150
    payment.refresh_from_db()
    assert payment.linked_sale_id == sale.pk


def test_standalone_payment_reversal_offsets_farm_totals(client, owner_farm):
    make_payment(owner_farm, type=PaymentType.RECEIVED, amount="15")
    payment = make_payment(owner_farm, type=PaymentType.RECEIVED, amount="60")
    paid = make_payment(owner_farm, type=PaymentType.PAID, amount="5")
    assert farm_payment_totals(owner_farm)["received"] == 75

    response = client.post(f"{PAYMENTS}/{payment.pk}/reverse")
    assert response.status_code == 201
    assert response.data["linkedSaleId"] is None
    assert response.data["linkedExpenseId"] is None
    assert farm_payment_totals(owner_farm) == {
        "received": Decimal("15"),
        "paid": Decimal("5"),
    }
    assert Expense.objects.count() == 0
    assert Sale.objects.count() == 0
    paid.refresh_from_db()
    assert paid.reversed_at is None


def test_payment_reversal_is_single_use_and_side_effect_free(
    client, owner_farm
):
    payment = make_payment(owner_farm)
    first = client.post(f"{PAYMENTS}/{payment.pk}/reverse")
    assert first.status_code == 201
    assert client.post(f"{PAYMENTS}/{payment.pk}/reverse").status_code == 409
    assert client.post(
        f"{PAYMENTS}/{first.data['id']}/reverse"
    ).status_code == 409
    assert Payment.objects.count() == 2
    assert farm_payment_totals(owner_farm)["paid"] == 0


# Reversal records are immutable


def test_reversal_records_cannot_be_changed_or_deleted(client, owner_farm):
    expense = make_expense(owner_farm)
    payment = make_payment(owner_farm)
    expense_reversal = reverse_expense(owner_farm, expense.pk)
    payment_reversal = reverse_payment(owner_farm, payment.pk)

    url = f"{EXPENSES}/{expense_reversal.pk}"
    assert client.put(url, expense_body(), format="json").status_code == 400
    assert client.delete(url).status_code == 400
    url = f"{PAYMENTS}/{payment_reversal.pk}"
    assert client.put(url, {}, format="json").status_code == 409
    assert client.patch(url, {}, format="json").status_code == 409
    assert client.delete(url).status_code == 409

    for record in (expense_reversal, payment_reversal):
        record.amount = Decimal("1")
        with pytest.raises(ImmutableTransactionError):
            record.save()
        with pytest.raises(ImmutableTransactionError):
            record.delete()
        model = type(record)
        with pytest.raises(ImmutableTransactionError):
            model.objects.filter(pk=record.pk).update(amount=1)
        with pytest.raises(ImmutableTransactionError):
            model.objects.filter(pk=record.pk).delete()
        raw = model._base_manager.filter(pk=record.pk)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                raw.update(amount=1)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                raw.delete()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                raw.update(reversed_at=record.created_at)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Expense._base_manager.filter(pk=expense.pk).update(
                reversal_of=expense_reversal
            )
    assert Expense.objects.get(pk=expense_reversal.pk).amount == -100


# Authorization


def test_unauthorized_reversal_changes_nothing(
    anon, other_client, client, owner_farm
):
    expense = make_expense(owner_farm)
    payment = make_payment(owner_farm)

    for url in (
        f"{EXPENSES}/{expense.pk}/reverse",
        f"{PAYMENTS}/{payment.pk}/reverse",
    ):
        assert anon.post(url).status_code == 401
        assert other_client.post(url).status_code == 404
    other_expense = other_client.post(
        EXPENSES, expense_body(status="posted"), format="json"
    ).data
    assert client.post(
        f"{EXPENSES}/{other_expense['id']}/reverse"
    ).status_code == 404

    assert anon.put(
        f"{EXPENSES}/{expense.pk}", expense_body(), format="json"
    ).status_code == 401
    assert other_client.delete(f"{EXPENSES}/{expense.pk}").status_code == 404
    assert other_client.delete(f"{PAYMENTS}/{payment.pk}").status_code == 404

    assert Expense.objects.filter(reversal_of__isnull=False).count() == 0
    assert Payment.objects.filter(reversal_of__isnull=False).count() == 0
    assert Expense.objects.get(pk=expense.pk).reversed_at is None
    assert Payment.objects.get(pk=payment.pk).reversed_at is None


def test_unknown_record_reversal_is_not_found(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"{EXPENSES}/{missing}/reverse").status_code == 404
    assert client.post(f"{PAYMENTS}/{missing}/reverse").status_code == 404
    assert client.post(f"{EXPENSES}/not-a-uuid/reverse").status_code == 404


# Atomicity and concurrency


@pytest.mark.parametrize(
    ("make", "reverse", "model"),
    [
        (make_expense, reverse_expense, Expense),
        (make_payment, reverse_payment, Payment),
    ],
)
def test_failure_between_writes_rolls_back_the_reversal(
    owner_farm, monkeypatch, make, reverse, model
):
    original = make(owner_farm)

    def boom(self, when):
        raise RuntimeError("write failed")

    monkeypatch.setattr(type(model.objects.all()), "mark_reversed", boom)
    with pytest.raises(RuntimeError):
        reverse(owner_farm, original.pk)

    monkeypatch.undo()
    assert model.objects.count() == 1
    assert model.objects.get(pk=original.pk).reversed_at is None
    reverse(owner_farm, original.pk)
    assert model.objects.count() == 2


@pytest.mark.parametrize(
    ("make", "reverse", "model"),
    [
        (make_expense, reverse_expense, Expense),
        (make_payment, reverse_payment, Payment),
    ],
)
def test_concurrent_attempt_with_stale_original_creates_one_reversal(
    owner_farm, monkeypatch, make, reverse, model
):
    original = make(owner_farm)
    stale = model.objects.get(pk=original.pk)
    reverse(owner_farm, original.pk)

    monkeypatch.setattr(transactions, "_lock", lambda *args: stale)
    with pytest.raises(ReversalError) as caught:
        reverse(owner_farm, original.pk)

    assert caught.value.status_code == 409
    assert model.objects.filter(reversal_of__isnull=False).count() == 1
    assert model.objects.count() == 2


def test_duplicate_reversal_rows_are_rejected_by_the_database(owner_farm):
    expense = make_expense(owner_farm)
    reverse_expense(owner_farm, expense.pk)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Expense._base_manager.bulk_create(
                [
                    Expense(
                        farm=owner_farm,
                        category=expense.category,
                        amount=-expense.amount,
                        date=expense.date,
                        status=ExpenseStatus.POSTED,
                        reversal_of=expense,
                    )
                ]
            )
    assert Expense.objects.filter(reversal_of=expense).count() == 1
