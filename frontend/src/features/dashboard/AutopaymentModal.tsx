import { useEffect, useState } from 'react';
import { usePlatform } from '@/platform';
import { useCreateAutopayment } from '@/shared/api/hooks';
import { autopaymentDraftSchema } from '@/shared/api/schemas';
import type { CategoryId } from '@/shared/api/types';
import { CATEGORY_META } from '@/shared/lib/categories';
import { Button, Field, FIELD_CLASS, Modal } from '@/shared/ui';

const CATEGORIES = Object.entries(CATEGORY_META) as Array<[CategoryId, { label: string }]>;

const toNumber = (raw: string) => (raw.trim() === '' ? NaN : Number(raw.replace(/\s/g, '').replace(',', '.')));

/**
 * Новый автоплатёж в календаре.
 *
 * Число месяца подставляется из выбранного дня — пользователь чаще всего
 * добавляет платёж, глядя на конкретную дату, — но его можно поменять.
 */
export function AutopaymentModal({
  open,
  defaultDay,
  onClose,
}: {
  open: boolean;
  defaultDay: number;
  onClose: () => void;
}) {
  const [session, setSession] = useState(0);

  useEffect(() => {
    if (open) setSession((n) => n + 1);
  }, [open]);

  return (
    <Modal open={open} title="Новый автоплатёж" onClose={onClose}>
      <AutopaymentForm key={session} defaultDay={defaultDay} onDone={onClose} />
    </Modal>
  );
}

function AutopaymentForm({ defaultDay, onDone }: { defaultDay: number; onDone: () => void }) {
  const { haptic } = usePlatform();
  const create = useCreateAutopayment();

  const [title, setTitle] = useState('');
  const [amount, setAmount] = useState('');
  const [day, setDay] = useState(String(defaultDay));
  const [category, setCategory] = useState<CategoryId>('other');
  const [errors, setErrors] = useState<Record<string, string>>({});

  /** Ошибка поля пропадает, как только пользователь начал его исправлять. */
  const change = (field: string, set: (value: string) => void) => (value: string) => {
    set(value);
    setErrors(({ [field]: _, form: __, ...rest }) => rest);
  };

  const submit = () => {
    const parsed = autopaymentDraftSchema.safeParse({
      title,
      amount: toNumber(amount),
      dayOfMonth: toNumber(day),
      category,
    });

    if (!parsed.success) {
      const next: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0] ?? 'form');
        if (!next[key]) next[key] = issue.message;
      }
      setErrors(next);
      haptic('error');
      return;
    }

    setErrors({});
    create.mutate(parsed.data, {
      onSuccess: () => {
        haptic('success');
        onDone();
      },
      onError: (err) => {
        setErrors({ form: err instanceof Error ? err.message : 'Не удалось добавить автоплатёж' });
        haptic('error');
      },
    });
  };

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <p className="text-sm text-muted">
        Платёж встанет в календарь на это число каждого месяца и сразу учтётся в прогнозе
        остатка и дневном лимите.
      </p>

      <Field label="Название" error={errors.title}>
        <input
          autoFocus
          value={title}
          maxLength={60}
          onChange={(e) => change('title', setTitle)(e.target.value)}
          placeholder="Например: спортзал"
          className={FIELD_CLASS}
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Сумма, ₽" error={errors.amount}>
          <input
            inputMode="decimal"
            value={amount}
            onChange={(e) => change('amount', setAmount)(e.target.value)}
            placeholder="1500"
            className={`${FIELD_CLASS} tabular`}
          />
        </Field>

        <Field label="Число месяца" error={errors.dayOfMonth}>
          <input
            inputMode="numeric"
            value={day}
            onChange={(e) => change('dayOfMonth', setDay)(e.target.value)}
            placeholder="1–31"
            className={`${FIELD_CLASS} tabular`}
          />
        </Field>
      </div>

      <Field label="Категория" error={errors.category}>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value as CategoryId)}
          className={FIELD_CLASS}
        >
          {CATEGORIES.map(([id, meta]) => (
            <option key={id} value={id}>
              {meta.label}
            </option>
          ))}
        </select>
      </Field>

      <p className="text-xs text-muted">
        Если в месяце меньше дней, чем выбранное число, платёж придётся на последний день месяца.
      </p>

      {errors.form && <p className="text-sm text-negative">{errors.form}</p>}

      <div className="flex gap-2 pt-1">
        <Button variant="secondary" fullWidth onClick={onDone}>
          Отмена
        </Button>
        <Button type="submit" fullWidth loading={create.isPending}>
          Добавить
        </Button>
      </div>
    </form>
  );
}
