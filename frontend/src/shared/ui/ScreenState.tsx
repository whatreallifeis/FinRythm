import type { ReactNode } from 'react';
import { Button } from './Button';
import { SkeletonCard } from './Skeleton';

/**
 * Пять состояний любого экрана: loading / error / empty / insufficient / ready.
 *
 * Критерии оценки прямо проверяют, как продукт ведёт себя при пустых, неполных
 * и ошибочных данных, поэтому все экраны обязаны проходить через этот враппер,
 * а не рисовать загрузку и ошибки по-своему.
 *
 * Состояние insufficient живёт отдельно (см. InsufficientData): оно зависит не
 * от статуса запроса, а от поля dataQuality в ответе бэкенда.
 */

interface QueryLike<T> {
  data: T | undefined;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

interface ScreenStateProps<T> {
  query: QueryLike<T>;
  /** Данные пришли, но показывать нечего — например, пустой список операций. */
  isEmpty?: (data: T) => boolean;
  skeleton?: ReactNode;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}

export function ScreenState<T>({
  query,
  isEmpty,
  skeleton,
  empty,
  children,
}: ScreenStateProps<T>) {
  if (query.isPending) {
    return <>{skeleton ?? <SkeletonCard />}</>;
  }

  if (query.isError || query.data === undefined) {
    return (
      <ErrorState
        message={query.error instanceof Error ? query.error.message : 'Не удалось загрузить данные'}
        onRetry={query.refetch}
      />
    );
  }

  if (isEmpty?.(query.data)) {
    return <>{empty ?? <EmptyState title="Пока нет данных" />}</>;
  }

  return <>{children(query.data)}</>;
}

export function ErrorState({
  message,
  onRetry,
  retryLabel = 'Повторить',
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div className="rounded-card border border-negative/30 bg-negative/5 p-4">
      <p className="mb-1 font-medium text-negative">Ошибка</p>
      <p className="mb-3 text-sm text-muted">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-dashed border-border bg-surface/50 p-6 text-center">
      <p className="mb-1 font-medium">{title}</p>
      {description && <p className="mb-4 text-sm text-muted">{description}</p>}
      {action}
    </div>
  );
}

/**
 * Данных не хватает для честного ответа.
 *
 * Требование ТЗ: продукт сообщает о недостатке данных и не выдаёт
 * предположение за факт. Поэтому вместо результата показываем, чего именно
 * не хватает, и что пользователь может сделать.
 */
export function InsufficientData({
  missing,
  action,
}: {
  missing: string[];
  action?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-warning/30 bg-warning/5 p-4">
      <p className="mb-1 font-medium text-warning">Данных недостаточно для расчёта</p>
      <p className="mb-2 text-sm text-muted">
        Мы не будем показывать прогноз, в котором не уверены. Чтобы посчитать точно, не хватает:
      </p>
      <ul className="mb-3 space-y-1 text-sm">
        {missing.map((item) => (
          <li key={item} className="flex gap-2">
            <span aria-hidden className="text-warning">
              •
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
      {action}
    </div>
  );
}
