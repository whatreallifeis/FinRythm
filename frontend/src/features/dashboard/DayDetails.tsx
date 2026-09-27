import { useCallback, useState } from 'react';
import { usePlatform } from '@/platform';
import { useDayInsight } from '@/shared/api/hooks';
import type { DayInsight, DayOperation } from '@/shared/api/types';
import { categoryColor } from '@/shared/lib/categories';
import { formatDayLong, formatMoney, formatSigned } from '@/shared/lib/format';
import { Badge, Card, Skeleton } from '@/shared/ui';
import { ExplainedView } from '@/features/explain/ExplainedView';
import { AutopaymentModal } from './AutopaymentModal';
import { OperationEditModal } from './OperationEditModal';

const KIND: Record<DayInsight['kind'], { tone: 'neutral' | 'info'; label: string }> = {
  past: { tone: 'neutral', label: 'Факт' },
  today: { tone: 'info', label: 'Сегодня' },
  future: { tone: 'info', label: 'План' },
};

const STATUS_TEXT = {
  ok: 'text-positive',
  tight: 'text-warning',
  shortfall: 'text-negative',
} as const;

/** «по субботам» — для строки про обычные траты. */
const WEEKDAY_DATIVE = [
  'воскресеньям',
  'понедельникам',
  'вторникам',
  'средам',
  'четвергам',
  'пятницам',
  'субботам',
];

function weekdayDative(iso: string) {
  const [year, month, day] = iso.split('-').map(Number);
  return WEEKDAY_DATIVE[new Date(year, month - 1, day).getDay()];
}

function DaySkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="mt-3 h-16 w-full" />
    </div>
  );
}

/**
 * Блок под календарём: операции выбранного дня и справка помощника.
 *
 * Справка появляется только для регулярных операций — аренды, подписок,
 * стипендии: по разовым тратам сказать что-то полезное без контекста нельзя.
 *
 * Здесь же операции можно переименовать, а на этот день — добавить автоплатёж.
 */
export function DayDetails({ date }: { date: string }) {
  const { haptic } = usePlatform();
  const insight = useDayInsight(date);
  const [editing, setEditing] = useState<DayOperation | null>(null);
  const [adding, setAdding] = useState(false);
  const closeEdit = useCallback(() => setEditing(null), []);
  const closeAdd = useCallback(() => setAdding(false), []);
  const dayOfMonth = Number(date.slice(8));

  return (
    <Card className="ios-reveal">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold">{formatDayLong(date)}</h2>
        {insight.data && <Badge tone={KIND[insight.data.result.kind].tone}>{KIND[insight.data.result.kind].label}</Badge>}
      </div>

      <ExplainedView query={insight} skeleton={<DaySkeleton />}>
        {(day) => {
          const oneOff = day.operations
            .filter((op) => op.amount < 0 && !op.isRecurring)
            .reduce((acc, op) => acc + Math.abs(op.amount), 0);

          return (
            <div className="space-y-4">
              {day.operations.length === 0 ? (
                <p className="text-sm text-muted">
                  {day.kind === 'future'
                    ? 'Регулярных платежей и поступлений в этот день нет'
                    : day.kind === 'today'
                      ? 'Сегодня операций пока не было'
                      : 'Операций в этот день не было'}
                </p>
              ) : (
                <ul className="-mx-2 space-y-0.5">
                  {day.operations.map((op) => (
                    <li key={`${op.ref.kind}-${op.ref.id}`}>
                      <button
                        type="button"
                        title="Изменить название"
                        onClick={() => {
                          haptic('light');
                          setEditing(op);
                        }}
                        className="group flex w-full items-center gap-2.5 rounded-[10px] px-2 py-1.5 text-left text-sm transition-colors hover:bg-surface-hover"
                      >
                        <span
                          aria-hidden
                          className="size-2 shrink-0 rounded-full"
                          style={{ backgroundColor: categoryColor(op.category) }}
                        />
                        <span className="min-w-0 flex-1 truncate">{op.title}</span>
                        {op.isRecurring && <Badge>{op.ref.kind === 'autopayment' ? 'автоплатёж' : 'регулярный'}</Badge>}
                        <span
                          className={
                            op.amount > 0 ? 'tabular shrink-0 text-positive' : 'tabular shrink-0 font-medium'
                          }
                        >
                          {formatSigned(op.amount)}
                        </span>
                        <span
                          aria-hidden
                          className="shrink-0 text-xs text-muted transition-colors group-hover:text-text"
                        >
                          ✎
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <button
                type="button"
                onClick={() => {
                  haptic('light');
                  setAdding(true);
                }}
                className="flex w-full items-center justify-center gap-1.5 rounded-card border border-dashed border-border py-2.5 text-sm text-muted transition-colors hover:border-accent/60 hover:text-text"
              >
                <span aria-hidden className="text-accent">
                  +
                </span>
                Автоплатёж на {dayOfMonth}-е число
              </button>

              <dl className="grid grid-cols-2 gap-3 rounded-card bg-bg p-3 text-sm">
                <div>
                  <dt className="text-xs text-muted">Обычно по {weekdayDative(day.date)}</dt>
                  <dd className="tabular font-medium">
                    {day.typicalSpend === null ? '—' : `≈ ${formatMoney(day.typicalSpend)}`}
                  </dd>
                </div>
                {day.kind === 'past' ? (
                  <div>
                    <dt className="text-xs text-muted">Разовые траты в этот день</dt>
                    <dd className="tabular font-medium">{formatMoney(oneOff)}</dd>
                  </div>
                ) : (
                  <div>
                    <dt className="text-xs text-muted">Остаток на конец дня</dt>
                    <dd
                      className={
                        day.status ? `tabular font-medium ${STATUS_TEXT[day.status]}` : 'tabular font-medium'
                      }
                    >
                      {day.balance === null ? 'за горизонтом' : formatMoney(day.balance)}
                    </dd>
                  </div>
                )}
              </dl>

              {day.note ? (
                <div className="rounded-card border border-accent/30 bg-accent/5 p-3">
                  <p className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold">
                    <span aria-hidden className="text-accent">
                      ✦
                    </span>
                    Справка помощника
                  </p>
                  <div className="space-y-2 text-sm leading-relaxed">
                    {day.note.split('\n\n').map((paragraph) => (
                      <p key={paragraph}>{paragraph}</p>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted">
                  Справка помощника появляется в дни с регулярными операциями — арендой, подписками,
                  стипендией. Такие дни отмечены точкой в календаре.
                </p>
              )}
            </div>
          );
        }}
      </ExplainedView>

      <OperationEditModal operation={editing} date={date} onClose={closeEdit} />
      <AutopaymentModal open={adding} defaultDay={dayOfMonth} onClose={closeAdd} />
    </Card>
  );
}
