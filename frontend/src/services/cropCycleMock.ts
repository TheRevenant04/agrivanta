import {
  CYCLE_ERRORS,
  parseEndDate,
  parseOptionalAmount,
  parseStartDate,
} from './cropCycleRules';
import {
  ApiError,
  UnauthorizedError,
  type CropCycle,
  type CropCycleInput,
  type CropCycleServices,
  type CropCycleUpdateInput,
} from './types';

export interface CropCycleMockOptions {
  /** Crop cycles the mock starts with; defaults to none. */
  seed?: CropCycle[];
  /**
   * Called before every request, mirroring the backend's 401 rule. Defaults
   * to rejecting like an unauthenticated API call; `createMockServices`
   * wires this to the stored session.
   */
  requireAuth?: () => void;
}

/**
 * In-memory implementation of the crop cycle domain. It enforces the same
 * rules (messages, 400/404/409 status codes, offending field) as the HTTP
 * implementation, so callers cannot tell them apart. Overlapping cycles on
 * the same field are allowed by design; a closed cycle rejects edits.
 */
export function createCropCycleMock(
  options: CropCycleMockOptions = {},
): CropCycleServices {
  const requireAuth =
    options.requireAuth ??
    (() => {
      throw new UnauthorizedError();
    });

  const cycles: CropCycle[] = (options.seed ?? []).map((item) => ({
    ...item,
  }));
  let sequence = cycles.length;

  function nextId(): string {
    sequence += 1;
    return `cycle-${sequence}`;
  }

  function copy(cycle: CropCycle): CropCycle {
    return { ...cycle };
  }

  function findCycleIndex(id: string): number {
    const index = cycles.findIndex((item) => item.id === id);

    if (index === -1) {
      throw new ApiError(CYCLE_ERRORS.cycleNotFound, 404);
    }

    return index;
  }

  function requireReferenceId(
    value: string,
    message: string,
    field: 'fieldId' | 'cropId' | 'varietyId',
  ): string {
    const trimmed = value.trim();

    if (!trimmed) {
      throw new ApiError(message, 400, field);
    }

    return trimmed;
  }

  /** Validates a create payload down to the stored cycle shape. */
  function parseCreate(input: CropCycleInput): Omit<CropCycle, 'id' | 'status'> {
    const fieldId = requireReferenceId(
      input.fieldId,
      CYCLE_ERRORS.cycleFieldRequired,
      'fieldId',
    );
    const cropId = requireReferenceId(
      input.cropId,
      CYCLE_ERRORS.cycleCropRequired,
      'cropId',
    );
    const varietyId = requireReferenceId(
      input.varietyId,
      CYCLE_ERRORS.cycleVarietyRequired,
      'varietyId',
    );
    const startDate = parseStartDate(input.startDate);
    const endDate = parseEndDate(input.endDate ?? '', startDate);
    const expectedYield = parseOptionalAmount(
      input.expectedYield,
      'expectedYield',
    );
    const expectedPrice = parseOptionalAmount(
      input.expectedPrice,
      'expectedPrice',
    );

    return {
      fieldId,
      cropId,
      varietyId,
      startDate,
      ...(endDate ? { endDate } : {}),
      ...(expectedYield !== undefined ? { expectedYield } : {}),
      ...(expectedPrice !== undefined ? { expectedPrice } : {}),
    };
  }

  return {
    cropCycles: {
      async list(fieldId?: string) {
        requireAuth();
        return cycles
          .filter((item) => (fieldId ? item.fieldId === fieldId : true))
          .map(copy);
      },

      async create(input: CropCycleInput) {
        requireAuth();
        const created: CropCycle = {
          id: nextId(),
          status: 'open',
          ...parseCreate(input),
        };
        cycles.push(created);
        return copy(created);
      },

      async update(id: string, input: CropCycleUpdateInput) {
        requireAuth();
        const index = findCycleIndex(id);

        if (cycles[index].status === 'closed') {
          throw new ApiError(CYCLE_ERRORS.cycleClosed, 409);
        }

        const current = cycles[index];
        const updated: CropCycle = {
          ...current,
          expectedYield:
            input.expectedYield !== undefined
              ? parseOptionalAmount(input.expectedYield, 'expectedYield')
              : current.expectedYield,
          expectedPrice:
            input.expectedPrice !== undefined
              ? parseOptionalAmount(input.expectedPrice, 'expectedPrice')
              : current.expectedPrice,
        };
        cycles[index] = updated;
        return copy(updated);
      },

      async close(id: string) {
        requireAuth();
        const index = findCycleIndex(id);

        if (cycles[index].status === 'closed') {
          throw new ApiError(CYCLE_ERRORS.cycleAlreadyClosed, 409);
        }

        cycles[index] = { ...cycles[index], status: 'closed' };
        return copy(cycles[index]);
      },
    },
  };
}
