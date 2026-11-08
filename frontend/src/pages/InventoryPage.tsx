import { useEffect, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/ui/button';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { isLowStock } from '../services/inventoryRules';
import { useServices } from '../services/servicesContext';
import type { InventoryItem, StockMovementType, Unit } from '../services/types';

/** Which of the two forms is open; the list stays visible underneath. */
type FormView = 'none' | 'item' | 'movement';

/** Badge rendered for an item at or below its reorder level. */
export function LowStockBadge() {
  return (
    <span className="inline-flex items-center rounded-full border border-destructive/20 bg-destructive/10 px-2.5 py-0.5 text-xs font-medium text-destructive">
      Low stock
    </span>
  );
}

/** Inventory list with item creation and stock movement entry. */
export function InventoryPage() {
  const services = useServices();
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  // Item form (create or edit).
  const [form, setForm] = useState<FormView>('none');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [unitId, setUnitId] = useState('');
  const [reorderLevel, setReorderLevel] = useState('');
  const [itemErrors, setItemErrors] = useState<Record<string, string>>({});
  const [itemFormError, setItemFormError] = useState<string | null>(null);
  const [submittingItem, setSubmittingItem] = useState(false);

  // Movement form.
  const [movementItemId, setMovementItemId] = useState('');
  const [movementType, setMovementType] =
    useState<StockMovementType>('purchase');
  const [movementQuantity, setMovementQuantity] = useState('');
  const [movementErrors, setMovementErrors] = useState<Record<string, string>>(
    {},
  );
  const [movementFormError, setMovementFormError] = useState<string | null>(
    null,
  );
  const [submittingMovement, setSubmittingMovement] = useState(false);

  useEffect(() => {
    let cancelled = false;

    Promise.all([services.items.list(), services.units.list()]).then(
      ([itemRows, unitRows]) => {
        if (!cancelled) {
          setItems(itemRows);
          setUnits(unitRows);
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

  async function refreshItems() {
    setItems(await services.items.list());
  }

  function unitName(id: string): string {
    return units.find((unit) => unit.id === id)?.name ?? 'Unknown unit';
  }

  function closeForms() {
    setForm('none');
    setEditingId(null);
    setItemErrors({});
    setItemFormError(null);
    setMovementErrors({});
    setMovementFormError(null);
  }

  function openCreate() {
    closeForms();
    setName('');
    setUnitId('');
    setReorderLevel('');
    setConfirmation(null);
    setForm('item');
  }

  function openEdit(item: InventoryItem) {
    closeForms();
    setName(item.name);
    setUnitId(item.unitId);
    setReorderLevel(String(item.reorderLevel));
    setConfirmation(null);
    setEditingId(item.id);
    setForm('item');
  }

  function openMovement(item: InventoryItem) {
    closeForms();
    setMovementItemId(item.id);
    setMovementType('purchase');
    setMovementQuantity('');
    setConfirmation(null);
    setForm('movement');
  }

  async function handleItemSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setItemErrors({});
    setItemFormError(null);
    setSubmittingItem(true);
    const input = { name, unitId, reorderLevel };

    try {
      if (editingId) {
        await services.items.update(editingId, input);
      } else {
        await services.items.create(input);
      }

      await refreshItems();
      closeForms();
      setConfirmation('Inventory item saved.');
    } catch (cause) {
      const { field, message } = apiFieldError(cause);

      if (field) {
        setItemErrors({ [field]: message });
      } else {
        setItemFormError(message);
      }
    } finally {
      setSubmittingItem(false);
    }
  }

  async function handleMovementSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMovementErrors({});
    setMovementFormError(null);
    setSubmittingMovement(true);

    try {
      await services.movements.create({
        itemId: movementItemId,
        type: movementType,
        quantity: movementQuantity,
      });

      await refreshItems();
      closeForms();
      setConfirmation('Movement saved.');
    } catch (cause) {
      const { field, message } = apiFieldError(cause);

      if (field) {
        setMovementErrors({ [field]: message });
      } else {
        setMovementFormError(message);
      }
    } finally {
      setSubmittingMovement(false);
    }
  }

  return (
    <section className="page-section">
      <div className="space-y-1">
        <h1>Inventory</h1>
        <p>Track stock levels, reorder points, and movements.</p>
      </div>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}

      {loaded && items.length === 0 && form === 'none' ? (
        <EmptyState message="No inventory items yet.">
          <Button type="button" onClick={openCreate}>
            Add inventory item
          </Button>
        </EmptyState>
      ) : null}

      {items.length > 0 ? (
        <div className="space-y-4">
          <ul className="record-list">
            {items.map((item) => (
              <li key={item.id}>
                <span className="font-medium">{item.name}</span>
                <span>{unitName(item.unitId)}</span>
                <span>Reorder level {item.reorderLevel}</span>
                <span>Current quantity {item.currentQuantity}</span>
                {isLowStock(item) ? <LowStockBadge /> : null}
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openMovement(item)}
                  >
                    Record movement for {item.name}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openEdit(item)}
                  >
                    Edit {item.name}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <Button type="button" onClick={openCreate}>
            Add inventory item
          </Button>
        </div>
      ) : null}

      {form === 'item' ? (
        <form
          className="page-form"
          aria-label={editingId ? 'Edit inventory item' : 'Add inventory item'}
          onSubmit={handleItemSubmit}
          noValidate
        >
          {itemFormError ? <p role="alert">{itemFormError}</p> : null}

          <div>
            <label htmlFor="inventory-item-name">Name</label>
            <input
              id="inventory-item-name"
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-invalid={itemErrors.name ? true : undefined}
              aria-describedby={
                itemErrors.name ? 'inventory-item-name-error' : undefined
              }
            />
            {itemErrors.name ? (
              <p role="alert" id="inventory-item-name-error">
                {itemErrors.name}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="inventory-item-unit">Unit</label>
            <select
              id="inventory-item-unit"
              name="unitId"
              value={unitId}
              onChange={(event) => setUnitId(event.target.value)}
              aria-invalid={itemErrors.unitId ? true : undefined}
              aria-describedby={
                itemErrors.unitId ? 'inventory-item-unit-error' : undefined
              }
            >
              <option value="">Select a unit</option>
              {units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            {itemErrors.unitId ? (
              <p role="alert" id="inventory-item-unit-error">
                {itemErrors.unitId}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="inventory-item-reorder">Reorder level</label>
            <input
              id="inventory-item-reorder"
              name="reorderLevel"
              inputMode="decimal"
              value={reorderLevel}
              onChange={(event) => setReorderLevel(event.target.value)}
              aria-invalid={itemErrors.reorderLevel ? true : undefined}
              aria-describedby={
                itemErrors.reorderLevel
                  ? 'inventory-item-reorder-error'
                  : undefined
              }
            />
            {itemErrors.reorderLevel ? (
              <p role="alert" id="inventory-item-reorder-error">
                {itemErrors.reorderLevel}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={submittingItem}>
              {submittingItem ? 'Saving…' : 'Save inventory item'}
            </Button>
            <Button type="button" variant="outline" onClick={closeForms}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}

      {form === 'movement' ? (
        <form
          className="page-form"
          aria-label="Record movement"
          onSubmit={handleMovementSubmit}
          noValidate
        >
          {movementFormError ? <p role="alert">{movementFormError}</p> : null}

          <div>
            <label htmlFor="movement-item">Item</label>
            <select
              id="movement-item"
              name="itemId"
              value={movementItemId}
              onChange={(event) => setMovementItemId(event.target.value)}
              aria-invalid={movementErrors.itemId ? true : undefined}
              aria-describedby={
                movementErrors.itemId ? 'movement-item-error' : undefined
              }
            >
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            {movementErrors.itemId ? (
              <p role="alert" id="movement-item-error">
                {movementErrors.itemId}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="movement-type">Type</label>
            <select
              id="movement-type"
              name="type"
              value={movementType}
              onChange={(event) =>
                setMovementType(event.target.value as StockMovementType)
              }
            >
              <option value="purchase">Purchase</option>
              <option value="usage">Usage</option>
            </select>
          </div>

          <div>
            <label htmlFor="movement-quantity">Quantity</label>
            <input
              id="movement-quantity"
              name="quantity"
              inputMode="decimal"
              value={movementQuantity}
              onChange={(event) => setMovementQuantity(event.target.value)}
              aria-invalid={movementErrors.quantity ? true : undefined}
              aria-describedby={
                movementErrors.quantity ? 'movement-quantity-error' : undefined
              }
            />
            {movementErrors.quantity ? (
              <p role="alert" id="movement-quantity-error">
                {movementErrors.quantity}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={submittingMovement}>
              {submittingMovement ? 'Saving…' : 'Save movement'}
            </Button>
            <Button type="button" variant="outline" onClick={closeForms}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
