import type { Autopayment, CategoryId, Income, Transaction } from '../types';

/**
 * Поиск регулярных операций в выписке.
 *
 * Банк не помечает, какой платёж регулярный, — это приходится выводить из
 * самих операций. Серией считаем операции с одним описанием, которые:
 *   - встречаются не реже двух месяцев подряд и не чаще раза в месяц;
 *   - почти не меняются по сумме (разброс до 15 %);
 *   - приходят примерно в одно число (разброс до 3 дней).
 *
 * Автобус за 48 ₽ по нескольку раз в месяц под это правило не попадает,
 * а связь, аренда и стипендия — попадают. Тот же разбор ожидается на бэкенде.
 */

const AMOUNT_SPREAD = 1.15;
const DAY_SPREAD = 3;

export interface Series {
  title: string;
  direction: 'income' | 'expense';
  /** Сумма последней операции серии, положительное число. */
  amount: number;
  dayOfMonth: number;
  category: CategoryId;
  transactionIds: string[];
}

const monthNumber = (iso: string) => Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7));

export function detectSeries(rows: Transaction[]): Series[] {
  const groups = new Map<string, Transaction[]>();
  for (const t of rows) {
    const key = `${t.amount > 0 ? '+' : '-'}|${t.merchant}`;
    groups.set(key, [...(groups.get(key) ?? []), t]);
  }

  const series: Series[] = [];

  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const sorted = [...group].sort((a, b) => a.date.localeCompare(b.date));

    const months = sorted.map((t) => monthNumber(t.date));
    const consecutive = months.every((m, i) => i === 0 || m - months[i - 1] === 1);
    if (!consecutive) continue;

    const amounts = sorted.map((t) => Math.abs(t.amount));
    if (Math.max(...amounts) / Math.min(...amounts) > AMOUNT_SPREAD) continue;

    const days = sorted.map((t) => Number(t.date.slice(8)));
    if (Math.max(...days) - Math.min(...days) > DAY_SPREAD) continue;

    const last = sorted[sorted.length - 1];
    series.push({
      title: last.merchant,
      direction: last.amount > 0 ? 'income' : 'expense',
      amount: Math.abs(last.amount),
      dayOfMonth: Number(last.date.slice(8)),
      category: last.category,
      transactionIds: sorted.map((t) => t.id),
    });
  }

  return series;
}

/**
 * Размечает операции и дополняет списки поступлений и автоплатежей.
 *
 * Уже существующие правила (в том числе созданные пользователем вручную)
 * не трогаем: новые серии добавляются, только если такого названия ещё нет.
 */
export function applySeries(
  transactions: Transaction[],
  incomes: Income[],
  autopayments: Autopayment[],
) {
  const series = detectSeries(transactions);
  const recurringIds = new Set(series.flatMap((s) => s.transactionIds));
  const stamp = Date.now();

  const newIncomes: Income[] = series
    .filter((s) => s.direction === 'income' && !incomes.some((i) => i.title === s.title))
    .map((s, n) => ({ id: `i-${stamp}-${n}`, title: s.title, amount: s.amount, dayOfMonth: s.dayOfMonth }));

  const newAutopayments: Autopayment[] = series
    .filter((s) => s.direction === 'expense' && !autopayments.some((a) => a.title === s.title))
    .map((s, n) => ({
      id: `a-${stamp}-${n}`,
      title: s.title,
      amount: s.amount,
      dayOfMonth: s.dayOfMonth,
      category: s.category,
    }));

  return {
    transactions: transactions.map((t) => (recurringIds.has(t.id) ? { ...t, isRecurring: true } : t)),
    incomes: [...incomes, ...newIncomes],
    autopayments: [...autopayments, ...newAutopayments],
    found: { incomes: newIncomes.length, autopayments: newAutopayments.length },
  };
}
