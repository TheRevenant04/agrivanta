import { useEffect, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type { Crop } from '../services/types';

/** List, create, and edit screen for the farm's crops. */
export function CropsPage() {
  const services = useServices();
  const [crops, setCrops] = useState<Crop[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    services.crops.list().then(
      (items) => {
        if (!cancelled) {
          setCrops(items);
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
    setCrops(await services.crops.list());
  }

  function resetForm() {
    setName('');
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

  function openEdit(crop: Crop) {
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setName(crop.name);
    setEditingId(crop.id);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setSubmitting(true);

    try {
      if (editingId) {
        await services.crops.update(editingId, { name });
      } else {
        await services.crops.create({ name });
      }

      await refresh();
      resetForm();
      setConfirmation('Crop saved.');
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
      <h1>Crops</h1>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      {loaded && crops.length === 0 && !formOpen ? (
        <EmptyState message="No crops yet.">
          <button type="button" onClick={openCreate}>
            Add crop
          </button>
        </EmptyState>
      ) : null}

      {crops.length > 0 && !formOpen ? (
        <>
          <ul>
            {crops.map((crop) => (
              <li key={crop.id}>
                <span>{crop.name}</span>
                <button type="button" onClick={() => openEdit(crop)}>
                  Edit {crop.name}
                </button>
              </li>
            ))}
          </ul>
          <button type="button" onClick={openCreate}>
            Add crop
          </button>
        </>
      ) : null}

      {formOpen ? (
        <form
          aria-label={editingId ? 'Edit crop' : 'Add crop'}
          onSubmit={handleSubmit}
          noValidate
        >
          {formError ? <p role="alert">{formError}</p> : null}

          <div>
            <label htmlFor="crop-name">Name</label>
            <input
              id="crop-name"
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? 'crop-name-error' : undefined}
            />
            {errors.name ? (
              <p role="alert" id="crop-name-error">
                {errors.name}
              </p>
            ) : null}
          </div>

          <button type="submit" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save crop'}
          </button>
          <button type="button" onClick={resetForm}>
            Cancel
          </button>
        </form>
      ) : null}
    </section>
  );
}
