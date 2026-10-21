import type { ServiceRequest } from './farmSetupHttp';
import type {
  CropCycle,
  CropCycleInput,
  CropCycleServices,
  CropCycleUpdateInput,
} from './types';

function body(input: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(input) };
}

function put(input: unknown): RequestInit {
  return { method: 'PUT', body: JSON.stringify(input) };
}

/**
 * HTTP implementation of the crop cycle domain. Thin, typed wrappers over
 * the REST endpoints the backend task (#11) will provide; error status
 * codes and messages are surfaced by the shared response mapper in
 * `httpServices.ts`.
 */
export function createCropCycleHttp(
  request: ServiceRequest,
): CropCycleServices {
  return {
    cropCycles: {
      list: (fieldId?: string) =>
        request<CropCycle[]>(
          fieldId
            ? `/crop-cycles?field=${encodeURIComponent(fieldId)}`
            : '/crop-cycles',
          { method: 'GET' },
          true,
        ),
      create: (input: CropCycleInput) =>
        request<CropCycle>('/crop-cycles', body(input), true),
      update: (id: string, input: CropCycleUpdateInput) =>
        request<CropCycle>(
          `/crop-cycles/${encodeURIComponent(id)}`,
          put(input),
          true,
        ),
      close: (id: string) =>
        request<CropCycle>(
          `/crop-cycles/${encodeURIComponent(id)}/close`,
          { method: 'POST' },
          true,
        ),
    },
  };
}
