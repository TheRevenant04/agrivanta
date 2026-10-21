import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../components/EmptyState';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type { Crop, CropCycle, Field, Variety } from '../services/types';

function cropNameOf(cycle: CropCycle, crops: Crop[]): string {
  return crops.find((item) => item.id === cycle.cropId)?.name ?? 'Unknown crop';
}

function varietyNameOf(cycle: CropCycle, varieties: Variety[]): string {
  return (
    varieties.find((item) => item.id === cycle.varietyId)?.name ??
    'Unknown variety'
  );
}

/** Human-readable name used in list actions and the close confirmation. */
function cycleLabel(
  cycle: CropCycle,
  crops: Crop[],
  varieties: Variety[],
): string {
  return `${cropNameOf(cycle, crops)} ${varietyNameOf(cycle, varieties)} (${cycle.startDate})`;
}

/**
 * Crop cycle screens (issue #45): pick a field to list its cycles with
 * open/closed badges, create new cycles from the existing field/crop/
 * variety data, edit the forecast amounts of open cycles, and formally
 * close a cycle behind a confirmation step.
 */
export function CropCyclesPage() {
  const services = useServices();
  const [fields, setFields] = useState<Field[]>([]);
  const [crops, setCrops] = useState<Crop[]>([]);
  const [varieties, setVarieties] = useState<Variety[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);
  const [cyclesForField, setCyclesForField] = useState<{
    fieldId: string;
    items: CropCycle[];
  } | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [fieldId, setFieldId] = useState('');
  const [cropId, setCropId] = useState('');
  const [varietyId, setVarietyId] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [expectedYield, setExpectedYield] = useState('');
  const [expectedPrice, setExpectedPrice] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  const [closingCycle, setClosingCycle] = useState<CropCycle | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      services.fields.list(),
      services.crops.list(),
      services.varieties.list(),
    ]).then(
      ([fieldItems, cropItems, varietyItems]) => {
        if (!cancelled) {
          setFields(fieldItems);
          setCrops(cropItems);
          setVarieties(varietyItems);
          setSelectedFieldId((current) => current ?? fieldItems[0]?.id ?? null);
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

  useEffect(() => {
    if (!selectedFieldId) {
      return;
    }

    let cancelled = false;

    services.cropCycles.list(selectedFieldId).then(
      (items) => {
        if (!cancelled) {
          setCyclesForField({ fieldId: selectedFieldId, items });
        }
      },
      (error: unknown) => {
        if (!cancelled) {
          setLoadError(toErrorMessage(error));
          setCyclesForField({ fieldId: selectedFieldId, items: [] });
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, [services, selectedFieldId]);

  // Stale results for a previously selected field are ignored instead of
  // being reset synchronously inside the effect.
  const cycles =
    selectedFieldId && cyclesForField?.fieldId === selectedFieldId
      ? cyclesForField.items
      : null;

  async function refresh() {
    if (selectedFieldId) {
      setCyclesForField({
        fieldId: selectedFieldId,
        items: await services.cropCycles.list(selectedFieldId),
      });
    }
  }

  function resetForm() {
    setFieldId('');
    setCropId('');
    setVarietyId('');
    setStartDate('');
    setEndDate('');
    setExpectedYield('');
    setExpectedPrice('');
    setErrors({});
    setFormError(null);
    setEditingId(null);
    setFormOpen(false);
  }

  function openCreate() {
    resetForm();
    setConfirmation(null);
    setClosingCycle(null);
    const firstCropId = crops[0]?.id ?? '';
    setFieldId(selectedFieldId ?? fields[0]?.id ?? '');
    setCropId(firstCropId);
    setVarietyId(
      varieties.find((item) => item.cropId === firstCropId)?.id ?? '',
    );
    setFormOpen(true);
  }

  function openEdit(cycle: CropCycle) {
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setClosingCycle(null);
    setEditingId(cycle.id);
    setExpectedYield(
      cycle.expectedYield !== undefined ? String(cycle.expectedYield) : '',
    );
    setExpectedPrice(
      cycle.expectedPrice !== undefined ? String(cycle.expectedPrice) : '',
    );
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setSubmitting(true);

    const wasEditing = editingId !== null;

    try {
      if (editingId) {
        await services.cropCycles.update(editingId, {
          expectedYield,
          expectedPrice,
        });
        await refresh();
      } else {
        const created = await services.cropCycles.create({
          fieldId,
          cropId,
          varietyId,
          startDate,
          endDate,
          expectedYield,
          expectedPrice,
        });

        if (created.fieldId === selectedFieldId) {
          await refresh();
        } else {
          // The cycles effect reloads the list for the newly selected field.
          setSelectedFieldId(created.fieldId);
        }
      }

      resetForm();
      setConfirmation(wasEditing ? 'Crop cycle updated.' : 'Crop cycle saved.');
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

  function openCloseConfirmation(cycle: CropCycle) {
    setDialogError(null);
    setConfirmation(null);
    setClosingCycle(cycle);
  }

  async function confirmClose() {
    if (!closingCycle) {
      return;
    }

    setDialogError(null);
    setSubmitting(true);

    try {
      await services.cropCycles.close(closingCycle.id);
      await refresh();
      setClosingCycle(null);
      setConfirmation('Crop cycle closed.');
    } catch (cause) {
      setDialogError(toErrorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  const editingCycle = editingId
    ? cycles?.find((item) => item.id === editingId)
    : undefined;
  const cropVarieties = varieties.filter((item) => item.cropId === cropId);

  return (
    <section>
      <h1>Crop cycles</h1>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      {loaded && fields.length === 0 ? (
        <EmptyState message="No fields yet.">
          <Link to="/fields">Set up fields</Link>
        </EmptyState>
      ) : null}

      {selectedFieldId ? (
        <>
          <div>
            <label htmlFor="cycle-field-filter">Show cycles for field</label>
            <select
              id="cycle-field-filter"
              value={selectedFieldId}
              onChange={(event) => {
                setSelectedFieldId(event.target.value);
                resetForm();
                setConfirmation(null);
                setClosingCycle(null);
              }}
            >
              {fields.map((field) => (
                <option key={field.id} value={field.id}>
                  {field.name}
                </option>
              ))}
            </select>
          </div>

          {cycles && cycles.length === 0 && !formOpen ? (
            <EmptyState message="No crop cycles for this field yet.">
              <button type="button" onClick={openCreate}>
                Add crop cycle
              </button>
            </EmptyState>
          ) : null}

          {cycles && cycles.length > 0 && !formOpen ? (
            <>
              <ul>
                {cycles.map((cycle) => {
                  const label = cycleLabel(cycle, crops, varieties);

                  return (
                    <li key={cycle.id}>
                      <span>{cropNameOf(cycle, crops)}</span>
                      <span>{varietyNameOf(cycle, varieties)}</span>
                      <span>Start: {cycle.startDate}</span>
                      <span>
                        {cycle.endDate ? `End: ${cycle.endDate}` : 'End: —'}
                      </span>
                      {cycle.expectedYield !== undefined ? (
                        <span>Expected yield: {cycle.expectedYield}</span>
                      ) : null}
                      {cycle.expectedPrice !== undefined ? (
                        <span>Expected price: {cycle.expectedPrice}</span>
                      ) : null}
                      <span>{cycle.status}</span>
                      {cycle.status === 'open' ? (
                        <>
                          <button type="button" onClick={() => openEdit(cycle)}>
                            Edit {label}
                          </button>
                          <button
                            type="button"
                            onClick={() => openCloseConfirmation(cycle)}
                          >
                            Close {label}
                          </button>
                        </>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              <button type="button" onClick={openCreate}>
                Add crop cycle
              </button>
            </>
          ) : null}

          {formOpen ? (
            <form
              aria-label={editingId ? 'Edit crop cycle' : 'Add crop cycle'}
              onSubmit={handleSubmit}
              noValidate
            >
              {formError ? <p role="alert">{formError}</p> : null}

              {editingId ? (
                editingCycle ? (
                  <p>
                    {cropNameOf(editingCycle, crops)}{' '}
                    {varietyNameOf(editingCycle, varieties)} — starts{' '}
                    {editingCycle.startDate}
                    {editingCycle.endDate
                      ? `, ends ${editingCycle.endDate}`
                      : ''}
                  </p>
                ) : null
              ) : (
                <>
                  <div>
                    <label htmlFor="cycle-form-field">Field</label>
                    <select
                      id="cycle-form-field"
                      name="fieldId"
                      value={fieldId}
                      onChange={(event) => setFieldId(event.target.value)}
                      aria-invalid={errors.fieldId ? true : undefined}
                      aria-describedby={
                        errors.fieldId ? 'cycle-field-error' : undefined
                      }
                    >
                      {fields.map((field) => (
                        <option key={field.id} value={field.id}>
                          {field.name}
                        </option>
                      ))}
                    </select>
                    {errors.fieldId ? (
                      <p role="alert" id="cycle-field-error">
                        {errors.fieldId}
                      </p>
                    ) : null}
                  </div>

                  <div>
                    <label htmlFor="cycle-form-crop">Crop</label>
                    <select
                      id="cycle-form-crop"
                      name="cropId"
                      value={cropId}
                      onChange={(event) => {
                        const nextCropId = event.target.value;
                        setCropId(nextCropId);
                        setVarietyId(
                          varieties.find((item) => item.cropId === nextCropId)
                            ?.id ?? '',
                        );
                      }}
                      aria-invalid={errors.cropId ? true : undefined}
                      aria-describedby={
                        errors.cropId ? 'cycle-crop-error' : undefined
                      }
                    >
                      {crops.map((crop) => (
                        <option key={crop.id} value={crop.id}>
                          {crop.name}
                        </option>
                      ))}
                    </select>
                    {errors.cropId ? (
                      <p role="alert" id="cycle-crop-error">
                        {errors.cropId}
                      </p>
                    ) : null}
                  </div>

                  <div>
                    <label htmlFor="cycle-form-variety">Variety</label>
                    <select
                      id="cycle-form-variety"
                      name="varietyId"
                      value={varietyId}
                      onChange={(event) => setVarietyId(event.target.value)}
                      aria-invalid={errors.varietyId ? true : undefined}
                      aria-describedby={
                        errors.varietyId ? 'cycle-variety-error' : undefined
                      }
                    >
                      {cropVarieties.map((variety) => (
                        <option key={variety.id} value={variety.id}>
                          {variety.name}
                        </option>
                      ))}
                    </select>
                    {errors.varietyId ? (
                      <p role="alert" id="cycle-variety-error">
                        {errors.varietyId}
                      </p>
                    ) : null}
                  </div>

                  <div>
                    <label htmlFor="cycle-form-start-date">Start date</label>
                    <input
                      id="cycle-form-start-date"
                      name="startDate"
                      type="date"
                      value={startDate}
                      onChange={(event) => setStartDate(event.target.value)}
                      aria-invalid={errors.startDate ? true : undefined}
                      aria-describedby={
                        errors.startDate ? 'cycle-start-date-error' : undefined
                      }
                    />
                    {errors.startDate ? (
                      <p role="alert" id="cycle-start-date-error">
                        {errors.startDate}
                      </p>
                    ) : null}
                  </div>

                  <div>
                    <label htmlFor="cycle-form-end-date">End date</label>
                    <input
                      id="cycle-form-end-date"
                      name="endDate"
                      type="date"
                      value={endDate}
                      onChange={(event) => setEndDate(event.target.value)}
                      aria-invalid={errors.endDate ? true : undefined}
                      aria-describedby={
                        errors.endDate ? 'cycle-end-date-error' : undefined
                      }
                    />
                    {errors.endDate ? (
                      <p role="alert" id="cycle-end-date-error">
                        {errors.endDate}
                      </p>
                    ) : null}
                  </div>
                </>
              )}

              <div>
                <label htmlFor="cycle-form-yield">Expected yield</label>
                <input
                  id="cycle-form-yield"
                  name="expectedYield"
                  inputMode="decimal"
                  value={expectedYield}
                  onChange={(event) => setExpectedYield(event.target.value)}
                  aria-invalid={errors.expectedYield ? true : undefined}
                  aria-describedby={
                    errors.expectedYield ? 'cycle-yield-error' : undefined
                  }
                />
                {errors.expectedYield ? (
                  <p role="alert" id="cycle-yield-error">
                    {errors.expectedYield}
                  </p>
                ) : null}
              </div>

              <div>
                <label htmlFor="cycle-form-price">Expected price</label>
                <input
                  id="cycle-form-price"
                  name="expectedPrice"
                  inputMode="decimal"
                  value={expectedPrice}
                  onChange={(event) => setExpectedPrice(event.target.value)}
                  aria-invalid={errors.expectedPrice ? true : undefined}
                  aria-describedby={
                    errors.expectedPrice ? 'cycle-price-error' : undefined
                  }
                />
                {errors.expectedPrice ? (
                  <p role="alert" id="cycle-price-error">
                    {errors.expectedPrice}
                  </p>
                ) : null}
              </div>

              <button type="submit" disabled={submitting}>
                {submitting ? 'Saving…' : 'Save crop cycle'}
              </button>
              <button type="button" onClick={resetForm}>
                Cancel
              </button>
            </form>
          ) : null}
        </>
      ) : null}

      {closingCycle ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Close ${cycleLabel(closingCycle, crops, varieties)}`}
        >
          <h2>Close crop cycle?</h2>
          <p>
            <strong>{cycleLabel(closingCycle, crops, varieties)}</strong> will
            be marked closed. Closed crop cycles cannot be edited.
          </p>
          {dialogError ? <p role="alert">{dialogError}</p> : null}
          <button type="button" onClick={confirmClose} disabled={submitting}>
            Confirm close
          </button>
          <button type="button" onClick={() => setClosingCycle(null)}>
            Keep cycle open
          </button>
        </div>
      ) : null}
    </section>
  );
}
