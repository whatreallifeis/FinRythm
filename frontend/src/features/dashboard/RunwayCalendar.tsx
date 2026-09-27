import { useState } from 'react';
import type { RunwayDay } from '@/shared/api/types';
import { formatDayNumber, formatMoney, formatWeekday } from '@/shared/lib/format';
import { cn } from '@/shared/lib/cn';

const TONE = {
  ok: 'bg-positive/20 text-positive',
  tight: 'bg-warning/20 text-warning',
  shortfall: 'bg-negative/20 text-negative',
} as const;

/** Лента дней до поступления: цвет сразу говорит, где кассовый разрыв. */
export function RunwayCalendar({ days }: { days: RunwayDay[] }) {
  const [open, setOpen] = useState<string | null>(days.find((day) => day.events.length > 0)?.date ?? null);
  const selected = days.find((day) => day.date === open);

  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {days.map((day) => {
          const isOpen = day.date === open;
          return (
            <button
              key={day.date}
              type="button"
              onClick={() => setOpen(isOpen ? null : day.date)}
              className={cn(
                'flex h-14 w-11 flex-col items-center justify-center rounded-[10px] text-[11px] transition-colors',
                TONE[day.status],
                isOpen && 'ring-2 ring-accent ring-offset-2 ring-offset-surface',
              )}
            >
              <span className="capitalize opacity-70">{formatWeekday(day.date)}</span>
              <span className="tabular text-sm font-semibold">{formatDayNumber(day.date)}</span>
            </button>
          );
        })}
      </div>

      {selected && (
        <div className="ios-reveal mt-3 rounded-card border border-border bg-bg p-3 text-sm">
          <p className="mb-1 font-medium">
            {formatWeekday(selected.date)} {formatDayNumber(selected.date)}
          </p>
          {selected.events.length === 0 ? (
            <p className="text-muted">Обязательных платежей нет</p>
          ) : (
            <ul className="space-y-1">
              {selected.events.map((event) => (
                <li key={`${event.title}-${event.amount}`} className="flex justify-between gap-2">
                  <span>{event.title}</span>
                  <span
                    className={
                      event.amount > 0 ? 'tabular text-positive' : 'tabular font-medium'
                    }
                  >
                    {event.amount > 0 ? '+' : ''}
                    {formatMoney(event.amount)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-muted">
            Остаток на конец дня:{' '}
            <span className="tabular font-medium text-text">{formatMoney(selected.balance)}</span>
          </p>
        </div>
      )}
    </div>
  );
}
