import { useMemo, useState } from 'react';
import type { DayStatus, RunwayDay, Transaction } from '@/shared/api/types';
import { formatDayLong, formatMonthYear } from '@/shared/lib/format';
import { cn } from '@/shared/lib/cn';

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

/** Будущие дни окрашены прогнозом остатка — те же цвета, что у ленты в «Могу купить». */
const TONE: Record<DayStatus, string> = {
  ok: 'bg-positive/15 text-positive',
  tight: 'bg-warning/20 text-warning',
  shortfall: 'bg-negative/20 text-negative',
};

interface DayMark {
  status: DayStatus | null;
  hasOperations: boolean;
  /** Есть регулярные операции — по ним помощник пишет справку. */
  hasRecurring: boolean;
}

const pad = (n: number) => String(n).padStart(2, '0');
const isoOf = (year: number, month: number, day: number) => `${year}-${pad(month + 1)}-${pad(day)}`;
const monthIndex = (iso: string) => Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7)) - 1;

function buildMarks(transactions: Transaction[], runwayDays: RunwayDay[], today: string) {
  const marks = new Map<string, DayMark>();

  for (const t of transactions) {
    if (t.date >= today) continue;
    const mark = marks.get(t.date) ?? { status: null, hasOperations: false, hasRecurring: false };
    mark.hasOperations = true;
    mark.hasRecurring ||= t.isRecurring;
    marks.set(t.date, mark);
  }

  for (const day of runwayDays) {
    marks.set(day.date, {
      status: day.status,
      hasOperations: day.events.length > 0,
      hasRecurring: day.events.length > 0,
    });
  }

  return marks;
}

/**
 * Месячный календарь на главной.
 *
 * Прошедшие дни — факт из выписки, будущие — прогноз остатка до поступления.
 * Точка под числом отмечает регулярные операции: по таким дням помощник
 * пишет справку в блоке под календарём.
 */
export function MonthCalendar({
  transactions,
  runwayDays,
  recurringDays,
  today,
  selected,
  onSelect,
}: {
  transactions: Transaction[];
  runwayDays: RunwayDay[];
  /** Числа месяца автоплатежей и поступлений — для дней за горизонтом прогноза. */
  recurringDays: number[];
  today: string;
  selected: string;
  onSelect: (date: string) => void;
}) {
  const marks = useMemo(
    () => buildMarks(transactions, runwayDays, today),
    [transactions, runwayDays, today],
  );

  // Листать можно от первой операции до конца прогноза, но минимум на два
  // месяца вперёд — чтобы видеть, куда встанут автоплатежи.
  const bounds = useMemo(() => {
    const dates = [today, ...transactions.map((t) => t.date), ...runwayDays.map((d) => d.date)];
    const indexes = dates.map(monthIndex);
    return {
      min: Math.min(...indexes),
      max: Math.max(...indexes, monthIndex(today) + 2),
    };
  }, [transactions, runwayDays, today]);

  const [visible, setVisible] = useState(() => monthIndex(selected));
  const year = Math.floor(visible / 12);
  const month = visible % 12;

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  // getDay(): 0 — воскресенье; неделя в календаре начинается с понедельника.
  const leading = (new Date(year, month, 1).getDay() + 6) % 7;

  const cells: Array<string | null> = [
    ...Array.from({ length: leading }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => isoOf(year, month, i + 1)),
  ];

  const go = (delta: number) => setVisible((v) => Math.min(bounds.max, Math.max(bounds.min, v + delta)));

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label="Предыдущий месяц"
          disabled={visible <= bounds.min}
          onClick={() => go(-1)}
          className="flex size-9 items-center justify-center rounded-[10px] text-lg text-muted transition-colors hover:bg-surface-hover hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
        >
          ‹
        </button>
        <p className="text-[15px] font-semibold">{formatMonthYear(year, month)}</p>
        <button
          type="button"
          aria-label="Следующий месяц"
          disabled={visible >= bounds.max}
          onClick={() => go(1)}
          className="flex size-9 items-center justify-center rounded-[10px] text-lg text-muted transition-colors hover:bg-surface-hover hover:text-text disabled:opacity-30 disabled:hover:bg-transparent"
        >
          ›
        </button>
      </div>

      <div className="mb-1 grid grid-cols-7 gap-1 text-center text-[11px] text-muted">
        {WEEKDAYS.map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>

      <div key={visible} className="ios-reveal grid grid-cols-7 gap-1">
        {cells.map((date, i) => {
          if (!date) return <span key={`blank-${i}`} aria-hidden />;

          const mark = marks.get(date);
          const dayNumber = Number(date.slice(8));
          // За горизонтом прогноза точку ставим по расписанию автоплатежей и поступлений.
          const scheduled =
            !mark &&
            date > today &&
            recurringDays.some(
              (dom) => dom === dayNumber || (dayNumber === daysInMonth && dom > daysInMonth),
            );
          const isSelected = date === selected;
          const isToday = date === today;
          const isPast = date < today;
          const tone = mark?.status ? TONE[mark.status] : null;

          return (
            <button
              key={date}
              type="button"
              aria-pressed={isSelected}
              aria-label={formatDayLong(date)}
              onClick={() => onSelect(date)}
              className={cn(
                'tabular relative flex h-11 flex-col items-center justify-center rounded-[10px] text-sm transition-colors',
                isSelected
                  ? 'bg-accent font-semibold text-accent-text'
                  : [
                      tone ?? (isPast && mark?.hasOperations ? 'text-text' : 'text-muted'),
                      !tone && 'hover:bg-surface-hover',
                      isToday && 'font-semibold ring-1 ring-accent/70',
                    ],
              )}
            >
              {dayNumber}
              {(mark?.hasRecurring || scheduled) && (
                <span
                  aria-hidden
                  className="absolute bottom-1.5 size-1 rounded-full bg-current opacity-80"
                />
              )}
            </button>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-1.5 rounded-full bg-text" />
          регулярные операции
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-[3px] bg-positive/40" />
          хватает
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-[3px] bg-warning/50" />
          впритык
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-[3px] bg-negative/50" />
          разрыв
        </span>
      </div>
    </div>
  );
}
