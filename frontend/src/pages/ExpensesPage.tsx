import { useEffect, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type { Expense, ExpenseCategory } from '../services/types';

/** The backend's expense categories (task #20). */
const CATEGORIES: ExpenseCategory[] = [
  'inputs',
  'labour',
  'equipment',
  'overhead',
  'other',
];

/**
 * Expense entry screen: drafts can be created, edited, deleted, receipt
 * attached and posted; posted records are read-only, so their edit and
 * delete controls are not rendered.
 */
export function ExpensesPage() {
  const services = useServices();
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [category, setCategory] = useState<ExpenseCategory>('inputs');
  const [amount, setAmount] = useState('');
  const [date, setDate] = useState('');
  const [supplier, setSupplier] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    services.expenses.list().then(
      (items) => {
        if (!cancelled) {
          setExpenses(items);
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
    setExpenses(await services.expenses.list());
  }

  function resetForm() {
    setCategory('inputs');
    setAmount('');
    setDate('');
    setSupplier('');
    setSelectedFile(null);
    setErrors({});
    setFormError(null);
    setEditingId(null);
    setFormOpen(false);
  }

  function openCreate() {
    resetForm();
    setConfirmation(null);
    setActionError(null);
    setFormOpen(true);
  }

  function openEdit(expense: Expense) {
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setActionError(null);
    setCategory(expense.category);
    setAmount(String(expense.amount));
    setDate(expense.date);
    setSupplier(expense.supplier ?? '');
    setSelectedFile(null);
    setEditingId(expense.id);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setSubmitting(true);

    const input = { category, amount, date, supplier };

    try {
      const saved = editingId
        ? await services.expenses.update(editingId, input)
        : await services.expenses.create(input);

      if (selectedFile) {
        await services.expenses.uploadAttachment(saved.id, selectedFile);
      }

      await refresh();
      resetForm();
      setConfirmation('Expense saved.');
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

  async function handlePost(expense: Expense) {
    setConfirmation(null);
    setActionError(null);

    try {
      await services.expenses.post(expense.id);
      await refresh();
      setConfirmation('Expense posted.');
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    }
  }

  async function handleDelete(expense: Expense) {
    setConfirmation(null);
    setActionError(null);

    try {
      await services.expenses.remove(expense.id);
      await refresh();
      setConfirmation('Expense deleted.');
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    }
  }

  return (
    <section>
      <h1>Expenses</h1>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {actionError ? <p role="alert">{actionError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      {loaded && expenses.length === 0 && !formOpen ? (
        <EmptyState message="No expenses yet.">
          <button type="button" onClick={openCreate}>
            Add expense
          </button>
        </EmptyState>
      ) : null}

      {expenses.length > 0 && !formOpen ? (
        <>
          <ul>
            {expenses.map((expense) => (
              <li key={expense.id} data-status={expense.status}>
                <span>{expense.category}</span>
                <span>{expense.amount}</span>
                <span>{expense.date}</span>
                {expense.supplier ? <span>{expense.supplier}</span> : null}
                <span>{expense.status === 'draft' ? 'draft' : 'posted'}</span>
                {expense.attachments?.length ? (
                  <span>
                    {expense.attachments[expense.attachments.length - 1].name}
                  </span>
                ) : null}
                {expense.status === 'draft' ? (
                  <>
                    <button
                      type="button"
                      aria-label={`Edit expense ${expense.id}`}
                      onClick={() => openEdit(expense)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete expense ${expense.id}`}
                      onClick={() => handleDelete(expense)}
                    >
                      Delete
                    </button>
                    <button
                      type="button"
                      aria-label={`Post expense ${expense.id}`}
                      onClick={() => handlePost(expense)}
                    >
                      Post
                    </button>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
          <button type="button" onClick={openCreate}>
            Add expense
          </button>
        </>
      ) : null}

      {formOpen ? (
        <form
          aria-label={editingId ? 'Edit expense' : 'Add expense'}
          onSubmit={handleSubmit}
          noValidate
        >
          {formError ? <p role="alert">{formError}</p> : null}

          <div>
            <label htmlFor="expense-category">Category</label>
            <select
              id="expense-category"
              name="category"
              value={category}
              onChange={(event) =>
                setCategory(event.target.value as ExpenseCategory)
              }
              aria-invalid={errors.category ? true : undefined}
              aria-describedby={
                errors.category ? 'expense-category-error' : undefined
              }
            >
              {CATEGORIES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            {errors.category ? (
              <p role="alert" id="expense-category-error">
                {errors.category}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="expense-amount">Amount</label>
            <input
              id="expense-amount"
              name="amount"
              inputMode="decimal"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              aria-invalid={errors.amount ? true : undefined}
              aria-describedby={
                errors.amount ? 'expense-amount-error' : undefined
              }
            />
            {errors.amount ? (
              <p role="alert" id="expense-amount-error">
                {errors.amount}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="expense-date">Date</label>
            <input
              id="expense-date"
              name="date"
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              aria-invalid={errors.date ? true : undefined}
              aria-describedby={errors.date ? 'expense-date-error' : undefined}
            />
            {errors.date ? (
              <p role="alert" id="expense-date-error">
                {errors.date}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="expense-supplier">Supplier (optional)</label>
            <input
              id="expense-supplier"
              name="supplier"
              value={supplier}
              onChange={(event) => setSupplier(event.target.value)}
            />
          </div>

          <div>
            <label htmlFor="expense-attachment">Receipt attachment</label>
            <input
              id="expense-attachment"
              name="attachment"
              type="file"
              onChange={(event) =>
                setSelectedFile(event.target.files?.[0] ?? null)
              }
            />
          </div>

          <button type="submit" disabled={submitting}>
            {submitting ? 'Saving...' : 'Save expense'}
          </button>
          <button type="button" onClick={resetForm}>
            Cancel
          </button>
        </form>
      ) : null}
    </section>
  );
}
