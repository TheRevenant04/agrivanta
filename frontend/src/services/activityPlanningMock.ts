import {
  ACTIVITY_ERRORS,
  STANDARD_ACTIVITY_TEMPLATES,
  canTransition,
  isActivityCategory,
  isActivityStatus,
  parseLabourHours,
  parseNeedQuantity,
  parsePlannedDate,
} from './activityPlanningRules';
import type {
  Activity,
  ActivityCycleRef,
  ActivityInput,
  ActivityPlanningServices,
  ActivityResourceNeeds,
  ActivityType,
  ActivityTypeInput,
  ResourceNeedsInput,
  SavedInputNeed,
} from './activityPlanningTypes';
import { ApiError, UnauthorizedError } from '@/services/types';

/**
 * Seed shape for the activity planning domains. Omitted collections fall
 * back to sensible defaults: the five standard templates are always
 * available, two demo crop cycles give the cycle picker something to
 * choose before the crop cycle screens (#45) provide real data, and no
 * activities exist so every filtered list renders its empty state.
 */
export interface ActivityPlanningSeed {
  activityTypes?: ActivityType[];
  cycles?: ActivityCycleRef[];
  activities?: Activity[];
}

export interface ActivityPlanningMockOptions {
  seed?: ActivityPlanningSeed;
  /**
   * Called before every request, mirroring the backend's 401 rule. Defaults
   * to rejecting like an unauthenticated API call; `createMockServices`
   * wires this to the stored session.
   */
  requireAuth?: () => void;
}

/** The crop cycles the mock farm plans against by default. */
export const DEFAULT_PLANNING_CYCLES: readonly ActivityCycleRef[] = [
  { id: 'cycle-1', label: 'North 40 — Wheat 2026' },
  { id: 'cycle-2', label: 'South 12 — Maize 2026' },
];

function copy<T extends { id: string }>(item: T): T {
  return { ...item };
}

function copyActivity(activity: Activity): Activity {
  return {
    ...activity,
    resourceNeeds: {
      ...activity.resourceNeeds,
      inputs: activity.resourceNeeds.inputs.map((item) => ({ ...item })),
    },
  };
}

function standardTemplates(): ActivityType[] {
  return STANDARD_ACTIVITY_TEMPLATES.map((template, index) => ({
    id: `activity-type-${index + 1}`,
    name: template.name,
    category: template.category,
    standard: true,
  }));
}

/**
 * In-memory implementation of the activity planning domains. It enforces
 * the same rules (messages, 400/404/409 status codes, offending field) as
 * the HTTP implementation, so callers cannot tell them apart.
 */
export function createActivityPlanningMock(
  options: ActivityPlanningMockOptions = {},
): ActivityPlanningServices {
  const requireAuth =
    options.requireAuth ??
    (() => {
      throw new UnauthorizedError();
    });
  const seed = options.seed ?? {};

  const activityTypes: ActivityType[] = seed.activityTypes
    ? seed.activityTypes.map((item) => ({ ...item }))
    : standardTemplates();

  const cycles: ActivityCycleRef[] = (
    seed.cycles ?? DEFAULT_PLANNING_CYCLES
  ).map((item) => ({ ...item }));

  const activities: Activity[] = (seed.activities ?? []).map(copyActivity);

  const sequence = {
    activityType: activityTypes.length,
    activity: activities.length,
    input: 0,
  };

  function nextId(kind: keyof typeof sequence): string {
    sequence[kind] += 1;
    return `${kind}-${sequence[kind]}`;
  }

  function findActivityType(id: string): ActivityType {
    const activityType = activityTypes.find((item) => item.id === id);

    if (!activityType) {
      throw new ApiError(ACTIVITY_ERRORS.activityTypeUnknown, 404, 'typeId');
    }

    return activityType;
  }

  function requireTypeId(id: string): ActivityType {
    if (!id.trim()) {
      throw new ApiError(ACTIVITY_ERRORS.activityTypeMissing, 400, 'typeId');
    }

    return findActivityType(id);
  }

  function requireCycleId(id: string): string {
    if (!id.trim()) {
      throw new ApiError(ACTIVITY_ERRORS.cycleMissing, 400, 'cycleId');
    }

    return id;
  }

  function requireTemplateName(value: string): string {
    const trimmed = value.trim();

    if (!trimmed) {
      throw new ApiError(ACTIVITY_ERRORS.activityTypeNameRequired, 400, 'name');
    }

    return trimmed;
  }

  function requireTemplateCategory(value: string): ActivityType['category'] {
    const trimmed = value.trim();

    if (!trimmed) {
      throw new ApiError(
        ACTIVITY_ERRORS.activityTypeCategoryRequired,
        400,
        'category',
      );
    }

    if (!isActivityCategory(trimmed)) {
      throw new ApiError(
        ACTIVITY_ERRORS.activityTypeCategoryInvalid,
        400,
        'category',
      );
    }

    return trimmed;
  }

  function normaliseResourceNeeds(
    input: ResourceNeedsInput,
  ): ActivityResourceNeeds {
    const labourHours = parseLabourHours(input.labourHours);
    const equipment = input.equipment.trim();
    const inputs: SavedInputNeed[] = input.inputs.map((row) => {
      if (!row.itemName.trim()) {
        throw new ApiError(ACTIVITY_ERRORS.itemNameRequired, 400, 'inputs');
      }

      return {
        id: nextId('input'),
        itemName: row.itemName.trim(),
        quantity: parseNeedQuantity(row.quantity),
      };
    });

    return { inputs, labourHours, equipment };
  }

  return {
    activityTypes: {
      async list() {
        requireAuth();
        return activityTypes.map(copy);
      },

      async create(input: ActivityTypeInput) {
        requireAuth();
        const name = requireTemplateName(input.name);
        const category = requireTemplateCategory(input.category);

        if (
          activityTypes.some(
            (item) => item.name.toLowerCase() === name.toLowerCase(),
          )
        ) {
          throw new ApiError(
            ACTIVITY_ERRORS.activityTypeDuplicate(name),
            409,
            'name',
          );
        }

        const created: ActivityType = {
          id: nextId('activityType'),
          name,
          category,
          standard: false,
        };
        activityTypes.push(created);
        return copy(created);
      },
    },

    activities: {
      async listCycles() {
        requireAuth();
        const merged = cycles.map(copy);

        for (const activity of activities) {
          if (!merged.some((item) => item.id === activity.cycleId)) {
            merged.push({ id: activity.cycleId, label: activity.cycleId });
          }
        }

        return merged;
      },

      async list(cycleId?: string) {
        requireAuth();
        return activities
          .filter((item) => (cycleId ? item.cycleId === cycleId : true))
          .map(copyActivity);
      },

      async create(input: ActivityInput) {
        requireAuth();
        requireTypeId(input.typeId);
        requireCycleId(input.cycleId);
        const plannedDate = parsePlannedDate(input.plannedDate);

        const created: Activity = {
          id: nextId('activity'),
          cycleId: input.cycleId,
          typeId: input.typeId,
          plannedDate,
          status: 'planned',
          ...(input.description?.trim()
            ? { description: input.description.trim() }
            : {}),
          resourceNeeds: { inputs: [], labourHours: 0, equipment: '' },
        };
        activities.push(created);
        return copyActivity(created);
      },

      async update(id: string, input: ActivityInput) {
        requireAuth();
        const index = activities.findIndex((item) => item.id === id);

        if (index === -1) {
          throw new ApiError(ACTIVITY_ERRORS.activityNotFound, 404);
        }

        requireTypeId(input.typeId);
        requireCycleId(input.cycleId);
        const plannedDate = parsePlannedDate(input.plannedDate);

        activities[index] = {
          ...activities[index],
          cycleId: input.cycleId,
          typeId: input.typeId,
          plannedDate,
          ...(input.description?.trim()
            ? { description: input.description.trim() }
            : { description: undefined }),
        };
        return copyActivity(activities[index]);
      },

      async updateStatus(id: string, status: string) {
        requireAuth();
        const index = activities.findIndex((item) => item.id === id);

        if (index === -1) {
          throw new ApiError(ACTIVITY_ERRORS.activityNotFound, 404);
        }

        const trimmed = status.trim();

        if (!isActivityStatus(trimmed)) {
          throw new ApiError(ACTIVITY_ERRORS.statusInvalid, 400, 'status');
        }

        const current = activities[index];

        if (!canTransition(current.status, trimmed)) {
          throw new ApiError(
            ACTIVITY_ERRORS.statusTransitionInvalid(current.status, trimmed),
            409,
            'status',
          );
        }

        const updated: Activity = { ...current, status: trimmed };
        activities[index] = updated;
        return copyActivity(updated);
      },

      async updateResourceNeeds(id: string, needs: ResourceNeedsInput) {
        requireAuth();
        const index = activities.findIndex((item) => item.id === id);

        if (index === -1) {
          throw new ApiError(ACTIVITY_ERRORS.activityNotFound, 404);
        }

        const updated: Activity = {
          ...activities[index],
          resourceNeeds: normaliseResourceNeeds(needs),
        };
        activities[index] = updated;
        return copyActivity(updated);
      },
    },
  };
}
