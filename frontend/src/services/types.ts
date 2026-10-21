/**
 * The single typed contract that all backend access flows through.
 *
 * Both the mock and the HTTP implementation are typed against
 * {@link AgrivantaServices}, so the rest of the app depends only on these
 * interfaces and never on a concrete transport.
 */

// Activity planning domain (issue #46) — types live in their own file.
import type { ActivityPlanningServices } from './activityPlanningTypes';
export * from './activityPlanningTypes';

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

// ---------------------------------------------------------------------------
// Inventory domains (inventory items and stock movements)
// ---------------------------------------------------------------------------

export interface InventoryItem {
  id: string;
  name: string;
  unitId: string;
  reorderLevel: number;
  /** Current quantity derived from stock movements (read-only). */
  currentQuantity: number;
}

export interface InventoryItemInput {
  name: string;
  unitId: string;
  /** Sent as typed so backend rules can be mirrored. */
  reorderLevel: string | number;
}

export type StockMovementType = 'purchase' | 'usage' | 'adjustment';

export interface StockMovement {
  id: string;
  itemId: string;
  type: StockMovementType;
  quantity: number;
  date?: string;
  note?: string;
}

export interface StockMovementInput {
  itemId: string;
  type: StockMovementType;
  /** Sent as typed so backend rules can be mirrored. */
  quantity: string | number;
  date?: string;
  note?: string;
}

export interface InventoryItemService {
  list(): Promise<InventoryItem[]>;
  create(input: InventoryItemInput): Promise<InventoryItem>;
  update(id: string, input: InventoryItemInput): Promise<InventoryItem>;
}

export interface StockMovementService {
  list(itemId?: string): Promise<StockMovement[]>;
  create(input: StockMovementInput): Promise<StockMovement>;
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

// ---------------------------------------------------------------------------
// Inventory services (issue #47)
// ---------------------------------------------------------------------------

export interface InventoryServices {
  items: InventoryItemService;
  movements: StockMovementService;
}

export interface AgrivantaServices
  extends FarmSetupServices, ActivityPlanningServices, InventoryServices {
  auth: AuthService;
  /** Crop cycle domain (issue #45). */
  cropCycles: CropCycleService;
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
// Crop cycle domain (issue #45)
// ---------------------------------------------------------------------------

/**
 * Lifecycle state of a crop cycle. Closed cycles are locked
 * (`_docs/plan.md` §3.1); reopening them is out of scope for now.
 */
export type CropCycleStatus = 'open' | 'closed';

export interface CropCycle {
  id: string;
  fieldId: string;
  cropId: string;
  varietyId: string;
  /** ISO calendar date (`YYYY-MM-DD`) the cycle starts on. */
  startDate: string;
  /** Optional ISO calendar date the cycle ended on. */
  endDate?: string;
  status: CropCycleStatus;
  expectedYield?: number;
  expectedPrice?: number;
}

export interface CropCycleInput {
  fieldId: string;
  cropId: string;
  varietyId: string;
  /**
   * Sent as a raw string so a blank value reaches the backend's
   * "start date is required" rule.
   */
  startDate: string;
  endDate?: string;
  /** Sent as typed so a blank clears and invalid values reach the backend. */
  expectedYield?: string | number;
  expectedPrice?: string | number;
}

/** Only the forecast amounts can be edited after a cycle is created. */
export interface CropCycleUpdateInput {
  expectedYield?: string | number;
  expectedPrice?: string | number;
}

export interface CropCycleService {
  /** When `fieldId` is given, only that field's cycles are returned. */
  list(fieldId?: string): Promise<CropCycle[]>;
  create(input: CropCycleInput): Promise<CropCycle>;
  /** Updates the expected yield/price of an open cycle. */
  update(id: string, input: CropCycleUpdateInput): Promise<CropCycle>;
  /** Formally closes the cycle; raises on an already-closed cycle. */
  close(id: string): Promise<CropCycle>;
}

/** The crop cycle domain exposed by the services layer. */
export interface CropCycleServices {
  cropCycles: CropCycleService;
}
