import type { ReactNode } from 'react';
import type { Explained } from '@/shared/api/types';
import { ScreenState, InsufficientData } from '@/shared/ui';
import { ExplainBlock } from './ExplainBlock';

interface QueryLike<T> {
  data: T | undefined;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

/**
 * Обёртка для любого аналитического ответа.
 *
 * Берёт на себя всё, что повторяется на каждом экране:
 *   загрузка → ошибка → «данных недостаточно» → результат + объяснение.
 *
 * Экрану остаётся описать только сам результат. Это главная причина, по которой
 * ответы бэкенда обязаны приходить в обёртке Explained<T>.
 */
export function ExplainedView<T>({
  query,
  skeleton,
  insufficientAction,
  children,
}: {
  query: QueryLike<Explained<T>>;
  skeleton?: ReactNode;
  insufficientAction?: ReactNode;
  children: (result: T) => ReactNode;
}) {
  return (
    <ScreenState query={query} skeleton={skeleton}>
      {(data) =>
        data.dataQuality.sufficient ? (
          <>
            {children(data.result)}
            <ExplainBlock data={data} />
          </>
        ) : (
          <InsufficientData missing={data.dataQuality.missing} action={insufficientAction} />
        )
      }
    </ScreenState>
  );
}
