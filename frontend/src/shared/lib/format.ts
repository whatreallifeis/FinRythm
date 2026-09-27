/** Форматирование чисел и дат. Везде одинаковое, чтобы суммы не выглядели по-разному. */

const rub = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
});

export const formatMoney = (value: number) => rub.format(value);

/** Со знаком: для операций, где важно отличить приход от расхода. */
export const formatSigned = (value: number) =>
  `${value > 0 ? '+' : value < 0 ? '−' : ''}${rub.format(Math.abs(value))}`;

export const formatPercent = (share: number) => `${Math.round(share * 100)}%`;

const dayMonth = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' });
const full = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });

const dayMonthTime = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

function localDate(iso: string) {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export const formatDate = (iso: string) => dayMonth.format(localDate(iso));
export const formatDateFull = (iso: string) => full.format(localDate(iso));

/** «24 сент. 19:12» — для списка истории, где важно и время. */
export const formatDateTime = (iso: string) => dayMonthTime.format(new Date(iso));

export const formatWeekday = (iso: string) =>
  new Intl.DateTimeFormat('ru-RU', { weekday: 'short' }).format(localDate(iso));

export const formatDayNumber = (iso: string) => String(localDate(iso).getDate());

/** «2 месяца», «5 месяцев» — правильная форма слова. */
export function pluralMonths(n: number) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} месяц`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} месяца`;
  return `${n} месяцев`;
}

const monthName = new Intl.DateTimeFormat('ru-RU', { month: 'long' });

/** «Сентябрь 2026» — заголовок календаря. */
export function formatMonthYear(year: number, monthIndex: number) {
  const name = monthName.format(new Date(year, monthIndex, 1));
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} ${year}`;
}

/** «Суббота, 26 сентября» — заголовок выбранного дня. */
export function formatDayLong(iso: string) {
  const text = new Intl.DateTimeFormat('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(localDate(iso));
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}
