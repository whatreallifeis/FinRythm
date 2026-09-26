import type { ReactNode } from 'react';
import type { AskAnswer, Explained } from '@/shared/api/types';
import { Card, InsufficientData } from '@/shared/ui';
import { ExplainBlock } from '@/features/explain/ExplainBlock';

/**
 * Ответ помощника: либо результат с объяснением, либо честный отказ.
 *
 * Один компонент используется и в живом диалоге, и в истории запросов, поэтому
 * сохранённый ответ выглядит ровно так же, как в момент получения.
 */
export function AnswerCard({
  answer,
  insufficientAction,
}: {
  answer: Explained<AskAnswer>;
  insufficientAction?: ReactNode;
}) {
  return (
    <Card>
      {answer.dataQuality.sufficient ? (
        <>
          <p className="text-[15px] leading-relaxed whitespace-pre-line">{answer.result.text}</p>
          <ExplainBlock data={answer} />
        </>
      ) : (
        <InsufficientData missing={answer.dataQuality.missing} action={insufficientAction} />
      )}
    </Card>
  );
}

/** Реплика пользователя. */
export function UserBubble({ text }: { text: string }) {
  return (
    <div className="ml-auto max-w-[85%] rounded-card bg-surface-hover px-3 py-2 text-sm whitespace-pre-line">
      {text}
    </div>
  );
}
