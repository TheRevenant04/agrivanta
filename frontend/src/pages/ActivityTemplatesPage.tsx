import { useEffect, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { ACTIVITY_CATEGORIES } from '../services/activityPlanningRules';
import { useServices } from '../services/servicesContext';
import type { ActivityType } from '../services/types';

/**
 * List screen for activity templates: the five standard templates seeded
 * on farm creation plus any custom types the farm adds.
 */
export function ActivityTemplatesPage() {
  const services = useServices();
  const [types, setTypes] = useState<ActivityType[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState<string>('custom');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    services.activityTypes.list().then(
      (items) => {
        if (!cancelled) {
          setTypes(items);
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
    setTypes(await services.activityTypes.list());
  }

  function resetForm() {
    setName('');
    setCategory('custom');
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

    try {
      await services.activityTypes.create({ name, category });

      await refresh();
      resetForm();
      setConfirmation('Template saved.');
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
      <h1>Activity templates</h1>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      {loaded && types.length === 0 && !formOpen ? (
        <EmptyState message="No activity templates yet.">
          <button type="button" onClick={openCreate}>
            Add template
          </button>
        </EmptyState>
      ) : null}

      {types.length > 0 && !formOpen ? (
        <>
          <ul>
            {types.map((activityType) => (
              <li key={activityType.id}>
                <span>{activityType.name}</span>
                <span>{activityType.category}</span>
                {activityType.standard ? <span>standard</span> : null}
              </li>
            ))}
          </ul>
          <button type="button" onClick={openCreate}>
            Add template
          </button>
        </>
      ) : null}

      {formOpen ? (
        <form
          aria-label="Add template"
          onSubmit={(event) => void handleSubmit(event)}
          noValidate
        >
          {formError ? <p role="alert">{formError}</p> : null}

          <div>
            <label htmlFor="template-name">Template name</label>
            <input
              id="template-name"
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? 'template-name-error' : undefined}
            />
            {errors.name ? (
              <p role="alert" id="template-name-error">
                {errors.name}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="template-category">Category</label>
            <select
              id="template-category"
              name="category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              aria-invalid={errors.category ? true : undefined}
              aria-describedby={
                errors.category ? 'template-category-error' : undefined
              }
            >
              {ACTIVITY_CATEGORIES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            {errors.category ? (
              <p role="alert" id="template-category-error">
                {errors.category}
              </p>
            ) : null}
          </div>

          <button type="submit" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save template'}
          </button>
          <button type="button" onClick={resetForm}>
            Cancel
          </button>
        </form>
      ) : null}
    </section>
  );
}
