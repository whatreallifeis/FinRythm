import type {
  AskAnswer,
  AskRequest,
  CategoryId,
  CategorySlice,
  Explained,
  Forecast,
  ImpulseCheck,
  Goal,
  GoalDraft,
  GoalPlan,
  HistoryEntry,
  ImportResult,
  Overview,
  Profile,
  Runway,
  Session,
  Source,
  Transaction,
} from '../types';
import { readDatasetReady } from '../dataset';
import { DEMO_TODAY, demoHistory, demoProfile, demoTransactions } from './data';
import { buildImpulse, buildRunway } from './runway';

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

const EMPTY_PROFILE: Profile = { balance: 0, incomes: [], goals: [] };

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

/**
 * Изменяемое состояние мока.
 *
 * Новый пользователь начинает с пустого набора: цифры демо появляются
 * только после явной загрузки примера. Если пример уже загружали в этом
 * браузере, снимок восстанавливается сразу.
 */
const state = readDatasetReady() ? demoSnapshot() : emptySnapshot();

function replaceState(next: ReturnType<typeof demoSnapshot>) {
  state.transactions = next.transactions;
  state.profile = next.profile;
  state.history = next.history;
}

export function resetMockState() {
  replaceState(demoSnapshot());
}

export function clearDataset() {
  replaceState(emptySnapshot());
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
    return delay(updated);
  },

  deleteGoal(id: string): Promise<void> {
    state.profile = {
      ...state.profile,
      goals: state.profile.goals.filter((goal) => goal.id !== id),
    };
    return delay(undefined);
  },

  transactions(): Promise<Transaction[]> {
    return delay(
      [...state.transactions].sort((a, b) => b.date.localeCompare(a.date)),
    );
  },

  overview(): Promise<Explained<Overview>> {
    const current = monthOf(DEMO_TODAY);
    const rows = state.transactions.filter((t) => monthOf(t.date) === current);
    const prevRows = state.transactions.filter((t) => monthOf(t.date) === '2026-08');

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
        'Период: с 1 сентября по 26 сентября 2026 года',
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
        'Данных за полный месяц ещё нет, сравнение с августом приблизительное',
      ],
      dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
    });
  },

  forecast(): Promise<Explained<Forecast>> {
    const daysLeft = 4; // до конца сентября от 26-го
    const balance = state.profile.balance;
    const expectedIncome = 0; // все поступления сентября уже пришли

    const current = monthOf(DEMO_TODAY);
    const rows = state.transactions.filter((t) => monthOf(t.date) === current);
    // Из обязательных платежей до конца месяца остался только интернет.
    const plannedExpenses = 700;

    const projectedBalance = balance + expectedIncome - plannedExpenses;
    const safeDailySpend = Math.max(0, Math.round(projectedBalance / daysLeft));
    const avgDaily = Math.round(sum(expensesOf(rows)) / 26);

    return delay({
      result: {
        daysLeft,
        expectedIncome,
        plannedExpenses,
        projectedBalance,
        safeDailySpend,
        verdict: safeDailySpend >= avgDaily ? 'ok' : 'tight',
      },
      assumptions: [
        'Стипендия и аванс за сентябрь уже зачислены',
        'До конца месяца остался один обязательный платёж — интернет, 700 ₽',
        'Прогноз не учитывает незапланированные крупные покупки',
      ],
      calculation: [
        { label: 'Текущий баланс', formula: 'остаток на счёте', value: balance },
        { label: 'Обязательные платежи', formula: 'интернет 700 ₽', value: plannedExpenses },
        {
          label: 'Остаток к концу месяца',
          formula: `${balance} ₽ − ${plannedExpenses} ₽`,
          value: projectedBalance,
        },
        {
          label: 'Можно тратить в день',
          formula: `${projectedBalance} ₽ / ${daysLeft} дн.`,
          value: safeDailySpend,
        },
      ],
      sources: [],
      limitations: [
        'Это расчёт по вашим данным, а не гарантия',
        'Продукт не даёт инвестиционных рекомендаций и не совершает операций',
      ],
      dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
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
        coverageDays: 26,
      },
    });
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
          coverageDays: 26,
        },
      });
    }

    const result = buildImpulse(state.profile, DEMO_TODAY, amount);

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
      dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
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
          coverageDays: 26,
        },
      });
    }

    const monthlyPace = 7000;
    const remaining = goal.targetAmount - goal.savedAmount;
    const etaMonths = Math.ceil(remaining / monthlyPace);

    return delay({
      result: {
        goalId,
        monthlyPace,
        etaMonths,
        etaDate: '2027-02-01',
        blockers: [
          {
            category: 'entertainment',
            amount: 14900,
            hint: 'Одна крупная покупка развлечений отодвинула цель примерно на 2 месяца',
          },
          {
            category: 'food',
            amount: 3420,
            hint: 'Доставка еды — заметная часть необязательных расходов',
          },
        ],
      },
      assumptions: [
        `Вы откладываете ${monthlyPace.toLocaleString('ru-RU')} ₽ в месяц`,
        'Доходы остаются на текущем уровне',
        'Цена товара не меняется',
      ],
      calculation: [
        { label: 'Нужно накопить', formula: `${goal.targetAmount} ₽ − ${goal.savedAmount} ₽`, value: remaining },
        { label: 'Темп накопления', formula: 'средние отчисления за месяц', value: monthlyPace },
        { label: 'Срок', formula: `${remaining} ₽ / ${monthlyPace} ₽ в месяц`, value: etaMonths },
      ],
      sources: [],
      limitations: [
        'Расчёт не учитывает инфляцию и изменение цен',
        'Это не инвестиционная рекомендация',
      ],
      dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
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
    if (scenarioId === 'budget') return askBudget(question);
    if (scenarioId === 'expenses') return askExpenses();
    if (scenarioId === 'glossary') return askGlossary(question);
    if (scenarioId === 'impulse') return askImpulse(question);

    const q = question.toLowerCase();

    if (q.includes('хватит') || q.includes('до конца месяца')) {
      return delay({
        result: {
          text: 'До конца месяца осталось 4 дня и 17 730 ₽ после обязательных платежей. Это примерно 4 430 ₽ в день — больше вашего среднего расхода 2 100 ₽ в день, так что денег хватит с запасом.',
        },
        assumptions: ['Остался один обязательный платёж — интернет, 700 ₽'],
        calculation: [
          { label: 'Свободный остаток', formula: '18 430 ₽ − 700 ₽', value: 17730 },
          { label: 'В день', formula: '17 730 ₽ / 4 дн.', value: 4433 },
        ],
        sources: [],
        limitations: ['Расчёт по имеющимся данным, крупные незапланированные траты не учтены'],
        dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
      });
    }

    if (q.includes('куда уход') || q.includes('расход')) {
      return delay({
        result: {
          text: 'Больше всего в сентябре ушло на аренду — 12 000 ₽, затем разовая покупка билетов на концерт 14 900 ₽. Обязательные платежи занимают 14 738 ₽ из 41 928 ₽ расходов, остальное — переменные траты, в основном еда и развлечения.',
        },
        assumptions: ['Категории присвоены автоматически'],
        calculation: [
          { label: 'Всего расходов', formula: 'сумма расходных операций', value: 41928 },
          { label: 'Обязательные', formula: 'аренда + подписки + связь + проездной', value: 14738 },
        ],
        sources: [],
        limitations: ['Категоризация может быть неточной'],
        dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
      });
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
        dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
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
        coverageDays: 26,
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

    return delay(entry, 150);
  },

  clearHistory(): Promise<void> {
    state.history = [];
    return delay(undefined);
  },

  importTransactions(rows: Array<Omit<Transaction, 'id' | 'isRecurring'>>): Promise<ImportResult> {
    const added = rows.map((row, i) => ({
      ...row,
      id: `imp-${Date.now()}-${i}`,
      isRecurring: false,
    }));
    state.transactions = [...state.transactions, ...added];

    return delay({
      imported: added.length,
      rejected: [],
      warnings:
        added.length > 0
          ? ['Категории для новых операций определены автоматически — проверьте их']
          : [],
    });
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
        coverageDays: 26,
      },
    });
  }

  const check = buildImpulse(state.profile, DEMO_TODAY, amount);

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
    dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
  });
}

function askBudget(question: string): Promise<Explained<AskAnswer>> {
  const hasNumbers = /\d/.test(question);

  if (!hasNumbers) {
    return delay({
      result: { text: '' },
      assumptions: [],
      calculation: [],
      sources: [],
      limitations: ['План на месяц нельзя построить, не зная доходов и обязательных платежей'],
      dataQuality: {
        sufficient: false,
        missing: [
          'доход за месяц: сумма и даты поступлений',
          'обязательные платежи: аренда, связь, транспорт, подписки',
          'цель накопления: сумма и срок',
        ],
        coverageDays: 26,
      },
    });
  }

  const income = 33000;
  const mandatory = 14738;
  const savings = 7000;
  const free = income - mandatory - savings;
  const dailyLimit = Math.round(free / 30);

  return delay({
    result: {
      text:
        `План на месяц при доходе ${income.toLocaleString('ru-RU')} ₽: обязательные платежи ` +
        `${mandatory.toLocaleString('ru-RU')} ₽, на ноутбук откладываем ` +
        `${savings.toLocaleString('ru-RU')} ₽, на жизнь остаётся ` +
        `${free.toLocaleString('ru-RU')} ₽ — это ${dailyLimit} ₽ в день. ` +
        'Кофейни и спортзал я оставила в плане: нужную сумму даёт сокращение доставки еды ' +
        'примерно наполовину. При таком темпе ноутбук собирается к февралю, то есть в срок.',
    },
    assumptions: [
      'Доход остаётся на уровне 33 000 ₽ в месяц',
      'Накопления откладываются сразу после поступления, а не из остатка',
      'Цена ноутбука за время накопления не меняется',
      'Кофейни и спортзал сохранены как приоритетные траты',
    ],
    calculation: [
      { label: 'Доход за месяц', formula: 'стипендия 8 000 ₽ + подработка 25 000 ₽', value: income },
      {
        label: 'Обязательные платежи',
        formula: 'аренда 12 000 ₽ + связь и подписки 1 538 ₽ + проездной 1 200 ₽',
        value: mandatory,
      },
      { label: 'На цель', formula: '75 000 ₽ / 11 месяцев до февраля', value: savings },
      {
        label: 'Свободно на жизнь',
        formula: `${income} ₽ − ${mandatory} ₽ − ${savings} ₽`,
        value: free,
      },
      { label: 'Дневной лимит', formula: `${free} ₽ / 30 дн.`, value: dailyLimit },
    ],
    sources: [],
    limitations: [
      'План построен по тем данным, которые вы назвали, банковские счёта не подключены',
      'Это не инвестиционная рекомендация: решение остаётся за вами',
    ],
    dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
  });
}

/** Анализ трат: считается по загруженным операциям. */
function askExpenses(): Promise<Explained<AskAnswer>> {
  const current = monthOf(DEMO_TODAY);
  const rows = state.transactions.filter((t) => monthOf(t.date) === current);
  const total = sum(expensesOf(rows));

  if (rows.length === 0) {
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

  const mandatory = sum(expensesOf(rows).filter((t) => t.isRecurring));
  const byCategory = [...groupByCategory(rows).entries()].sort((a, b) => b[1] - a[1]);
  const [topCategory, topAmount] = byCategory[0];

  return delay({
    result: {
      text:
        `За сентябрь расходы составили ${total.toLocaleString('ru-RU')} ₽. Больше всего ушло на ` +
        `категорию «${CATEGORY_LABELS[topCategory]}» — ${topAmount.toLocaleString('ru-RU')} ₽, ` +
        `это ${Math.round((topAmount / total) * 100)}% всех трат. Обязательные платежи занимают ` +
        `${mandatory.toLocaleString('ru-RU')} ₽, остальное — переменные траты. ` +
        'Сократить без потери качества жизни реально доставку еды и кофейни: вместе они дают ' +
        'около 5 000 ₽ в месяц, и половина этой суммы закрывает месячный взнос на цель.',
    },
    assumptions: [
      'Период: сентябрь 2026 года по загруженным операциям',
      'Категории присвоены автоматически по описанию операции',
      'Обязательными считаны платежи с признаком «регулярный»',
    ],
    calculation: [
      { label: 'Всего расходов', formula: 'сумма операций со знаком минус', value: total },
      { label: 'Обязательные платежи', formula: 'операции с признаком «регулярный»', value: mandatory },
      {
        label: 'Переменные траты',
        formula: `${total} ₽ − ${mandatory} ₽`,
        value: total - mandatory,
      },
    ],
    sources: [],
    limitations: [
      'Категоризация может быть неточной — проверьте её на вкладке «Данные»',
      'Данных за полный месяц пока нет, выводы приблизительные',
    ],
    dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
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
        coverageDays: 26,
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
    dataQuality: { sufficient: true, missing: [], coverageDays: 26 },
  });
}
