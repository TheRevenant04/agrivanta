import {
  EXPENSE_PAYMENT_ERRORS,
  parseAmount,
  parseExpenseDate,
  requireCategory,
  requirePaymentType,
} from './expensePaymentRules';
import { ApiError, UnauthorizedError } from './types';
import type {
  Attachment,
  Expense,
  ExpenseInput,
  ExpensePaymentServices,
  ExpenseService,
  Payment,
  PaymentInput,
  PaymentService,
} from './types';

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
  const payments: Payment[] = (seed.payments ?? []).map((item) => ({ ...item }));

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

  function applyInput(expense: Expense, input: ExpenseInput): void {
    expense.category = requireCategory(input.category);
    expense.amount = parseAmount(input.amount);
    expense.date = parseExpenseDate(input.date);

    const supplier = input.supplier?.trim();
    expense.supplier = supplier ? supplier : null;
  }

  const expensesService: ExpenseService = {
    async list() {
      requireAuth();
      return expenses.map((expense) => copy(expense));
    },

    async create(input: ExpenseInput) {
      requireAuth();

      const expense: Expense = {
        id: nextId('expense'),
        category: 'other',
        amount: 0,
        date: '',
        supplier: null,
        status: 'draft',
        attachments: [],
      };

      applyInput(expense, input);
      expenses.push(expense);
      return copy(expense);
    },

    async update(id: string, input: ExpenseInput) {
      requireAuth();

      const expense = findExpense(id);

      if (expense.status === 'posted') {
        throw new ApiError(EXPENSE_PAYMENT_ERRORS.postedEditRejected, 400);
      }

      applyInput(expense, input);
      return copy(expense);
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

  const paymentsService: PaymentService = {
    async list() {
      requireAuth();
      return payments.map((payment) => copy(payment));
    },

    async create(input: PaymentInput) {
      requireAuth();

      const date = parseExpenseDate(input.date);
      const amount = parseAmount(input.amount);
      const type = requirePaymentType(input.type);

      const payment: Payment = {
        id: nextId('payment'),
        type,
        amount,
        date,
        linkedExpenseId: input.linkedExpenseId?.trim() || null,
        linkedSaleId: input.linkedSaleId?.trim() || null,
        reference: input.reference?.trim() || null,
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
