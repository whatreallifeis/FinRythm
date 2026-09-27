import { useEffect, useRef, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { Screen } from '@/layouts/Screen';
import { useBackButton, useMainButton, usePlatform } from '@/platform';
import { useAsk, useSaveHistory } from '@/shared/api/hooks';
import type { AskAnswer, Explained, HistoryMessage } from '@/shared/api/types';
import { createId } from '@/shared/lib/id';
import { Button, Card, Skeleton } from '@/shared/ui';
import { AnswerCard, UserBubble } from './AnswerCard';
import { findScenario, type Scenario } from './scenarios';

type Turn =
  | { id: number; role: 'user'; text: string }
  | { id: number; role: 'assistant'; data: Explained<AskAnswer> };

const toHistoryMessage = (turn: Turn): HistoryMessage =>
  turn.role === 'user' ? { role: 'user', text: turn.text } : { role: 'assistant', answer: turn.data };

/** Проверяет сценарий из URL и пересоздаёт диалог при его смене. */
export function ScenarioDialogRoute() {
  const { scenarioId } = useParams();
  const scenario = findScenario(scenarioId);

  if (!scenario) return <Navigate to="/app/assistant" replace />;

  // key сбрасывает историю диалога при переходе к другому сценарию.
  return <ScenarioDialog key={scenario.id} scenario={scenario} />;
}

function ScenarioDialog({ scenario }: { scenario: Scenario }) {
  const navigate = useNavigate();
  const { haptic } = usePlatform();

  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const ask = useAsk();
  const saveHistory = useSaveHistory();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Один диалог — одна запись в истории. Компонент пересоздаётся при смене
  // сценария (key в ScenarioDialogRoute), поэтому и id диалога новый.
  const dialogId = useRef(createId());
  const startedAt = useRef(new Date().toISOString());
  const title = useRef<string | null>(null);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || ask.isPending) return;

    // Заголовок записи в истории — первый вопрос пользователя в этом диалоге.
    if (!title.current) title.current = trimmed;

    const withUser: Turn[] = [...turns, { id: Date.now(), role: 'user', text: trimmed }];
    setTurns(withUser);
    setDraft('');

    const persist = (messages: HistoryMessage[]) => {
      saveHistory.mutate({
        id: dialogId.current,
        scenarioId: scenario.id,
        title: title.current ?? trimmed,
        createdAt: startedAt.current,
        messages,
      });
    };

    // Сохраняем уже вопрос: если пользователь уйдёт до ответа, запись не потеряется.
    persist(withUser.map(toHistoryMessage));

    ask.mutate(
      { question: trimmed, scenarioId: scenario.id },
      {
        onSuccess: (data) => {
          const next: Turn[] = [...withUser, { id: Date.now() + 1, role: 'assistant', data }];
          setTurns(next);
          haptic(data.dataQuality.sufficient ? 'success' : 'warning');
          persist(next.map(toHistoryMessage));
        },
        onError: () => haptic('error'),
      },
    );
  };

  // Нативная кнопка «назад» в Telegram, своя в шапке на сайте.
  useBackButton(() => navigate('/app/assistant'));

  useMainButton(
    draft.trim()
      ? { text: 'Отправить', loading: ask.isPending, onClick: () => submit(draft) }
      : null,
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns.length, ask.isPending]);

  return (
    <Screen title={scenario.title} subtitle={scenario.tagline}>
      <Greeting scenario={scenario} />

      {turns.map((turn) =>
        turn.role === 'user' ? (
          <UserBubble key={turn.id} text={turn.text} />
        ) : (
          <AnswerCard
            key={turn.id}
            answer={turn.data}
            insufficientAction={
              <Button variant="secondary" size="sm" onClick={() => setDraft(scenario.example)}>
                Подставить пример
              </Button>
            }
          />
        ),
      )}

      {ask.isPending && (
        <Card>
          <Skeleton className="mb-2 h-4 w-full" />
          <Skeleton className="mb-2 h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </Card>
      )}

      <div className="space-y-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={4}
          placeholder={scenario.placeholder}
          className="w-full resize-none rounded-card border border-border bg-surface p-3 text-sm outline-none placeholder:text-muted focus:border-accent/60"
        />

        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => setDraft(scenario.example)}>
            Подставить пример
          </Button>
          {draft && (
            <Button variant="ghost" size="sm" onClick={() => setDraft('')}>
              Очистить
            </Button>
          )}
        </div>
      </div>

      <div ref={bottomRef} />
    </Screen>
  );
}

/**
 * Первое сообщение помощника.
 *
 * Требование ТЗ — пользователь должен понимать, на чём основан результат.
 * Здесь это начинается ещё до вопроса: сразу видно, какие данные нужны и что
 * именно он получит в ответе.
 */
function Greeting({ scenario }: { scenario: Scenario }) {
  return (
    <Card>
      <p className="text-[15px] leading-relaxed">{scenario.greeting}</p>

      <div className="mt-4 space-y-4">
        <List title="Что мне понадобится" items={scenario.needs} marker="•" tone="text-accent" />
        <List title="Что вы получите" items={scenario.delivers} marker="→" tone="text-positive" />
      </div>
    </Card>
  );
}

function List({
  title,
  items,
  marker,
  tone,
}: {
  title: string;
  items: string[];
  marker: string;
  tone: string;
}) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold tracking-wide text-muted uppercase">{title}</p>
      <ul className="space-y-1.5 text-sm">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span aria-hidden className={`shrink-0 ${tone}`}>
              {marker}
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
