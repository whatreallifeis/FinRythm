import type { ReactNode } from 'react';

/** Общий вид текстовых полей и списков в формах. */
export const FIELD_CLASS =
  'w-full rounded-card border border-border bg-bg px-3 py-2.5 text-sm outline-none placeholder:text-muted focus:border-accent/60';

/** Подпись, поле и ошибка валидации под ним. */
export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold tracking-wide text-muted uppercase">
        {label}
      </span>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p className="mt-1 text-xs text-negative">{error}</p>}
    </label>
  );
}
