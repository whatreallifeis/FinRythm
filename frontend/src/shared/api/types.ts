/**
 * Контракт с бэкендом. Это тот файл, который нужно согласовать с бэкендером
 * до начала интеграции: фронт уже умеет рисовать всё, что здесь описано.
 */

/** Категории расходов. Список фиксирован, чтобы UI знал цвета и иконки. */
export type CategoryId =
  | 'food'
  | 'transport'
  | 'subscriptions'
  | 'entertainment'
  | 'health'
  | 'education'
  | 'rent'
  | 'other';

export interface Transaction {
  id: string;
  /** ISO-дата, YYYY-MM-DD. */
  date: string;
  /** Отрицательная сумма — расход, положительная — доход. В рублях. */
  amount: number;
  category: CategoryId;
  merchant: string;
  /** Платёж распознан как регулярный (подписка, аренда, связь). */
  isRecurring: boolean;
}

export interface Goal {
  id: string;
  title: string;
  targetAmount: number;
  savedAmount: number;
  /** ISO-дата желаемого срока или null, если срок не задан. */
  deadline: string | null;
}

/** Поля цели без id — для создания и редактирования. */
export interface GoalDraft {
  title: string;
  targetAmount: number;
  savedAmount: number;
  deadline: string | null;
}

export interface Income {
  id: string;
  title: string;
  amount: number;
  dayOfMonth: number;
}

/**
 * Автоплатёж: регулярное списание в один и тот же день месяца — аренда,
 * подписка, связь. По ним строится календарь до поступления.
 */
export interface Autopayment {
  id: string;
  title: string;
  /** Сумма списания, положительное число. */
  amount: number;
  /** 1–31. Если в месяце меньше дней, платёж приходится на последний день. */
  dayOfMonth: number;
  category: CategoryId;
}

/** Поля автоплатежа без id — для создания. */
export type AutopaymentDraft = Omit<Autopayment, 'id'>;

export interface Profile {
  balance: number;
  /** Регулярные поступления: стипендия, зарплата, подработка. */
  incomes: Income[];
  /** Регулярные списания. */
  autopayments: Autopayment[];
  goals: Goal[];
}

/* ------------------------------------------------------------------ */
/* Обёртка объяснимости                                               */
/* ------------------------------------------------------------------ */

export interface CalcStep {
  label: string;
  /** Человекочитаемая формула: «7 800 ₽ / 12 дней». */
  formula: string;
  value: number;
}

export interface Source {
  title: string;
  url: string;
}

export interface DataQuality {
  /** false — показываем InsufficientData вместо результата. */
  sufficient: boolean;
  /** Чего конкретно не хватает, чтобы посчитать точно. */
  missing: string[];
  /** За сколько дней есть данные. */
  coverageDays: number;
}

/**
 * Каждый аналитический ответ приходит в этой обёртке.
 *
 * Именно она закрывает требования ТЗ: показать допущения, расчёты, источники
 * и ограничения, а при недостатке данных — не выдавать предположение за факт.
 */
export interface Explained<T> {
  result: T;
  assumptions: string[];
  calculation: CalcStep[];
  sources: Source[];
  limitations: string[];
  dataQuality: DataQuality;
}

/* ------------------------------------------------------------------ */
/* Результаты конкретных запросов                                     */
/* ------------------------------------------------------------------ */

export interface CategorySlice {
  category: CategoryId;
  amount: number;
  /** Доля в общих расходах, 0..1. */
  share: number;
  /** Изменение к прошлому периоду в процентах, null если сравнить не с чем. */
  deltaPercent: number | null;
}

export interface Overview {
  periodFrom: string;
  periodTo: string;
  totalIncome: number;
  totalExpense: number;
  recurringTotal: number;
  byCategory: CategorySlice[];
  /** Необычные траты: подсвечиваем как потенциальный риск. */
  anomalies: Array<{ transactionId: string; reason: string }>;
}

export interface Forecast {
  daysLeft: number;
  expectedIncome: number;
  plannedExpenses: number;
  projectedBalance: number;
  /** Сколько можно тратить в день, чтобы дожить до конца месяца. */
  safeDailySpend: number;
  verdict: 'ok' | 'tight' | 'shortfall';
}

export type DayStatus = 'ok' | 'tight' | 'shortfall';

export interface UpcomingIncome {
  date: string;
  title: string;
  amount: number;
  daysUntil: number;
}

export interface RunwayDay {
  date: string;
  events: Array<{ title: string; amount: number }>;
  balance: number;
  status: DayStatus;
}

/**
 * Календарь до следующего поступления: не «хватит ли в среднем за месяц»,
 * а какие дни станут красными между стипендией и подработкой.
 */
export interface Runway {
  horizonTo: string;
  nextIncome: UpcomingIncome | null;
  todaySafeSpend: number;
  lowestBalance: number;
  redDays: number;
  days: RunwayDay[];
}

/**
 * Откуда взялась операция дня — по этой ссылке её можно переименовать.
 * Прошедшие операции — это транзакции, будущие — автоплатежи и поступления.
 */
export type OperationRef =
  | { kind: 'transaction'; id: string }
  | { kind: 'autopayment'; id: string }
  | { kind: 'income'; id: string };

export interface DayOperation {
  ref: OperationRef;
  title: string;
  /** Отрицательная сумма — расход, положительная — доход. */
  amount: number;
  category: CategoryId;
  isRecurring: boolean;
}

/**
 * Один день календаря на главной: что в этот день происходит с деньгами
 * и справка помощника о регулярных операциях.
 *
 * Для прошедших дней операции — факт из выписки, для будущих — план
 * по регулярным платежам и поступлениям.
 */
export interface DayInsight {
  date: string;
  kind: 'past' | 'today' | 'future';
  operations: DayOperation[];
  /** Сколько обычно уходит в этот день недели на необязательные траты; null — не с чем сравнить. */
  typicalSpend: number | null;
  /** Остаток на конец дня. Для будущих — прогноз, null — за горизонтом расчёта. */
  balance: number | null;
  status: DayStatus | null;
  /** Справка помощника. null, если регулярных операций в этот день нет. */
  note: string | null;
}

export type ImpulseVerdict = 'ok' | 'wait' | 'shortfall';

/** Проверка покупки на том же календаре: что будет, если потратить сумму сегодня. */
export interface ImpulseCheck {
  amount: number;
  verdict: ImpulseVerdict;
  hint: string;
  todaySafeSpendBefore: number;
  todaySafeSpendAfter: number;
  redDaysBefore: number;
  redDaysAfter: number;
  lowestBalanceAfter: number;
  waitUntil: UpcomingIncome | null;
  goalImpact: { goalTitle: string; delayDays: number } | null;
  daysAfter: RunwayDay[];
}

export interface GoalPlan {
  goalId: string;
  monthlyPace: number;
  etaMonths: number | null;
  etaDate: string | null;
  /** Что мешает достичь цели быстрее. */
  blockers: Array<{ category: CategoryId; amount: number; hint: string }>;
}

export interface AskAnswer {
  text: string;
}

/**
 * Сценарий помощника. Пересекает границу API: фронт присылает идентификатор,
 * а бэкенд по нему подставляет свой системный промпт.
 *
 * Промпты сознательно живут на сервере, а не в бандле: их правит тот, кто
 * занимается моделью, и они не должны быть видны пользователю.
 */
export type ScenarioId = 'expenses' | 'budget' | 'glossary' | 'impulse' | 'free';

export interface AskRequest {
  question: string;
  scenarioId: ScenarioId;
}

/* ------------------------------------------------------------------ */
/* История запросов                                                   */
/* ------------------------------------------------------------------ */

/**
 * Одна реплика сохранённого диалога.
 *
 * Ответ помощника хранится вместе с обёрткой объяснимости, поэтому в истории
 * видно не только текст, но и на чём он был основан. Это важно: вывод без
 * допущений и расчётов через неделю бесполезен.
 */
export type HistoryMessage =
  | { role: 'user'; text: string }
  | { role: 'assistant'; answer: Explained<AskAnswer> };

export interface HistoryEntry {
  id: string;
  scenarioId: ScenarioId;
  /** Первый вопрос пользователя — заголовок в списке истории. */
  title: string;
  /** ISO-дата со временем. */
  createdAt: string;
  messages: HistoryMessage[];
}

/* ------------------------------------------------------------------ */
/* Импорт данных                                                      */
/* ------------------------------------------------------------------ */

export interface ImportRowError {
  /** Номер строки в исходном файле, начиная с 1. */
  row: number;
  message: string;
}

/**
 * Замена всей выписки. Баланса в CSV нет, поэтому он передаётся отдельно —
 * как в шапке банковской выписки.
 */
export interface DatasetReplace {
  rows: Array<Omit<Transaction, 'id' | 'isRecurring'>>;
  balance: number;
}

export interface ImportResult {
  imported: number;
  rejected: ImportRowError[];
  warnings: string[];
}

export interface Session {
  token: string;
  userId: string;
  displayName: string;
  mode: 'demo' | 'telegram';
}
