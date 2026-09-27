import type { Autopayment, DayInsight, DayOperation, Explained, Profile, Transaction } from '../types';
import { addDays, buildRunway, daysBetween, occursOn, parseIso } from './runway';

/**
 * Справка по одному дню календаря на главной.
 *
 * Числа считает код, текст справки на бэкенде пишет модель по этим числам.
 * Здесь текст собирается шаблоном — так же, как остальные ответы мока.
 */

const money = (value: number) => `${Math.abs(value).toLocaleString('ru-RU')} ₽`;
const human = (iso: string) =>
  parseIso(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });

function operationsOf(date: string, today: string, profile: Profile, rows: Transaction[]): DayOperation[] {
  const actual = rows
    .filter((t) => t.date === date)
    .map((t) => ({
      ref: { kind: 'transaction' as const, id: t.id },
      title: t.merchant,
      amount: t.amount,
      category: t.category,
      isRecurring: t.isRecurring,
    }));

  if (date <= today) return actual;

  // Будущий день: в план попадают только регулярные платежи и поступления.
  const bills = profile.autopayments
    .filter((bill) => occursOn(bill.dayOfMonth, date))
    .map((bill) => ({
      ref: { kind: 'autopayment' as const, id: bill.id },
      title: bill.title,
      amount: -bill.amount,
      category: bill.category,
      isRecurring: true,
    }));
  const incomes = profile.incomes
    .filter((income) => occursOn(income.dayOfMonth, date))
    .map((income) => ({
      ref: { kind: 'income' as const, id: income.id },
      title: income.title,
      amount: income.amount,
      category: 'other' as const,
      isRecurring: true,
    }));

  return [...incomes, ...bills];
}

/** Средние необязательные траты в этот же день недели за всю историю до сегодня. */
function typicalFor(date: string, today: string, rows: Transaction[]) {
  if (rows.length === 0) return null;

  const weekday = parseIso(date).getDay();
  const first = rows.reduce((min, t) => (t.date < min ? t.date : min), today);

  let sameDays = 0;
  for (let d = first; d < today; d = addDays(d, 1)) {
    if (parseIso(d).getDay() === weekday) sameDays += 1;
  }
  if (sameDays < 2) return null;

  const spent = rows
    .filter((t) => t.amount < 0 && !t.isRecurring && t.date < today && parseIso(t.date).getDay() === weekday)
    .reduce((acc, t) => acc + Math.abs(t.amount), 0);

  return { value: Math.round(spent / sameDays / 10) * 10, spent, sameDays };
}

function describeExpense(
  op: DayOperation,
  date: string,
  today: string,
  rows: Transaction[],
  autopayments: Autopayment[],
) {
  const history = rows
    .filter((t) => t.isRecurring && t.amount < 0 && t.merchant === op.title && t.date < date)
    .sort((a, b) => a.date.localeCompare(b.date));
  const amount = Math.abs(op.amount);
  const parts: string[] = [];

  if (history.length === 0) {
    parts.push(
      date < today
        ? `${op.title} — ${money(amount)}, регулярный платёж. Это первое его списание в загруженной выписке.`
        : `${op.title} — ${money(amount)}, регулярный платёж ${parseIso(date).getDate()}-го числа. В выписке его истории пока нет, дата взята из графика платежей.`,
    );
  } else {
    const last = Math.abs(history[history.length - 1].amount);
    const trend =
      last === amount
        ? `сумма не менялась с ${human(history[0].date)}`
        : amount > last
          ? `сумма выросла с ${money(last)} до ${money(amount)}`
          : `сумма снизилась с ${money(last)} до ${money(amount)}`;
    parts.push(`${op.title} — ${money(amount)}, списывается каждый месяц; ${trend}.`);
  }

  const monthly = autopayments.reduce((acc, bill) => acc + bill.amount, 0);
  const largest = autopayments.every((bill) => bill.amount <= amount);
  const share = monthly === 0 ? 0 : Math.round((amount / monthly) * 100);
  if (largest && share > 0) {
    parts.push(`Это самый крупный обязательный платёж — ${share}% всех регулярных расходов месяца.`);
  } else if (op.category === 'subscriptions') {
    parts.push(`За год выходит ${money(amount * 12)} — стоит проверить, пользуетесь ли вы этим сервисом.`);
  } else if (share >= 5) {
    parts.push(`Это ${share}% регулярных расходов месяца.`);
  }

  return parts.join(' ');
}

function describeIncome(op: DayOperation, date: string) {
  return `${op.title} — ${money(op.amount)}, регулярное поступление ${parseIso(date).getDate()}-го числа. С этого дня дневной лимит пересчитывается до следующих денег.`;
}

export function buildDayInsight(args: {
  date: string;
  today: string;
  profile: Profile;
  transactions: Transaction[];
}): Explained<DayInsight> {
  const { date, today, profile, transactions } = args;
  const kind: DayInsight['kind'] = date < today ? 'past' : date === today ? 'today' : 'future';

  const operations = operationsOf(date, today, profile, transactions);
  const typical = typicalFor(date, today, transactions);

  const runwayDay =
    date >= today && profile.incomes.length > 0
      ? buildRunway(profile, today).days.find((day) => day.date === date)
      : undefined;
  const balance = runwayDay?.balance ?? null;
  const status = runwayDay?.status ?? null;

  const recurring = operations.filter((op) => op.isRecurring);
  let note: string | null = null;

  if (recurring.length > 0) {
    const lines = recurring.map((op) =>
      op.amount > 0 ? describeIncome(op, date) : describeExpense(op, date, today, transactions, profile.autopayments),
    );

    const outflow = recurring.filter((op) => op.amount < 0).reduce((acc, op) => acc + op.amount, 0);
    if (balance !== null && outflow < 0) {
      if (status === 'shortfall') {
        lines.push(
          `После списаний баланс уйдёт в минус: ${money(balance)} не хватит. Отложите разовые покупки до ближайшего поступления.`,
        );
      } else if (status === 'tight') {
        lines.push(
          `После списаний останется ${money(balance)} — это впритык. Крупные покупки лучше не планировать на эти дни.`,
        );
      } else {
        lines.push(`После списаний останется около ${money(balance)} — платежи проходят без напряжения.`);
      }
    }

    note = lines.join('\n\n');
  }

  const recurringSum = recurring.reduce((acc, op) => acc + op.amount, 0);
  const calculation: Explained<DayInsight>['calculation'] = [];

  if (recurring.length > 0) {
    calculation.push({
      label: 'Регулярные операции дня',
      formula: recurring.map((op) => `${op.title} ${money(op.amount)}`).join(' + '),
      value: recurringSum,
    });
  }
  if (typical) {
    calculation.push({
      label: 'Обычные траты в этот день недели',
      formula: `${money(typical.spent)} необязательных трат / ${typical.sameDays} дн.`,
      value: typical.value,
    });
  }
  if (balance !== null) {
    calculation.push({
      label: 'Остаток на конец дня',
      formula: 'прогноз по календарю до поступления',
      value: balance,
    });
  }

  return {
    result: { date, kind, operations, typicalSpend: typical?.value ?? null, balance, status, note },
    assumptions:
      kind === 'future'
        ? [
            'В план дня входят регулярные платежи и поступления в те же числа месяца, что раньше',
            'Разовые покупки в план не входят — их проверяет «Могу купить это сегодня?»',
          ]
        : [
            'Операции взяты из загруженной выписки',
            'Регулярным считается платёж, который повторяется в тот же день каждого месяца',
          ],
    calculation,
    sources: [],
    limitations: [
      'Суммы посчитаны кодом по вашим операциям, справка помощника только объясняет их',
      'Это не инвестиционная рекомендация — решение остаётся за вами',
    ],
    dataQuality: {
      sufficient: transactions.length > 0 || profile.incomes.length > 0,
      missing: ['загруженные операции — хотя бы за пару недель'],
      coverageDays:
        transactions.length === 0
          ? 0
          : daysBetween(transactions.reduce((min, t) => (t.date < min ? t.date : min), today), today),
    },
  };
}
