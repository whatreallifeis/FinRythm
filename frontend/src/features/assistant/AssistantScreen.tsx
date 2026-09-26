import { useNavigate } from 'react-router-dom';
import { Screen } from '@/layouts/Screen';
import { usePlatform } from '@/platform';
import { useHistory } from '@/shared/api/hooks';
import { Badge, Card } from '@/shared/ui';
import { SCENARIOS } from './scenarios';

function pluralDialogs(n: number) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'диалог';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'диалога';
  return 'диалогов';
}

/**
 * Список сценариев помощника.
 *
 * Пользователю не нужно догадываться, что можно спросить: он выбирает задачу,
 * а помощник уже введён в её контекст и сам объясняет, какие данные нужны.
 */
export function AssistantScreen() {
  const navigate = useNavigate();
  const { haptic } = usePlatform();
  const history = useHistory();
  const historyCount = history.data?.length ?? 0;

  return (
    <Screen title="Помощник" subtitle="Выберите задачу — я подскажу, что рассказать о себе">
      <Card
        onClick={() => {
          haptic('light');
          navigate('/app/assistant/history');
        }}
      >
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="flex size-9 shrink-0 items-center justify-center rounded-card bg-surface-hover text-muted"
          >
            ≡
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">История запросов</p>
            <p className="text-sm text-muted">
              {historyCount > 0
                ? `${historyCount} ${pluralDialogs(historyCount)} с помощником`
                : 'Пока пусто — диалоги появятся после первого ответа'}
            </p>
          </div>
          {historyCount > 0 && <Badge>{historyCount}</Badge>}
          <span aria-hidden className="shrink-0 text-muted">
            ›
          </span>
        </div>
      </Card>

      <div className="space-y-3">
        {SCENARIOS.map((scenario) => (
          <Card
            key={scenario.id}
            onClick={() => {
              haptic('light');
              navigate(`/app/assistant/${scenario.id}`);
            }}
          >
            <div className="flex items-start gap-3">
              <span
                aria-hidden
                className="flex size-9 shrink-0 items-center justify-center rounded-card bg-surface-hover text-accent"
              >
                {scenario.icon}
              </span>

              <div className="min-w-0 flex-1">
                <p className="font-semibold">{scenario.title}</p>
                <p className="mt-0.5 text-sm text-muted">{scenario.tagline}</p>
              </div>

              <span aria-hidden className="shrink-0 text-muted">
                ›
              </span>
            </div>
          </Card>
        ))}
      </div>
    </Screen>
  );
}
