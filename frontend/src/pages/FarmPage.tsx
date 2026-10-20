import { useEffect, useState, type FormEvent } from 'react';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type { Farm } from '../services/types';

/** Shows the farm's name and reporting currency and saves edits inline. */
export function FarmPage() {
  const services = useServices();
  const [farm, setFarm] = useState<Farm | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    services.farm.get().then(
      (loaded) => {
        if (!cancelled) {
          setFarm(loaded);
        }
      },
      (error: unknown) => {
        if (!cancelled) {
          setLoadError(toErrorMessage(error));
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, [services]);

  function startEditing() {
    if (!farm) {
      return;
    }

    setName(farm.name);
    setCurrency(farm.reportingCurrency);
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setEditing(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setSubmitting(true);

    try {
      const saved = await services.farm.update({
        name,
        reportingCurrency: currency,
      });
      setFarm(saved);
      setEditing(false);
      setConfirmation('Farm saved.');
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
      <h1>Farm</h1>

      {loadError ? <p role="alert">{loadError}</p> : null}

      {farm && !editing ? (
        <>
          <dl>
            <dt>Farm name</dt>
            <dd>{farm.name}</dd>
            <dt>Reporting currency</dt>
            <dd>{farm.reportingCurrency}</dd>
          </dl>

          {confirmation ? <p role="status">{confirmation}</p> : null}

          <button type="button" onClick={startEditing}>
            Edit farm
          </button>
        </>
      ) : null}

      {farm && editing ? (
        <form aria-label="Edit farm" onSubmit={handleSubmit} noValidate>
          {formError ? <p role="alert">{formError}</p> : null}

          <div>
            <label htmlFor="farm-name">Farm name</label>
            <input
              id="farm-name"
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? 'farm-name-error' : undefined}
            />
            {errors.name ? (
              <p role="alert" id="farm-name-error">
                {errors.name}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="farm-currency">Reporting currency</label>
            <input
              id="farm-currency"
              name="reportingCurrency"
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
              aria-invalid={errors.reportingCurrency ? true : undefined}
              aria-describedby={
                errors.reportingCurrency ? 'farm-currency-error' : undefined
              }
            />
            {errors.reportingCurrency ? (
              <p role="alert" id="farm-currency-error">
                {errors.reportingCurrency}
              </p>
            ) : null}
          </div>

          <button type="submit" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save farm'}
          </button>
          <button type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
      ) : null}
    </section>
  );
}
