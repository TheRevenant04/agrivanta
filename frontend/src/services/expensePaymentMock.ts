import {
  EXPENSE_PAYMENT_ERRORS,
  parseAmount,
  parseExpenseDate,
  requireCategory,
  requirePaymentType,
} from './expensePaymentRules';
import { ApiError, UnauthorizedError } from '@/services/types';
import type {
  Attachment,
  Expense,
  ExpenseCategory,
  ExpenseInput,
  ExpensePaymentServices,
  ExpenseService,
  Payment,
  PaymentInput,
  PaymentService,
  PaymentType,
} from '@/services/types';

/** Seed shape for the expense and payment domains. */
export interface ExpensePaymentSeed {
  expenses?: Expense[];
  payments?: Payment[];
}

export interface ExpensePaymentMockOptions {
  seed?: ExpensePaymentSeed;
  /**
   * Called before every request, mirroring the backend's 401 rule. Defaults
   * to rejecting like an unauthenticated API call; `createMockServices`
   * wires this to the stored session.
   */
  requireAuth?: () => void;
}

function copy<T extends { id: string }>(item: T): T {
  return { ...item };
}

/**
 * Copies an expense together with its attachments, so a caller can never
 * reach the stored array by accident.
 */
function copyExpense(expense: Expense): Expense {
  return {
    ...expense,
    attachments: (expense.attachments ?? []).map((attachment) => ({
      ...attachment,
    })),
  };
}

/**
 * In-memory implementation of the expense and payment domains. It enforces
 * the same rules (messages, 400/404 status codes, offending field) as the
 * HTTP implementation, so callers cannot tell them apart.
 */
export function createExpensePaymentMock(
  options: ExpensePaymentMockOptions = {},
): ExpensePaymentServices {
  const requireAuth =
    options.requireAuth ??
    (() => {
      throw new UnauthorizedError();
    });
  const seed = options.seed ?? {};

  const expenses: Expense[] = (seed.expenses ?? []).map((item) => ({
    ...item,
    attachments: (item.attachments ?? []).map((attachment) => ({
      ...attachment,
    })),
  }));
  const payments: Payment[] = (seed.payments ?? []).map((item) => ({
    ...item,
  }));

  const sequence = {
    expense: expenses.length,
    payment: payments.length,
    attachment: 0,
  };

  function nextId(kind: keyof typeof sequence): string {
    sequence[kind] += 1;
    return `${kind}-${sequence[kind]}`;
  }

  function findExpense(id: string): Expense {
    const expense = expenses.find((item) => item.id === id);

    if (!expense) {
      throw new ApiError(EXPENSE_PAYMENT_ERRORS.expenseNotFound, 404);
    }

    return expense;
  }

  /**
   * The validated, ready-to-store form of an expense input.
   */
  interface ValidatedExpenseInput {
    category: ExpenseCategory;
    amount: number;
    date: string;
    supplier: string | null;
  }

  /**
   * Validates the whole input before any record is touched. Every field is
   * parsed up front so a rejected input leaves the stored record exactly as
   * it was, the way the backend behaves when it refuses a request.
   */
  function validateExpenseInput(input: ExpenseInput): ValidatedExpenseInput {
    const category = requireCategory(input.category);
    const amount = parseAmount(input.amount);
    const date = parseExpenseDate(input.date);
    const supplier = input.supplier?.trim();

    return {
      category,
      amount,
      date,
      supplier: supplier ? supplier : null,
    };
  }

  const expensesService: ExpenseService = {
    async list() {
      requireAuth();
      return expenses.map((expense) => copyExpense(expense));
    },

    async create(input: ExpenseInput) {
      requireAuth();

      // Validate everything before the record exists, so a rejected input
      // leaves no trace at all.
      const validated = validateExpenseInput(input);

      const expense: Expense = {
        id: nextId('expense'),
        category: validated.category,
        amount: validated.amount,
        date: validated.date,
        supplier: validated.supplier,
        status: 'draft',
        attachments: [],
      };

      expenses.push(expense);
      return copyExpense(expense);
    },

    async update(id: string, input: ExpenseInput) {
      requireAuth();

      const index = expenses.findIndex((item) => item.id === id);

      if (index === -1) {
        throw new ApiError(EXPENSE_PAYMENT_ERRORS.expenseNotFound, 404);
      }

      if (expenses[index].status === 'posted') {
        throw new ApiError(EXPENSE_PAYMENT_ERRORS.postedEditRejected, 400);
      }

      // Validate before writing: a rejected edit must not apply the fields
      // that happened to be parsed first.
      const validated = validateExpenseInput(input);

      const updated: Expense = {
        ...expenses[index],
        category: validated.category,
        amount: validated.amount,
        date: validated.date,
        supplier: validated.supplier,
      };

      expenses[index] = updated;
      return copyExpense(updated);
    },

    async remove(id: string) {
      requireAuth();

      const expense = findExpense(id);

      if (expense.status === 'posted') {
        throw new ApiError(EXPENSE_PAYMENT_ERRORS.postedDeleteRejected, 400);
      }

      const index = expenses.findIndex((item) => item.id === id);

      if (index >= 0) {
        expenses.splice(index, 1);
      }
    },

    async post(id: string) {
      requireAuth();

      const expense = findExpense(id);
      expense.status = 'posted';
      return copy(expense);
    },

    async uploadAttachment(expenseId: string, file: File) {
      requireAuth();

      const expense = findExpense(expenseId);

      if (expense.status === 'posted') {
        throw new ApiError(EXPENSE_PAYMENT_ERRORS.postedImmutable, 400);
      }

      if (!file || !file.name) {
        throw new ApiError(EXPENSE_PAYMENT_ERRORS.attachmentInvalid, 400);
      }

      sequence.attachment += 1;

      const attachment: Attachment = {
        id: `attachment-${sequence.attachment}`,
        name: file.name,
      };

      if (!expense.attachments) {
        expense.attachments = [];
      }

      expense.attachments.push(attachment);
      return attachment;
    },
  };

  /**
   * The validated, ready-to-store form of a payment input.
   */
  interface ValidatedPaymentInput {
    type: PaymentType;
    amount: number;
    date: string;
    linkedExpenseId: string | null;
    linkedSaleId: string | null;
    reference: string | null;
  }

  /**
   * Validates the whole input before any record is touched, so a rejected
   * input leaves the stored records exactly as they were.
   */
  function validatePaymentInput(input: PaymentInput): ValidatedPaymentInput {
    const type = requirePaymentType(input.type);
    const amount = parseAmount(input.amount);
    const date = parseExpenseDate(input.date);

    return {
      type,
      amount,
      date,
      linkedExpenseId: input.linkedExpenseId?.trim() || null,
      linkedSaleId: input.linkedSaleId?.trim() || null,
      reference: input.reference?.trim() || null,
    };
  }

  const paymentsService: PaymentService = {
    async list() {
      requireAuth();
      return payments.map((payment) => copy(payment));
    },

    async create(input: PaymentInput) {
      requireAuth();

      // Validate everything before the record exists, so a rejected input
      // leaves no trace at all.
      const validated = validatePaymentInput(input);

      const payment: Payment = {
        id: nextId('payment'),
        type: validated.type,
        amount: validated.amount,
        date: validated.date,
        linkedExpenseId: validated.linkedExpenseId,
        linkedSaleId: validated.linkedSaleId,
        reference: validated.reference,
      };

      payments.push(payment);
      return copy(payment);
    },
  };

  return {
    expenses: expensesService,
    payments: paymentsService,
  };
}
