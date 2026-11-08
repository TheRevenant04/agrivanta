import { useEffect, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/ui/button';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { BASE_MEASURE_CATEGORIES } from '../services/farmSetupRules';
import { useServices } from '../services/servicesContext';
import type { Unit } from '../services/types';

/** List, create, and edit screen for units of measure. */
export function UnitsPage() {
  const services = useServices();
  const [units, setUnits] = useState<Unit[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [baseMeasure, setBaseMeasure] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    services.units.list().then(
      (items) => {
        if (!cancelled) {
          setUnits(items);
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
    setUnits(await services.units.list());
  }

  function resetForm() {
    setName('');
    setBaseMeasure('');
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

  function openEdit(unit: Unit) {
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setName(unit.name);
    setBaseMeasure(unit.baseMeasure);
    setEditingId(unit.id);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setSubmitting(true);

    try {
      if (editingId) {
        await services.units.update(editingId, { name, baseMeasure });
      } else {
        await services.units.create({ name, baseMeasure });
      }

      await refresh();
      resetForm();
      setConfirmation('Unit saved.');
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
        <h1>Units</h1>
        <p>Define the units of measure used across the farm.</p>
      </div>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      {loaded && units.length === 0 && !formOpen ? (
        <EmptyState message="No units yet.">
          <Button type="button" onClick={openCreate}>
            Add unit
          </Button>
        </EmptyState>
      ) : null}

      {units.length > 0 && !formOpen ? (
        <div className="space-y-4">
          <ul className="record-list">
            {units.map((unit) => (
              <li key={unit.id}>
                <span className="font-medium">{unit.name}</span>
                <span>{unit.baseMeasure}</span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => openEdit(unit)}
                >
                  Edit {unit.name}
                </Button>
              </li>
            ))}
          </ul>
          <Button type="button" onClick={openCreate}>
            Add unit
          </Button>
        </div>
      ) : null}

      {formOpen ? (
        <form
          className="page-form"
          aria-label={editingId ? 'Edit unit' : 'Add unit'}
          onSubmit={handleSubmit}
          noValidate
        >
          {formError ? <p role="alert">{formError}</p> : null}

          <div>
            <label htmlFor="unit-name">Name</label>
            <input
              id="unit-name"
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? 'unit-name-error' : undefined}
            />
            {errors.name ? (
              <p role="alert" id="unit-name-error">
                {errors.name}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="unit-base-measure">Base measure</label>
            <select
              id="unit-base-measure"
              name="baseMeasure"
              value={baseMeasure}
              onChange={(event) => setBaseMeasure(event.target.value)}
              aria-invalid={errors.baseMeasure ? true : undefined}
              aria-describedby={
                errors.baseMeasure ? 'unit-base-measure-error' : undefined
              }
            >
              <option value="">Select a base measure…</option>
              {BASE_MEASURE_CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </select>
            {errors.baseMeasure ? (
              <p role="alert" id="unit-base-measure-error">
                {errors.baseMeasure}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save unit'}
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
