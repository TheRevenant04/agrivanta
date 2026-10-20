import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../components/EmptyState';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type { Crop, Variety } from '../services/types';

/**
 * Varieties screen: pick a crop, then manage only that crop's varieties.
 * The variety selector is scoped to the selected crop, so it can never
 * offer a variety that belongs to a different one.
 */
export function VarietiesPage() {
  const services = useServices();
  const [crops, setCrops] = useState<Crop[]>([]);
  const [varieties, setVarieties] = useState<Variety[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [selectedCropId, setSelectedCropId] = useState('');
  const [selectedVarietyId, setSelectedVarietyId] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([services.crops.list(), services.varieties.list()]).then(
      ([cropItems, varietyItems]) => {
        if (!cancelled) {
          setCrops(cropItems);
          setVarieties(varietyItems);
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
    setVarieties(await services.varieties.list());
  }

  const selectedCrop = crops.find((crop) => crop.id === selectedCropId);
  const cropVarieties = varieties.filter(
    (variety) => variety.cropId === selectedCropId,
  );

  function resetForm() {
    setName('');
    setErrors({});
    setFormError(null);
    setEditingId(null);
    setSelectedVarietyId('');
    setFormOpen(false);
  }

  function openCreate() {
    resetForm();
    setConfirmation(null);
    setFormOpen(true);
  }

  function handleVarietySelect(value: string) {
    setSelectedVarietyId(value);
    setConfirmation(null);
    setErrors({});
    setFormError(null);

    const variety = varieties.find((item) => item.id === value);

    if (variety) {
      setName(variety.name);
      setEditingId(variety.id);
      setFormOpen(true);
    } else {
      setName('');
      setEditingId(null);
      setFormOpen(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setSubmitting(true);

    try {
      if (editingId) {
        await services.varieties.update(editingId, {
          cropId: selectedCropId,
          name,
        });
      } else {
        await services.varieties.create({ cropId: selectedCropId, name });
      }

      await refresh();
      resetForm();
      setConfirmation('Variety saved.');
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

  if (loaded && crops.length === 0) {
    return (
      <section>
        <h1>Varieties</h1>
        {loadError ? <p role="alert">{loadError}</p> : null}
        <EmptyState message="No crops yet. Add a crop before adding varieties.">
          <Link to="/crops">Add crop</Link>
        </EmptyState>
      </section>
    );
  }

  return (
    <section>
      <h1>Varieties</h1>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      <div>
        <label htmlFor="variety-crop">Crop</label>
        <select
          id="variety-crop"
          value={selectedCropId}
          onChange={(event) => {
            setSelectedCropId(event.target.value);
            resetForm();
            setConfirmation(null);
          }}
        >
          <option value="">Select a crop…</option>
          {crops.map((crop) => (
            <option key={crop.id} value={crop.id}>
              {crop.name}
            </option>
          ))}
        </select>
      </div>

      {selectedCrop ? (
        <>
          <div>
            <label htmlFor="variety-select">Variety</label>
            <select
              id="variety-select"
              value={selectedVarietyId}
              onChange={(event) => handleVarietySelect(event.target.value)}
            >
              <option value="">Select a variety to edit…</option>
              {cropVarieties.map((variety) => (
                <option key={variety.id} value={variety.id}>
                  {variety.name}
                </option>
              ))}
            </select>
          </div>

          {cropVarieties.length === 0 && !formOpen ? (
            <EmptyState message={`No varieties for ${selectedCrop.name} yet.`}>
              <button type="button" onClick={openCreate}>
                Add variety
              </button>
            </EmptyState>
          ) : null}

          {cropVarieties.length > 0 && !formOpen ? (
            <>
              <ul>
                {cropVarieties.map((variety) => (
                  <li key={variety.id}>
                    <span>{variety.name}</span>
                  </li>
                ))}
              </ul>
              <button type="button" onClick={openCreate}>
                Add variety
              </button>
            </>
          ) : null}

          {formOpen ? (
            <form
              aria-label={editingId ? 'Edit variety' : 'Add variety'}
              onSubmit={handleSubmit}
              noValidate
            >
              {formError ? <p role="alert">{formError}</p> : null}

              <div>
                <label htmlFor="variety-name">Name</label>
                <input
                  id="variety-name"
                  name="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  aria-invalid={errors.name ? true : undefined}
                  aria-describedby={
                    errors.name ? 'variety-name-error' : undefined
                  }
                />
                {errors.name ? (
                  <p role="alert" id="variety-name-error">
                    {errors.name}
                  </p>
                ) : null}
              </div>

              {errors.cropId ? (
                <p role="alert" id="variety-crop-error">
                  {errors.cropId}
                </p>
              ) : null}

              <button type="submit" disabled={submitting}>
                {submitting ? 'Saving…' : 'Save variety'}
              </button>
              <button type="button" onClick={resetForm}>
                Cancel
              </button>
            </form>
          ) : null}
        </>
      ) : (
        <p>Select a crop to see its varieties.</p>
      )}
    </section>
  );
}
