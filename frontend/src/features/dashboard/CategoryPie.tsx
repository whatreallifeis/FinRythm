import type { CategorySlice } from '@/shared/api/types';
import { categoryColor, categoryLabel } from '@/shared/lib/categories';
import { formatMoney, formatPercent } from '@/shared/lib/format';
import { Badge } from '@/shared/ui';

const SIZE = 196;
const CENTER = SIZE / 2;
const RADIUS = 68;
const STROKE = 32;
const CIRC = 2 * Math.PI * RADIUS;
const GAP = 3;

/**
 * Круговая диаграмма расходов по категориям.
 *
 * SVG без сторонней библиотеки: меньше бандл и нет лишней зависимости в Mini App.
 */
export function CategoryPie({ slices }: { slices: CategorySlice[] }) {
  const visible = slices.filter((slice) => slice.amount > 0 && slice.share > 0);
  const total = visible.reduce((sum, slice) => sum + slice.amount, 0);

  if (visible.length === 0) {
    return <p className="text-sm text-muted">Расходов за период нет</p>;
  }

  let offset = 0;

  return (
    <div className="space-y-4">
      <div className="flex justify-center">
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="img"
          aria-label="Расходы по категориям"
        >
          {visible.map((slice) => {
            const length = Math.max(slice.share * CIRC - GAP, 0);
            const dashOffset = offset;
            offset += slice.share * CIRC;

            return (
              <circle
                key={slice.category}
                cx={CENTER}
                cy={CENTER}
                r={RADIUS}
                fill="none"
                stroke={categoryColor(slice.category)}
                strokeWidth={STROKE}
                strokeDasharray={`${length} ${CIRC - length}`}
                strokeDashoffset={-dashOffset}
                transform={`rotate(-90 ${CENTER} ${CENTER})`}
              />
            );
          })}

          <text
            x={CENTER}
            y={CENTER - 8}
            textAnchor="middle"
            className="fill-text tabular"
            fontSize="15"
            fontWeight="600"
          >
            {formatMoney(total)}
          </text>
          <text
            x={CENTER}
            y={CENTER + 12}
            textAnchor="middle"
            className="fill-muted"
            fontSize="11"
          >
            расходы
          </text>
        </svg>
      </div>

      <ul className="space-y-2">
        {visible.map((slice) => (
          <li key={slice.category} className="flex items-center justify-between gap-2 text-sm">
            <span className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden
                className="size-2.5 shrink-0 rounded-full"
                style={{ background: categoryColor(slice.category) }}
              />
              <span className="truncate">{categoryLabel(slice.category)}</span>
              {slice.deltaPercent !== null && Math.abs(slice.deltaPercent) >= 20 && (
                <Badge tone={slice.deltaPercent > 0 ? 'negative' : 'positive'}>
                  {slice.deltaPercent > 0 ? '+' : '−'}
                  {Math.abs(slice.deltaPercent)}%
                </Badge>
              )}
            </span>
            <span className="tabular shrink-0 text-muted">
              {formatPercent(slice.share)} · {formatMoney(slice.amount)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
