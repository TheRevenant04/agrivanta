import { useEffect, useRef, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/ui/button';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import {
  computeHarvestedTotal,
  formatAmount,
  type HarvestedTotal,
} from '../services/harvestSaleRules';
import { useServices } from '../services/servicesContext';
import type { Harvest, HarvestCycleRef, Unit } from '../services/types';

/**
 * Harvest entry screen: pick a crop cycle, record quantity/unit/date against
 * it, and see that cycle's harvests and harvested total grow. The cycle
 * picker scopes both the form and the list below it.
 */
export function HarvestsPage() {
  const services = useServices();
  const quantityRef = useRef<HTMLInputElement>(null);

  const [cycles, setCycles] = useState<HarvestCycleRef[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [harvests, setHarvests] = useState<Harvest[]>([]);
  const [selectedCycleId, setSelectedCycleId] = useState('');
  const [total, setTotal] = useState<HarvestedTotal | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [totalError, setTotalError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [quantity, setQuantity] = useState('');
  const [unitId, setUnitId] = useState('');
  const [date, setDate] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([services.harvests.listCycles(), services.units.list()]).then(
      ([cycleItems, unitItems]) => {
        if (cancelled) {
          return;
        }

        setCycles(cycleItems);
        setUnits(unitItems);
        setSelectedCycleId(cycleItems[0]?.id ?? '');
        setLoaded(true);
      },
      (error: unknown) => {
        if (cancelled) {
          return;
        }

        setLoadError(toErrorMessage(error));
        setLoaded(true);
      },
    );

    return () => {
      cancelled = true;
    };
  }, [services]);

  useEffect(() => {
    if (!selectedCycleId) {
      return;
    }

    let cancelled = false;

    void (async () => {
      try {
        const items = await services.harvests.list(selectedCycleId);

        if (cancelled) {
          return;
        }

        setHarvests(items);

        const summary = await computeHarvestedTotal(
          items,
          services.conversions.convert,
        );

        if (!cancelled) {
          setTotal(summary);
          setTotalError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setTotalError(toErrorMessage(cause));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [services, selectedCycleId, reloadKey]);

  const selectedCycle = cycles.find((cycle) => cycle.id === selectedCycleId);

  function unitName(id: string | null): string {
    if (!id) {
      return '';
    }

    return units.find((unit) => unit.id === id)?.name ?? 'unknown unit';
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setSubmitting(true);

    try {
      await services.harvests.create({
        cycleId: selectedCycleId,
        quantity,
        unitId,
        date,
      });

      setQuantity('');
      setDate('');
      setConfirmation('Harvest saved.');
      setReloadKey((key) => key + 1);
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

  if (loaded && cycles.length === 0) {
    return (
      <section className="page-section">
        <div className="space-y-1">
          <h1>Harvests</h1>
          <p>Record harvested quantities against open crop cycles.</p>
        </div>
        {loadError ? <p role="alert">{loadError}</p> : null}
        <EmptyState message="No crop cycles yet.">
          <p>Create a crop cycle before recording harvests.</p>
        </EmptyState>
      </section>
    );
  }

  return (
    <section className="page-section">
      <div className="space-y-1">
        <h1>Harvests</h1>
        <p>Record harvested quantities against open crop cycles.</p>
      </div>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      <form
        className="page-form"
        aria-label="Record harvest"
        onSubmit={handleSubmit}
        noValidate
      >
        {formError ? <p role="alert">{formError}</p> : null}

        <div>
          <label htmlFor="harvest-cycle">Crop cycle</label>
          <select
            id="harvest-cycle"
            name="cycleId"
            value={selectedCycleId}
            onChange={(event) => {
              setSelectedCycleId(event.target.value);
              setHarvests([]);
              setTotal(null);
              setTotalError(null);
              setErrors({});
              setFormError(null);
              setConfirmation(null);
            }}
            aria-invalid={errors.cycleId ? true : undefined}
            aria-describedby={
              errors.cycleId ? 'harvest-cycle-error' : undefined
            }
          >
            <option value="">Select a crop cycle…</option>
            {cycles.map((cycle) => (
              <option key={cycle.id} value={cycle.id}>
                {cycle.label}
              </option>
            ))}
          </select>
          {errors.cycleId ? (
            <p role="alert" id="harvest-cycle-error">
              {errors.cycleId}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="harvest-quantity">Quantity</label>
          <input
            id="harvest-quantity"
            name="quantity"
            inputMode="decimal"
            ref={quantityRef}
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            aria-invalid={errors.quantity ? true : undefined}
            aria-describedby={
              errors.quantity ? 'harvest-quantity-error' : undefined
            }
          />
          {errors.quantity ? (
            <p role="alert" id="harvest-quantity-error">
              {errors.quantity}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="harvest-unit">Unit</label>
          <select
            id="harvest-unit"
            name="unitId"
            value={unitId}
            onChange={(event) => setUnitId(event.target.value)}
            aria-invalid={errors.unitId ? true : undefined}
            aria-describedby={errors.unitId ? 'harvest-unit-error' : undefined}
          >
            <option value="">Select a unit…</option>
            {units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.name}
              </option>
            ))}
          </select>
          {errors.unitId ? (
            <p role="alert" id="harvest-unit-error">
              {errors.unitId}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="harvest-date">Date</label>
          <input
            id="harvest-date"
            name="date"
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            aria-invalid={errors.date ? true : undefined}
            aria-describedby={errors.date ? 'harvest-date-error' : undefined}
          />
          {errors.date ? (
            <p role="alert" id="harvest-date-error">
              {errors.date}
            </p>
          ) : null}
        </div>

        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : 'Save harvest'}
        </Button>
      </form>

      {selectedCycle ? (
        <div className="space-y-4">
          <h2>Harvests for {selectedCycle.label}</h2>

          {totalError ? <p role="alert">{totalError}</p> : null}
          {total ? (
            <p>
              Harvested total: {formatAmount(total.total)}
              {total.unitId ? ` ${unitName(total.unitId)}` : ''}
            </p>
          ) : null}

          {harvests.length === 0 ? (
            <EmptyState message="No harvests for this cycle yet.">
              <Button
                type="button"
                variant="outline"
                onClick={() => quantityRef.current?.focus()}
              >
                Record harvest
              </Button>
            </EmptyState>
          ) : (
            <ul className="record-list">
              {harvests.map((harvest) => (
                <li key={harvest.id}>
                  <span className="font-medium">
                    {formatAmount(harvest.quantity)} {unitName(harvest.unitId)}
                  </span>
                  <span>{harvest.date}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p>Select a crop cycle to see its harvests.</p>
      )}
    </section>
  );
}
