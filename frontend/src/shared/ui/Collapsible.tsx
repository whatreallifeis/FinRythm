import { useId, useState, type ReactNode } from 'react';

/** Раскрывающийся блок. Используется для «как посчитано» и списка ограничений. */
export function Collapsible({
  title,
  defaultOpen = false,
  children,
}: {
  title: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <div className="border-t border-border pt-3">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 text-left text-sm font-medium text-muted transition-colors hover:text-text"
      >
        <span>{title}</span>
        <span aria-hidden className={open ? 'ios-chevron rotate-180' : 'ios-chevron'}>
          ⌄
        </span>
      </button>
      {open && (
        <div id={contentId} className="ios-reveal mt-3">
          {children}
        </div>
      )}
    </div>
  );
}
