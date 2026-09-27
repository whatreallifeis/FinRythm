import { useState } from 'react';
import { useBackButton, usePlatform } from '@/platform';
import { goalDraftSchema } from '@/shared/api/schemas';
import type { Goal, GoalDraft } from '@/shared/api/types';
import { Button, Card, Field, FIELD_CLASS as FIELD } from '@/shared/ui';

/**
 * Форма создания и редактирования цели.
 *
 * Одна и та же форма на оба случая: разница только в начальных значениях
 * и подписи кнопки. Валидация — та же схема, что уйдёт на бэкенд.
 */
export function GoalForm({
  goal,
  loading,
  error,
  onSubmit,
  onCancel,
}: {
  goal?: Goal;
  loading: boolean;
  error: string | null;
  onSubmit: (draft: GoalDraft) => void;
  onCancel: () => void;
}) {
  const { haptic } = usePlatform();
  const isEdit = Boolean(goal);

  const [title, setTitle] = useState(goal?.title ?? '');
  const [target, setTarget] = useState(goal ? String(goal.targetAmount) : '');
  const [saved, setSaved] = useState(goal ? String(goal.savedAmount) : '0');
  const [deadline, setDeadline] = useState(goal?.deadline ?? '');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const submit = () => {
    const parsed = goalDraftSchema.safeParse({
      title,
      targetAmount: target === '' ? NaN : Number(target.replace(/\s/g, '').replace(',', '.')),
      savedAmount: saved === '' ? NaN : Number(saved.replace(/\s/g, '').replace(',', '.')),
      deadline: deadline === '' ? null : deadline,
    });

    if (!parsed.success) {
      const next: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0] ?? 'form');
        if (!next[key]) next[key] = issue.message;
      }
      setFieldErrors(next);
      haptic('error');
      return;
    }

    setFieldErrors({});
    onSubmit(parsed.data);
  };

  useBackButton(onCancel);

  return (
    <Card>
      <p className="mb-4 font-semibold">{isEdit ? 'Редактирование цели' : 'Новая цель'}</p>

      <div className="space-y-3">
        <Field label="Название" error={fieldErrors.title}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Например: ноутбук для учёбы"
            className={FIELD}
          />
        </Field>

        <Field label="Сколько нужно, ₽" error={fieldErrors.targetAmount}>
          <input
            inputMode="numeric"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="75000"
            className={`${FIELD} tabular`}
          />
        </Field>

        <Field label="Уже накоплено, ₽" error={fieldErrors.savedAmount}>
          <input
            inputMode="numeric"
            value={saved}
            onChange={(e) => setSaved(e.target.value)}
            placeholder="0"
            className={`${FIELD} tabular`}
          />
        </Field>

        <Field
          label="Срок"
          error={fieldErrors.deadline}
          hint="Можно оставить пустым — тогда срок не задан"
        >
          <input
            type="date"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
            className={FIELD}
          />
        </Field>
      </div>

      {error && <p className="mt-3 text-sm text-negative">{error}</p>}

      <div className="mt-4 flex gap-2">
        <Button variant="secondary" fullWidth onClick={onCancel}>
          Отмена
        </Button>
        <Button fullWidth loading={loading} onClick={submit}>
          {isEdit ? 'Сохранить' : 'Добавить'}
        </Button>
      </div>
    </Card>
  );
}
