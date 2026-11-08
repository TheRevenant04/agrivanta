import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { toErrorMessage } from '../lib/errors';
import { useAuth } from '../auth/authContext';
import { useServices } from '../services/servicesContext';
import type {
  Crop,
  FarmSetupStatus,
  FarmSetupStepId,
  Field,
  Variety,
} from '../services/types';

const STEPS: { id: FarmSetupStepId; label: string }[] = [
  { id: 'farm', label: 'Farm' },
  { id: 'fields', label: 'Fields' },
  { id: 'crops', label: 'Crops' },
  { id: 'initialCycle', label: 'Initial crop cycle' },
];

interface SetupDraft {
  farmName: string;
  reportingCurrency: string;
  fieldName: string;
  fieldArea: string;
  fieldNotes: string;
  cropName: string;
  varietyName: string;
  fieldId: string;
  cropId: string;
  varietyId: string;
  cycleStartDate: string;
  cycleType: 'annual' | 'perennial';
}

interface SetupProgress {
  currentStep: FarmSetupStepId;
  draft: SetupDraft;
}

const EMPTY_DRAFT: SetupDraft = {
  farmName: '',
  reportingCurrency: 'USD',
  fieldName: '',
  fieldArea: '',
  fieldNotes: '',
  cropName: '',
  varietyName: '',
  fieldId: '',
  cropId: '',
  varietyId: '',
  cycleStartDate: '',
  cycleType: 'annual',
};

function isStepId(value: unknown): value is FarmSetupStepId {
  return STEPS.some((step) => step.id === value);
}

function readProgress(key: string): SetupProgress | null {
  try {
    const stored = window.localStorage.getItem(key);
    if (!stored) return null;

    const parsed: unknown = JSON.parse(stored);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const record = parsed as Record<string, unknown>;
    if (!isStepId(record.currentStep)) return null;
    const draft =
      typeof record.draft === 'object' && record.draft !== null
        ? (record.draft as Record<string, unknown>)
        : {};

    return {
      currentStep: record.currentStep,
      draft: Object.fromEntries(
        Object.keys(EMPTY_DRAFT).map((field) => [
          field,
          typeof draft[field] === 'string'
            ? draft[field]
            : EMPTY_DRAFT[field as keyof SetupDraft],
        ]),
      ) as unknown as SetupDraft,
    };
  } catch {
    return null;
  }
}

function firstIncompleteStep(status: FarmSetupStatus): FarmSetupStepId | null {
  return STEPS.find((step) => !status.steps[step.id])?.id ?? null;
}

function defaultStep(
  status: FarmSetupStatus,
  savedStep: FarmSetupStepId | undefined,
): FarmSetupStepId {
  const firstIncomplete = firstIncompleteStep(status);
  if (!savedStep || !firstIncomplete) return firstIncomplete ?? 'initialCycle';
  const savedIndex = STEPS.findIndex((step) => step.id === savedStep);
  const nextIndex = STEPS.findIndex((step) => step.id === firstIncomplete);
  return savedIndex <= nextIndex ? savedStep : firstIncomplete;
}

function nextStepAfter(status: FarmSetupStatus): FarmSetupStepId | null {
  return firstIncompleteStep(status);
}

const STORAGE_PREFIX = 'agrivanta:guided-setup:';

export function GuidedSetupPage() {
  const services = useServices();
  const { user } = useAuth();
  const storageKey = `${STORAGE_PREFIX}${user?.id ?? 'unknown'}`;
  const [progress, setProgress] = useState<SetupProgress>(
    () =>
      readProgress(storageKey) ?? { currentStep: 'farm', draft: EMPTY_DRAFT },
  );
  const [status, setStatus] = useState<FarmSetupStatus | null>(null);
  const [fields, setFields] = useState<Field[]>([]);
  const [crops, setCrops] = useState<Crop[]>([]);
  const [varieties, setVarieties] = useState<Variety[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function saveProgress(next: SetupProgress) {
    setProgress(next);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      // The setup flow remains usable if browser storage is unavailable.
    }
  }

  function updateDraft(patch: Partial<SetupDraft>) {
    saveProgress({
      ...progress,
      draft: { ...progress.draft, ...patch },
    });
  }

  useEffect(() => {
    let active = true;
    Promise.all([
      services.setupStatus.get(),
      services.farm.get(),
      services.fields.list(),
      services.crops.list(),
      services.varieties.list(),
    ]).then(
      ([setupStatus, farmInfo, fieldItems, cropItems, varietyItems]) => {
        if (!active) return;
        const saved = readProgress(storageKey);
        const currentStep = defaultStep(setupStatus, saved?.currentStep);
        const cropWithVariety = varietyItems.find((variety) =>
          cropItems.some((crop) => crop.id === variety.cropId),
        );
        const savedCropId = cropItems.some(
          (crop) => crop.id === saved?.draft.cropId,
        )
          ? saved?.draft.cropId
          : undefined;
        const savedCropHasVariety = varietyItems.some(
          (variety) => variety.cropId === savedCropId,
        );
        const cropId =
          (savedCropId && (!setupStatus.steps.crops || savedCropHasVariety)
            ? savedCropId
            : undefined) ||
          (setupStatus.steps.crops
            ? cropWithVariety?.cropId
            : cropItems[0]?.id) ||
          '';
        const savedFieldId = fieldItems.some(
          (field) => field.id === saved?.draft.fieldId,
        )
          ? saved?.draft.fieldId
          : undefined;
        const fieldId = savedFieldId || fieldItems[0]?.id || '';
        const selectedField = fieldItems.find((field) => field.id === fieldId);
        const draft = {
          ...(saved?.draft ?? EMPTY_DRAFT),
          farmName: saved?.draft.farmName || farmInfo.name,
          reportingCurrency:
            saved?.draft.reportingCurrency || farmInfo.reportingCurrency,
          fieldId,
          fieldName:
            saved?.draft.fieldName ||
            (savedFieldId ? '' : (selectedField?.name ?? '')),
          fieldArea:
            saved?.draft.fieldArea ||
            (savedFieldId ? '' : String(selectedField?.area ?? '')),
          fieldNotes:
            saved?.draft.fieldNotes ||
            (savedFieldId ? '' : (selectedField?.notes ?? '')),
          cropId,
          varietyId:
            saved?.draft.varietyId ||
            varietyItems.find((variety) => variety.cropId === cropId)?.id ||
            '',
        };
        const nextProgress = { currentStep, draft };
        setStatus(setupStatus);
        setFields(fieldItems);
        setCrops(cropItems);
        setVarieties(varietyItems);
        setProgress(nextProgress);
        try {
          window.localStorage.setItem(storageKey, JSON.stringify(nextProgress));
        } catch {
          // Ignore unavailable browser storage.
        }
        setLoading(false);
      },
      (cause: unknown) => {
        if (!active) return;
        setError(toErrorMessage(cause));
        setLoading(false);
      },
    );

    return () => {
      active = false;
    };
  }, [services, storageKey]);

  function goBack() {
    const index = STEPS.findIndex((step) => step.id === progress.currentStep);
    if (index > 0) {
      saveProgress({
        ...progress,
        currentStep: STEPS[index - 1].id,
      });
      setError(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!status) return;
    setSubmitting(true);
    setError(null);

    try {
      const step = progress.currentStep;
      let updatedDraft = { ...progress.draft };
      let updatedFields = fields;
      let updatedCrops = crops;

      if (step === 'farm') {
        await services.farm.update({
          name: updatedDraft.farmName,
          reportingCurrency: updatedDraft.reportingCurrency,
        });
      } else if (step === 'fields') {
        const fieldInput = {
          name: updatedDraft.fieldName,
          area: updatedDraft.fieldArea,
          notes: updatedDraft.fieldNotes,
        };
        const field = updatedDraft.fieldId
          ? await services.fields.update(updatedDraft.fieldId, fieldInput)
          : await services.fields.create(fieldInput);
        updatedFields = updatedDraft.fieldId
          ? fields.map((item) => (item.id === field.id ? field : item))
          : [...fields, field];
        setFields(updatedFields);
        updatedDraft = { ...updatedDraft, fieldId: field.id };
      } else if (step === 'crops') {
        let cropId = updatedDraft.cropId;
        if (!cropId) {
          const createdCrop = await services.crops.create({
            name: updatedDraft.cropName,
          });
          cropId = createdCrop.id;
          updatedCrops = [...crops, createdCrop];
          setCrops(updatedCrops);
          updatedDraft = { ...updatedDraft, cropId };
          saveProgress({ ...progress, draft: updatedDraft });
        }
        if (!updatedDraft.varietyId) {
          const createdVariety = await services.varieties.create({
            cropId,
            name: updatedDraft.varietyName,
          });
          setVarieties([...varieties, createdVariety]);
          updatedDraft = { ...updatedDraft, varietyId: createdVariety.id };
        }
      } else {
        await services.cropCycles.create({
          fieldId: updatedDraft.fieldId || fields[0]?.id || '',
          cropId: updatedDraft.cropId || crops[0]?.id || '',
          varietyId: updatedDraft.varietyId,
          cycleType: updatedDraft.cycleType,
          startDate: updatedDraft.cycleStartDate,
        });
      }

      const updatedStatus: FarmSetupStatus = {
        ...status,
        steps: { ...status.steps, [step]: true },
      };
      const nextStatus =
        step === 'initialCycle'
          ? {
              ...updatedStatus,
              complete: true,
              nextStep: null,
            }
          : {
              ...updatedStatus,
              complete: false,
              nextStep: nextStepAfter(updatedStatus),
            };
      setStatus(nextStatus);
      const currentStep = nextStatus.nextStep ?? 'initialCycle';
      const nextProgress = {
        ...progress,
        currentStep,
        draft: updatedDraft,
      };
      saveProgress(nextProgress);

      try {
        const confirmedStatus = await services.setupStatus.get();
        setStatus(confirmedStatus);
        const confirmedStep = defaultStep(confirmedStatus, currentStep);
        saveProgress({ ...nextProgress, currentStep: confirmedStep });
      } catch {
        // The successful setup write still advances; status is refreshed on reload.
      }
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  const stepIndex = STEPS.findIndex((step) => step.id === progress.currentStep);
  const activeStep = STEPS[stepIndex] ?? STEPS[0];
  const isComplete = status?.complete ?? false;

  return (
    <section className="page-section" aria-labelledby="guided-setup-title">
      <div className="space-y-1">
        <h1 id="guided-setup-title">Guided farm setup</h1>
        <p>Set up your farm, fields, crops, and first crop cycle.</p>
      </div>

      <ol
        aria-label="Setup steps"
        className="flex flex-wrap gap-2 text-sm text-muted-foreground"
      >
        {STEPS.map((step) => (
          <li
            key={step.id}
            aria-current={step.id === progress.currentStep ? 'step' : undefined}
            className="rounded-full border px-3 py-1 aria-[current=step]:border-primary aria-[current=step]:bg-primary/10 aria-[current=step]:font-medium aria-[current=step]:text-primary"
          >
            {step.label}
            {status?.steps[step.id] ? ' — complete' : ''}
          </li>
        ))}
      </ol>

      {loading ? (
        <p role="status">Loading setup status…</p>
      ) : error && !status ? (
        <p role="alert">{error}</p>
      ) : isComplete ? (
        <div className="space-y-4 rounded-xl border bg-card p-6 shadow-sm">
          <h2>Farm setup complete</h2>
          <p>Your farm is ready to use.</p>
          <Button asChild>
            <Link to="/dashboard">Go to dashboard</Link>
          </Button>
        </div>
      ) : (
        <>
          <h2>
            Step {stepIndex + 1} of {STEPS.length}: {activeStep.label}
          </h2>
          {error && <p role="alert">{error}</p>}
          <form className="page-form" onSubmit={handleSubmit}>
            {progress.currentStep === 'farm' && (
              <>
                <label htmlFor="setup-farm-name">Farm name</label>
                <input
                  id="setup-farm-name"
                  required
                  maxLength={255}
                  value={progress.draft.farmName}
                  onChange={(event) =>
                    updateDraft({ farmName: event.target.value })
                  }
                />
                <label htmlFor="setup-currency">Reporting currency</label>
                <input
                  id="setup-currency"
                  required
                  maxLength={3}
                  value={progress.draft.reportingCurrency}
                  onChange={(event) =>
                    updateDraft({ reportingCurrency: event.target.value })
                  }
                />
              </>
            )}

            {progress.currentStep === 'fields' && (
              <>
                <label htmlFor="setup-field-name">Field name</label>
                <input
                  id="setup-field-name"
                  required
                  maxLength={255}
                  value={progress.draft.fieldName}
                  onChange={(event) =>
                    updateDraft({ fieldName: event.target.value })
                  }
                />
                <label htmlFor="setup-field-area">Area</label>
                <input
                  id="setup-field-area"
                  required
                  type="number"
                  min="0"
                  step="any"
                  value={progress.draft.fieldArea}
                  onChange={(event) =>
                    updateDraft({ fieldArea: event.target.value })
                  }
                />
                <label htmlFor="setup-field-notes">Notes (optional)</label>
                <textarea
                  id="setup-field-notes"
                  value={progress.draft.fieldNotes}
                  onChange={(event) =>
                    updateDraft({ fieldNotes: event.target.value })
                  }
                />
              </>
            )}

            {progress.currentStep === 'crops' && (
              <>
                {progress.draft.cropId ? (
                  <p>
                    Adding a variety to{' '}
                    {crops.find((crop) => crop.id === progress.draft.cropId)
                      ?.name ?? 'the selected crop'}
                    .
                  </p>
                ) : (
                  <>
                    <label htmlFor="setup-crop-name">Crop name</label>
                    <input
                      id="setup-crop-name"
                      required
                      maxLength={255}
                      value={progress.draft.cropName}
                      onChange={(event) =>
                        updateDraft({ cropName: event.target.value })
                      }
                    />
                  </>
                )}
                <label htmlFor="setup-variety-name">Variety name</label>
                <input
                  id="setup-variety-name"
                  required
                  maxLength={255}
                  value={progress.draft.varietyName}
                  onChange={(event) =>
                    updateDraft({ varietyName: event.target.value })
                  }
                />
              </>
            )}

            {progress.currentStep === 'initialCycle' && (
              <>
                <label htmlFor="setup-cycle-field">Field</label>
                <select
                  id="setup-cycle-field"
                  required
                  value={progress.draft.fieldId}
                  onChange={(event) =>
                    updateDraft({ fieldId: event.target.value })
                  }
                >
                  <option value="">Select a field</option>
                  {fields.map((field) => (
                    <option key={field.id} value={field.id}>
                      {field.name}
                    </option>
                  ))}
                </select>
                <label htmlFor="setup-cycle-crop">Crop</label>
                <select
                  id="setup-cycle-crop"
                  required
                  value={progress.draft.cropId}
                  onChange={(event) => {
                    const cropId = event.target.value;
                    updateDraft({
                      cropId,
                      varietyId:
                        varieties.find((variety) => variety.cropId === cropId)
                          ?.id ?? '',
                    });
                  }}
                >
                  <option value="">Select a crop</option>
                  {crops.map((crop) => (
                    <option key={crop.id} value={crop.id}>
                      {crop.name}
                    </option>
                  ))}
                </select>
                <label htmlFor="setup-cycle-variety">Variety</label>
                <select
                  id="setup-cycle-variety"
                  required
                  value={progress.draft.varietyId}
                  onChange={(event) =>
                    updateDraft({ varietyId: event.target.value })
                  }
                >
                  <option value="">Select a variety</option>
                  {varieties
                    .filter(
                      (variety) => variety.cropId === progress.draft.cropId,
                    )
                    .map((variety) => (
                      <option key={variety.id} value={variety.id}>
                        {variety.name}
                      </option>
                    ))}
                </select>
                <label htmlFor="setup-cycle-type">Cycle type</label>
                <select
                  id="setup-cycle-type"
                  value={progress.draft.cycleType}
                  onChange={(event) =>
                    updateDraft({
                      cycleType: event.target.value as 'annual' | 'perennial',
                    })
                  }
                >
                  <option value="annual">Annual</option>
                  <option value="perennial">Perennial</option>
                </select>
                <label htmlFor="setup-cycle-start-date">Start date</label>
                <input
                  id="setup-cycle-start-date"
                  type="date"
                  required
                  value={progress.draft.cycleStartDate}
                  onChange={(event) =>
                    updateDraft({ cycleStartDate: event.target.value })
                  }
                />
              </>
            )}

            <div className="flex flex-wrap gap-2">
              {stepIndex > 0 && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={goBack}
                  disabled={submitting}
                >
                  Back
                </Button>
              )}
              <Button type="submit" disabled={submitting}>
                {submitting
                  ? 'Saving…'
                  : progress.currentStep === 'initialCycle'
                    ? 'Complete setup'
                    : 'Continue'}
              </Button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}
