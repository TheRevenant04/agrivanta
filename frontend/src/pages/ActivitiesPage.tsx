import { useEffect, useState, type FormEvent } from 'react';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/ui/button';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import {
  INVENTORY_ITEM_OPTIONS,
  statusLabel,
} from '../services/activityPlanningRules';
import { useServices } from '../services/servicesContext';
import type {
  Activity,
  ActivityCycleRef,
  ActivityType,
} from '../services/types';

interface NeedRow {
  itemName: string;
  quantity: string;
}

/**
 * List, create, and edit screen for planned farm activities, filtered by
 * crop cycle, with inline status transitions and resource-needs editing.
 */
export function ActivitiesPage() {
  const services = useServices();
  const [cycles, setCycles] = useState<ActivityCycleRef[]>([]);
  const [types, setTypes] = useState<ActivityType[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [selectedCycleId, setSelectedCycleId] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formCycleId, setFormCycleId] = useState('');
  const [typeId, setTypeId] = useState('');
  const [plannedDate, setPlannedDate] = useState('');
  const [description, setDescription] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [needsActivityId, setNeedsActivityId] = useState<string | null>(null);
  const [needRows, setNeedRows] = useState<NeedRow[]>([]);
  const [needsLabourHours, setNeedsLabourHours] = useState('');
  const [needsEquipment, setNeedsEquipment] = useState('');
  const [needsErrors, setNeedsErrors] = useState<Record<string, string>>({});
  const [needsFormError, setNeedsFormError] = useState<string | null>(null);
  const [needsSubmitting, setNeedsSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [cycleRefs, activityTypes, all] = await Promise.all([
          services.activities.listCycles(),
          services.activityTypes.list(),
          services.activities.list(),
        ]);

        if (!cancelled) {
          setCycles(cycleRefs);
          setTypes(activityTypes);
          setActivities(all);
          setLoaded(true);
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(toErrorMessage(error));
          setLoaded(true);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [services]);

  async function refresh(filter: string) {
    setActivities(await services.activities.list(filter || undefined));
  }

  function handleCycleChange(value: string) {
    setSelectedCycleId(value);
    setFormOpen(false);
    setNeedsActivityId(null);
    setStatusError(null);
    void refresh(value);
  }

  function typeNameOf(activity: Activity): string {
    return (
      types.find((item) => item.id === activity.typeId)?.name ?? activity.typeId
    );
  }

  function resetForm() {
    setTypeId('');
    setPlannedDate('');
    setDescription('');
    setErrors({});
    setFormError(null);
    setEditingId(null);
    setFormCycleId('');
    setFormOpen(false);
  }

  function openCreate() {
    resetForm();
    setConfirmation(null);
    setStatusError(null);
    setFormCycleId(selectedCycleId || cycles[0]?.id || '');
    setTypeId(types[0]?.id ?? '');
    setFormOpen(true);
  }

  function openEdit(activity: Activity) {
    setErrors({});
    setFormError(null);
    setConfirmation(null);
    setStatusError(null);
    setFormCycleId(activity.cycleId);
    setTypeId(activity.typeId);
    setPlannedDate(activity.plannedDate);
    setDescription(activity.description ?? '');
    setEditingId(activity.id);
    setFormOpen(true);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setFormError(null);
    setSubmitting(true);

    const input = {
      cycleId: formCycleId,
      typeId,
      plannedDate,
      description,
    };

    try {
      if (editingId) {
        await services.activities.update(editingId, input);
      } else {
        await services.activities.create(input);
      }

      await refresh(selectedCycleId);
      resetForm();
      setConfirmation('Activity saved.');
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

  function resetNeeds() {
    setNeedsActivityId(null);
    setNeedRows([]);
    setNeedsLabourHours('');
    setNeedsEquipment('');
    setNeedsErrors({});
    setNeedsFormError(null);
  }

  function openNeeds(activity: Activity) {
    resetForm();
    setConfirmation(null);
    setStatusError(null);
    setNeedsActivityId(activity.id);
    setNeedRows(
      activity.resourceNeeds.inputs.map((item) => ({
        itemName: item.itemName,
        quantity: String(item.quantity),
      })),
    );
    setNeedsLabourHours(String(activity.resourceNeeds.labourHours));
    setNeedsEquipment(activity.resourceNeeds.equipment);
    setNeedsErrors({});
    setNeedsFormError(null);
  }

  async function handleNeedsSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!needsActivityId) {
      return;
    }

    setNeedsErrors({});
    setNeedsFormError(null);
    setNeedsSubmitting(true);

    try {
      const updated = await services.activities.updateResourceNeeds(
        needsActivityId,
        {
          inputs: needRows.map((row) => ({
            itemName: row.itemName,
            quantity: row.quantity,
          })),
          labourHours: needsLabourHours,
          equipment: needsEquipment,
        },
      );

      setActivities((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      resetNeeds();
      setConfirmation('Resource needs saved.');
    } catch (cause) {
      const { field, message } = apiFieldError(cause);

      if (field) {
        setNeedsErrors({ [field]: message });
      } else {
        setNeedsFormError(message);
      }
    } finally {
      setNeedsSubmitting(false);
    }
  }

  async function moveStatus(activity: Activity, next: string) {
    setStatusError(null);

    try {
      const updated = await services.activities.updateStatus(activity.id, next);
      setActivities((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (cause) {
      setStatusError(toErrorMessage(cause));
    }
  }

  const listVisible = !formOpen && needsActivityId === null;

  return (
    <section className="page-section">
      <div className="space-y-1">
        <h1>Activities</h1>
        <p>Plan work, track status, and capture resource needs by cycle.</p>
      </div>

      {loadError ? <p role="alert">{loadError}</p> : null}
      {confirmation ? <p role="status">{confirmation}</p> : null}
      {statusError ? <p role="alert">{statusError}</p> : null}

      <div className="max-w-sm">
        <label htmlFor="activity-cycle-filter">Crop cycle</label>
        <select
          id="activity-cycle-filter"
          value={selectedCycleId}
          onChange={(event) => handleCycleChange(event.target.value)}
        >
          <option value="">All cycles</option>
          {cycles.map((cycle) => (
            <option key={cycle.id} value={cycle.id}>
              {cycle.label}
            </option>
          ))}
        </select>
      </div>

      {loaded && activities.length === 0 && listVisible ? (
        <EmptyState
          message={
            selectedCycleId
              ? 'No activities for this cycle.'
              : 'No activities yet.'
          }
        >
          <Button type="button" onClick={openCreate}>
            Create activity
          </Button>
        </EmptyState>
      ) : null}

      {activities.length > 0 && listVisible ? (
        <div className="space-y-4">
          <ul className="record-list">
            {activities.map((activity) => (
              <li key={activity.id}>
                <span className="font-medium">{typeNameOf(activity)}</span>
                <span>{activity.plannedDate}</span>
                <span data-status={activity.status}>
                  {statusLabel(activity.status)}
                </span>
                {activity.resourceNeeds.inputs.length > 0 ? (
                  <ul className="flex flex-wrap gap-1.5">
                    {activity.resourceNeeds.inputs.map((item) => (
                      <li
                        key={item.id}
                        className="rounded-md border bg-muted/50 px-2 py-0.5 text-xs text-foreground"
                      >
                        {item.quantity} × {item.itemName}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {activity.resourceNeeds.labourHours > 0 ? (
                  <span>
                    Labour: {activity.resourceNeeds.labourHours} hours
                  </span>
                ) : null}
                {activity.resourceNeeds.equipment ? (
                  <span>Equipment: {activity.resourceNeeds.equipment}</span>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  {activity.status === 'planned' ||
                  activity.status === 'overdue' ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void moveStatus(activity, 'in_progress')}
                    >
                      Start {typeNameOf(activity)}
                    </Button>
                  ) : null}
                  {activity.status === 'in_progress' ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void moveStatus(activity, 'completed')}
                    >
                      Complete {typeNameOf(activity)}
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openEdit(activity)}
                  >
                    Edit {typeNameOf(activity)}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openNeeds(activity)}
                  >
                    Edit needs {typeNameOf(activity)}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <Button type="button" onClick={openCreate}>
            Create activity
          </Button>
        </div>
      ) : null}

      {formOpen ? (
        <form
          className="page-form"
          aria-label={editingId ? 'Edit activity' : 'Add activity'}
          onSubmit={(event) => void handleSubmit(event)}
          noValidate
        >
          {formError ? <p role="alert">{formError}</p> : null}

          <div>
            <label htmlFor="activity-cycle">Crop cycle</label>
            <select
              id="activity-cycle"
              name="cycleId"
              value={formCycleId}
              onChange={(event) => setFormCycleId(event.target.value)}
              aria-invalid={errors.cycleId ? true : undefined}
              aria-describedby={
                errors.cycleId ? 'activity-cycle-error' : undefined
              }
            >
              <option value="">Select a cycle</option>
              {cycles.map((cycle) => (
                <option key={cycle.id} value={cycle.id}>
                  {cycle.label}
                </option>
              ))}
            </select>
            {errors.cycleId ? (
              <p role="alert" id="activity-cycle-error">
                {errors.cycleId}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="activity-type">Type</label>
            <select
              id="activity-type"
              name="typeId"
              value={typeId}
              onChange={(event) => setTypeId(event.target.value)}
              aria-invalid={errors.typeId ? true : undefined}
              aria-describedby={
                errors.typeId ? 'activity-type-error' : undefined
              }
            >
              <option value="">Select a type</option>
              {types.map((activityType) => (
                <option key={activityType.id} value={activityType.id}>
                  {activityType.name}
                </option>
              ))}
            </select>
            {errors.typeId ? (
              <p role="alert" id="activity-type-error">
                {errors.typeId}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="activity-planned-date">Planned date</label>
            <input
              id="activity-planned-date"
              name="plannedDate"
              type="date"
              value={plannedDate}
              onChange={(event) => setPlannedDate(event.target.value)}
              aria-invalid={errors.plannedDate ? true : undefined}
              aria-describedby={
                errors.plannedDate ? 'activity-planned-date-error' : undefined
              }
            />
            {errors.plannedDate ? (
              <p role="alert" id="activity-planned-date-error">
                {errors.plannedDate}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="activity-description">Description</label>
            <textarea
              id="activity-description"
              name="description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save activity'}
            </Button>
            <Button type="button" variant="outline" onClick={resetForm}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}

      {needsActivityId ? (
        <form
          className="page-form"
          aria-label="Edit resource needs"
          onSubmit={(event) => void handleNeedsSubmit(event)}
          noValidate
        >
          {needsFormError ? <p role="alert">{needsFormError}</p> : null}

          {needRows.map((row, index) => (
            <div key={index}>
              <label htmlFor={`need-item-${index}`}>Item</label>
              <select
                id={`need-item-${index}`}
                value={
                  INVENTORY_ITEM_OPTIONS.includes(row.itemName)
                    ? row.itemName
                    : ''
                }
                onChange={(event) =>
                  setNeedRows((current) =>
                    current.map((item, i) =>
                      i === index
                        ? { ...item, itemName: event.target.value }
                        : item,
                    ),
                  )
                }
              >
                <option value="">Select an item</option>
                {INVENTORY_ITEM_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
                {!INVENTORY_ITEM_OPTIONS.includes(row.itemName) &&
                row.itemName ? (
                  <option value={row.itemName}>{row.itemName}</option>
                ) : null}
              </select>

              <label htmlFor={`need-quantity-${index}`}>Quantity</label>
              <input
                id={`need-quantity-${index}`}
                inputMode="decimal"
                value={row.quantity}
                onChange={(event) =>
                  setNeedRows((current) =>
                    current.map((item, i) =>
                      i === index
                        ? { ...item, quantity: event.target.value }
                        : item,
                    ),
                  )
                }
              />

              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  setNeedRows((current) =>
                    current.filter((_, i) => i !== index),
                  )
                }
              >
                Remove row {index + 1}
              </Button>
            </div>
          ))}

          {needsErrors.inputs ? (
            <p role="alert" id="needs-inputs-error">
              {needsErrors.inputs}
            </p>
          ) : null}

          <Button
            type="button"
            variant="outline"
            onClick={() =>
              setNeedRows((current) => [
                ...current,
                { itemName: '', quantity: '' },
              ])
            }
          >
            Add input row
          </Button>

          <div>
            <label htmlFor="need-labour-hours">Labour hours</label>
            <input
              id="need-labour-hours"
              inputMode="decimal"
              value={needsLabourHours}
              onChange={(event) => setNeedsLabourHours(event.target.value)}
              aria-invalid={needsErrors.labourHours ? true : undefined}
              aria-describedby={
                needsErrors.labourHours ? 'needs-labour-hours-error' : undefined
              }
            />
            {needsErrors.labourHours ? (
              <p role="alert" id="needs-labour-hours-error">
                {needsErrors.labourHours}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="need-equipment">Equipment</label>
            <input
              id="need-equipment"
              value={needsEquipment}
              onChange={(event) => setNeedsEquipment(event.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={needsSubmitting}>
              {needsSubmitting ? 'Saving…' : 'Save resource needs'}
            </Button>
            <Button type="button" variant="outline" onClick={resetNeeds}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
