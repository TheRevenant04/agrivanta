/**
 * Activity planning domain types (issue #46): activity templates
 * (activity types), crop cycle references for the cycle picker, and the
 * activities themselves with their statuses and planned resource needs.
 *
 * Kept out of `types.ts` so the domain lives in files owned by this
 * feature; `types.ts` re-exports everything and folds
 * {@link ActivityPlanningServices} into `AgrivantaServices`.
 */

/** Lifecycle statuses an activity can hold, as the API reports them. */
export type ActivityStatus =
  'planned' | 'in_progress' | 'completed' | 'overdue';

/** Categories a template can belong to; custom types use `custom`. */
export type ActivityCategory =
  | 'land preparation'
  | 'planting'
  | 'fertilizing'
  | 'spraying'
  | 'harvesting'
  | 'custom';

/** A standard or custom template activities are created from. */
export interface ActivityType {
  id: string;
  name: string;
  category: ActivityCategory;
  /** True for the templates seeded on farm creation. */
  standard: boolean;
}

export interface ActivityTypeInput {
  name: string;
  /** Sent as typed so an unknown category reaches the backend's rule. */
  category: string;
}

/**
 * Minimal display reference for a crop cycle, used by the cycle picker on
 * the activities screen. The full crop cycle model belongs to the crop
 * cycle screens (issue #45).
 */
export interface ActivityCycleRef {
  id: string;
  label: string;
}

/** A planned input line on an activity, before the backend normalises it. */
export interface ActivityInputNeed {
  itemName: string;
  quantity: string | number;
}

/** A planned input line as stored (normalised quantity, stable id). */
export interface SavedInputNeed {
  id: string;
  itemName: string;
  quantity: number;
}

/** Planned resource needs captured on an activity. */
export interface ActivityResourceNeeds {
  inputs: SavedInputNeed[];
  labourHours: number;
  equipment: string;
}

/** Resource needs as submitted for editing; strings so rules can reject. */
export interface ResourceNeedsInput {
  inputs: ActivityInputNeed[];
  labourHours: string | number;
  equipment: string;
}

export interface Activity {
  id: string;
  cycleId: string;
  typeId: string;
  /** ISO calendar date (`YYYY-MM-DD`). */
  plannedDate: string;
  status: ActivityStatus;
  description?: string;
  resourceNeeds: ActivityResourceNeeds;
}

export interface ActivityInput {
  cycleId: string;
  typeId: string;
  /** Sent as typed so a blank/invalid date reaches the backend's rule. */
  plannedDate: string;
  description?: string;
}

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
