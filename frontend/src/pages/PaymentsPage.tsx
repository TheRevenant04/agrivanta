import { useEffect, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/ui/button';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { PAYMENT_TYPES } from '../services/expensePaymentRules';
import { useServices } from '../services/servicesContext';
import type { Payment, PaymentInput, PaymentType } from '../services/types';

/**
 * Payment entry screen: a received/paid record with an amount and a date,
 * optionally linked to an expense or a sale, listed once it is saved.
 */
export function PaymentsPage() {
  const services = useServices();
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [type, setType] = useState<PaymentType>('paid');
  const [amount, setAmount] = useState('');
  const [date, setDate] = useState('');
  const [linkedExpenseId, setLinkedExpenseId] = useState('');
  const [linkedSaleId, setLinkedSaleId] = useState('');
  const [reference, setReference] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    services.payments.list().then(
      (items) => {
        if (!cancelled) {
          setPayments(items);
          setLoaded(true);
        }
      },
      (error: unknown) => {
        if (!cancelled) {
          setLoadError(toErrorMessage(error));
          setLoaded(true);
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, [services]);

  async function refresh() {
    setPayments(await services.payments.list());
  }

  function resetForm() {
    setType('paid');
    setAmount('');
    setDate('');
    setLinkedExpenseId('');
    setLinkedSaleId('');
    setReference('');
    setErrors({});
    setFormError(null);
    setFormOpen(false);
  }

  function openCreate() {
    resetForm();
    setConfirmation(null);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setSubmitting(true);

    const input: PaymentInput = { type, amount, date };

    if (linkedExpenseId.trim()) {
      input.linkedExpenseId = linkedExpenseId.trim();
    }
    if (linkedSaleId.trim()) {
      input.linkedSaleId = linkedSaleId.trim();
    }
    if (reference.trim()) {
      input.reference = reference.trim();
    }

    try {
      await services.payments.create(input);
      await refresh();
      resetForm();
      setConfirmation('Payment saved.');
    } catch (cause) {
      const { field, message } = apiFieldError(cause);

      if (field) {
        setErrors({ [field]: message });
      } else {
        setFormError(message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="page-section">
      <div className="space-y-1">
        <h1>Payments</h1>
        <p>Record money paid and received against expenses and sales.</p>
      </div>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      {loaded && payments.length === 0 && !formOpen ? (
        <EmptyState message="No payments yet.">
          <Button type="button" onClick={openCreate}>
            Add payment
          </Button>
        </EmptyState>
      ) : null}

      {payments.length > 0 && !formOpen ? (
        <div className="space-y-4">
          <ul className="record-list">
            {payments.map((payment) => (
              <li key={payment.id}>
                <span className="font-medium capitalize">{payment.type}</span>
                <span>{payment.amount}</span>
                <span>{payment.date}</span>
                {payment.linkedExpenseId ? (
                  <span>{payment.linkedExpenseId}</span>
                ) : null}
                {payment.linkedSaleId ? (
                  <span>{payment.linkedSaleId}</span>
                ) : null}
                {payment.reference ? <span>{payment.reference}</span> : null}
              </li>
            ))}
          </ul>
          <Button type="button" onClick={openCreate}>
            Add payment
          </Button>
        </div>
      ) : null}

      {formOpen ? (
        <form
          className="page-form"
          aria-label="Add payment"
          onSubmit={handleSubmit}
          noValidate
        >
          {formError ? <p role="alert">{formError}</p> : null}

          <div>
            <label htmlFor="payment-type">Type</label>
            <select
              id="payment-type"
              name="type"
              value={type}
              onChange={(event) => setType(event.target.value as PaymentType)}
              aria-invalid={errors.type ? true : undefined}
              aria-describedby={errors.type ? 'payment-type-error' : undefined}
            >
              {PAYMENT_TYPES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            {errors.type ? (
              <p role="alert" id="payment-type-error">
                {errors.type}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="payment-amount">Amount</label>
            <input
              id="payment-amount"
              name="amount"
              inputMode="decimal"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              aria-invalid={errors.amount ? true : undefined}
              aria-describedby={
                errors.amount ? 'payment-amount-error' : undefined
              }
            />
            {errors.amount ? (
              <p role="alert" id="payment-amount-error">
                {errors.amount}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="payment-date">Date</label>
            <input
              id="payment-date"
              name="date"
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              aria-invalid={errors.date ? true : undefined}
              aria-describedby={errors.date ? 'payment-date-error' : undefined}
            />
            {errors.date ? (
              <p role="alert" id="payment-date-error">
                {errors.date}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="payment-expense">Link to expense (optional)</label>
            <input
              id="payment-expense"
              name="linkedExpenseId"
              value={linkedExpenseId}
              onChange={(event) => setLinkedExpenseId(event.target.value)}
            />
          </div>

          <div>
            <label htmlFor="payment-sale">Link to sale (optional)</label>
            <input
              id="payment-sale"
              name="linkedSaleId"
              value={linkedSaleId}
              onChange={(event) => setLinkedSaleId(event.target.value)}
            />
          </div>

          <div>
            <label htmlFor="payment-reference">Reference (optional)</label>
            <input
              id="payment-reference"
              name="reference"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Saving...' : 'Save payment'}
            </Button>
            <Button type="button" variant="outline" onClick={resetForm}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
