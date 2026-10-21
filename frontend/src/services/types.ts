/**
 * The single typed contract that all backend access flows through.
 *
 * Both the mock and the HTTP implementation are typed against
 * {@link AgrivantaServices}, so the rest of the app depends only on these
 * interfaces and never on a concrete transport.
 */

export interface User {
  id: string;
  email: string;
  role: string;
}

export interface AuthSession {
  token: string;
  user: User;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterInput {
  name?: string;
  email: string;
  password: string;
}

export interface AuthService {
  login(credentials: LoginCredentials): Promise<AuthSession>;
  register(input: RegisterInput): Promise<AuthSession>;
  logout(): Promise<void>;
  me(): Promise<User>;
}

// ---------------------------------------------------------------------------
// Farm setup domains (farm, fields, crops, varieties, units, conversions)
// ---------------------------------------------------------------------------

/** Allowed base-measure categories for a unit of measure. */
export type BaseMeasureCategory = 'mass' | 'volume' | 'count';

export interface Farm {
  id: string;
  name: string;
  /** Three-letter reporting currency code, e.g. `USD`. */
  reportingCurrency: string;
}

export interface FarmInput {
  name: string;
  reportingCurrency: string;
}

export interface Field {
  id: string;
  farmId: string;
  name: string;
  area: number;
  notes?: string;
}

export interface FieldInput {
  name: string;
  /** Sent as typed so a non-numeric value reaches the backend's rule. */
  area: string | number;
  notes?: string;
}

export interface Crop {
  id: string;
  name: string;
}

export interface CropInput {
  name: string;
}

export interface Variety {
  id: string;
  cropId: string;
  name: string;
}

export interface VarietyInput {
  cropId: string;
  name: string;
}

export interface Unit {
  id: string;
  name: string;
  baseMeasure: BaseMeasureCategory;
}

export interface UnitInput {
  name: string;
  /** Sent as typed so a missing/invalid category reaches the backend rule. */
  baseMeasure: string;
}

export interface UnitConversion {
  id: string;
  fromUnitId: string;
  toUnitId: string;
  factor: number;
}

export interface ConversionInput {
  fromUnitId: string;
  toUnitId: string;
  factor: string | number;
}

export interface ConversionQuery {
  fromUnitId: string;
  toUnitId: string;
  quantity: string | number;
}

export interface ConversionResult {
  fromUnitId: string;
  toUnitId: string;
  quantity: number;
  factor: number;
  converted: number;
}

export interface FarmService {
  get(): Promise<Farm>;
  update(input: FarmInput): Promise<Farm>;
}

export interface FieldService {
  list(): Promise<Field[]>;
  create(input: FieldInput): Promise<Field>;
  update(id: string, input: FieldInput): Promise<Field>;
}

export interface CropService {
  list(): Promise<Crop[]>;
  create(input: CropInput): Promise<Crop>;
  update(id: string, input: CropInput): Promise<Crop>;
}

export interface VarietyService {
  /** When `cropId` is given, only varieties of that crop are returned. */
  list(cropId?: string): Promise<Variety[]>;
  create(input: VarietyInput): Promise<Variety>;
  update(id: string, input: VarietyInput): Promise<Variety>;
}

export interface UnitService {
  list(): Promise<Unit[]>;
  create(input: UnitInput): Promise<Unit>;
  update(id: string, input: UnitInput): Promise<Unit>;
}

export interface ConversionService {
  list(): Promise<UnitConversion[]>;
  create(input: ConversionInput): Promise<UnitConversion>;
  /** Converts a quantity; raises the backend's "no rule exists" error. */
  convert(query: ConversionQuery): Promise<ConversionResult>;
}

/** The farm-setup domains exposed by the services layer. */
export interface FarmSetupServices {
  farm: FarmService;
  fields: FieldService;
  crops: CropService;
  varieties: VarietyService;
  units: UnitService;
  conversions: ConversionService;
}

// Harvest and sale domains (issue #49) extend the services contract here so
// the rest of the app keeps depending only on `AgrivantaServices`.
export interface AgrivantaServices
  extends FarmSetupServices, HarvestSaleServices {
  auth: AuthService;
}

/**
 * Error thrown for any non-successful backend response. The HTTP
 * implementation maps response status codes onto it; the mock throws it for
 * equivalent failures so callers cannot tell the implementations apart.
 */
export class ApiError extends Error {
  readonly status: number;
  /**
   * Input field the error belongs to (e.g. `name`, `area`), so forms can
   * render the backend message inline next to the offending control.
   * Absent for form-level errors.
   */
  readonly field?: string;

  constructor(message: string, status: number, field?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.field = field;
  }
}

/** Thrown when credentials are rejected by login or register. */
export class InvalidCredentialsError extends ApiError {
  constructor(message = 'Invalid email or password.') {
    super(message, 401);
    this.name = 'InvalidCredentialsError';
  }
}

/**
 * Thrown when an authenticated request is rejected (HTTP 401 / expired
 * token). The services provider reacts to this error by clearing the stored
 * session and sending the visitor back to the login screen.
 */
export class UnauthorizedError extends ApiError {
  constructor(message = 'Your session has expired. Please sign in again.') {
    super(message, 401);
    this.name = 'UnauthorizedError';
  }
}

export function isUnauthorizedError(
  error: unknown,
): error is UnauthorizedError {
  return error instanceof UnauthorizedError;
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

// ---------------------------------------------------------------------------
// Harvest and sale domains (issue #49)
// ---------------------------------------------------------------------------

/**
 * Minimal display reference for a crop cycle, used by the harvest and sale
 * cycle pickers. The full crop cycle model belongs to the crop cycle screens
 * (issue #45), so this domain only needs an id and a human-readable label.
 */
export interface HarvestCycleRef {
  id: string;
  label: string;
}

export interface Harvest {
  id: string;
  cycleId: string;
  quantity: number;
  unitId: string;
  /** ISO calendar date (`YYYY-MM-DD`). */
  date: string;
}

export interface HarvestInput {
  cycleId: string;
  /** Sent as typed so a blank/invalid quantity reaches the backend rule. */
  quantity: string | number;
  unitId: string;
  /** Sent as typed so a blank/invalid date reaches the backend rule. */
  date: string;
}

/** A customer profile the sale form can pick from (backend task #19). */
export interface SaleCustomer {
  id: string;
  name: string;
}

export interface Sale {
  id: string;
  customerId: string;
  /** The harvest this sale draws from; its cycle scopes the sale list. */
  harvestId: string;
  quantity: number;
  unitPrice: number;
  /** ISO calendar date (`YYYY-MM-DD`). */
  date: string;
  /** Quantity × unit price, computed by the backend (issue #29). */
  revenue: number;
}

export interface SaleInput {
  customerId: string;
  harvestId: string;
  quantity: string | number;
  unitPrice: string | number;
  date: string;
}

export interface HarvestService {
  /** Crop cycles the farm can record harvests against, for the picker. */
  listCycles(): Promise<HarvestCycleRef[]>;
  /** When `cycleId` is given, only that cycle's harvests are returned. */
  list(cycleId?: string): Promise<Harvest[]>;
  create(input: HarvestInput): Promise<Harvest>;
}

export interface SaleService {
  /** Customer profiles the sale form offers (backend task #19). */
  listCustomers(): Promise<SaleCustomer[]>;
  list(): Promise<Sale[]>;
  create(input: SaleInput): Promise<Sale>;
}

/** The harvest and sale domains exposed by the services layer. */
export interface HarvestSaleServices {
  harvests: HarvestService;
  sales: SaleService;
}
