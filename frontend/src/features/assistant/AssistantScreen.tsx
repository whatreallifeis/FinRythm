import { useNavigate } from 'react-router-dom';
import { Screen } from '@/layouts/Screen';
import { usePlatform } from '@/platform';
import { useHistory } from '@/shared/api/hooks';
import { Badge, Card } from '@/shared/ui';
import { COMPACT_SCENARIOS, FEATURED_SCENARIO } from './scenarios';

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
 * Сверху — крупная кнопка «Свой вопрос», под ней три готовые задачи. Выбрав
 * задачу, пользователь попадает в диалог, где помощник уже введён в её
 * контекст и сам объясняет, какие данные нужны.
 */
export function AssistantScreen() {
  const navigate = useNavigate();
  const { haptic } = usePlatform();
  const history = useHistory();
  const historyCount = history.data?.length ?? 0;

  const open = (id: string) => {
    haptic('light');
    navigate(`/app/assistant/${id}`);
  };

  return (
    <Screen title="Помощник" subtitle="Спросите своими словами или выберите готовую задачу">
      <button
        type="button"
        onClick={() => open(FEATURED_SCENARIO.id)}
        className="ios-surface block w-full rounded-card bg-accent p-5 text-left text-accent-text transition-colors hover:bg-accent-hover"
      >
        <div className="flex items-start gap-4">
          <span
            aria-hidden
            className="flex size-12 shrink-0 items-center justify-center rounded-card bg-accent-text/10 text-2xl"
          >
            {FEATURED_SCENARIO.icon}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold">{FEATURED_SCENARIO.title}</p>
            <p className="mt-1 text-sm opacity-75">{FEATURED_SCENARIO.tagline}</p>
          </div>
          <span aria-hidden className="shrink-0 text-xl opacity-60">
            ›
          </span>
        </div>
      </button>

      <div className="grid grid-cols-3 gap-2">
        {COMPACT_SCENARIOS.map((scenario) => (
          <button
            key={scenario.id}
            type="button"
            title={scenario.tagline}
            onClick={() => open(scenario.id)}
            className="ios-surface flex min-h-20 flex-col items-start justify-between gap-2 rounded-card border border-border bg-surface p-3 text-left transition-colors hover:bg-surface-hover"
          >
            <span
              aria-hidden
              className="flex size-7 items-center justify-center rounded-[8px] bg-surface-hover text-sm text-accent"
            >
              {scenario.icon}
            </span>
            <span className="text-[13px] leading-tight font-medium">{scenario.shortTitle}</span>
          </button>
        ))}
      </div>

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
    </Screen>
  );
}
