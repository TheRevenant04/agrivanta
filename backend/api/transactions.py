"""Reversal operations and balance helpers for posted expenses/payments.

A reversal is a retained compensating record: a new posted row with the
negated amount, linked to its original through ``reversal_of``. The original
is only stamped with ``reversed_at``; its transaction fields never change.
Existing sums over posted expenses and payments therefore net to the same
result as if the reversed record were absent.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    Expense,
    ExpenseStatus,
    Payment,
    PaymentType,
)


class ReversalError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _lock(model, farm, pk, not_found):
    try:
        return model.objects.select_for_update().get(farm=farm, pk=pk)
    except (model.DoesNotExist, ValueError, TypeError, ValidationError):
        raise ReversalError(not_found, 404)


def _persist_reversal(model, original, reversal):
    """Insert the reversal and stamp the original in one atomic unit."""
    try:
        with transaction.atomic():
            reversal.save()
            marked = model.objects.filter(pk=original.pk).mark_reversed(
                reversal.created_at
            )
            if marked != 1:
                raise ReversalError("That record was already reversed.", 409)
    except IntegrityError as exc:
        raise ReversalError("That record was already reversed.", 409) from exc
    return reversal


def reverse_expense(farm, expense_id):
    with transaction.atomic():
        original = _lock(
            Expense, farm, expense_id, "That expense no longer exists."
        )
        if original.is_reversal:
            raise ReversalError(
                "A reversal record cannot be reversed.", 409
            )
        if original.status != ExpenseStatus.POSTED:
            raise ReversalError(
                "Only posted expenses can be reversed.", 400
            )
        if original.reversed_at is not None:
            raise ReversalError("That expense was already reversed.", 409)
        reversal = Expense(
            farm=farm,
            cycle=original.cycle,
            category_record=original.category_record,
            category=original.category,
            amount=-original.amount,
            date=original.date,
            supplier=original.supplier,
            supplier_record=original.supplier_record,
            status=ExpenseStatus.POSTED,
            notes=f"Reversal of expense {original.pk}",
            reversal_of=original,
        )
        return _persist_reversal(Expense, original, reversal)


def reverse_payment(farm, payment_id):
    with transaction.atomic():
        original = _lock(
            Payment, farm, payment_id, "That payment no longer exists."
        )
        if original.is_reversal:
            raise ReversalError(
                "A reversal record cannot be reversed.", 409
            )
        if original.reversed_at is not None:
            raise ReversalError("That payment was already reversed.", 409)
        reversal = Payment(
            farm=farm,
            type=original.type,
            amount=-original.amount,
            date=original.date,
            linked_expense=original.linked_expense,
            linked_sale=original.linked_sale,
            reference=original.reference,
            reversal_of=original,
        )
        return _persist_reversal(Payment, original, reversal)


def _total(queryset):
    return queryset.aggregate(total=Sum("amount"))["total"] or Decimal(0)


def expense_total(farm, **filters):
    """Net posted expense total; reversals offset their originals."""
    return _total(
        Expense.objects.filter(
            farm=farm, status=ExpenseStatus.POSTED, **filters
        )
    )


def expense_paid_total(expense):
    """Net amount paid against an expense, excluding reversed payments."""
    return _total(expense.payments.all())


def expense_outstanding_balance(expense):
    return expense.amount - expense_paid_total(expense)


def sale_received_total(sale):
    return _total(sale.payments.all())


def sale_outstanding_balance(sale):
    return sale.revenue - sale_received_total(sale)


def farm_payment_totals(farm):
    """Net farm-level payment totals by type, including linked payments."""
    return {
        payment_type: _total(
            Payment.objects.filter(farm=farm, type=payment_type)
        )
        for payment_type in PaymentType.values
    }
