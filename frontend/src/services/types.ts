/**
 * The single typed contract that all backend access flows through.
 *
 * Both the mock and the HTTP implementation are typed against
 * {@link AgrivantaServices}, so the rest of the app depends only on these
 * interfaces and never on a concrete transport.
 */

// Activity planning domain (issue #46) — types live in their own file.
import type { ActivityPlanningServices } from './activityPlanningTypes';
import type { ReportingServices } from './reportingTypes';
export * from './reportingTypes';
export * from './activityPlanningTypes';
import type {
  AuthSession as ApiAuthSession,
  Attachment as ApiAttachment,
  BaseMeasureCategory as ApiBaseMeasureCategory,
  ChatAnswer as ApiChatAnswer,
  ChatEvidence as ApiChatEvidence,
  ChatEvidenceItem as ApiChatEvidenceItem,
  ConversionInput as ApiConversionInput,
  ConversionQuery as ApiConversionQuery,
  ConversionResult as ApiConversionResult,
  Crop as ApiCrop,
  CropCycle as ApiCropCycle,
  CropCycleInput as ApiCropCycleInput,
  CropCycleStatus as ApiCropCycleStatus,
  CropCycleType as ApiCropCycleType,
  CropCycleUpdateInput as ApiCropCycleUpdateInput,
  CropInput as ApiCropInput,
  Expense as ApiExpense,
  ExpenseCategory as ApiExpenseCategory,
  ExpenseInput as ApiExpenseInput,
  ExpenseStatus as ApiExpenseStatus,
  Farm as ApiFarm,
  FarmInput as ApiFarmInput,
  FarmSetupStatus as ApiFarmSetupStatus,
  Field as ApiField,
  FieldInput as ApiFieldInput,
  Harvest as ApiHarvest,
  HarvestInput as ApiHarvestInput,
  InventoryItem as ApiInventoryItem,
  InventoryItemInput as ApiInventoryItemInput,
  ImportCommitInput as ApiImportCommitInput,
  ImportCommitResult as ApiImportCommitResult,
  ImportDuplicateRow as ApiImportDuplicateRow,
  ImportEntityType as ApiImportEntityType,
  ImportInvalidRow as ApiImportInvalidRow,
  ImportPreview as ApiImportPreview,
  ImportRowError as ApiImportRowError,
  ImportValidRow as ApiImportValidRow,
  LoginCredentials as ApiLoginCredentials,
  Notification as ApiNotification,
  NotificationPage as ApiNotificationPage,
  Payment as ApiPayment,
  PaymentInput as ApiPaymentInput,
  PaymentType as ApiPaymentType,
  RegisterInput as ApiRegisterInput,
  Sale as ApiSale,
  SaleCustomer as ApiSaleCustomer,
  SaleInput as ApiSaleInput,
  StockMovement as ApiStockMovement,
  StockMovementInput as ApiStockMovementInput,
  StockMovementType as ApiStockMovementType,
  Unit as ApiUnit,
  UnitConversion as ApiUnitConversion,
  UnitInput as ApiUnitInput,
  User as ApiUser,
  UnreadCountResponse as ApiUnreadCountResponse,
  Variety as ApiVariety,
  VarietyInput as ApiVarietyInput,
  CycleRef as ApiCycleRef,
} from './generated/types.gen';

export type User = ApiUser;
export type AuthSession = ApiAuthSession;
export type LoginCredentials = ApiLoginCredentials;
export type RegisterInput = ApiRegisterInput;

export interface AuthService {
  login(credentials: LoginCredentials): Promise<AuthSession>;
  register(input: RegisterInput): Promise<AuthSession>;
  logout(): Promise<void>;
  me(): Promise<User>;
}

export type ChatEvidenceItem = ApiChatEvidenceItem;
export type ChatEvidence = ApiChatEvidence;
export type ChatAnswer = ApiChatAnswer;

export interface ChatService {
  ask(question: string, onToken: (text: string) => void): Promise<ChatAnswer>;
}

export interface ChatServices {
  chat: ChatService;
}

// ---------------------------------------------------------------------------
// Farm setup domains (farm, fields, crops, varieties, units, conversions)
// ---------------------------------------------------------------------------

/** Allowed base-measure categories for a unit of measure. */
export type BaseMeasureCategory = ApiBaseMeasureCategory;

export type FarmSetupStepId = Exclude<ApiFarmSetupStatus['nextStep'], null>;

export type FarmSetupStatus = ApiFarmSetupStatus;

export interface FarmSetupStatusService {
  get(): Promise<FarmSetupStatus>;
}

export type Farm = ApiFarm;
export type FarmInput = ApiFarmInput;
export type Field = ApiField;
export type FieldInput = ApiFieldInput;
export type Crop = ApiCrop;
export type CropInput = ApiCropInput;
export type Variety = ApiVariety;
export type VarietyInput = ApiVarietyInput;
export type Unit = ApiUnit;
export type UnitInput = Pick<ApiUnitInput, 'name'> & { baseMeasure: string };
export type UnitConversion = ApiUnitConversion;
export type ConversionInput = ApiConversionInput;
export type ConversionQuery = ApiConversionQuery;
export type ConversionResult = ApiConversionResult;

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

export type InventoryItem = ApiInventoryItem;
export type InventoryItemInput = ApiInventoryItemInput;
export type StockMovementType = ApiStockMovementType;
export type StockMovement = ApiStockMovement;
export type StockMovementInput = ApiStockMovementInput;

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
  setupStatus: FarmSetupStatusService;
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

/** Posted records are immutable; drafts may still be edited or deleted. */
export type ExpenseCategory = ApiExpenseCategory;
export type ExpenseStatus = ApiExpenseStatus;

/** Direction of a payment (task #23). */
export type PaymentType = ApiPaymentType;

/** A receipt or invoice file linked to an expense (task #24). */
export type Attachment = ApiAttachment;
export type Expense = ApiExpense;
export type ExpenseInput = ApiExpenseInput;
export type Payment = ApiPayment;
export type PaymentInput = ApiPaymentInput;

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

// ---------------------------------------------------------------------------
// CSV and Excel imports (issues #34, #35, #50)
// ---------------------------------------------------------------------------

export type ImportEntityType = ApiImportEntityType;
export type ImportRowError = ApiImportRowError;
export type ImportValidRow = ApiImportValidRow;
export type ImportInvalidRow = ApiImportInvalidRow;
export type ImportDuplicateRow = ApiImportDuplicateRow;
export type ImportPreview = ApiImportPreview;
export type ImportCommitInput = ApiImportCommitInput;
export type ImportCommitResult = ApiImportCommitResult;

export interface ImportService {
  preview(entityType: ImportEntityType, file: File): Promise<ImportPreview>;
  commit(input: ImportCommitInput): Promise<ImportCommitResult>;
}

export interface ImportServices {
  imports: ImportService;
}

// ---------------------------------------------------------------------------
// Inventory services (issue #47)
// ---------------------------------------------------------------------------

export interface InventoryServices {
  items: InventoryItemService;
  movements: StockMovementService;
}

export interface AgrivantaServices
  extends
    FarmSetupServices,
    ActivityPlanningServices,
    InventoryServices,
    ExpensePaymentServices,
    ImportServices,
    ReportingServices,
    HarvestSaleServices,
    NotificationServices,
    ChatServices {
  auth: AuthService;
  /** Crop cycle domain (issue #45). */
  cropCycles: CropCycleService;
}

export type Notification = ApiNotification;
export type NotificationPage = ApiNotificationPage;
export type UnreadCountResponse = ApiUnreadCountResponse;

export interface NotificationService {
  list(): Promise<Notification[]>;
  unreadCount(): Promise<number>;
  markRead(id: string): Promise<Notification>;
}

export interface NotificationServices {
  notifications: NotificationService;
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
export type HarvestCycleRef = ApiCycleRef;

export type Harvest = ApiHarvest;
export type HarvestInput = ApiHarvestInput;
export type SaleCustomer = ApiSaleCustomer;
export type Sale = ApiSale;
export type SaleInput = ApiSaleInput;

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

// ---------------------------------------------------------------------------
// Crop cycle domain (issue #45)
// ---------------------------------------------------------------------------

/**
 * Lifecycle state of a crop cycle. Closed cycles are locked
 * (`_docs/plan.md` §3.1); reopening them is out of scope for now.
 */
export type CropCycleStatus = ApiCropCycleStatus;
export type CropCycleType = ApiCropCycleType;
export type CropCycle = Pick<
  ApiCropCycle,
  | 'id'
  | 'fieldId'
  | 'cropId'
  | 'varietyId'
  | 'startDate'
  | 'endDate'
  | 'status'
  | 'expectedYield'
  | 'expectedPrice'
> &
  Partial<Pick<ApiCropCycle, 'cycleType'>>;
export type CropCycleInput = Pick<
  ApiCropCycleInput,
  'fieldId' | 'cropId' | 'startDate' | 'endDate'
> & {
  varietyId: string;
  cycleType?: ApiCropCycleInput['cycleType'];
  expectedYield?: NonNullable<ApiCropCycleInput['expectedYield']>;
  expectedPrice?: NonNullable<ApiCropCycleInput['expectedPrice']>;
};
export type CropCycleUpdateInput = {
  expectedYield?: NonNullable<ApiCropCycleUpdateInput['expectedYield']>;
  expectedPrice?: NonNullable<ApiCropCycleUpdateInput['expectedPrice']>;
};

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
