/**
 * Activity planning domain types (issue #46): activity templates
 * (activity types), crop cycle references for the cycle picker, and the
 * activities themselves with their statuses and planned resource needs.
 *
 * Kept out of `types.ts` so the domain lives in files owned by this
 * feature; `types.ts` re-exports everything and folds
 * {@link ActivityPlanningServices} into `AgrivantaServices`.
 */
import type {
  Activity as ApiActivity,
  ActivityCategory as ApiActivityCategory,
  ActivityInput as ApiActivityInput,
  ActivityInputNeed as ApiActivityInputNeed,
  ActivityResourceNeeds as ApiActivityResourceNeeds,
  ActivityStatus as ApiActivityStatus,
  ActivityType as ApiActivityType,
  ActivityTypeInput as ApiActivityTypeInput,
  CycleRef,
  ResourceNeedsInput as ApiResourceNeedsInput,
  SavedInputNeed as ApiSavedInputNeed,
} from './generated/types.gen';

/** Lifecycle statuses an activity can hold, as the API reports them. */
export type ActivityStatus = ApiActivityStatus;

/** Categories a template can belong to; custom types use `custom`. */
export type ActivityCategory = ApiActivityCategory | 'custom';

/** A standard or custom template activities are created from. */
export type ActivityType = Pick<
  ApiActivityType,
  'id' | 'name' | 'category' | 'standard'
>;

export type ActivityTypeInput = Pick<ApiActivityTypeInput, 'name' | 'category'>;

/**
 * Minimal display reference for a crop cycle, used by the cycle picker on
 * the activities screen. The full crop cycle model belongs to the crop
 * cycle screens (issue #45).
 */
export type ActivityCycleRef = CycleRef;

/** A planned input line on an activity, before the backend normalises it. */
export type ActivityInputNeed = ApiActivityInputNeed;

/** A planned input line as stored (normalised quantity, stable id). */
export type SavedInputNeed = ApiSavedInputNeed;

/** Planned resource needs captured on an activity. */
export type ActivityResourceNeeds = ApiActivityResourceNeeds;

/** Resource needs as submitted for editing; strings so rules can reject. */
export type ResourceNeedsInput = ApiResourceNeedsInput;

export type Activity = Pick<
  ApiActivity,
  'id' | 'cycleId' | 'typeId' | 'plannedDate' | 'status' | 'resourceNeeds'
> &
  Partial<Pick<ApiActivity, 'description'>>;

export type ActivityInput = ApiActivityInput;

export interface ActivityTypeService {
  list(): Promise<ActivityType[]>;
  create(input: ActivityTypeInput): Promise<ActivityType>;
}

export interface ActivityService {
  /** Crop cycles the farm can plan activities against, for the picker. */
  listCycles(): Promise<ActivityCycleRef[]>;
  /** When `cycleId` is given, only that cycle's activities are returned. */
  list(cycleId?: string): Promise<Activity[]>;
  create(input: ActivityInput): Promise<Activity>;
  update(id: string, input: ActivityInput): Promise<Activity>;
  /**
   * Moves an activity to a new status; raises the backend's rule when the
   * transition is not allowed (e.g. completed back to in progress).
   */
  updateStatus(id: string, status: string): Promise<Activity>;
  /** Replaces an activity's planned resource needs. */
  updateResourceNeeds(id: string, needs: ResourceNeedsInput): Promise<Activity>;
}

/** The activity planning domains exposed by the services layer. */
export interface ActivityPlanningServices {
  activities: ActivityService;
  activityTypes: ActivityTypeService;
}
