import { useEffect, useState } from 'react';
import { usePlatform } from '@/platform';
import { useDeleteAutopayment, useRenameOperation } from '@/shared/api/hooks';
import { operationTitleSchema } from '@/shared/api/schemas';
import type { DayOperation } from '@/shared/api/types';
import { categoryLabel } from '@/shared/lib/categories';
import { formatDate, formatSigned } from '@/shared/lib/format';
import { Button, Field, FIELD_CLASS, Modal } from '@/shared/ui';

function scopeHint(operation: DayOperation) {
  if (operation.ref.kind === 'autopayment') {
    return 'Это автоплатёж: название поменяется во всех будущих списаниях и в истории платежа.';
  }
  if (operation.ref.kind === 'income') {
    return 'Это регулярное поступление: название поменяется во всех будущих зачислениях и в истории.';
  }
  return operation.isRecurring
    ? 'Операция регулярная: название поменяется во всей её истории и в будущих платежах.'
    : 'Изменится название только этой операции.';
}

/**
 * Переименование операции из блока дня.
 *
 * Модалка держит последнюю открытую операцию, пока играет анимация закрытия, —
 * иначе содержимое исчезло бы раньше самого окна.
 */
export function OperationEditModal({
  operation,
  date,
  onClose,
}: {
  operation: DayOperation | null;
  date: string;
  onClose: () => void;
}) {
  const [shown, setShown] = useState(operation);
  // Счётчик открытий: каждое открытие начинает форму с чистого листа.
  const [session, setSession] = useState(0);

  useEffect(() => {
    if (operation) {
      setShown(operation);
      setSession((n) => n + 1);
    }
  }, [operation]);

  const isIncome = shown ? shown.amount > 0 : false;

  return (
    <Modal
      open={Boolean(operation)}
      title={isIncome ? 'Название поступления' : 'Название траты'}
      onClose={onClose}
    >
      {shown && (
        <RenameForm
          key={session}
          operation={shown}
          date={date}
          onDone={onClose}
        />
      )}
    </Modal>
  );
}

function RenameForm({
  operation,
  date,
  onDone,
}: {
  operation: DayOperation;
  date: string;
  onDone: () => void;
}) {
  const { haptic } = usePlatform();
  const rename = useRenameOperation();
  const remove = useDeleteAutopayment();

  const [title, setTitle] = useState(operation.title);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isAutopayment = operation.ref.kind === 'autopayment';
  const unchanged = title.trim() === operation.title;

  const submit = () => {
    const parsed = operationTitleSchema.safeParse(title);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? 'проверьте название');
      haptic('error');
      return;
    }
    if (parsed.data === operation.title) {
      onDone();
      return;
    }

    setError(null);
    rename.mutate(
      { ref: operation.ref, title: parsed.data },
      {
        onSuccess: () => {
          haptic('success');
          onDone();
        },
        onError: (err) => {
          setError(err instanceof Error ? err.message : 'Не удалось сохранить название');
          haptic('error');
        },
      },
    );
  };

  const deleteAutopayment = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      haptic('warning');
      return;
    }
    remove.mutate(operation.ref.id, {
      onSuccess: () => {
        haptic('success');
        onDone();
      },
      onError: (err) => {
        setError(err instanceof Error ? err.message : 'Не удалось удалить автоплатёж');
        haptic('error');
      },
    });
  };

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="flex items-baseline justify-between gap-3 rounded-card bg-bg p-3 text-sm">
        <span className="text-muted">
          {categoryLabel(operation.category)} ·{' '}
          {operation.ref.kind === 'transaction'
            ? formatDate(date)
            : `каждый месяц, ${Number(date.slice(8))}-го`}
        </span>
        <span className={operation.amount > 0 ? 'tabular text-positive' : 'tabular font-medium'}>
          {formatSigned(operation.amount)}
        </span>
      </div>

      <Field label="Название" error={error ?? undefined} hint={scopeHint(operation)}>
        <input
          autoFocus
          value={title}
          maxLength={60}
          onChange={(e) => {
            setTitle(e.target.value);
            setError(null);
          }}
          className={FIELD_CLASS}
        />
      </Field>

      <div className="flex gap-2">
        <Button variant="secondary" fullWidth onClick={onDone}>
          Отмена
        </Button>
        <Button type="submit" fullWidth loading={rename.isPending} disabled={unchanged}>
          Сохранить
        </Button>
      </div>

      {isAutopayment && (
        <Button
          variant="danger"
          size="sm"
          fullWidth
          loading={remove.isPending}
          onClick={deleteAutopayment}
        >
          {confirmDelete ? 'Точно удалить автоплатёж?' : 'Удалить автоплатёж'}
        </Button>
      )}
    </form>
  );
}
