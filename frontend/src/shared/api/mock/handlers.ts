import type {
  AskAnswer,
  AskRequest,
  Autopayment,
  AutopaymentDraft,
  DatasetReplace,
  CategoryId,
  CategorySlice,
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
  Profile,
  Runway,
  Session,
  Source,
  Transaction,
} from '../types';
import { readDatasetReady } from '../dataset';
import { DEMO_TODAY, demoHistory, demoProfile, demoTransactions } from './data';
import { buildDayInsight } from './day';
import { applySeries } from './recurring';
import { buildImpulse, buildRunway, daysBetween, parseIso, plannedEvents, toIso } from './runway';

/**
 * Мок бэкенда.
 *
 * Показатели считаются из demoTransactions, а не прописаны руками: если
 * кто-то поменяет датасет, цифры на экранах останутся согласованными.
 *
 * Когда появится настоящий бэкенд — этот файл удаляется, а VITE_USE_MOCK
 * переключается в false. Компоненты не меняются.
 */

const LATENCY_MS = 450;
/** Дольше обычного запроса: сцена загрузки должна успеть проиграться. */
const SEED_MS = 1000;

const EMPTY_PROFILE: Profile = { balance: 0, incomes: [], autopayments: [], goals: [] };

function demoSnapshot() {
  return {
    transactions: [...demoTransactions],
    profile: structuredClone(demoProfile) as Profile,
    history: structuredClone(demoHistory) as HistoryEntry[],
  };
}

function emptySnapshot() {
  return {
    transactions: [] as Transaction[],
    profile: structuredClone(EMPTY_PROFILE),
    history: [] as HistoryEntry[],
  };
}

function delay<T>(value: T, ms = LATENCY_MS): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

type Snapshot = ReturnType<typeof demoSnapshot>;

const STATE_KEY = 'fin:mock-state';

/**
 * Мок хранит свой снимок в localStorage, чтобы после перезагрузки страницы
 * остались загруженная выписка, переименования и автоплатежи — как это было
 * бы с настоящим сервером.
 */
function persist() {
  try {
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
  } catch {
    // Приватный режим или переполнение: состояние живёт до перезагрузки.
  }
}

function restore(): Snapshot {
  if (!readDatasetReady()) return emptySnapshot();
  try {
    const saved = JSON.parse(localStorage.getItem(STATE_KEY) ?? 'null') as Snapshot | null;
    // Снимок старого формата (до автоплатежей) не восстанавливаем.
    if (saved && Array.isArray(saved.transactions) && Array.isArray(saved.profile?.autopayments)) {
      return saved;
    }
  } catch {
    // Испорченный снимок — начинаем с демо.
  }
  return demoSnapshot();
}

/**
 * Изменяемое состояние мока.
 *
 * Новый пользователь начинает с пустого набора: цифры появляются только
 * после загрузки выписки или примера. Если данные уже загружали в этом
 * браузере, снимок восстанавливается сразу.
 */
const state: Snapshot = restore();

function replaceState(next: Snapshot) {
  state.transactions = next.transactions;
  state.profile = next.profile;
  state.history = next.history;
  persist();
}

export function resetMockState() {
  replaceState(demoSnapshot());
}

export function clearDataset() {
  replaceState(emptySnapshot());
  try {
    localStorage.removeItem(STATE_KEY);
  } catch {
    // Нечего чистить.
  }
}

/* ------------------------------------------------------------------ */
/* Вспомогательные расчёты                                            */
/* ------------------------------------------------------------------ */

const monthOf = (date: string) => date.slice(0, 7);

const expensesOf = (rows: Transaction[]) => rows.filter((t) => t.amount < 0);
const incomesOf = (rows: Transaction[]) => rows.filter((t) => t.amount > 0);
const sum = (rows: Transaction[]) => rows.reduce((acc, t) => acc + Math.abs(t.amount), 0);

function groupByCategory(rows: Transaction[]) {
  const map = new Map<CategoryId, number>();
  for (const t of expensesOf(rows)) {
    map.set(t.category, (map.get(t.category) ?? 0) + Math.abs(t.amount));
  }
  return map;
}

const rub = (value: number) => `${Math.round(value).toLocaleString('ru-RU')} ₽`;

/** За сколько дней есть операции — от первой до сегодняшнего дня. */
function coverage() {
  if (state.transactions.length === 0) return 0;
  const first = state.transactions.reduce((min, t) => (t.date < min ? t.date : min), DEMO_TODAY);
  return Math.max(daysBetween(first, DEMO_TODAY), 0);
}

const currentMonth = () => monthOf(DEMO_TODAY);

function previousMonth() {
  const [year, month] = DEMO_TODAY.split('-').map(Number);
  return month === 1 ? `${year - 1}-12` : `${year}-${String(month - 1).padStart(2, '0')}`;
}

const MONTH_NAMES = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
];
const monthName = (month: string) => MONTH_NAMES[Number(month.slice(5, 7)) - 1];

/**
 * Сколько реально остаётся за месяц: доходы минус расходы последнего полного
 * месяца. Текущий месяц не берём — он ещё не закончился.
 */
function monthlyNet() {
  const rows = state.transactions.filter((t) => monthOf(t.date) === previousMonth());
  if (rows.length === 0) return null;
  return sum(incomesOf(rows)) - sum(expensesOf(rows));
}

/** Разовые траты текущего месяца по категориям — кандидаты на сокращение. */
function discretionaryByCategory() {
  const rows = state.transactions.filter(
    (t) => monthOf(t.date) === currentMonth() && t.amount < 0 && !t.isRecurring,
  );
  return [...groupByCategory(rows).entries()]
    .filter(([category]) => category !== 'other')
    .sort((a, b) => b[1] - a[1]);
}

/** Средний разовый расход в день в текущем месяце. */
function averageDailySpend() {
  const rows = state.transactions.filter(
    (t) => monthOf(t.date) === currentMonth() && t.amount < 0 && !t.isRecurring,
  );
  return Math.round(sum(rows) / Math.max(Number(DEMO_TODAY.slice(8)), 1));
}

/** Остаток к концу месяца по графику регулярных платежей и поступлений. */
function monthEndForecast() {
  const today = parseIso(DEMO_TODAY);
  const monthEnd = toIso(new Date(today.getFullYear(), today.getMonth() + 1, 0));
  const daysLeft = Math.max(daysBetween(DEMO_TODAY, monthEnd), 1);
  const events = plannedEvents(state.profile, DEMO_TODAY).filter((e) => e.date <= monthEnd);
  const expectedIncome = events.filter((e) => e.amount > 0).reduce((acc, e) => acc + e.amount, 0);
  const plannedExpenses = events.filter((e) => e.amount < 0).reduce((acc, e) => acc - e.amount, 0);
  const projected = state.profile.balance + expectedIncome - plannedExpenses;
  const safeDaily = Math.max(0, Math.floor(projected / daysLeft));
  const avgDaily = averageDailySpend();

  return {
    daysLeft,
    events,
    expectedIncome,
    plannedExpenses,
    projected,
    safeDaily,
    avgDaily,
    calculation: [
      { label: 'Текущий баланс', formula: 'остаток на счёте', value: state.profile.balance },
      { label: 'Поступления до конца месяца', formula: 'регулярные, по графику', value: expectedIncome },
      { label: 'Платежи до конца месяца', formula: 'автоплатежи по графику', value: plannedExpenses },
      { label: 'Можно тратить в день', formula: `${rub(Math.max(projected, 0))} / ${daysLeft} дн.`, value: safeDaily },
      { label: 'Обычный расход в день', formula: 'разовые траты месяца / прошедшие дни', value: avgDaily },
    ],
  };
}

/** Что отодвигает цель: крупнейшие категории разовых трат этого месяца. */
function blockersFor(remaining: number, pace: number): GoalPlan['blockers'] {
  return discretionaryByCategory()
    .slice(0, 2)
    .map(([category, amount]) => {
      const gain = pace > 0 ? Math.ceil(remaining / pace) - Math.ceil(remaining / (pace + amount / 2)) : 0;
      return {
        category,
        amount: Math.round(amount),
        hint:
          gain > 0
            ? `Если сократить вдвое, цель приблизится примерно на ${gain} мес.`
            : `Если сократить вдвое, на цель освободится около ${rub(amount / 2)} в месяц`,
      };
    });
}

/**
 * Переименование регулярной серии: все регулярные операции с прежним
 * названием и того же знака (списание или поступление) получают новое.
 */
function renameSeries(oldTitle: string, newTitle: string, direction: 'expense' | 'income') {
  state.transactions = state.transactions.map((t) =>
    t.isRecurring &&
    t.merchant === oldTitle &&
    (direction === 'expense' ? t.amount < 0 : t.amount > 0)
      ? { ...t, merchant: newTitle }
      : t,
  );
}

function seriesWarnings(found: { incomes: number; autopayments: number }) {
  const parts = [
    found.autopayments > 0 ? `автоплатежей: ${found.autopayments}` : null,
    found.incomes > 0 ? `регулярных поступлений: ${found.incomes}` : null,
  ].filter(Boolean);
  return parts.length > 0
    ? [`Найдено ${parts.join(', ')} — они добавлены в календарь. Проверьте их названия.`]
    : [];
}

/* ------------------------------------------------------------------ */
/* Обработчики                                                        */
/* ------------------------------------------------------------------ */

export const mockHandlers = {
  seedDemo(): Promise<void> {
    replaceState(demoSnapshot());
    return delay(undefined, SEED_MS);
  },

  authDemo(): Promise<Session> {
    return delay({
      token: 'demo-token',
      userId: 'demo-user',
      displayName: 'Демо-режим',
      mode: 'demo' as const,
    });
  },

  authTelegram(displayName: string): Promise<Session> {
    return delay({
      token: 'telegram-token',
      userId: 'tg-user',
      displayName,
      mode: 'telegram' as const,
    });
  },

  profile(): Promise<Profile> {
    return delay(structuredClone(state.profile));
  },

  createGoal(draft: GoalDraft): Promise<Goal> {
    const goal: Goal = { id: `g-${Date.now()}`, ...draft };
    state.profile = { ...state.profile, goals: [...state.profile.goals, goal] };
    persist();
    return delay(goal);
  },

  updateGoal(id: string, draft: GoalDraft): Promise<Goal> {
    const current = state.profile.goals.find((goal) => goal.id === id);
    if (!current) return Promise.reject(new Error('Цель не найдена'));

    const updated: Goal = { ...current, ...draft };
    state.profile = {
      ...state.profile,
      goals: state.profile.goals.map((goal) => (goal.id === id ? updated : goal)),
    };
    persist();
    return delay(updated);
  },

  deleteGoal(id: string): Promise<void> {
    state.profile = {
      ...state.profile,
      goals: state.profile.goals.filter((goal) => goal.id !== id),
    };
    persist();
    return delay(undefined);
  },

  renameTransaction(id: string, merchant: string): Promise<Transaction> {
    const current = state.transactions.find((t) => t.id === id);
    if (!current) return Promise.reject(new Error('Операция не найдена'));

    const title = merchant.trim();
    if (current.isRecurring) {
      // Регулярная операция — переименовываем всю серию вместе с правилом,
      // иначе в календаре будущие платежи останутся под старым именем.
      const direction = current.amount < 0 ? 'expense' : 'income';
      renameSeries(current.merchant, title, direction);
      state.profile = {
        ...state.profile,
        autopayments:
          direction === 'expense'
            ? state.profile.autopayments.map((a) => (a.title === current.merchant ? { ...a, title } : a))
            : state.profile.autopayments,
        incomes:
          direction === 'income'
            ? state.profile.incomes.map((i) => (i.title === current.merchant ? { ...i, title } : i))
            : state.profile.incomes,
      };
    } else {
      state.transactions = state.transactions.map((t) => (t.id === id ? { ...t, merchant: title } : t));
    }

    persist();
    return delay(state.transactions.find((t) => t.id === id)!);
  },

  createAutopayment(draft: AutopaymentDraft): Promise<Autopayment> {
    const autopayment: Autopayment = { id: `a-${Date.now()}`, ...draft, title: draft.title.trim() };
    state.profile = {
      ...state.profile,
      autopayments: [...state.profile.autopayments, autopayment],
    };
    persist();
    return delay(autopayment);
  },

  renameAutopayment(id: string, title: string): Promise<Autopayment> {
    const current = state.profile.autopayments.find((a) => a.id === id);
    if (!current) return Promise.reject(new Error('Автоплатёж не найден'));

    const updated: Autopayment = { ...current, title: title.trim() };
    renameSeries(current.title, updated.title, 'expense');
    state.profile = {
      ...state.profile,
      autopayments: state.profile.autopayments.map((a) => (a.id === id ? updated : a)),
    };
    persist();
    return delay(updated);
  },

  deleteAutopayment(id: string): Promise<void> {
    state.profile = {
      ...state.profile,
      autopayments: state.profile.autopayments.filter((a) => a.id !== id),
    };
    persist();
    return delay(undefined);
  },

  renameIncome(id: string, title: string): Promise<Income> {
    const current = state.profile.incomes.find((i) => i.id === id);
    if (!current) return Promise.reject(new Error('Поступление не найдено'));

    const updated: Income = { ...current, title: title.trim() };
    renameSeries(current.title, updated.title, 'income');
    state.profile = {
      ...state.profile,
      incomes: state.profile.incomes.map((i) => (i.id === id ? updated : i)),
    };
    persist();
    return delay(updated);
  },

  transactions(): Promise<Transaction[]> {
    return delay(
      [...state.transactions].sort((a, b) => b.date.localeCompare(a.date)),
    );
  },

  overview(): Promise<Explained<Overview>> {
    const current = monthOf(DEMO_TODAY);
    const rows = state.transactions.filter((t) => monthOf(t.date) === current);
    const prevRows = state.transactions.filter((t) => monthOf(t.date) === previousMonth());

    const totalExpense = sum(expensesOf(rows));
    const prevByCategory = groupByCategory(prevRows);

    const byCategory: CategorySlice[] = [...groupByCategory(rows).entries()]
      .map(([category, amount]) => {
        const prev = prevByCategory.get(category);
        return {
          category,
          amount,
          share: totalExpense === 0 ? 0 : amount / totalExpense,
          deltaPercent: prev ? Math.round(((amount - prev) / prev) * 100) : null,
        };
      })
      .sort((a, b) => b.amount - a.amount);

    const recurringTotal = sum(expensesOf(rows).filter((t) => t.isRecurring));

    // Аномалией считаем расход, который больше четверти всех трат месяца.
    const anomalies = expensesOf(rows)
      .filter((t) => Math.abs(t.amount) > totalExpense * 0.25)
      .map((t) => ({
        transactionId: t.id,
        reason: `Разовая трата ${Math.abs(t.amount).toLocaleString('ru-RU')} ₽ — это ${Math.round(
          (Math.abs(t.amount) / totalExpense) * 100,
        )}% расходов месяца`,
      }));

    return delay({
      result: {
        periodFrom: `${current}-01`,
        periodTo: DEMO_TODAY,
        totalIncome: sum(incomesOf(rows)),
        totalExpense,
        recurringTotal,
        byCategory,
        anomalies,
      },
      assumptions: [
        `Период: с 1 по ${Number(DEMO_TODAY.slice(8))} число, ${monthName(current)}`,
        'Категории присвоены автоматически по описанию операции',
        'Переводы между своими счетами в расходы не включены',
      ],
      calculation: [
        { label: 'Расходы за период', formula: 'сумма операций со знаком минус', value: totalExpense },
        { label: 'из них регулярные', formula: 'операции с признаком «регулярный»', value: recurringTotal },
        {
          label: 'Доля регулярных',
          formula: `${recurringTotal} ₽ / ${totalExpense} ₽`,
          value: totalExpense === 0 ? 0 : Math.round((recurringTotal / totalExpense) * 100),
        },
      ],
      sources: [],
      limitations: [
        'Категории могут быть определены неточно — их можно поправить вручную',
        `Данных за полный месяц ещё нет, сравнение с прошлым месяцем (${monthName(previousMonth())}) приблизительное`,
      ],
      dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
    });
  },

  forecast(): Promise<Explained<Forecast>> {
    const f = monthEndForecast();

    return delay({
      result: {
        daysLeft: f.daysLeft,
        expectedIncome: f.expectedIncome,
        plannedExpenses: f.plannedExpenses,
        projectedBalance: f.projected,
        safeDailySpend: f.safeDaily,
        verdict: f.projected < 0 ? 'shortfall' : f.safeDaily >= f.avgDaily ? 'ok' : 'tight',
      },
      assumptions: [
        f.events.length > 0
          ? `До конца месяца по графику: ${f.events.map((e) => `${e.title} ${rub(Math.abs(e.amount))}`).join(', ')}`
          : 'До конца месяца регулярных платежей и поступлений нет',
        'Прогноз не учитывает незапланированные крупные покупки',
      ],
      calculation: f.calculation,
      sources: [],
      limitations: [
        'Это расчёт по вашим данным, а не гарантия',
        'Продукт не даёт инвестиционных рекомендаций и не совершает операций',
      ],
      dataQuality: {
        sufficient: state.transactions.length > 0,
        missing: ['загруженные операции — хотя бы за пару недель'],
        coverageDays: coverage(),
      },
    });
  },

  runway(): Promise<Explained<Runway>> {
    const result = buildRunway(state.profile, DEMO_TODAY);
    const next = result.nextIncome;

    return delay({
      result,
      assumptions: [
        'Календарь строится от сегодняшнего дня до следующего крупного поступления',
        'Обязательные платежи стоят в те же дни месяца, что и раньше',
        'Незапланированные покупки в календарь не включены — их проверяет поле ниже',
      ],
      calculation: [
        { label: 'Текущий баланс', formula: 'остаток на счёте', value: state.profile.balance },
        {
          label: 'Дней до поступления',
          formula: next ? `${next.title} ${next.date}` : 'нет ближайшего дохода',
          value: next?.daysUntil ?? 0,
        },
        {
          label: 'Можно тратить в день',
          formula: 'свободные деньги до поступления / число дней',
          value: result.todaySafeSpend,
        },
        { label: 'Минимальный остаток на горизонте', formula: 'после всех обязательных платежей', value: result.lowestBalance },
      ],
      sources: [],
      limitations: [
        'Это расчёт по загруженным данным, а не гарантия',
        'Даты платежей взяты из регулярных операций — их можно поправить',
      ],
      dataQuality: {
        sufficient: Boolean(next) && state.profile.balance > 0,
        missing: next ? [] : ['хотя бы одно регулярное поступление с датой'],
        coverageDays: coverage(),
      },
    });
  },

  dayInsight(date: string): Promise<Explained<DayInsight>> {
    return delay(
      buildDayInsight({
        date,
        today: DEMO_TODAY,
        profile: state.profile,
        transactions: state.transactions,
      }),
    );
  },

  impulse(amount: number): Promise<Explained<ImpulseCheck>> {
    if (!Number.isFinite(amount) || amount <= 0) {
      return delay({
        result: {
          amount: 0,
          verdict: 'wait',
          hint: '',
          todaySafeSpendBefore: 0,
          todaySafeSpendAfter: 0,
          redDaysBefore: 0,
          redDaysAfter: 0,
          lowestBalanceAfter: 0,
          waitUntil: null,
          goalImpact: null,
          daysAfter: [],
        },
        assumptions: [],
        calculation: [],
        sources: [],
        limitations: [],
        dataQuality: {
          sufficient: false,
          missing: ['сумма покупки — сколько хотите потратить сегодня'],
          coverageDays: coverage(),
        },
      });
    }

    const result = buildImpulse(state.profile, DEMO_TODAY, amount, monthlyNet());

    return delay({
      result,
      assumptions: [
        'Покупка списывается сегодня, обязательные платежи остаются на своих датах',
        'Поступления — стипендия и подработка в те же дни месяца, что обычно',
      ],
      calculation: [
        { label: 'Покупка', formula: 'сумма, которую хотите потратить сегодня', value: amount },
        {
          label: 'Лимит в день до покупки',
          formula: 'свободные деньги / дни до поступления',
          value: result.todaySafeSpendBefore,
        },
        {
          label: 'Лимит в день после покупки',
          formula: 'то же после списания',
          value: result.todaySafeSpendAfter,
        },
        { label: 'Минимальный остаток после покупки', formula: 'худший день на горизонте', value: result.lowestBalanceAfter },
      ],
      sources: [],
      limitations: [
        'Расчёт не бронирует деньги и не совершает платёж',
        'Это не инвестиционная рекомендация — решение остаётся за вами',
      ],
      dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
    });
  },

  goalPlan(goalId: string): Promise<Explained<GoalPlan>> {
    const goal = state.profile.goals.find((g) => g.id === goalId);
    if (!goal) return Promise.reject(new Error('Цель не найдена'));

    // У цели без срока и с почти нулевыми накоплениями честно говорим,
    // что данных для прогноза недостаточно.
    if (!goal.deadline || goal.savedAmount < goal.targetAmount * 0.1) {
      return delay({
        result: {
          goalId,
          monthlyPace: 0,
          etaMonths: null,
          etaDate: null,
          blockers: [],
        },
        assumptions: [],
        calculation: [],
        sources: [],
        limitations: ['Без регулярных отчислений срок достижения цели рассчитать нельзя'],
        dataQuality: {
          sufficient: false,
          missing: [
            'срок, к которому нужна сумма',
            'сколько вы готовы откладывать каждый месяц',
            'история пополнений цели хотя бы за один месяц',
          ],
          coverageDays: coverage(),
        },
      });
    }

    const pace = monthlyNet();
    const prev = monthName(previousMonth());
    const remaining = goal.targetAmount - goal.savedAmount;

    if (pace === null || pace <= 0) {
      return delay({
        result: { goalId, monthlyPace: 0, etaMonths: null, etaDate: null, blockers: blockersFor(remaining, 0) },
        assumptions: [],
        calculation:
          pace === null
            ? []
            : [{ label: `Доходы минус расходы, ${prev}`, formula: 'последний полный месяц', value: Math.round(pace) }],
        sources: [],
        limitations: ['Срок не считается, пока в месяце не остаётся свободных денег'],
        dataQuality: {
          sufficient: false,
          missing: [
            pace === null
              ? 'операции хотя бы за один полный месяц — по ним видно, сколько остаётся на цель'
              : `свободные деньги на цель: за ${prev} расходы превысили доходы на ${rub(-pace)}`,
          ],
          coverageDays: coverage(),
        },
      });
    }

    const monthlyPace = Math.round(pace);
    const etaMonths = Math.ceil(remaining / monthlyPace);
    const [year, month] = DEMO_TODAY.split('-').map(Number);
    const eta = new Date(year, month - 1 + etaMonths, 1);
    const etaDate = `${eta.getFullYear()}-${String(eta.getMonth() + 1).padStart(2, '0')}-01`;

    return delay({
      result: { goalId, monthlyPace, etaMonths, etaDate, blockers: blockersFor(remaining, monthlyPace) },
      assumptions: [
        `Откладывается всё, что осталось за ${prev}: ${rub(monthlyPace)} в месяц`,
        'Доходы и регулярные платежи остаются на текущем уровне',
        'Цена цели не меняется',
      ],
      calculation: [
        { label: 'Нужно накопить', formula: `${rub(goal.targetAmount)} − ${rub(goal.savedAmount)}`, value: remaining },
        { label: 'Темп накопления', formula: `доходы минус расходы, ${prev}`, value: monthlyPace },
        { label: 'Срок, мес.', formula: `${rub(remaining)} / ${rub(monthlyPace)} в месяц`, value: etaMonths },
      ],
      sources: [],
      limitations: [
        'Расчёт не учитывает инфляцию и изменение цен',
        'Это не инвестиционная рекомендация',
      ],
      dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
    });
  },

  /**
   * Заглушка вопрос-ответ.
   *
   * Ответ зависит от сценария: на бэкенде по scenarioId будет подставляться
   * системный промпт, здесь — заготовленный ответ. В каждом сценарии есть
   * ветка «данных недостаточно»: продукт не должен выдумывать факты.
   */
  ask({ question, scenarioId }: AskRequest): Promise<Explained<AskAnswer>> {
    if (scenarioId === 'budget') return askBudget();
    if (scenarioId === 'expenses') return askExpenses();
    if (scenarioId === 'glossary') return askGlossary(question);
    if (scenarioId === 'impulse') return askImpulse(question);

    const q = question.toLowerCase();

    if (q.includes('хватит') || q.includes('до конца месяца')) {
      if (state.transactions.length === 0) return askExpenses();
      const f = monthEndForecast();
      const verdict =
        f.projected < 0
          ? `денег не хватит: после платежей не хватает ${rub(-f.projected)}. Отложите разовые покупки и проверьте, какие автоплатежи можно перенести.`
          : f.safeDaily >= f.avgDaily
            ? `денег хватит с запасом: это больше вашего обычного расхода ${rub(f.avgDaily)} в день.`
            : `впритык: обычно вы тратите ${rub(f.avgDaily)} в день, придётся ужаться.`;

      return delay({
        result: {
          text:
            `До конца месяца ${f.daysLeft} дн., на счёте ${rub(state.profile.balance)}. ` +
            (f.events.length > 0
              ? `По графику впереди: ${f.events.map((e) => `${e.title} ${e.amount > 0 ? '+' : '−'}${rub(Math.abs(e.amount))}`).join(', ')}. `
              : 'Регулярных платежей до конца месяца нет. ') +
            `Свободно ${rub(Math.max(f.projected, 0))} — ${rub(f.safeDaily)} в день, и ${verdict}`,
        },
        assumptions: ['Регулярные платежи и поступления стоят в те же числа месяца, что и раньше'],
        calculation: f.calculation,
        sources: [],
        limitations: ['Расчёт по имеющимся данным, крупные незапланированные траты не учтены'],
        dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
      });
    }

    if (q.includes('куда уход') || q.includes('расход') || q.includes('трат')) {
      return askExpenses();
    }

    if (q.includes('инфляц') || q.includes('что такое') || q.includes('объясни')) {
      return delay({
        result: {
          text: 'Инфляция — это устойчивый рост общего уровня цен, из-за которого на ту же сумму со временем можно купить меньше. Для накоплений это значит, что отложенные деньги постепенно теряют покупательную способность.',
        },
        assumptions: [],
        calculation: [],
        sources: [
          { title: 'Банк России — об инфляции', url: 'https://www.cbr.ru/hd_base/infl/' },
        ],
        limitations: ['Это объяснение термина, а не прогноз и не рекомендация'],
        dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
      });
    }

    return delay({
      result: { text: '' },
      assumptions: [],
      calculation: [],
      sources: [],
      limitations: ['Вопрос не удалось соотнести с имеющимися данными'],
      dataQuality: {
        sufficient: false,
        missing: ['уточните вопрос: о расходах, бюджете до конца месяца или о цели накопления'],
        coverageDays: coverage(),
      },
    });
  },

  history(): Promise<HistoryEntry[]> {
    // Свежие диалоги сверху.
    return delay(
      [...state.history].sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
    );
  },

  /** Upsert: диалог сохраняется целиком по мере того, как он растёт. */
  saveHistory(entry: HistoryEntry): Promise<HistoryEntry> {
    const index = state.history.findIndex((item) => item.id === entry.id);
    if (index === -1) state.history = [...state.history, entry];
    else state.history = state.history.map((item) => (item.id === entry.id ? entry : item));

    persist();
    return delay(entry, 150);
  },

  clearHistory(): Promise<void> {
    state.history = [];
    persist();
    return delay(undefined);
  },

  importTransactions(rows: Array<Omit<Transaction, 'id' | 'isRecurring'>>): Promise<ImportResult> {
    const added = rows.map((row, i) => ({
      ...row,
      id: `imp-${Date.now()}-${i}`,
      isRecurring: false,
    }));

    // Новые операции могут продолжить серию, начатую раньше, — размечаем заново.
    const marked = applySeries(
      [...state.transactions, ...added],
      state.profile.incomes,
      state.profile.autopayments,
    );
    state.transactions = marked.transactions;
    state.profile = { ...state.profile, incomes: marked.incomes, autopayments: marked.autopayments };
    persist();

    return delay({
      imported: added.length,
      rejected: [],
      warnings: [
        ...(added.length > 0
          ? ['Категории для новых операций определены автоматически — проверьте их']
          : []),
        ...seriesWarnings(marked.found),
      ],
    });
  },

  /**
   * Замена всей выписки: старые операции, правила и история диалогов
   * удаляются, регулярные платежи ищутся в новой выписке заново.
   */
  replaceDataset({ rows, balance }: DatasetReplace): Promise<ImportResult> {
    const transactions = rows.map((row, i) => ({
      ...row,
      id: `t-${Date.now()}-${i}`,
      isRecurring: false,
    }));
    const marked = applySeries(transactions, [], []);

    replaceState({
      transactions: marked.transactions,
      profile: { balance, incomes: marked.incomes, autopayments: marked.autopayments, goals: [] },
      history: [],
    });

    return delay(
      {
        imported: transactions.length,
        rejected: [],
        warnings: seriesWarnings(marked.found),
      },
      SEED_MS,
    );
  },
};

/* ------------------------------------------------------------------ */
/* Ответы по сценариям помощника                                      */
/* ------------------------------------------------------------------ */

/**
 * Планирование бюджета.
 *
 * Без чисел в сообщении план строить нечестно, поэтому сначала просим данные.
 * Это же поведение ожидается от настоящего бэкенда.
 */
function askImpulse(question: string): Promise<Explained<AskAnswer>> {
  const match = question.replace(/\s/g, '').match(/(\d+(?:[.,]\d+)?)/);
  const amount = match ? Number(match[1].replace(',', '.')) : NaN;

  if (!Number.isFinite(amount) || amount <= 0) {
    return delay({
      result: { text: '' },
      assumptions: [],
      calculation: [],
      sources: [],
      limitations: ['Без суммы покупки нельзя сказать, влезет ли она в дни до поступления'],
      dataQuality: {
        sufficient: false,
        missing: ['сумма, которую хотите потратить сегодня'],
        coverageDays: coverage(),
      },
    });
  }

  const check = buildImpulse(state.profile, DEMO_TODAY, amount, monthlyNet());

  return delay({
    result: { text: check.hint },
    assumptions: [
      'Покупка списывается сегодня',
      'Обязательные платежи остаются на своих датах',
    ],
    calculation: [
      { label: 'Покупка', formula: 'сумма из вопроса', value: amount },
      { label: 'Лимит в день после', formula: 'свободные деньги / дни до поступления', value: check.todaySafeSpendAfter },
      { label: 'Минимальный остаток', formula: 'худший день после покупки', value: check.lowestBalanceAfter },
    ],
    sources: [],
    limitations: ['Расчёт не совершает платёж и не является инвестиционной рекомендацией'],
    dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
  });
}

/**
 * Планирование бюджета по выписке: регулярный доход, автоплатежи, цель
 * и обычные разовые траты. Если в выписке нет регулярного дохода, план
 * строить не из чего — просим данные, а не придумываем их.
 */
function askBudget(): Promise<Explained<AskAnswer>> {
  const { incomes, autopayments, goals } = state.profile;
  const income = incomes.reduce((acc, i) => acc + i.amount, 0);

  if (income === 0) {
    return delay({
      result: { text: '' },
      assumptions: [],
      calculation: [],
      sources: [],
      limitations: ['План на месяц нельзя построить, не зная регулярного дохода'],
      dataQuality: {
        sufficient: false,
        missing: [
          'регулярный доход: в выписке нет поступлений, которые повторяются каждый месяц',
          'загрузите выписку хотя бы за два месяца или добавьте доход с датой поступления',
        ],
        coverageDays: coverage(),
      },
    });
  }

  const mandatory = autopayments.reduce((acc, a) => acc + a.amount, 0);
  const goal = goals.find((g) => g.deadline && g.savedAmount < g.targetAmount);
  const monthsLeft = goal ? Math.max(1, Math.round(daysBetween(DEMO_TODAY, goal.deadline!) / 30)) : 0;
  const savings = goal
    ? Math.ceil((goal.targetAmount - goal.savedAmount) / monthsLeft / 100) * 100
    : Math.round((income * 0.1) / 100) * 100;
  const free = income - mandatory - savings;
  const daily = Math.max(0, Math.floor(free / 30));

  // Обычные разовые траты — по последнему полному месяцу.
  const prevRows = state.transactions.filter((t) => monthOf(t.date) === previousMonth());
  const usual = sum(expensesOf(prevRows).filter((t) => !t.isRecurring));
  const irregular = sum(incomesOf(prevRows).filter((t) => !t.isRecurring));
  const top = discretionaryByCategory()[0];

  const parts = [
    `Регулярный доход — ${rub(income)} в месяц (${incomes.map((i) => i.title).join(', ')}).`,
    `Автоплатежи забирают ${rub(mandatory)}.`,
    goal
      ? `Чтобы собрать «${goal.title}» к сроку, нужно откладывать ${rub(savings)} в месяц.`
      : `Цели со сроком нет — предлагаю откладывать 10 % дохода, ${rub(savings)}.`,
    free > 0
      ? `На жизнь остаётся ${rub(free)} — ${rub(daily)} в день.`
      : 'После этого на жизнь не остаётся ничего: план в таком виде не сходится, срок цели стоит сдвинуть.',
  ];
  if (free > 0 && usual > free) {
    parts.push(
      `Сейчас разовые траты — около ${rub(usual)} в месяц, придётся сократить их на ${rub(usual - free)}` +
        (top ? `; больше всего уходит на «${CATEGORY_LABELS[top[0]]}» — ${rub(top[1])} в этом месяце.` : '.'),
    );
  } else if (free > 0) {
    parts.push(`Это не меньше ваших обычных разовых трат (${rub(usual)} в месяц), так что план выполним.`);
  }
  if (irregular > 0) {
    parts.push(
      `Нерегулярные поступления (${rub(irregular)} за прошлый месяц) в план не заложены — их можно сразу отправлять на цель.`,
    );
  }

  return delay({
    result: { text: parts.join(' ') },
    assumptions: [
      'Доход — только поступления, которые повторяются каждый месяц',
      'Накопления откладываются сразу после поступления, а не из остатка',
      goal ? `До срока цели ${monthsLeft} мес.` : 'Цель без срока — взят ориентир 10 % дохода',
    ],
    calculation: [
      {
        label: 'Регулярный доход',
        formula: incomes.map((i) => `${i.title} ${rub(i.amount)}`).join(' + '),
        value: income,
      },
      { label: 'Автоплатежи', formula: `${autopayments.length} платежей в месяц`, value: mandatory },
      {
        label: 'На цель',
        formula: goal ? `${rub(goal.targetAmount - goal.savedAmount)} / ${monthsLeft} мес.` : '10 % дохода',
        value: savings,
      },
      { label: 'Свободно на жизнь', formula: `${rub(income)} − ${rub(mandatory)} − ${rub(savings)}`, value: free },
      { label: 'Дневной лимит', formula: `${rub(Math.max(free, 0))} / 30 дн.`, value: daily },
    ],
    sources: [],
    limitations: [
      'План построен по загруженной выписке, другие счета не учтены',
      'Это не инвестиционная рекомендация: решение остаётся за вами',
    ],
    dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
  });
}

/** Анализ трат: считается по загруженным операциям. */
function askExpenses(): Promise<Explained<AskAnswer>> {
  const current = currentMonth();
  const rows = state.transactions.filter((t) => monthOf(t.date) === current);
  const total = sum(expensesOf(rows));

  if (rows.length === 0 || total === 0) {
    return delay({
      result: { text: '' },
      assumptions: [],
      calculation: [],
      sources: [],
      limitations: ['Без операций разбор расходов построить не на чем'],
      dataQuality: {
        sufficient: false,
        missing: ['загрузите выгрузку операций на вкладке «Данные» — хотя бы за один месяц'],
        coverageDays: 0,
      },
    });
  }

  const recurring = expensesOf(rows).filter((t) => t.isRecurring);
  const mandatory = sum(recurring);
  const categories = [...groupByCategory(rows).entries()].sort((a, b) => b[1] - a[1]);
  // «Прочее» — это переводы людям и нераспознанное; как «главная статья» оно ничего не говорит.
  const [topCategory, topAmount] = categories.find(([category]) => category !== 'other') ?? categories[0];
  const otherAmount = groupByCategory(rows).get('other') ?? 0;
  const prevTotal = sum(expensesOf(state.transactions.filter((t) => monthOf(t.date) === previousMonth())));

  const largestOneOff = expensesOf(rows)
    .filter((t) => !t.isRecurring)
    .sort((a, b) => a.amount - b.amount)[0];
  const anomaly = largestOneOff && Math.abs(largestOneOff.amount) > total * 0.25 ? largestOneOff : null;

  const cuts = discretionaryByCategory().slice(0, 2);
  const cutSavings = cuts.reduce((acc, [, amount]) => acc + amount / 2, 0);

  const parts = [
    `С 1 по ${parseIso(DEMO_TODAY).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })} расходы составили ${rub(total)}.`,
    `Больше всего — «${CATEGORY_LABELS[topCategory]}»: ${rub(topAmount)}, это ${Math.round((topAmount / total) * 100)} % трат.`,
    ...(topCategory !== 'other' && otherAmount > 0
      ? [`Ещё ${rub(otherAmount)} — переводы и прочие операции.`]
      : []),
    recurring.length > 0
      ? `Регулярные платежи — ${rub(mandatory)} (${recurring.length} шт.), остальное — разовые траты.`
      : 'Регулярных платежей в этом месяце не найдено — все траты разовые.',
  ];
  if (anomaly) {
    parts.push(
      `Выделяется разовая трата «${anomaly.merchant}» на ${rub(Math.abs(anomaly.amount))} — ${Math.round((Math.abs(anomaly.amount) / total) * 100)} % расходов месяца.`,
    );
  }
  if (cuts.length > 0) {
    parts.push(
      `Проще всего сократить ${cuts.map(([category, amount]) => `«${CATEGORY_LABELS[category]}» (${rub(amount)})`).join(' и ')}: если урезать вдвое, освободится около ${rub(cutSavings)} в месяц.`,
    );
  }
  if (prevTotal > 0) {
    parts.push(`За ${monthName(previousMonth())} целиком расходы были ${rub(prevTotal)}.`);
  }

  return delay({
    result: { text: parts.join(' ') },
    assumptions: [
      `Период: ${monthName(current)} по загруженным операциям`,
      'Категории присвоены по описанию операции',
      'Регулярными считаются платежи, которые повторяются каждый месяц',
    ],
    calculation: [
      { label: 'Всего расходов', formula: 'сумма операций со знаком минус', value: Math.round(total) },
      { label: 'Регулярные платежи', formula: 'повторяются каждый месяц', value: Math.round(mandatory) },
      { label: 'Разовые траты', formula: `${rub(total)} − ${rub(mandatory)}`, value: Math.round(total - mandatory) },
      ...(cuts.length > 0
        ? [
            {
              label: 'Можно освободить',
              formula: 'половина двух крупнейших категорий разовых трат',
              value: Math.round(cutSavings),
            },
          ]
        : []),
    ],
    sources: [],
    limitations: [
      'Категоризация может быть неточной — переименуйте операцию в календаре, если описание непонятное',
      'Переводы людям попадают в «Прочее» и в сокращения не предлагаются',
    ],
    dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
  });
}

/** Подписи категорий для текстовых ответов мока. */
const CATEGORY_LABELS: Record<CategoryId, string> = {
  food: 'Еда',
  transport: 'Транспорт',
  subscriptions: 'Подписки и связь',
  entertainment: 'Развлечения',
  health: 'Здоровье',
  education: 'Образование',
  rent: 'Жильё',
  other: 'Прочее',
};

/**
 * Справочник терминов.
 *
 * Отвечаем только по тем терминам, для которых есть проверенный источник.
 * На незнакомый термин честно сообщаем, что источника нет.
 */
const GLOSSARY: Array<{ keys: string[]; text: string; source: Source }> = [
  {
    keys: ['инфляц'],
    text:
      'Инфляция — устойчивый рост общего уровня цен, из-за которого на ту же сумму со временем ' +
      'можно купить меньше. Для накоплений это значит, что отложенные деньги постепенно теряют ' +
      'покупательную способность: если вы держите 21 000 ₽ на цель, а цены за год вырастут на 8 %, ' +
      'то в товарах эта сумма будет стоить примерно 19 400 ₽. Поэтому для целей со сроком больше ' +
      'года сумму обычно закладывают с запасом.',
    source: { title: 'Банк России — инфляция и её измерение', url: 'https://www.cbr.ru/hd_base/infl/' },
  },
  {
    keys: ['вклад', 'депозит'],
    text:
      'Вклад — это передача денег банку на срок под заранее известный процент. Банк платит доход, ' +
      'а вы не можете свободно пользоваться суммой до конца срока без потери процентов. Вклады ' +
      'в банках-участниках системы страхования застрахованы государством в пределах ' +
      'установленного лимита.',
    source: {
      title: 'Агентство по страхованию вкладов — о страховании',
      url: 'https://www.asv.org.ru/insurance/',
    },
  },
  {
    keys: ['кредитн', 'кредитная история', 'рейтинг'],
    text:
      'Кредитная история — запись о том, какие кредиты и займы вы брали и как их возвращали. ' +
      'Её ведут кредитные бюро, а банки смотрят на неё, когда решают, давать ли вам кредит. ' +
      'Просрочки остаются в истории на годы, поэтому даже небольшой невозвращённый вовремя ' +
      'платёж влияет на будущие условия.',
    source: {
      title: 'Банк России — кредитная история',
      url: 'https://www.cbr.ru/faq/subekt_kredit/',
    },
  },
];

function askGlossary(question: string): Promise<Explained<AskAnswer>> {
  const q = question.toLowerCase();
  const entry = GLOSSARY.find((item) => item.keys.some((key) => q.includes(key)));

  if (!entry) {
    return delay({
      result: { text: '' },
      assumptions: [],
      calculation: [],
      sources: [],
      limitations: [
        'Я отвечаю только по терминам, для которых есть проверенный источник, и не придумываю определения',
      ],
      dataQuality: {
        sufficient: false,
        missing: [
          'уточните термин — в справочнике пока есть «инфляция», «вклад» и «кредитная история»',
          'если термин из договора, приведите формулировку целиком',
        ],
        coverageDays: coverage(),
      },
    });
  }

  return delay({
    result: { text: entry.text },
    assumptions: [],
    calculation: [],
    sources: [entry.source],
    limitations: [
      'Это объяснение термина, а не прогноз и не инвестиционная рекомендация',
      'Условия конкретного банка или договора могут отличаться — сверяйтесь с документом',
    ],
    dataQuality: { sufficient: true, missing: [], coverageDays: coverage() },
  });
}
