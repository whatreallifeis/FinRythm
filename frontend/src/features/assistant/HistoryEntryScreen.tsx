import { useNavigate, useParams } from 'react-router-dom';
import { Screen } from '@/layouts/Screen';
import { useBackButton } from '@/platform';
import { useHistory } from '@/shared/api/hooks';
import { formatDateTime } from '@/shared/lib/format';
import { Button, EmptyState, ScreenState, SkeletonCard } from '@/shared/ui';
import { AnswerCard, UserBubble } from './AnswerCard';
import { findScenario } from './scenarios';

/**
 * Просмотр сохранённого диалога.
 *
 * Отдельного запроса за одной записью нет: берём её из уже загруженного списка
 * истории, поэтому переход из списка открывается мгновенно и без лишнего
 * эндпоинта на бэкенде.
 */
export function HistoryEntryScreen() {
  const { entryId } = useParams();
  const navigate = useNavigate();
  const history = useHistory();

  useBackButton(() => navigate('/app/assistant/history'));

  return (
    <ScreenState query={history} skeleton={<SkeletonCard />}>
      {(entries) => {
        const entry = entries.find((item) => item.id === entryId);

        if (!entry) {
          return (
            <Screen title="Диалог не найден">
              <EmptyState
                title="Эта запись больше недоступна"
                description="Возможно, историю очистили"
                action={
                  <Button size="sm" onClick={() => navigate('/app/assistant/history')}>
                    К истории
                  </Button>
                }
              />
            </Screen>
          );
        }

        const scenario = findScenario(entry.scenarioId);

        return (
          <Screen
            title={scenario?.title ?? 'Диалог'}
            subtitle={formatDateTime(entry.createdAt)}
            action={
              scenario ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(`/app/assistant/${scenario.id}`)}
                >
                  Спросить снова
                </Button>
              ) : undefined
            }
          >
            {entry.messages.map((message, i) =>
              message.role === 'user' ? (
                <UserBubble key={i} text={message.text} />
              ) : (
                <AnswerCard key={i} answer={message.answer} />
              ),
            )}
          </Screen>
        );
      }}
    </ScreenState>
  );
}
