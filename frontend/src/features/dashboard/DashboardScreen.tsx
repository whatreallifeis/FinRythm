import { useCallback, useRef, useState } from 'react';
import { Screen } from '@/layouts/Screen';
import { usePlatform } from '@/platform';
import { useProfile, useRunway, useTransactions } from '@/shared/api/hooks';
import { formatDate, formatMoney } from '@/shared/lib/format';
import { Badge, Button, Card, Modal, ScreenState, Skeleton } from '@/shared/ui';
import { DayDetails } from './DayDetails';
import { ImpulsePanel } from './ImpulsePanel';
import { MonthCalendar } from './MonthCalendar';

const DAY_VERDICT: Record<string, { tone: 'positive' | 'warning' | 'negative'; label: string }> = {
  ok: { tone: 'positive', label: 'Доживёте' },
  tight: { tone: 'warning', label: 'Впритык' },
  shortfall: { tone: 'negative', label: 'Будет разрыв' },
};

function CalendarSkeleton() {
  return (
    <Card>
      <Skeleton className="mb-4 h-10 w-2/3" />
      <Skeleton className="mx-auto mb-3 h-5 w-1/3" />
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: 35 }, (_, i) => (
          <Skeleton key={i} className="h-11" />
        ))}
      </div>
    </Card>
  );
}

/**
 * Главная: сверху календарь, снизу — выбранный день.
 *
 * Прошедшие дни показывают факт из выписки, будущие — прогноз остатка до
 * поступления. По дням с регулярными операциями помощник пишет справку.
 */
export function DashboardScreen() {
  const { haptic } = usePlatform();
  const profile = useProfile();
  const runway = useRunway();
  const transactions = useTransactions();

  const [selected, setSelected] = useState<string | null>(null);
  const [impulseOpen, setImpulseOpen] = useState(false);
  const detailsRef = useRef<HTMLDivElement>(null);
  const closeImpulse = useCallback(() => setImpulseOpen(false), []);

  return (
    <Screen
      title="Обзор"
      subtitle="Нажмите на дату, чтобы увидеть операции"
      action={
        <Button
          variant="secondary"
          size="sm"
          className="shrink-0 whitespace-nowrap"
          onClick={() => {
            haptic('light');
            setImpulseOpen(true);
          }}
        >
          <span aria-hidden className="text-accent">
            ◎
          </span>
          Могу купить?
        </Button>
      }
    >
      <ScreenState query={runway} skeleton={<CalendarSkeleton />}>
        {(data) => {
          const forecast = data.dataQuality.sufficient ? data.result : null;
          const days = forecast?.days ?? [];
          const today = data.result.days[0]?.date ?? new Date().toISOString().slice(0, 10);
          const active = selected ?? today;

          const worst = days.some((day) => day.status === 'shortfall')
            ? 'shortfall'
            : days.some((day) => day.status === 'tight')
              ? 'tight'
              : 'ok';

          return (
            <>
              <Card>
                <div className="mb-4 flex items-start justify-between gap-3 border-b border-border pb-4">
                  <div>
                    <p className="text-xs text-muted">Баланс</p>
                    <p className="tabular text-2xl font-semibold">
                      {profile.data ? formatMoney(profile.data.balance) : '—'}
                    </p>
                  </div>
                  {forecast ? (
                    <div className="text-right">
                      <p className="text-xs text-muted">
                        {forecast.nextIncome
                          ? `В день до ${formatDate(forecast.nextIncome.date)}`
                          : 'Можно тратить в день'}
                      </p>
                      <p className="tabular flex items-center justify-end gap-2 text-lg font-semibold">
                        {formatMoney(forecast.todaySafeSpend)}
                        <Badge tone={DAY_VERDICT[worst].tone}>{DAY_VERDICT[worst].label}</Badge>
                      </p>
                    </div>
                  ) : (
                    <p className="max-w-[55%] text-right text-xs text-muted">
                      Добавьте регулярный доход — посчитаю лимит в день и прогноз по дням
                    </p>
                  )}
                </div>

                <MonthCalendar
                  transactions={transactions.data ?? []}
                  runwayDays={days}
                  recurringDays={[
                    ...(profile.data?.autopayments ?? []),
                    ...(profile.data?.incomes ?? []),
                  ].map((item) => item.dayOfMonth)}
                  today={today}
                  selected={active}
                  onSelect={(date) => {
                    haptic('light');
                    setSelected(date);
                    requestAnimationFrame(() =>
                      detailsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }),
                    );
                  }}
                />
              </Card>

              <div ref={detailsRef} className="scroll-mb-24">
                <DayDetails key={active} date={active} />
              </div>
            </>
          );
        }}
      </ScreenState>

      <Modal open={impulseOpen} title="Могу купить это сегодня?" onClose={closeImpulse}>
        <ImpulsePanel />
      </Modal>
    </Screen>
  );
}
