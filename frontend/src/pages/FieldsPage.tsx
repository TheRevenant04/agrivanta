import { useEffect, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type { Field } from '../services/types';

/** List, create, and edit screen for the farm's fields. */
export function FieldsPage() {
  const services = useServices();
  const [fields, setFields] = useState<Field[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [area, setArea] = useState('');
  const [notes, setNotes] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    services.fields.list().then(
      (items) => {
        if (!cancelled) {
          setFields(items);
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
    setFields(await services.fields.list());
  }

  function resetForm() {
    setName('');
    setArea('');
    setNotes('');
    setErrors({});
    setFormError(null);
    setEditingId(null);
    setFormOpen(false);
  }

  function openCreate() {
    resetForm();
    setConfirmation(null);
    setFormOpen(true);
  }

  function openEdit(field: Field) {
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setName(field.name);
    setArea(String(field.area));
    setNotes(field.notes ?? '');
    setEditingId(field.id);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setSubmitting(true);

    const input = { name, area, notes };

    try {
      if (editingId) {
        await services.fields.update(editingId, input);
      } else {
        await services.fields.create(input);
      }

      await refresh();
      resetForm();
      setConfirmation('Field saved.');
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
    <section>
      <h1>Fields</h1>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      {loaded && fields.length === 0 && !formOpen ? (
        <EmptyState message="No fields yet.">
          <button type="button" onClick={openCreate}>
            Add field
          </button>
        </EmptyState>
      ) : null}

      {fields.length > 0 && !formOpen ? (
        <>
          <ul>
            {fields.map((field) => (
              <li key={field.id}>
                <span>{field.name}</span>
                <span>{field.area}</span>
                <button type="button" onClick={() => openEdit(field)}>
                  Edit {field.name}
                </button>
              </li>
            ))}
          </ul>
          <button type="button" onClick={openCreate}>
            Add field
          </button>
        </>
      ) : null}

      {formOpen ? (
        <form
          aria-label={editingId ? 'Edit field' : 'Add field'}
          onSubmit={handleSubmit}
          noValidate
        >
          {formError ? <p role="alert">{formError}</p> : null}

          <div>
            <label htmlFor="field-name">Name</label>
            <input
              id="field-name"
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? 'field-name-error' : undefined}
            />
            {errors.name ? (
              <p role="alert" id="field-name-error">
                {errors.name}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="field-area">Area</label>
            <input
              id="field-area"
              name="area"
              inputMode="decimal"
              value={area}
              onChange={(event) => setArea(event.target.value)}
              aria-invalid={errors.area ? true : undefined}
              aria-describedby={errors.area ? 'field-area-error' : undefined}
            />
            {errors.area ? (
              <p role="alert" id="field-area-error">
                {errors.area}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="field-notes">Notes</label>
            <textarea
              id="field-notes"
              name="notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>

          <button type="submit" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save field'}
          </button>
          <button type="button" onClick={resetForm}>
            Cancel
          </button>
        </form>
      ) : null}
    </section>
  );
}
