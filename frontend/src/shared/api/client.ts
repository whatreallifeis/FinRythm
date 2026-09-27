import type { z } from 'zod';
import { clearDataset as clearMockDataset, mockHandlers } from './mock/handlers';
import {
  askAnswerSchema,
  autopaymentSchema,
  dayInsightSchema,
  explainedSchema,
  forecastSchema,
  impulseCheckSchema,
  goalPlanSchema,
  goalSchema,
  historyEntrySchema,
  incomeSchema,
  importResultSchema,
  overviewSchema,
  runwaySchema,
  profileSchema,
  sessionSchema,
  transactionSchema,
} from './schemas';
import type {
  AskAnswer,
  AskRequest,
  Autopayment,
  AutopaymentDraft,
  DatasetReplace,
  DayInsight,
  Explained,
  Forecast,
  ImpulseCheck,
  Goal,
  GoalDraft,
  GoalPlan,
  HistoryEntry,
  ImportResult,
  Income,
  Overview,
  Runway,
  Profile,
  Session,
  Transaction,
} from './types';

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';
const API_URL = import.meta.env.VITE_API_URL ?? '';

/** Единый тип ошибки: UI различает «нет сети», «сервер ответил ошибкой» и «формат не тот». */
export class ApiError extends Error {
  constructor(
    readonly kind: 'network' | 'http' | 'validation',
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Токен хранится здесь, чтобы client не зависел от стора и не было циклов. */
let authToken: string | null = null;
export function setAuthToken(token: string | null) {
  authToken = token;
}

/**
 * Один запрос к бэкенду с валидацией ответа.
 *
 * `schema: null` — ответ без тела (например, DELETE): парсить нечего,
 * иначе response.json() упал бы на пустом теле.
 */
async function request<T>(
  path: string,
  schema: z.ZodType<T> | null,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError('network', 'Не удалось связаться с сервером. Проверьте подключение.');
  }

  if (!response.ok) {
    throw new ApiError('http', `Сервер вернул ошибку ${response.status}`, response.status);
  }

  if (schema === null) return undefined as T;

  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) {
    throw new ApiError('validation', 'Сервер вернул данные в неожидаемом формате.');
  }
  return parsed.data;
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

/**
 * Единственная точка входа к данным.
 *
 * Пока VITE_USE_MOCK !== 'false' все вызовы уходят в mock/handlers.
 * Переключение на реальный бэкенд — это изменение одной переменной окружения,
 * компоненты и хуки не меняются.
 */
export const api = {
  /** Подставляет демо-набор студента. */
  seedDemo(): Promise<void> {
    if (USE_MOCK) return mockHandlers.seedDemo();
    return request<void>('/api/demo/seed', null, post({}));
  },

  clearDataset(): Promise<void> {
    if (USE_MOCK) {
      clearMockDataset();
      return Promise.resolve();
    }
    return Promise.resolve();
  },

  authDemo(): Promise<Session> {
    if (USE_MOCK) return mockHandlers.authDemo();
    return request('/api/auth/demo', sessionSchema, post({}));
  },

  authTelegram(initData: string, displayName: string): Promise<Session> {
    if (USE_MOCK) return mockHandlers.authTelegram(displayName);
    return request('/api/auth/telegram', sessionSchema, post({ initData }));
  },

  profile(): Promise<Profile> {
    if (USE_MOCK) return mockHandlers.profile();
    return request('/api/profile', profileSchema);
  },

  transactions(): Promise<Transaction[]> {
    if (USE_MOCK) return mockHandlers.transactions();
    return request('/api/transactions', transactionSchema.array());
  },

  overview(): Promise<Explained<Overview>> {
    if (USE_MOCK) return mockHandlers.overview();
    return request('/api/analysis/overview', explainedSchema(overviewSchema));
  },

  forecast(): Promise<Explained<Forecast>> {
    if (USE_MOCK) return mockHandlers.forecast();
    return request('/api/analysis/forecast', explainedSchema(forecastSchema));
  },

  runway(): Promise<Explained<Runway>> {
    if (USE_MOCK) return mockHandlers.runway();
    return request('/api/analysis/runway', explainedSchema(runwaySchema));
  },

  dayInsight(date: string): Promise<Explained<DayInsight>> {
    if (USE_MOCK) return mockHandlers.dayInsight(date);
    return request(`/api/calendar/${date}`, explainedSchema(dayInsightSchema));
  },

  impulse(amount: number): Promise<Explained<ImpulseCheck>> {
    if (USE_MOCK) return mockHandlers.impulse(amount);
    return request('/api/analysis/impulse', explainedSchema(impulseCheckSchema), post({ amount }));
  },

  goalPlan(goalId: string): Promise<Explained<GoalPlan>> {
    if (USE_MOCK) return mockHandlers.goalPlan(goalId);
    return request(`/api/goals/${goalId}/plan`, explainedSchema(goalPlanSchema));
  },

  createGoal(draft: GoalDraft): Promise<Goal> {
    if (USE_MOCK) return mockHandlers.createGoal(draft);
    return request('/api/goals', goalSchema, post(draft));
  },

  updateGoal(id: string, draft: GoalDraft): Promise<Goal> {
    if (USE_MOCK) return mockHandlers.updateGoal(id, draft);
    return request(`/api/goals/${id}`, goalSchema, {
      method: 'PATCH',
      body: JSON.stringify(draft),
    });
  },

  deleteGoal(id: string): Promise<void> {
    if (USE_MOCK) return mockHandlers.deleteGoal(id);
    return request<void>(`/api/goals/${id}`, null, { method: 'DELETE' });
  },

  /**
   * Бэкенд получает только идентификатор сценария и подставляет свой
   * системный промпт — текст промпта во фронтенде не хранится.
   */
  ask(payload: AskRequest): Promise<Explained<AskAnswer>> {
    if (USE_MOCK) return mockHandlers.ask(payload);
    return request('/api/ask', explainedSchema(askAnswerSchema), post(payload));
  },

  /**
   * Переименование операции. Если операция регулярная, бэкенд переименовывает
   * всю серию: такие же регулярные операции в истории и связанный автоплатёж
   * или поступление — иначе справка по дню потеряет историю платежа.
   */
  renameTransaction(id: string, merchant: string): Promise<Transaction> {
    if (USE_MOCK) return mockHandlers.renameTransaction(id, merchant);
    return request(`/api/transactions/${id}`, transactionSchema, {
      method: 'PATCH',
      body: JSON.stringify({ merchant }),
    });
  },

  createAutopayment(draft: AutopaymentDraft): Promise<Autopayment> {
    if (USE_MOCK) return mockHandlers.createAutopayment(draft);
    return request('/api/autopayments', autopaymentSchema, post(draft));
  },

  /** Переименовывает автоплатёж и прошедшие регулярные списания с тем же названием. */
  renameAutopayment(id: string, title: string): Promise<Autopayment> {
    if (USE_MOCK) return mockHandlers.renameAutopayment(id, title);
    return request(`/api/autopayments/${id}`, autopaymentSchema, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    });
  },

  deleteAutopayment(id: string): Promise<void> {
    if (USE_MOCK) return mockHandlers.deleteAutopayment(id);
    return request<void>(`/api/autopayments/${id}`, null, { method: 'DELETE' });
  },

  /** Переименовывает регулярное поступление и прошедшие зачисления с тем же названием. */
  renameIncome(id: string, title: string): Promise<Income> {
    if (USE_MOCK) return mockHandlers.renameIncome(id, title);
    return request(`/api/incomes/${id}`, incomeSchema, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    });
  },

  /**
   * Замена всей выписки: операции, найденные в ней регулярные платежи
   * и баланс. Прежние операции, автоплатежи, цели и история удаляются.
   */
  replaceDataset(payload: DatasetReplace): Promise<ImportResult> {
    if (USE_MOCK) return mockHandlers.replaceDataset(payload);
    return request('/api/dataset', importResultSchema, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },

  importTransactions(
    rows: Array<Omit<Transaction, 'id' | 'isRecurring'>>,
  ): Promise<ImportResult> {
    if (USE_MOCK) return mockHandlers.importTransactions(rows);
    return request('/api/transactions/import', importResultSchema, post({ rows }));
  },

  history(): Promise<HistoryEntry[]> {
    if (USE_MOCK) return mockHandlers.history();
    return request('/api/history', historyEntrySchema.array());
  },

  /**
   * Upsert по id: диалог сохраняется целиком после каждого обмена репликами.
   * Идемпотентно, поэтому повторный вызов с теми же данными безопасен.
   */
  saveHistory(entry: HistoryEntry): Promise<HistoryEntry> {
    if (USE_MOCK) return mockHandlers.saveHistory(entry);
    return request(`/api/history/${entry.id}`, historyEntrySchema, {
      method: 'PUT',
      body: JSON.stringify(entry),
    });
  },

  clearHistory(): Promise<void> {
    if (USE_MOCK) return mockHandlers.clearHistory();
    return request<void>('/api/history', null, { method: 'DELETE' });
  },
};
