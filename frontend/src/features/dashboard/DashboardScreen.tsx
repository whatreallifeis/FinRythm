import { useNavigate } from 'react-router-dom';
import { Screen } from '@/layouts/Screen';
import { useOverview, useProfile, useRunway } from '@/shared/api/hooks';
import { formatDate, formatDateFull, formatMoney } from '@/shared/lib/format';
import { Badge, Button, Card, CardTitle, ScreenState, SkeletonCard } from '@/shared/ui';
import { ExplainedView } from '@/features/explain/ExplainedView';
import { CategoryPie } from './CategoryPie';
import { ImpulsePanel } from './ImpulsePanel';
import { RunwayCalendar } from './RunwayCalendar';

const DAY_VERDICT: Record<string, { tone: 'positive' | 'warning' | 'negative'; label: string }> = {
  ok: { tone: 'positive', label: 'Доживёте' },
  tight: { tone: 'warning', label: 'Впритык' },
  shortfall: { tone: 'negative', label: 'Будет разрыв' },
};

export function DashboardScreen() {
  const navigate = useNavigate();
  const profile = useProfile();
  const runway = useRunway();
  const overview = useOverview();

  return (
    <Screen title="Обзор" subtitle="Сентябрь 2026">
      <ScreenState query={profile} skeleton={<SkeletonCard />}>
        {(data) => (
          <Card>
            <p className="text-sm text-muted">Баланс</p>
            <p className="tabular mt-1 text-3xl font-semibold">{formatMoney(data.balance)}</p>
          </Card>
        )}
      </ScreenState>

      <Card>
        <CardTitle
          action={
            <Button variant="ghost" size="sm" onClick={() => runway.refetch()}>
              Обновить
            </Button>
          }
        >
          Дожить до стипендии
        </CardTitle>

        <ExplainedView query={runway}>
          {(result) => {
            const worst = result.days.some((day) => day.status === 'shortfall')
              ? 'shortfall'
              : result.days.some((day) => day.status === 'tight')
                ? 'tight'
                : 'ok';

            return (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <p className="tabular text-2xl font-semibold">
                    {formatMoney(result.todaySafeSpend)}
                  </p>
                  <span className="text-sm text-muted">в день до поступления</span>
                  <span className="ml-auto">
                    <Badge tone={DAY_VERDICT[worst].tone}>{DAY_VERDICT[worst].label}</Badge>
                  </span>
                </div>

                {result.nextIncome && (
                  <p className="text-sm text-muted">
                    Следующие деньги — {result.nextIncome.title}{' '}
                    {formatMoney(result.nextIncome.amount)} {formatDate(result.nextIncome.date)}, через{' '}
                    {result.nextIncome.daysUntil} дн.
                  </p>
                )}

                <RunwayCalendar days={result.days} />

                <ImpulsePanel />
              </div>
            );
          }}
        </ExplainedView>
      </Card>

      <Card>
        <CardTitle
          action={
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/app/assistant/expenses')}
            >
              Разобрать
            </Button>
          }
        >
          Куда уходят деньги
        </CardTitle>

        <ExplainedView query={overview}>
          {(result) => (
            <div className="space-y-4">
              <div className="flex gap-4 text-sm">
                <div>
                  <p className="text-muted">Доходы</p>
                  <p className="tabular font-medium text-positive">
                    {formatMoney(result.totalIncome)}
                  </p>
                </div>
                <div>
                  <p className="text-muted">Расходы</p>
                  <p className="tabular font-medium text-negative">
                    {formatMoney(result.totalExpense)}
                  </p>
                </div>
                <div>
                  <p className="text-muted">Из них обязательные</p>
                  <p className="tabular font-medium">{formatMoney(result.recurringTotal)}</p>
                </div>
              </div>

              <CategoryPie slices={result.byCategory} />

              {result.anomalies.length > 0 && (
                <div className="rounded-card border border-warning/30 bg-warning/5 p-3">
                  <p className="mb-1 text-sm font-medium text-warning">Необычные траты</p>
                  <ul className="space-y-1 text-sm text-muted">
                    {result.anomalies.map((item) => (
                      <li key={item.transactionId}>{item.reason}</li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-xs text-muted">
                Период: с {formatDateFull(result.periodFrom)} по {formatDateFull(result.periodTo)}
              </p>
            </div>
          )}
        </ExplainedView>
      </Card>
    </Screen>
  );
}

