import {
  isBaseMeasureCategory,
  isValidReportingCurrency,
  parseArea,
  parseFactor,
  parseQuantity,
  SETUP_ERRORS,
} from './farmSetupRules';
import {
  ApiError,
  UnauthorizedError,
  type ConversionInput,
  type ConversionQuery,
  type ConversionResult,
  type Crop,
  type CropInput,
  type Farm,
  type FarmInput,
  type FarmSetupStatus,
  type FarmSetupServices,
  type Field,
  type FieldInput,
  type Unit,
  type UnitConversion,
  type UnitInput,
  type Variety,
  type VarietyInput,
} from '@/services/types';

/**
 * Seed shape for the farm setup domains. Omitted collections start empty
 * (so every list renders its empty state) and `farm` defaults to a single
 * configured farm, matching the one-farm-per-business rule.
 */
export interface FarmSetupSeed {
  farm?: Farm | null;
  fields?: Field[];
  crops?: Crop[];
  varieties?: Variety[];
  units?: Unit[];
  conversions?: UnitConversion[];
}

export interface FarmSetupMockOptions {
  seed?: FarmSetupSeed;
  /**
   * Called before every request, mirroring the backend's 401 rule. Defaults
   * to rejecting like an unauthenticated API call; `createMockServices`
   * wires this to the stored session.
   */
  requireAuth?: () => void;
  hasInitialCycle?: () => Promise<boolean>;
}

/** The farm every mock business starts with. */
export const DEFAULT_FARM: Farm = {
  id: 'farm-1',
  name: 'Willow Creek Farm',
  reportingCurrency: 'USD',
};

function copy<T extends { id: string }>(item: T): T {
  return { ...item };
}

/**
 * In-memory implementation of the farm setup domains. It enforces the same
 * rules (messages, 400/404/409 status codes, offending field) as the HTTP
 * implementation, so callers cannot tell them apart.
 */
export function createFarmSetupMock(
  options: FarmSetupMockOptions = {},
): FarmSetupServices {
  const requireAuth =
    options.requireAuth ??
    (() => {
      throw new UnauthorizedError();
    });
  const seed = options.seed ?? {};

  let farm: Farm | null =
    seed.farm === undefined
      ? { ...DEFAULT_FARM }
      : seed.farm && { ...seed.farm };
  let farmConfigured = Boolean(
    farm?.name.trim() && farm.reportingCurrency.length === 3,
  );

  const fields: Field[] = (seed.fields ?? []).map((item) => ({ ...item }));
  const crops: Crop[] = (seed.crops ?? []).map((item) => ({ ...item }));
  const varieties: Variety[] = (seed.varieties ?? []).map((item) => ({
    ...item,
  }));
  const units: Unit[] = (seed.units ?? []).map((item) => ({ ...item }));
  const conversions: UnitConversion[] = (seed.conversions ?? []).map(
    (item) => ({
      ...item,
    }),
  );

  const sequence = {
    field: fields.length,
    crop: crops.length,
    variety: varieties.length,
    unit: units.length,
    conversion: conversions.length,
  };

  function nextId(kind: keyof typeof sequence): string {
    sequence[kind] += 1;
    return `${kind}-${sequence[kind]}`;
  }

  function requireFarm(): Farm {
    if (!farm) {
      throw new ApiError(SETUP_ERRORS.farmNotFound, 404);
    }
    return farm;
  }

  function requireName(value: string): string {
    const trimmed = value.trim();

    if (!trimmed) {
      throw new ApiError(SETUP_ERRORS.cropNameRequired, 400, 'name');
    }

    return trimmed;
  }

  function requireFieldName(value: string): string {
    const trimmed = value.trim();

    if (!trimmed) {
      throw new ApiError(SETUP_ERRORS.fieldNameRequired, 400, 'name');
    }

    return trimmed;
  }

  function requireUnitName(value: string): string {
    const trimmed = value.trim();

    if (!trimmed) {
      throw new ApiError(SETUP_ERRORS.unitNameRequired, 400, 'name');
    }

    return trimmed;
  }

  function requireVarietyName(value: string): string {
    const trimmed = value.trim();

    if (!trimmed) {
      throw new ApiError(SETUP_ERRORS.varietyNameRequired, 400, 'name');
    }

    return trimmed;
  }

  function findCrop(id: string): Crop {
    const crop = crops.find((item) => item.id === id);

    if (!crop) {
      throw new ApiError(SETUP_ERRORS.varietyCropNotFound, 404, 'cropId');
    }

    return crop;
  }

  function findUnit(id: string | null, field: 'fromUnitId' | 'toUnitId'): Unit {
    if (!id) {
      throw new ApiError(SETUP_ERRORS.unitMissing, 400, field);
    }

    const unit = units.find((item) => item.id === id);

    if (!unit) {
      throw new ApiError(SETUP_ERRORS.unitUnknown, 404, field);
    }

    return unit;
  }

  return {
    setupStatus: {
      async get(): Promise<FarmSetupStatus> {
        requireAuth();
        const steps = {
          farm: farmConfigured,
          fields: fields.length > 0,
          crops: crops.some((crop) =>
            varieties.some((variety) => variety.cropId === crop.id),
          ),
          initialCycle: (await options.hasInitialCycle?.()) ?? false,
        };
        const nextStep =
          (Object.entries(steps).find(([, complete]) => !complete)?.[0] as
            keyof typeof steps | undefined) ?? null;
        return {
          steps,
          complete: nextStep === null,
          nextStep,
        };
      },
    },

    farm: {
      async get() {
        requireAuth();
        return copy(requireFarm());
      },

      async update(input: FarmInput) {
        requireAuth();
        const current = requireFarm();
        const name = input.name.trim();

        if (!name) {
          throw new ApiError(SETUP_ERRORS.farmNameRequired, 400, 'name');
        }

        if (!isValidReportingCurrency(input.reportingCurrency)) {
          throw new ApiError(
            SETUP_ERRORS.currencyInvalid,
            400,
            'reportingCurrency',
          );
        }

        farm = {
          ...current,
          name,
          reportingCurrency: input.reportingCurrency.trim().toUpperCase(),
        };
        farmConfigured = true;
        return copy(farm);
      },
    },

    fields: {
      async list() {
        requireAuth();
        return fields.map(copy);
      },

      async create(input: FieldInput) {
        requireAuth();
        const created: Field = {
          id: nextId('field'),
          farmId: requireFarm().id,
          name: requireFieldName(input.name),
          area: parseArea(input.area),
          ...(input.notes?.trim() ? { notes: input.notes.trim() } : {}),
        };
        fields.push(created);
        return copy(created);
      },

      async update(id: string, input: FieldInput) {
        requireAuth();
        const index = fields.findIndex((item) => item.id === id);

        if (index === -1) {
          throw new ApiError(SETUP_ERRORS.fieldNotFound, 404);
        }

        const updated: Field = {
          ...fields[index],
          name: requireFieldName(input.name),
          area: parseArea(input.area),
          ...(input.notes?.trim() ? { notes: input.notes.trim() } : {}),
        };
        fields[index] = updated;
        return copy(updated);
      },
    },

    crops: {
      async list() {
        requireAuth();
        return crops.map(copy);
      },

      async create(input: CropInput) {
        requireAuth();
        const name = requireName(input.name);

        if (
          crops.some((item) => item.name.toLowerCase() === name.toLowerCase())
        ) {
          throw new ApiError(SETUP_ERRORS.cropNameDuplicate(name), 409, 'name');
        }

        const created: Crop = { id: nextId('crop'), name };
        crops.push(created);
        return copy(created);
      },

      async update(id: string, input: CropInput) {
        requireAuth();
        const index = crops.findIndex((item) => item.id === id);

        if (index === -1) {
          throw new ApiError(SETUP_ERRORS.cropNotFound, 404);
        }

        const name = requireName(input.name);
        const duplicate = crops.some(
          (item, i) =>
            i !== index && item.name.toLowerCase() === name.toLowerCase(),
        );

        if (duplicate) {
          throw new ApiError(SETUP_ERRORS.cropNameDuplicate(name), 409, 'name');
        }

        crops[index] = { ...crops[index], name };
        return copy(crops[index]);
      },
    },

    varieties: {
      async list(cropId?: string) {
        requireAuth();
        return varieties
          .filter((item) => (cropId ? item.cropId === cropId : true))
          .map(copy);
      },

      async create(input: VarietyInput) {
        requireAuth();
        const name = requireVarietyName(input.name);

        if (!input.cropId) {
          throw new ApiError(SETUP_ERRORS.varietyCropMissing, 400, 'cropId');
        }

        const crop = findCrop(input.cropId);
        const created: Variety = {
          id: nextId('variety'),
          cropId: crop.id,
          name,
        };
        varieties.push(created);
        return copy(created);
      },

      async update(id: string, input: VarietyInput) {
        requireAuth();
        const index = varieties.findIndex((item) => item.id === id);

        if (index === -1) {
          throw new ApiError(SETUP_ERRORS.varietyNotFound, 404);
        }

        const name = requireVarietyName(input.name);

        if (!input.cropId) {
          throw new ApiError(SETUP_ERRORS.varietyCropMissing, 400, 'cropId');
        }

        const crop = findCrop(input.cropId);
        varieties[index] = { ...varieties[index], cropId: crop.id, name };
        return copy(varieties[index]);
      },
    },

    units: {
      async list() {
        requireAuth();
        return units.map(copy);
      },

      async create(input: UnitInput) {
        requireAuth();
        const name = requireUnitName(input.name);
        const baseMeasure = input.baseMeasure.trim();

        if (!baseMeasure) {
          throw new ApiError(
            SETUP_ERRORS.unitCategoryRequired,
            400,
            'baseMeasure',
          );
        }

        if (!isBaseMeasureCategory(baseMeasure)) {
          throw new ApiError(
            SETUP_ERRORS.unitCategoryInvalid,
            400,
            'baseMeasure',
          );
        }

        if (
          units.some((item) => item.name.toLowerCase() === name.toLowerCase())
        ) {
          throw new ApiError(SETUP_ERRORS.unitNameDuplicate(name), 409, 'name');
        }

        const created: Unit = {
          id: nextId('unit'),
          name,
          baseMeasure,
        };
        units.push(created);
        return copy(created);
      },

      async update(id: string, input: UnitInput) {
        requireAuth();
        const index = units.findIndex((item) => item.id === id);

        if (index === -1) {
          throw new ApiError(SETUP_ERRORS.unitNotFound, 404);
        }

        const name = requireUnitName(input.name);
        const baseMeasure = input.baseMeasure.trim();

        if (!baseMeasure) {
          throw new ApiError(
            SETUP_ERRORS.unitCategoryRequired,
            400,
            'baseMeasure',
          );
        }

        if (!isBaseMeasureCategory(baseMeasure)) {
          throw new ApiError(
            SETUP_ERRORS.unitCategoryInvalid,
            400,
            'baseMeasure',
          );
        }

        const duplicate = units.some(
          (item, i) =>
            i !== index && item.name.toLowerCase() === name.toLowerCase(),
        );

        if (duplicate) {
          throw new ApiError(SETUP_ERRORS.unitNameDuplicate(name), 409, 'name');
        }

        units[index] = { ...units[index], name, baseMeasure };
        return copy(units[index]);
      },
    },

    conversions: {
      async list() {
        requireAuth();
        return conversions.map(copy);
      },

      async create(input: ConversionInput) {
        requireAuth();
        const from = findUnit(input.fromUnitId, 'fromUnitId');
        const to = findUnit(input.toUnitId, 'toUnitId');

        if (from.id === to.id) {
          throw new ApiError(SETUP_ERRORS.conversionSelf, 400, 'toUnitId');
        }

        const factor = parseFactor(input.factor);
        const duplicate = conversions.some(
          (item) => item.fromUnitId === from.id && item.toUnitId === to.id,
        );

        if (duplicate) {
          throw new ApiError(
            SETUP_ERRORS.conversionDuplicate(from.name, to.name),
            409,
          );
        }

        const created: UnitConversion = {
          id: nextId('conversion'),
          fromUnitId: from.id,
          toUnitId: to.id,
          factor,
        };
        conversions.push(created);
        return copy(created);
      },

      async convert(query: ConversionQuery): Promise<ConversionResult> {
        requireAuth();
        const from = findUnit(query.fromUnitId, 'fromUnitId');
        const to = findUnit(query.toUnitId, 'toUnitId');
        const quantity = parseQuantity(query.quantity);

        if (from.id === to.id) {
          return {
            fromUnitId: from.id,
            toUnitId: to.id,
            quantity,
            factor: 1,
            converted: quantity,
          };
        }

        if (from.baseMeasure !== to.baseMeasure) {
          throw new ApiError(
            SETUP_ERRORS.categoryMismatch(
              from.name,
              from.baseMeasure,
              to.name,
              to.baseMeasure,
            ),
            400,
          );
        }

        const forward = conversions.find(
          (item) => item.fromUnitId === from.id && item.toUnitId === to.id,
        );

        if (forward) {
          return {
            fromUnitId: from.id,
            toUnitId: to.id,
            quantity,
            factor: forward.factor,
            converted: quantity * forward.factor,
          };
        }

        const reverse = conversions.find(
          (item) => item.fromUnitId === to.id && item.toUnitId === from.id,
        );

        if (reverse) {
          return {
            fromUnitId: from.id,
            toUnitId: to.id,
            quantity,
            factor: 1 / reverse.factor,
            converted: quantity / reverse.factor,
          };
        }

        throw new ApiError(
          SETUP_ERRORS.noConversionRule(from.name, to.name),
          404,
        );
      },
    },
  };
}
