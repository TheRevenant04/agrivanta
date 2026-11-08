import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/ui/button';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type { Unit, UnitConversion } from '../services/types';

function formatQuantity(value: number): string {
  return String(Math.round(value * 10000) / 10000);
}

/** Unit conversion rules (list/create) plus a quantity conversion tool. */
export function ConversionsPage() {
  const services = useServices();
  const [units, setUnits] = useState<Unit[]>([]);
  const [rules, setRules] = useState<UnitConversion[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Rule form state.
  const [ruleFormOpen, setRuleFormOpen] = useState(false);
  const [fromUnitId, setFromUnitId] = useState('');
  const [toUnitId, setToUnitId] = useState('');
  const [factor, setFactor] = useState('');
  const [ruleErrors, setRuleErrors] = useState<Record<string, string>>({});
  const [ruleFormError, setRuleFormError] = useState<string | null>(null);
  const [submittingRule, setSubmittingRule] = useState(false);
  const [ruleConfirmation, setRuleConfirmation] = useState<string | null>(null);

  // Convert form state.
  const [convertFromId, setConvertFromId] = useState('');
  const [convertToId, setConvertToId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [convertErrors, setConvertErrors] = useState<Record<string, string>>(
    {},
  );
  const [convertFormError, setConvertFormError] = useState<string | null>(null);
  const [converting, setConverting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([services.units.list(), services.conversions.list()]).then(
      ([unitItems, ruleItems]) => {
        if (!cancelled) {
          setUnits(unitItems);
          setRules(ruleItems);
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

  const unitName = (id: string) =>
    units.find((unit) => unit.id === id)?.name ?? 'unknown unit';

  function openRuleForm() {
    setFromUnitId('');
    setToUnitId('');
    setFactor('');
    setRuleErrors({});
    setRuleFormError(null);
    setRuleConfirmation(null);
    setRuleFormOpen(true);
  }

  async function refreshRules() {
    setRules(await services.conversions.list());
  }

  async function handleRuleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRuleErrors({});
    setRuleFormError(null);
    setSubmittingRule(true);

    try {
      await services.conversions.create({ fromUnitId, toUnitId, factor });
      await refreshRules();
      setRuleFormOpen(false);
      setRuleConfirmation('Conversion rule saved.');
    } catch (cause) {
      const { field, message } = apiFieldError(cause);

      if (field) {
        setRuleErrors({ [field]: message });
      } else {
        setRuleFormError(message);
      }
    } finally {
      setSubmittingRule(false);
    }
  }

  async function handleConvert(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setConvertErrors({});
    setConvertFormError(null);
    setResult(null);
    setConverting(true);

    try {
      const converted = await services.conversions.convert({
        fromUnitId: convertFromId,
        toUnitId: convertToId,
        quantity,
      });
      setResult(
        `${formatQuantity(converted.quantity)} ${unitName(converted.fromUnitId)} = ${formatQuantity(converted.converted)} ${unitName(converted.toUnitId)}`,
      );
    } catch (cause) {
      const { field, message } = apiFieldError(cause);

      if (field) {
        setConvertErrors({ [field]: message });
      } else {
        setConvertFormError(message);
      }
    } finally {
      setConverting(false);
    }
  }

  return (
    <section className="page-section">
      <div className="space-y-1">
        <h1>Conversions</h1>
        <p>Define unit conversion rules and convert quantities.</p>
      </div>

      {loadError ? <p role="alert">{loadError}</p> : null}

      <div className="space-y-4">
        <h2>Conversion rules</h2>

        {loaded && units.length === 0 ? (
          <EmptyState message="No units yet. Create a unit before adding conversion rules.">
            <Button asChild>
              <Link to="/units">Add unit</Link>
            </Button>
          </EmptyState>
        ) : (
          <>
            {ruleConfirmation ? <p role="status">{ruleConfirmation}</p> : null}

            {loaded && rules.length === 0 && !ruleFormOpen ? (
              <EmptyState message="No conversion rules yet.">
                <Button type="button" onClick={openRuleForm}>
                  Add conversion rule
                </Button>
              </EmptyState>
            ) : null}

            {rules.length > 0 && !ruleFormOpen ? (
              <div className="space-y-4">
                <ul className="record-list">
                  {rules.map((rule) => (
                    <li key={rule.id}>
                      <span className="font-medium">
                        {unitName(rule.fromUnitId)} → {unitName(rule.toUnitId)}
                      </span>
                      <span>Factor: {rule.factor}</span>
                    </li>
                  ))}
                </ul>
                <Button type="button" onClick={openRuleForm}>
                  Add conversion rule
                </Button>
              </div>
            ) : null}

            {ruleFormOpen ? (
              <form
                className="page-form"
                aria-label="Add conversion rule"
                onSubmit={handleRuleSubmit}
                noValidate
              >
                {ruleFormError ? <p role="alert">{ruleFormError}</p> : null}

                <div>
                  <label htmlFor="conversion-from">From unit</label>
                  <select
                    id="conversion-from"
                    name="fromUnitId"
                    value={fromUnitId}
                    onChange={(event) => setFromUnitId(event.target.value)}
                    aria-invalid={ruleErrors.fromUnitId ? true : undefined}
                    aria-describedby={
                      ruleErrors.fromUnitId
                        ? 'conversion-from-error'
                        : undefined
                    }
                  >
                    <option value="">Select a unit…</option>
                    {units.map((unit) => (
                      <option key={unit.id} value={unit.id}>
                        {unit.name}
                      </option>
                    ))}
                  </select>
                  {ruleErrors.fromUnitId ? (
                    <p role="alert" id="conversion-from-error">
                      {ruleErrors.fromUnitId}
                    </p>
                  ) : null}
                </div>

                <div>
                  <label htmlFor="conversion-to">To unit</label>
                  <select
                    id="conversion-to"
                    name="toUnitId"
                    value={toUnitId}
                    onChange={(event) => setToUnitId(event.target.value)}
                    aria-invalid={ruleErrors.toUnitId ? true : undefined}
                    aria-describedby={
                      ruleErrors.toUnitId ? 'conversion-to-error' : undefined
                    }
                  >
                    <option value="">Select a unit…</option>
                    {units.map((unit) => (
                      <option key={unit.id} value={unit.id}>
                        {unit.name}
                      </option>
                    ))}
                  </select>
                  {ruleErrors.toUnitId ? (
                    <p role="alert" id="conversion-to-error">
                      {ruleErrors.toUnitId}
                    </p>
                  ) : null}
                </div>

                <div>
                  <label htmlFor="conversion-factor">Factor</label>
                  <input
                    id="conversion-factor"
                    name="factor"
                    inputMode="decimal"
                    value={factor}
                    onChange={(event) => setFactor(event.target.value)}
                    aria-invalid={ruleErrors.factor ? true : undefined}
                    aria-describedby={
                      ruleErrors.factor ? 'conversion-factor-error' : undefined
                    }
                  />
                  {ruleErrors.factor ? (
                    <p role="alert" id="conversion-factor-error">
                      {ruleErrors.factor}
                    </p>
                  ) : null}
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button type="submit" disabled={submittingRule}>
                    {submittingRule ? 'Saving…' : 'Save conversion rule'}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setRuleFormOpen(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </form>
            ) : null}
          </>
        )}
      </div>

      <div className="space-y-4">
        <h2>Convert a quantity</h2>

        <form
          className="page-form"
          aria-label="Convert a quantity"
          onSubmit={handleConvert}
          noValidate
        >
          {convertFormError ? <p role="alert">{convertFormError}</p> : null}

          <div>
            <label htmlFor="convert-from">Convert from</label>
            <select
              id="convert-from"
              name="convertFrom"
              value={convertFromId}
              onChange={(event) => setConvertFromId(event.target.value)}
              aria-invalid={convertErrors.fromUnitId ? true : undefined}
              aria-describedby={
                convertErrors.fromUnitId ? 'convert-from-error' : undefined
              }
            >
              <option value="">Select a unit…</option>
              {units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            {convertErrors.fromUnitId ? (
              <p role="alert" id="convert-from-error">
                {convertErrors.fromUnitId}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="convert-to">Convert to</label>
            <select
              id="convert-to"
              name="convertTo"
              value={convertToId}
              onChange={(event) => setConvertToId(event.target.value)}
              aria-invalid={convertErrors.toUnitId ? true : undefined}
              aria-describedby={
                convertErrors.toUnitId ? 'convert-to-error' : undefined
              }
            >
              <option value="">Select a unit…</option>
              {units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            {convertErrors.toUnitId ? (
              <p role="alert" id="convert-to-error">
                {convertErrors.toUnitId}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="convert-quantity">Quantity</label>
            <input
              id="convert-quantity"
              name="quantity"
              inputMode="decimal"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              aria-invalid={convertErrors.quantity ? true : undefined}
              aria-describedby={
                convertErrors.quantity ? 'convert-quantity-error' : undefined
              }
            />
            {convertErrors.quantity ? (
              <p role="alert" id="convert-quantity-error">
                {convertErrors.quantity}
              </p>
            ) : null}
          </div>

          <Button type="submit" disabled={converting}>
            {converting ? 'Converting…' : 'Convert'}
          </Button>

          {result ? <p role="status">{result}</p> : null}
        </form>
      </div>
    </section>
  );
}
