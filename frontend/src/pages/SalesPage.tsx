import { useEffect, useRef, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/ui/button';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { formatAmount } from '../services/harvestSaleRules';
import { useServices } from '../services/servicesContext';
import type {
  Harvest,
  HarvestCycleRef,
  Sale,
  SaleCustomer,
  Unit,
} from '../services/types';

/**
 * Sale entry screen: pick a crop cycle, link the sale to one of that cycle's
 * harvests, and record customer, quantity, unit price, and date. The cycle
 * picker scopes both the form and the sale list below it, and the backend's
 * sold-exceeds-harvested error lands inline next to the quantity field.
 */
export function SalesPage() {
  const services = useServices();
  const quantityRef = useRef<HTMLInputElement>(null);

  const [cycles, setCycles] = useState<HarvestCycleRef[]>([]);
  const [customers, setCustomers] = useState<SaleCustomer[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [harvests, setHarvests] = useState<Harvest[]>([]);
  const [sales, setSales] = useState<Sale[]>([]);
  const [selectedCycleId, setSelectedCycleId] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [customerId, setCustomerId] = useState('');
  const [harvestId, setHarvestId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [unitPrice, setUnitPrice] = useState('');
  const [date, setDate] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      services.harvests.listCycles(),
      services.sales.listCustomers(),
      services.units.list(),
    ]).then(
      ([cycleItems, customerItems, unitItems]) => {
        if (cancelled) {
          return;
        }

        setCycles(cycleItems);
        setCustomers(customerItems);
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
    let cancelled = false;

    services.sales.list().then(
      (items) => {
        if (!cancelled) {
          setSales(items);
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
  }, [services, reloadKey]);

  useEffect(() => {
    if (!selectedCycleId) {
      return;
    }

    let cancelled = false;

    services.harvests.list(selectedCycleId).then(
      (items) => {
        if (!cancelled) {
          setHarvests(items);
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
  }, [services, selectedCycleId]);

  const selectedCycle = cycles.find((cycle) => cycle.id === selectedCycleId);
  const cycleHarvestIds = new Set(harvests.map((harvest) => harvest.id));
  const cycleSales = sales.filter((sale) =>
    cycleHarvestIds.has(sale.harvestId),
  );

  function unitName(id: string): string {
    return units.find((unit) => unit.id === id)?.name ?? 'unknown unit';
  }

  function customerName(id: string): string {
    return customers.find((customer) => customer.id === id)?.name ?? 'Unknown';
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setSubmitting(true);

    try {
      await services.sales.create({
        customerId,
        harvestId,
        quantity,
        unitPrice,
        date,
      });

      setQuantity('');
      setUnitPrice('');
      setConfirmation('Sale saved.');
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
          <h1>Sales</h1>
          <p>Record sales against harvested crop quantities.</p>
        </div>
        {loadError ? <p role="alert">{loadError}</p> : null}
        <EmptyState message="No crop cycles yet.">
          <p>Create a crop cycle before recording sales.</p>
        </EmptyState>
      </section>
    );
  }

  return (
    <section className="page-section">
      <div className="space-y-1">
        <h1>Sales</h1>
        <p>Record sales against harvested crop quantities.</p>
      </div>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      <form
        className="page-form"
        aria-label="Record sale"
        onSubmit={handleSubmit}
        noValidate
      >
        {formError ? <p role="alert">{formError}</p> : null}

        <div>
          <label htmlFor="sale-cycle">Crop cycle</label>
          <select
            id="sale-cycle"
            name="cycleId"
            value={selectedCycleId}
            onChange={(event) => {
              setSelectedCycleId(event.target.value);
              setHarvests([]);
              setHarvestId('');
              setErrors({});
              setFormError(null);
              setConfirmation(null);
            }}
            aria-invalid={errors.cycleId ? true : undefined}
            aria-describedby={errors.cycleId ? 'sale-cycle-error' : undefined}
          >
            <option value="">Select a crop cycle…</option>
            {cycles.map((cycle) => (
              <option key={cycle.id} value={cycle.id}>
                {cycle.label}
              </option>
            ))}
          </select>
          {errors.cycleId ? (
            <p role="alert" id="sale-cycle-error">
              {errors.cycleId}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="sale-customer">Customer</label>
          <select
            id="sale-customer"
            name="customerId"
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
            aria-invalid={errors.customerId ? true : undefined}
            aria-describedby={
              errors.customerId ? 'sale-customer-error' : undefined
            }
          >
            <option value="">Select a customer…</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name}
              </option>
            ))}
          </select>
          {errors.customerId ? (
            <p role="alert" id="sale-customer-error">
              {errors.customerId}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="sale-harvest">Harvest</label>
          <select
            id="sale-harvest"
            name="harvestId"
            value={harvestId}
            onChange={(event) => setHarvestId(event.target.value)}
            aria-invalid={errors.harvestId ? true : undefined}
            aria-describedby={
              errors.harvestId ? 'sale-harvest-error' : undefined
            }
          >
            <option value="">Select a harvest…</option>
            {harvests.map((harvest) => (
              <option key={harvest.id} value={harvest.id}>
                {formatAmount(harvest.quantity)} {unitName(harvest.unitId)} —{' '}
                {harvest.date}
              </option>
            ))}
          </select>
          {errors.harvestId ? (
            <p role="alert" id="sale-harvest-error">
              {errors.harvestId}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="sale-quantity">Quantity</label>
          <input
            id="sale-quantity"
            name="quantity"
            inputMode="decimal"
            ref={quantityRef}
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            aria-invalid={errors.quantity ? true : undefined}
            aria-describedby={
              errors.quantity ? 'sale-quantity-error' : undefined
            }
          />
          {errors.quantity ? (
            <p role="alert" id="sale-quantity-error">
              {errors.quantity}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="sale-unit-price">Unit price</label>
          <input
            id="sale-unit-price"
            name="unitPrice"
            inputMode="decimal"
            value={unitPrice}
            onChange={(event) => setUnitPrice(event.target.value)}
            aria-invalid={errors.unitPrice ? true : undefined}
            aria-describedby={
              errors.unitPrice ? 'sale-unit-price-error' : undefined
            }
          />
          {errors.unitPrice ? (
            <p role="alert" id="sale-unit-price-error">
              {errors.unitPrice}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="sale-date">Date</label>
          <input
            id="sale-date"
            name="date"
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            aria-invalid={errors.date ? true : undefined}
            aria-describedby={errors.date ? 'sale-date-error' : undefined}
          />
          {errors.date ? (
            <p role="alert" id="sale-date-error">
              {errors.date}
            </p>
          ) : null}
        </div>

        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : 'Save sale'}
        </Button>
      </form>

      {selectedCycle ? (
        <div className="space-y-4">
          <h2>Sales for {selectedCycle.label}</h2>

          {cycleSales.length === 0 ? (
            <EmptyState message="No sales for this cycle yet.">
              <Button
                type="button"
                variant="outline"
                onClick={() => quantityRef.current?.focus()}
              >
                Record sale
              </Button>
            </EmptyState>
          ) : (
            <ul className="record-list">
              {cycleSales.map((sale) => (
                <li key={sale.id}>
                  <span className="font-medium">
                    {customerName(sale.customerId)}
                  </span>
                  <span>
                    {formatAmount(sale.quantity)}{' '}
                    {unitName(
                      harvests.find((harvest) => harvest.id === sale.harvestId)
                        ?.unitId ?? '',
                    )}
                  </span>
                  <span>{formatAmount(sale.revenue)}</span>
                  <span>{sale.date}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p>Select a crop cycle to see its sales.</p>
      )}
    </section>
  );
}
