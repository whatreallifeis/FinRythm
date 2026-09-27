import { useMemo } from 'react';
import { usePlatform } from '@/platform';
import { parseCsv } from '@/shared/lib/csv';
import { formatDate, formatMoney } from '@/shared/lib/format';
import { Card, CardTitle } from '@/shared/ui';
import { DATASET_PRESETS, type DatasetPreset } from './presets';

function operationsWord(n: number) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'операция';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'операции';
  return 'операций';
}

/**
 * Готовые выписки для проверки платформы.
 *
 * Выписка разбирается тем же парсером, что и файл пользователя, и уходит
 * на сервер тем же путём — так проверяется весь сценарий, а не подставленный
 * снимок данных.
 */
export function PresetPicker({ onPick }: { onPick: (preset: DatasetPreset) => void }) {
  const { haptic } = usePlatform();

  const stats = useMemo(
    () =>
      DATASET_PRESETS.map((preset) => {
        const { rows } = parseCsv(preset.csv);
        const dates = rows.map((row) => row.date).sort();
        return { count: rows.length, from: dates[0], to: dates[dates.length - 1] };
      }),
    [],
  );

  return (
    <Card>
      <CardTitle>Готовые выписки</CardTitle>
      <p className="-mt-1 mb-3 text-sm text-muted">
        Синтетические выписки в формате банковской — чтобы проверить календарь, справки и
        помощника без своих данных. Загрузка заменит текущие операции, цели и историю.
      </p>

      <div className="space-y-2">
        {DATASET_PRESETS.map((preset, i) => (
          <button
            key={preset.id}
            type="button"
            onClick={() => {
              haptic('light');
              onPick(preset);
            }}
            className="flex w-full items-start gap-3 rounded-card border border-border bg-bg p-3 text-left transition-colors hover:border-accent/60 hover:bg-surface-hover"
          >
            <span
              aria-hidden
              className="tabular flex size-8 shrink-0 items-center justify-center rounded-[10px] bg-accent text-sm font-semibold text-accent-text"
            >
              {i + 1}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-semibold">{preset.title}</span>
              <span className="mt-0.5 block text-sm text-muted">{preset.persona}</span>
              <span className="mt-1.5 block text-xs text-muted">
                {stats[i].count} {operationsWord(stats[i].count)} · {formatDate(stats[i].from)} –{' '}
                {formatDate(stats[i].to)} · баланс {formatMoney(preset.balance)} · {preset.fileName}
              </span>
              <span className="mt-1 block text-xs">
                <span className="text-muted">Что проверить: </span>
                {preset.check}
              </span>
            </span>
            <span aria-hidden className="shrink-0 self-center text-muted">
              ›
            </span>
          </button>
        ))}
      </div>
    </Card>
  );
}
