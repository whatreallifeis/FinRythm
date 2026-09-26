import type { Explained } from '@/shared/api/types';
import { Collapsible } from '@/shared/ui';
import { usePlatform } from '@/platform';

/**
 * Блок «на чём основан результат».
 *
 * Закрывает сразу четыре требования ТЗ к результату: допущения, расчёты,
 * источники и ограничения. Один компонент на все экраны — значит объяснение
 * выглядит одинаково везде и его нельзя забыть добавить.
 */
export function ExplainBlock({ data }: { data: Explained<unknown> }) {
  const { openExternal } = usePlatform();
  const { assumptions, calculation, sources, limitations } = data;

  const hasContent =
    assumptions.length > 0 ||
    calculation.length > 0 ||
    sources.length > 0 ||
    limitations.length > 0;

  if (!hasContent) return null;

  return (
    <div className="mt-4 space-y-3">
      {calculation.length > 0 && (
        <Collapsible title="Как это посчитано">
          <dl className="space-y-2">
            {calculation.map((step) => (
              <div key={step.label} className="flex items-baseline justify-between gap-3 text-sm">
                <div className="min-w-0">
                  <dt className="truncate">{step.label}</dt>
                  <dd className="text-xs text-muted">{step.formula}</dd>
                </div>
                <span className="tabular shrink-0 font-medium">
                  {step.value.toLocaleString('ru-RU')}
                </span>
              </div>
            ))}
          </dl>
        </Collapsible>
      )}

      {assumptions.length > 0 && (
        <Collapsible title={`Допущения (${assumptions.length})`}>
          <ul className="space-y-1.5 text-sm text-muted">
            {assumptions.map((item) => (
              <li key={item} className="flex gap-2">
                <span aria-hidden>•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {sources.length > 0 && (
        <Collapsible title="Источники" defaultOpen>
          <ul className="space-y-1.5 text-sm">
            {sources.map((source) => (
              <li key={source.url}>
                <button
                  type="button"
                  onClick={() => openExternal(source.url)}
                  className="text-left text-info underline decoration-info/40 underline-offset-2"
                >
                  {source.title}
                </button>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {limitations.length > 0 && (
        <Collapsible title="Ограничения">
          <ul className="space-y-1.5 text-sm text-muted">
            {limitations.map((item) => (
              <li key={item} className="flex gap-2">
                <span aria-hidden className="text-warning">
                  !
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}
    </div>
  );
}
