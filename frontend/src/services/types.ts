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


// ---------------------------------------------------------------------------
// Expenses and payments (issues #49, #20, #23, #24)
// ---------------------------------------------------------------------------

/** The backend's expense categories (task #20). */
export type ExpenseCategory =
  | 'inputs'
  | 'labour'
  | 'equipment'
  | 'overhead'
  | 'other';

/** Posted records are immutable; drafts may still be edited or deleted. */
export type ExpenseStatus = 'draft' | 'posted';

/** Direction of a payment (task #23). */
export type PaymentType = 'received' | 'paid';

/** A receipt or invoice file linked to an expense (task #24). */
export interface Attachment {
  id: string;
  /** The uploaded file name, shown on the saved expense. */
  name: string;
  url?: string;
}

export interface Expense {
  id: string;
  category: ExpenseCategory;
  amount: number;
  date: string;
  supplier?: string | null;
  status: ExpenseStatus;
  attachments?: Attachment[];
  notes?: string | null;
}

export interface ExpenseInput {
  category: ExpenseCategory;
  /** Sent as typed so the backend rules can reject a missing amount. */
  amount: string | number;
  date: string;
  /** Optional counterparty; the backend allows an expense without one. */
  supplier?: string;
}

export interface Payment {
  id: string;
  type: PaymentType;
  amount: number;
  date: string;
  linkedExpenseId?: string | null;
  linkedSaleId?: string | null;
  reference?: string | null;
}

export interface PaymentInput {
  type: PaymentType;
  /** Sent as typed so the backend rules can reject a missing amount. */
  amount: string | number;
  date: string;
  /** A payment may link to an expense, a sale, or neither. */
  linkedExpenseId?: string;
  linkedSaleId?: string;
  reference?: string;
}

export interface ExpenseService {
  list(): Promise<Expense[]>;
  create(input: ExpenseInput): Promise<Expense>;
  update(id: string, input: ExpenseInput): Promise<Expense>;
  remove(id: string): Promise<void>;
  post(id: string): Promise<Expense>;
  uploadAttachment(expenseId: string, file: File): Promise<Attachment>;
}

export interface PaymentService {
  list(): Promise<Payment[]>;
  create(input: PaymentInput): Promise<Payment>;
  update?(id: string, input: PaymentInput): Promise<Payment>;
  remove?(id: string): Promise<void>;
}

export interface ExpensePaymentServices {
  expenses: ExpenseService;
  payments: PaymentService;
}

export interface AgrivantaServices extends FarmSetupServices, ExpensePaymentServices {
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
