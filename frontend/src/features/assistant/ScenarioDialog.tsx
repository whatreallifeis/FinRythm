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

/**
 * Сколько раз можно отправить один и тот же вопрос: первый раз и два повтора.
 * Повтор нужен, чтобы получить другую формулировку ответа или дождаться ответа после сбоя сети;
 * ограничение не даёт упереться в лимит сервера (20 вопросов в минуту) одной кнопкой.
 */
const MAX_ATTEMPTS = 3;

type Turn =
  | { id: number; role: 'user'; text: string; questionId: number; attempt: number }
  | { id: number; role: 'assistant'; data: Explained<AskAnswer>; questionId: number };

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
  // Сколько раз уже отправлен каждый вопрос (ключ — id первой отправки).
  const [attempts, setAttempts] = useState<Record<number, number>>({});
  const [failed, setFailed] = useState<{ questionId: number; text: string } | null>(null);
  const ask = useAsk();
  const saveHistory = useSaveHistory();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Один диалог — одна запись в истории. Компонент пересоздаётся при смене
  // сценария (key в ScenarioDialogRoute), поэтому и id диалога новый.
  const dialogId = useRef(createId());
  const startedAt = useRef(new Date().toISOString());
  const title = useRef<string | null>(null);

  const persist = (messages: Turn[]) => {
    saveHistory.mutate({
      id: dialogId.current,
      scenarioId: scenario.id,
      title: title.current ?? '',
      createdAt: startedAt.current,
      messages: messages.map(toHistoryMessage),
    });
  };

  /** Отправка вопроса. base — диалог, в котором вопрос уже показан. */
  const send = (text: string, questionId: number, base: Turn[]) => {
    setAttempts((current) => ({ ...current, [questionId]: (current[questionId] ?? 0) + 1 }));
    setFailed(null);
    // Сохраняем уже вопрос: если пользователь уйдёт до ответа, запись не потеряется.
    persist(base);

    ask.mutate(
      { question: text, scenarioId: scenario.id },
      {
        onSuccess: (data) => {
          const next: Turn[] = [...base, { id: Date.now() + 1, role: 'assistant', data, questionId }];
          setTurns(next);
          haptic(data.dataQuality.sufficient ? 'success' : 'warning');
          persist(next);
        },
        onError: () => {
          setFailed({ questionId, text });
          haptic('error');
        },
      },
    );
  };

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || ask.isPending) return;

    // Заголовок записи в истории — первый вопрос пользователя в этом диалоге.
    if (!title.current) title.current = trimmed;

    const questionId = Date.now();
    const withUser: Turn[] = [
      ...turns,
      { id: questionId, role: 'user', text: trimmed, questionId, attempt: 1 },
    ];
    setTurns(withUser);
    setDraft('');
    send(trimmed, questionId, withUser);
  };

  /** Тот же вопрос ещё раз — помощник сформулирует ответ заново. */
  const askAgain = (questionId: number) => {
    const used = attempts[questionId] ?? 0;
    const question = turns.find((turn) => turn.role === 'user' && turn.questionId === questionId);
    if (ask.isPending || used >= MAX_ATTEMPTS || question?.role !== 'user') return;
    haptic('light');
    const withRepeat: Turn[] = [
      ...turns,
      { id: Date.now(), role: 'user', text: question.text, questionId, attempt: used + 1 },
    ];
    setTurns(withRepeat);
    send(question.text, questionId, withRepeat);
  };

  /** После сбоя вопрос уже на экране — отправляем его снова без новой реплики. */
  const retryFailed = () => {
    if (!failed || ask.isPending || (attempts[failed.questionId] ?? 0) >= MAX_ATTEMPTS) return;
    haptic('light');
    send(failed.text, failed.questionId, turns);
  };

  const last = turns[turns.length - 1];

  // Нативная кнопка «назад» в Telegram, своя в шапке на сайте.
  useBackButton(() => navigate('/app/assistant'));

  useMainButton(
    draft.trim()
      ? { text: 'Отправить', loading: ask.isPending, onClick: () => submit(draft) }
      : null,
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns.length, ask.isPending, failed]);

  return (
    <Screen title={scenario.title} subtitle={scenario.tagline}>
      <Greeting scenario={scenario} />

      {turns.map((turn) =>
        turn.role === 'assistant' ? (
          <AnswerCard key={turn.id} answer={turn.data} />
        ) : turn.attempt > 1 ? (
          <p key={turn.id} className="text-center text-xs text-muted">
            ↻ Тот же вопрос ещё раз · попытка {turn.attempt} из {MAX_ATTEMPTS}
          </p>
        ) : (
          <UserBubble key={turn.id} text={turn.text} />
        ),
      )}

      {last?.role === 'assistant' && !ask.isPending && !failed && (
        <AskAgain
          left={MAX_ATTEMPTS - (attempts[last.questionId] ?? 0)}
          onClick={() => askAgain(last.questionId)}
        />
      )}

      {ask.isPending && (
        <Card>
          <Skeleton className="mb-2 h-4 w-full" />
          <Skeleton className="mb-2 h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </Card>
      )}

      {failed && !ask.isPending && (
        <Card>
          <p className="mb-1 font-medium text-negative">Ответ не пришёл</p>
          <p className="mb-3 text-sm text-muted">
            {ask.error instanceof Error ? ask.error.message : 'Не удалось связаться с помощником.'}
          </p>
          {(attempts[failed.questionId] ?? 0) < MAX_ATTEMPTS ? (
            <Button variant="secondary" size="sm" onClick={retryFailed}>
              Отправить ещё раз
            </Button>
          ) : (
            <p className="text-sm text-muted">
              Попытки для этого вопроса закончились — попробуйте позже.
            </p>
          )}
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

        {draft && (
          <Button variant="ghost" size="sm" onClick={() => setDraft('')}>
            Очистить
          </Button>
        )}
      </div>

      <div ref={bottomRef} />
    </Screen>
  );
}

/** «Спросить ещё раз» под последним ответом — или объяснение, почему повторов больше нет. */
function AskAgain({ left, onClick }: { left: number; onClick: () => void }) {
  if (left <= 0) {
    return (
      <p className="text-center text-xs text-muted">
        Повторы для этого вопроса закончились — переформулируйте его, если ответ не подошёл.
      </p>
    );
  }
  return (
    <div className="flex items-center justify-center gap-2">
      <Button variant="ghost" size="sm" onClick={onClick}>
        ↻ Спросить ещё раз
      </Button>
      <span className="text-xs text-muted">осталось {left}</span>
    </div>
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
