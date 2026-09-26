import { z } from 'zod';

/**
 * Схемы ответов бэкенда.
 *
 * Валидируем всё, что приходит извне: если бэкенд поменяет формат, мы увидим
 * понятную ошибку в одном месте, а не «undefined is not an object» в вёрстке.
 */

export const categoryIdSchema = z.enum([
  'food',
  'transport',
  'subscriptions',
  'entertainment',
  'health',
  'education',
  'rent',
  'other',
]);

export const transactionSchema = z.object({
  id: z.string(),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'ожидается дата в формате YYYY-MM-DD'),
  amount: z.number(),
  category: categoryIdSchema,
  merchant: z.string(),
  isRecurring: z.boolean(),
});

export const goalSchema = z.object({
  id: z.string(),
  title: z.string(),
  targetAmount: z.number().nonnegative(),
  savedAmount: z.number().nonnegative(),
  deadline: z.string().nullable(),
});

export const goalDraftSchema = z
  .object({
    title: z.string().trim().min(1, 'укажите название'),
    targetAmount: z
      .number({ invalid_type_error: 'сумма цели должна быть числом' })
      .positive('сумма цели должна быть больше нуля'),
    savedAmount: z
      .number({ invalid_type_error: 'накоплено должно быть числом' })
      .nonnegative('накоплено не может быть отрицательным'),
    deadline: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/, 'срок должен быть датой')
      .nullable(),
  })
  .refine((draft) => draft.savedAmount <= draft.targetAmount, {
    message: 'накоплено не может быть больше суммы цели',
    path: ['savedAmount'],
  });

export const profileSchema = z.object({
  balance: z.number(),
  incomes: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      amount: z.number(),
      dayOfMonth: z.number().int().min(1).max(31),
    }),
  ),
  goals: z.array(goalSchema),
});

const dataQualitySchema = z.object({
  sufficient: z.boolean(),
  missing: z.array(z.string()),
  coverageDays: z.number().int().nonnegative(),
});

/** Обёртка объяснимости: параметризуется схемой полезной нагрузки. */
export function explainedSchema<T extends z.ZodTypeAny>(result: T) {
  return z.object({
    result,
    assumptions: z.array(z.string()),
    calculation: z.array(
      z.object({ label: z.string(), formula: z.string(), value: z.number() }),
    ),
    sources: z.array(z.object({ title: z.string(), url: z.string().url() })),
    limitations: z.array(z.string()),
    dataQuality: dataQualitySchema,
  });
}

export const overviewSchema = z.object({
  periodFrom: z.string(),
  periodTo: z.string(),
  totalIncome: z.number(),
  totalExpense: z.number(),
  recurringTotal: z.number(),
  byCategory: z.array(
    z.object({
      category: categoryIdSchema,
      amount: z.number(),
      share: z.number().min(0).max(1),
      deltaPercent: z.number().nullable(),
    }),
  ),
  anomalies: z.array(z.object({ transactionId: z.string(), reason: z.string() })),
});

export const forecastSchema = z.object({
  daysLeft: z.number().int().nonnegative(),
  expectedIncome: z.number(),
  plannedExpenses: z.number(),
  projectedBalance: z.number(),
  safeDailySpend: z.number(),
  verdict: z.enum(['ok', 'tight', 'shortfall']),
});

const upcomingIncomeSchema = z.object({
  date: z.string(),
  title: z.string(),
  amount: z.number(),
  daysUntil: z.number().int().nonnegative(),
});

const runwayDaySchema = z.object({
  date: z.string(),
  events: z.array(z.object({ title: z.string(), amount: z.number() })),
  balance: z.number(),
  status: z.enum(['ok', 'tight', 'shortfall']),
});

export const runwaySchema = z.object({
  horizonTo: z.string(),
  nextIncome: upcomingIncomeSchema.nullable(),
  todaySafeSpend: z.number(),
  lowestBalance: z.number(),
  redDays: z.number().int().nonnegative(),
  days: z.array(runwayDaySchema),
});

export const impulseCheckSchema = z.object({
  amount: z.number().positive(),
  verdict: z.enum(['ok', 'wait', 'shortfall']),
  hint: z.string(),
  todaySafeSpendBefore: z.number(),
  todaySafeSpendAfter: z.number(),
  redDaysBefore: z.number().int().nonnegative(),
  redDaysAfter: z.number().int().nonnegative(),
  lowestBalanceAfter: z.number(),
  waitUntil: upcomingIncomeSchema.nullable(),
  goalImpact: z.object({ goalTitle: z.string(), delayDays: z.number().int() }).nullable(),
  daysAfter: z.array(runwayDaySchema),
});

export const goalPlanSchema = z.object({
  goalId: z.string(),
  monthlyPace: z.number(),
  etaMonths: z.number().nullable(),
  etaDate: z.string().nullable(),
  blockers: z.array(
    z.object({ category: categoryIdSchema, amount: z.number(), hint: z.string() }),
  ),
});

export const askAnswerSchema = z.object({ text: z.string() });

export const scenarioIdSchema = z.enum(['expenses', 'budget', 'glossary', 'impulse', 'free']);

export const historyEntrySchema = z.object({
  id: z.string(),
  scenarioId: scenarioIdSchema,
  title: z.string(),
  createdAt: z.string(),
  messages: z.array(
    z.discriminatedUnion('role', [
      z.object({ role: z.literal('user'), text: z.string() }),
      z.object({ role: z.literal('assistant'), answer: explainedSchema(askAnswerSchema) }),
    ]),
  ),
});

export const importResultSchema = z.object({
  imported: z.number().int().nonnegative(),
  rejected: z.array(z.object({ row: z.number().int(), message: z.string() })),
  warnings: z.array(z.string()),
});

export const sessionSchema = z.object({
  token: z.string(),
  userId: z.string(),
  displayName: z.string(),
  mode: z.enum(['demo', 'telegram']),
});

/** Схема одной строки CSV при импорте. Используется и в предпросмотре. */
export const csvRowSchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'дата должна быть в формате ГГГГ-ММ-ДД'),
  amount: z
    .number({ invalid_type_error: 'сумма должна быть числом' })
    // Number('abc') даёт NaN, а NaN проходит проверку типа number — отсекаем явно.
    .refine(Number.isFinite, 'сумма должна быть числом')
    .refine((v) => v !== 0, 'сумма не может быть нулевой'),
  category: categoryIdSchema.catch('other'),
  merchant: z.string().min(1, 'не указано описание операции'),
});
