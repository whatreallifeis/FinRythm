import type { z } from 'zod';
import {
  askAnswerSchema,
  explainedSchema,
  forecastSchema,
  impulseCheckSchema,
  goalPlanSchema,
  goalSchema,
  historyEntrySchema,
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
  Explained,
  Forecast,
  ImpulseCheck,
  Goal,
  GoalDraft,
  GoalPlan,
  HistoryEntry,
  ImportResult,
  Overview,
  Runway,
  Profile,
  Session,
  Transaction,
} from './types';

/** Пусто — API на том же адресе, что и сайт (так работает стенд за caddy). */
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
 * Единственная точка входа к данным. Все вызовы идут в бэкенд (contracts/api.md в main).
 */
export const api = {
  /** Подставляет демо-набор студента на сервере. */
  seedDemo(): Promise<void> {
    return request('/api/demo/seed', null, post({}));
  },

  clearDataset(): Promise<void> {
    return request<void>('/api/dataset', null, { method: 'DELETE' });
  },

  authDemo(): Promise<Session> {
    return request('/api/auth/demo', sessionSchema, post({}));
  },

  authTelegram(initData: string): Promise<Session> {
    return request('/api/auth/telegram', sessionSchema, post({ initData }));
  },

  profile(): Promise<Profile> {
    return request('/api/profile', profileSchema);
  },

  transactions(): Promise<Transaction[]> {
    return request('/api/transactions', transactionSchema.array());
  },

  overview(): Promise<Explained<Overview>> {
    return request('/api/analysis/overview', explainedSchema(overviewSchema));
  },

  forecast(): Promise<Explained<Forecast>> {
    return request('/api/analysis/forecast', explainedSchema(forecastSchema));
  },

  runway(): Promise<Explained<Runway>> {
    return request('/api/analysis/runway', explainedSchema(runwaySchema));
  },

  impulse(amount: number): Promise<Explained<ImpulseCheck>> {
    return request('/api/analysis/impulse', explainedSchema(impulseCheckSchema), post({ amount }));
  },

  goalPlan(goalId: string): Promise<Explained<GoalPlan>> {
    return request(`/api/goals/${goalId}/plan`, explainedSchema(goalPlanSchema));
  },

  createGoal(draft: GoalDraft): Promise<Goal> {
    return request('/api/goals', goalSchema, post(draft));
  },

  updateGoal(id: string, draft: GoalDraft): Promise<Goal> {
    return request(`/api/goals/${id}`, goalSchema, {
      method: 'PATCH',
      body: JSON.stringify(draft),
    });
  },

  deleteGoal(id: string): Promise<void> {
    return request<void>(`/api/goals/${id}`, null, { method: 'DELETE' });
  },

  /**
   * Бэкенд получает только идентификатор сценария и подставляет свой
   * системный промпт — текст промпта во фронтенде не хранится.
   */
  ask(payload: AskRequest): Promise<Explained<AskAnswer>> {
    return request('/api/ask', explainedSchema(askAnswerSchema), post(payload));
  },

  importTransactions(
    rows: Array<Omit<Transaction, 'id' | 'isRecurring'>>,
  ): Promise<ImportResult> {
    return request('/api/transactions/import', importResultSchema, post({ rows }));
  },

  history(): Promise<HistoryEntry[]> {
    return request('/api/history', historyEntrySchema.array());
  },

  /**
   * Upsert по id: диалог сохраняется целиком после каждого обмена репликами.
   * Идемпотентно, поэтому повторный вызов с теми же данными безопасен.
   */
  saveHistory(entry: HistoryEntry): Promise<HistoryEntry> {
    return request(`/api/history/${entry.id}`, historyEntrySchema, {
      method: 'PUT',
      body: JSON.stringify(entry),
    });
  },

  clearHistory(): Promise<void> {
    return request<void>('/api/history', null, { method: 'DELETE' });
  },
};
