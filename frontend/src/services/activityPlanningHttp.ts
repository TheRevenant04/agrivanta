import type { ServiceRequest } from './farmSetupHttp';
import type {
  Activity,
  ActivityCycleRef,
  ActivityInput,
  ActivityPlanningServices,
  ActivityType,
  ActivityTypeInput,
  ResourceNeedsInput,
} from './activityPlanningTypes';

function body(input: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(input) };
}

function put(input: unknown): RequestInit {
  return { method: 'PUT', body: JSON.stringify(input) };
}

/**
 * HTTP implementation of the activity planning domains. Thin, typed
 * wrappers over the REST endpoints; error status codes and messages are
 * surfaced by the shared response mapper in `httpServices.ts`.
 */
export function createActivityPlanningHttp(
  request: ServiceRequest,
): ActivityPlanningServices {
  return {
    activityTypes: {
      list: () =>
        request<ActivityType[]>('/activity-types', { method: 'GET' }, true),
      create: (input: ActivityTypeInput) =>
        request<ActivityType>('/activity-types', body(input), true),
    },

    activities: {
      listCycles: () =>
        request<ActivityCycleRef[]>(
          '/activities/cycles',
          { method: 'GET' },
          true,
        ),
      list: (cycleId?: string) =>
        request<Activity[]>(
          cycleId
            ? `/activities?cycle=${encodeURIComponent(cycleId)}`
            : '/activities',
          { method: 'GET' },
          true,
        ),
      create: (input: ActivityInput) =>
        request<Activity>('/activities', body(input), true),
      update: (id: string, input: ActivityInput) =>
        request<Activity>(
          `/activities/${encodeURIComponent(id)}`,
          put(input),
          true,
        ),
      updateStatus: (id: string, status: string) =>
        request<Activity>(
          `/activities/${encodeURIComponent(id)}/status`,
          put({ status }),
          true,
        ),
      updateResourceNeeds: (id: string, needs: ResourceNeedsInput) =>
        request<Activity>(
          `/activities/${encodeURIComponent(id)}/resource-needs`,
          put(needs),
          true,
        ),
    },
  };
}
