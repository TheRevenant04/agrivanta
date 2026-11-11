import type {
  ConversionInput,
  ConversionQuery,
  ConversionResult,
  Crop,
  CropInput,
  Farm,
  FarmInput,
  FarmSetupStatus,
  FarmSetupServices,
  Field,
  FieldInput,
  Unit,
  UnitConversion,
  UnitInput,
  Variety,
  VarietyInput,
} from '@/services/types';

/** The request helper `createHttpServices` exposes to domain factories. */
export type ServiceRequest = <T>(
  path: string,
  init: RequestInit,
  authenticated: boolean,
) => Promise<T>;

function body(input: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(input) };
}

function put(input: unknown): RequestInit {
  return { method: 'PUT', body: JSON.stringify(input) };
}

/**
 * HTTP implementation of the farm setup domains. Thin, typed wrappers over
 * the REST endpoints; error status codes and messages are surfaced by the
 * shared response mapper in `httpServices.ts`.
 */
export function createFarmSetupHttp(
  request: ServiceRequest,
): FarmSetupServices {
  return {
    setupStatus: {
      get: () =>
        request<FarmSetupStatus>('/farm-setup/status', { method: 'GET' }, true),
    },

    farm: {
      get: () => request<Farm>('/farm', { method: 'GET' }, true),
      update: (input: FarmInput) => request<Farm>('/farm', put(input), true),
    },

    fields: {
      list: () => request<Field[]>('/fields', { method: 'GET' }, true),
      create: (input: FieldInput) =>
        request<Field>('/fields', body(input), true),
      update: (id: string, input: FieldInput) =>
        request<Field>(`/fields/${encodeURIComponent(id)}`, put(input), true),
    },

    crops: {
      list: () => request<Crop[]>('/crops', { method: 'GET' }, true),
      create: (input: CropInput) => request<Crop>('/crops', body(input), true),
      update: (id: string, input: CropInput) =>
        request<Crop>(`/crops/${encodeURIComponent(id)}`, put(input), true),
    },

    varieties: {
      list: (cropId?: string) =>
        request<Variety[]>(
          cropId
            ? `/varieties?crop=${encodeURIComponent(cropId)}`
            : '/varieties',
          { method: 'GET' },
          true,
        ),
      create: (input: VarietyInput) =>
        request<Variety>('/varieties', body(input), true),
      update: (id: string, input: VarietyInput) =>
        request<Variety>(
          `/varieties/${encodeURIComponent(id)}`,
          put(input),
          true,
        ),
    },

    units: {
      list: () => request<Unit[]>('/units', { method: 'GET' }, true),
      create: (input: UnitInput) => request<Unit>('/units', body(input), true),
      update: (id: string, input: UnitInput) =>
        request<Unit>(`/units/${encodeURIComponent(id)}`, put(input), true),
    },

    conversions: {
      list: () =>
        request<UnitConversion[]>('/conversions', { method: 'GET' }, true),
      create: (input: ConversionInput) =>
        request<UnitConversion>('/conversions', body(input), true),
      convert: (query: ConversionQuery) =>
        request<ConversionResult>('/conversions/convert', body(query), true),
    },
  };
}
