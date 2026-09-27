import { useState } from 'react';
import { useImpulseCheck } from '@/shared/api/hooks';
import type { Explained, ImpulseCheck } from '@/shared/api/types';
import { formatDate, formatMoney } from '@/shared/lib/format';
import { usePlatform } from '@/platform';
import { Badge, Button, InsufficientData, Skeleton } from '@/shared/ui';
import { ExplainBlock } from '@/features/explain/ExplainBlock';
import { RunwayCalendar } from './RunwayCalendar';

const EXAMPLES = [1500, 4900, 14900];

const VERDICT: Record<ImpulseCheck['verdict'], { tone: 'positive' | 'warning' | 'negative'; label: string }> =
  {
    ok: { tone: 'positive', label: 'Влезет сегодня' },
    wait: { tone: 'warning', label: 'Лучше подождать' },
    shortfall: { tone: 'negative', label: 'Сломает месяц' },
  };

/**
 * Проверка импульсной покупки на том же календаре, что и «дожить до стипендии».
 * Открывается в модальном окне с главной; заголовок рисует окно.
 */
export function ImpulsePanel() {
  const { haptic } = usePlatform();
  const [raw, setRaw] = useState('');
  const [answer, setAnswer] = useState<Explained<ImpulseCheck> | null>(null);
  const check = useImpulseCheck();

  const submit = (value: string) => {
    const amount = Number(value.replace(/\s/g, '').replace(',', '.'));
    check.mutate(amount, {
      onSuccess: (data) => {
        setAnswer(data);
        haptic(data.dataQuality.sufficient && data.result.verdict === 'ok' ? 'success' : 'warning');
      },
      onError: () => haptic('error'),
    });
  };

  return (
    <div>
      <p className="mb-3 text-sm text-muted">
        Сумма прогонится по календарю до стипендии — до покупки, а не после.
      </p>

      <div className="flex gap-2">
        <input
          inputMode="numeric"
          value={raw}
          onChange={(e) => {
            setRaw(e.target.value);
            setAnswer(null);
          }}
          placeholder="4900"
          className="tabular h-11 min-w-0 flex-1 rounded-card border border-border bg-bg px-3 text-sm outline-none placeholder:text-muted focus:border-accent/60"
        />
        <Button loading={check.isPending} onClick={() => submit(raw)}>
          Проверить
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {EXAMPLES.map((amount) => (
          <button
            key={amount}
            type="button"
            onClick={() => {
              setRaw(String(amount));
              submit(String(amount));
            }}
            className="rounded-full border border-border bg-bg px-3 py-1.5 text-xs text-muted transition-colors hover:bg-surface-hover hover:text-text"
          >
            {formatMoney(amount)}
          </button>
        ))}
      </div>

      {check.isPending && (
        <div className="mt-3">
          <Skeleton className="mb-2 h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      )}

      {answer && !check.isPending && (
        <div className="ios-reveal mt-3">
          {answer.dataQuality.sufficient ? (
            <ImpulseResult data={answer} />
          ) : (
            <InsufficientData missing={answer.dataQuality.missing} />
          )}
        </div>
      )}
    </div>
  );
}

function ImpulseResult({ data }: { data: Explained<ImpulseCheck> }) {
  const result = data.result;
  const badge = VERDICT[result.verdict];

  return (
    <div className="space-y-3 rounded-card border border-border bg-bg p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[15px] leading-relaxed">{result.hint}</p>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>

      <dl className="space-y-1.5 text-sm">
        <div className="flex justify-between gap-2">
          <dt className="text-muted">Лимит в день</dt>
          <dd className="tabular">
            {formatMoney(result.todaySafeSpendBefore)} → {formatMoney(result.todaySafeSpendAfter)}
          </dd>
        </div>
        {result.redDaysAfter !== result.redDaysBefore && (
          <div className="flex justify-between gap-2">
            <dt className="text-muted">Красных дней</dt>
            <dd className="tabular">
              {result.redDaysBefore} → {result.redDaysAfter}
            </dd>
          </div>
        )}
        {result.waitUntil && (
          <div className="flex justify-between gap-2">
            <dt className="text-muted">Подождать до</dt>
            <dd>
              {result.waitUntil.title}, {formatDate(result.waitUntil.date)}
            </dd>
          </div>
        )}
        {result.goalImpact && (
          <div className="flex justify-between gap-2">
            <dt className="text-muted">Цель «{result.goalImpact.goalTitle}»</dt>
            <dd>отодвинется примерно на {result.goalImpact.delayDays} дн.</dd>
          </div>
        )}
      </dl>

      {result.daysAfter.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">
            Календарь, если купить сегодня
          </p>
          <RunwayCalendar days={result.daysAfter} />
        </div>
      )}

      <ExplainBlock data={data} />
    </div>
  );
}
