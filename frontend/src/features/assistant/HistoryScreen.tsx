import { useNavigate } from 'react-router-dom';
import { Screen } from '@/layouts/Screen';
import { useBackButton, usePlatform } from '@/platform';
import { useClearHistory, useHistory } from '@/shared/api/hooks';
import { formatDateTime } from '@/shared/lib/format';
import { Badge, Button, Card, EmptyState, ScreenState, Skeleton } from '@/shared/ui';
import { findScenario } from './scenarios';

/** Список всех сохранённых диалогов с помощником. */
export function HistoryScreen() {
  const navigate = useNavigate();
  const { haptic } = usePlatform();
  const history = useHistory();
  const clear = useClearHistory();

  useBackButton(() => navigate('/app/assistant'));

  return (
    <Screen
      title="История запросов"
      subtitle="Все диалоги с помощником"
      action={
        history.data && history.data.length > 0 ? (
          <Button
            variant="ghost"
            size="sm"
            loading={clear.isPending}
            onClick={() => {
              haptic('warning');
              clear.mutate();
            }}
          >
            Очистить
          </Button>
        ) : undefined
      }
    >
      <ScreenState
        query={history}
        isEmpty={(entries) => entries.length === 0}
        skeleton={
          <div className="space-y-2">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        }
        empty={
          <EmptyState
            title="История пуста"
            description="Здесь появятся ваши диалоги с помощником — вместе с расчётами и допущениями"
            action={
              <Button size="sm" onClick={() => navigate('/app/assistant')}>
                К сценариям
              </Button>
            }
          />
        }
      >
        {(entries) => (
          <div className="space-y-3">
            {entries.map((entry) => {
              const scenario = findScenario(entry.scenarioId);
              const answers = entry.messages.filter((m) => m.role === 'assistant');
              // В истории видно и те диалоги, где помощнику не хватило данных.
              const unanswered = answers.every(
                (m) => m.role === 'assistant' && !m.answer.dataQuality.sufficient,
              );

              return (
                <Card
                  key={entry.id}
                  onClick={() => navigate(`/app/assistant/history/${entry.id}`)}
                >
                  <div className="mb-1.5 flex items-center gap-2">
                    <span aria-hidden className="text-accent">
                      {scenario?.icon ?? '✦'}
                    </span>
                    <span className="text-xs text-muted">{scenario?.title ?? 'Диалог'}</span>
                    <span className="ml-auto text-xs text-muted">
                      {formatDateTime(entry.createdAt)}
                    </span>
                  </div>

                  <p className="line-clamp-2 text-sm">{entry.title}</p>

                  <div className="mt-2 flex items-center gap-2">
                    <Badge>{entry.messages.length} сообщ.</Badge>
                    {unanswered && answers.length > 0 && <Badge tone="warning">нужны данные</Badge>}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </ScreenState>
    </Screen>
  );
}
