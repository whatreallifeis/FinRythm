import type { HistoryEntry, Profile, Transaction } from '../types';

/**
 * Синтетические данные для UI-разработки и демо-режима.
 *
 * Реальные банковские данные использовать нельзя по условиям кейса, поэтому
 * этот датасет — и заглушка для фронта, и демо для проверяющего.
 *
 * Сегмент: студент со стипендией и подработкой, сентябрь 2026.
 */

export const DEMO_TODAY = '2026-09-26';

export const demoTransactions: Transaction[] = [
  // --- сентябрь 2026 (текущий период) ---
  { id: 't-901', date: '2026-09-01', amount: -12000, category: 'rent', merchant: 'Аренда комнаты', isRecurring: true },
  { id: 't-902', date: '2026-09-02', amount: -299, category: 'subscriptions', merchant: 'Музыкальная подписка', isRecurring: true },
  { id: 't-903', date: '2026-09-02', amount: -649, category: 'subscriptions', merchant: 'Онлайн-кинотеатр', isRecurring: true },
  { id: 't-904', date: '2026-09-03', amount: -1450, category: 'food', merchant: 'Супермаркет', isRecurring: false },
  { id: 't-905', date: '2026-09-04', amount: -1200, category: 'transport', merchant: 'Проездной', isRecurring: true },
  { id: 't-906', date: '2026-09-05', amount: 8000, category: 'other', merchant: 'Стипендия', isRecurring: true },
  { id: 't-907', date: '2026-09-06', amount: -780, category: 'entertainment', merchant: 'Кофейня', isRecurring: false },
  { id: 't-908', date: '2026-09-08', amount: -2300, category: 'food', merchant: 'Доставка еды', isRecurring: false },
  { id: 't-909', date: '2026-09-10', amount: 25000, category: 'other', merchant: 'Подработка, аванс', isRecurring: false },
  { id: 't-910', date: '2026-09-11', amount: -450, category: 'health', merchant: 'Аптека', isRecurring: false },
  { id: 't-911', date: '2026-09-13', amount: -14900, category: 'entertainment', merchant: 'Концертные билеты', isRecurring: false },
  { id: 't-912', date: '2026-09-15', amount: -1890, category: 'food', merchant: 'Супермаркет', isRecurring: false },
  { id: 't-913', date: '2026-09-17', amount: -590, category: 'subscriptions', merchant: 'Мобильная связь', isRecurring: true },
  { id: 't-914', date: '2026-09-19', amount: -3200, category: 'education', merchant: 'Онлайн-курс', isRecurring: false },
  { id: 't-915', date: '2026-09-21', amount: -1120, category: 'food', merchant: 'Доставка еды', isRecurring: false },
  { id: 't-916', date: '2026-09-23', amount: -860, category: 'entertainment', merchant: 'Кофейня', isRecurring: false },
  { id: 't-917', date: '2026-09-25', amount: -240, category: 'transport', merchant: 'Такси', isRecurring: false },

  // --- август 2026 (нужен, чтобы считать динамику «к прошлому месяцу») ---
  { id: 't-801', date: '2026-08-01', amount: -12000, category: 'rent', merchant: 'Аренда комнаты', isRecurring: true },
  { id: 't-802', date: '2026-08-02', amount: -299, category: 'subscriptions', merchant: 'Музыкальная подписка', isRecurring: true },
  { id: 't-803', date: '2026-08-05', amount: 8000, category: 'other', merchant: 'Стипендия', isRecurring: true },
  { id: 't-804', date: '2026-08-07', amount: -4300, category: 'food', merchant: 'Супермаркет', isRecurring: false },
  { id: 't-805', date: '2026-08-12', amount: 22000, category: 'other', merchant: 'Подработка', isRecurring: false },
  { id: 't-806', date: '2026-08-14', amount: -1600, category: 'entertainment', merchant: 'Кинотеатр', isRecurring: false },
  { id: 't-807', date: '2026-08-20', amount: -1200, category: 'transport', merchant: 'Проездной', isRecurring: true },
  { id: 't-808', date: '2026-08-26', amount: -2400, category: 'food', merchant: 'Доставка еды', isRecurring: false },
];

export const demoProfile: Profile = {
  balance: 18430,
  incomes: [
    { id: 'i-1', title: 'Стипендия', amount: 8000, dayOfMonth: 5 },
    { id: 'i-2', title: 'Подработка', amount: 25000, dayOfMonth: 10 },
  ],
  // Названия совпадают с описаниями в выписке — по ним справка находит историю платежа.
  autopayments: [
    { id: 'a-1', title: 'Аренда комнаты', amount: 12000, dayOfMonth: 1, category: 'rent' },
    { id: 'a-2', title: 'Музыкальная подписка', amount: 299, dayOfMonth: 2, category: 'subscriptions' },
    { id: 'a-3', title: 'Онлайн-кинотеатр', amount: 649, dayOfMonth: 2, category: 'subscriptions' },
    { id: 'a-4', title: 'Проездной', amount: 1200, dayOfMonth: 4, category: 'transport' },
    { id: 'a-5', title: 'Мобильная связь', amount: 590, dayOfMonth: 17, category: 'subscriptions' },
    { id: 'a-6', title: 'Интернет', amount: 700, dayOfMonth: 28, category: 'subscriptions' },
  ],
  goals: [
    {
      id: 'g-1',
      title: 'Ноутбук для учёбы',
      targetAmount: 75000,
      savedAmount: 21000,
      deadline: '2027-02-01',
    },
    {
      // Вторая цель намеренно без срока: на ней проверяется состояние
      // «данных недостаточно» — продукт не должен выдумывать прогноз.
      id: 'g-2',
      title: 'Финансовая подушка',
      targetAmount: 60000,
      savedAmount: 3000,
      deadline: null,
    },
  ],
};

/**
 * Пара сохранённых диалогов, чтобы история не была пустой при первом открытии.
 *
 * Второй пример намеренно закончился отказом: в истории должно быть видно и то,
 * где помощнику не хватило данных, а не только удачные ответы.
 */
export const demoHistory: HistoryEntry[] = [
  {
    id: 'h-1',
    scenarioId: 'budget',
    title: 'Стипендия 8 000 ₽ и подработка 25 000 ₽, хочу накопить на ноутбук',
    createdAt: '2026-09-24T19:12:00',
    messages: [
      {
        role: 'user',
        text: 'Стипендия 8 000 ₽ приходит 5-го, подработка 25 000 ₽ — 10-го. Аренда 12 000 ₽, связь и подписки около 1 500 ₽. Хочу накопить 75 000 ₽ на ноутбук к февралю.',
      },
      {
        role: 'assistant',
        answer: {
          result: {
            text: 'План на месяц при доходе 33 000 ₽: обязательные платежи 14 738 ₽, на ноутбук откладываем 7 000 ₽, на жизнь остаётся 11 262 ₽ — это 375 ₽ в день. При таком темпе ноутбук собирается к февралю, то есть в срок.',
          },
          assumptions: [
            'Доход остаётся на уровне 33 000 ₽ в месяц',
            'Накопления откладываются сразу после поступления, а не из остатка',
          ],
          calculation: [
            { label: 'Доход за месяц', formula: 'стипендия 8 000 ₽ + подработка 25 000 ₽', value: 33000 },
            { label: 'Обязательные платежи', formula: 'аренда 12 000 ₽ + связь и подписки 1 538 ₽ + проездной 1 200 ₽', value: 14738 },
            { label: 'На цель', formula: '75 000 ₽ / 11 месяцев до февраля', value: 7000 },
            { label: 'Дневной лимит', formula: '11 262 ₽ / 30 дн.', value: 375 },
          ],
          sources: [],
          limitations: [
            'План построен по названным вами данным, банковские счёта не подключены',
            'Это не инвестиционная рекомендация: решение остаётся за вами',
          ],
          dataQuality: { sufficient: true, missing: [], coverageDays: 24 },
        },
      },
    ],
  },
  {
    id: 'h-2',
    scenarioId: 'glossary',
    title: 'Что такое эскроу-счёт?',
    createdAt: '2026-09-22T11:40:00',
    messages: [
      { role: 'user', text: 'Что такое эскроу-счёт? Встретила в договоре.' },
      {
        role: 'assistant',
        answer: {
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
            coverageDays: 22,
          },
        },
      },
    ],
  },
];

/** Пример CSV, который можно вставить на экране импорта. */
export const demoCsv = `date,amount,category,merchant
2026-09-27,-540,food,Супермаркет
2026-09-27,-99,subscriptions,Облачное хранилище
2026-09-28,-1500,transport,Такси в аэропорт`;

/** Тот же пример, но с ошибками — для проверки разбора некорректного ввода. */
export const demoCsvWithErrors = `date,amount,category,merchant
2026-09-27,-540,food,Супермаркет
27.09.2026,-99,subscriptions,Облачное хранилище
2026-09-28,abc,transport,Такси
2026-09-29,-300,food,`;
