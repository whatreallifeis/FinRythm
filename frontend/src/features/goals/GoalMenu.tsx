import { useEffect, useRef, useState } from 'react';
import { cn } from '@/shared/lib/cn';

/**
 * Меню цели: редактировать или удалить.
 *
 * Удаление двухшаговое — сразу не стираем, чтобы случайный тап не уничтожил цель.
 */
export function GoalMenu({
  onEdit,
  onDelete,
  deleting,
}: {
  onEdit: () => void;
  onDelete: () => void;
  deleting?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setConfirm(false);
      }
    };

    document.addEventListener('pointerdown', onPointer);
    return () => document.removeEventListener('pointerdown', onPointer);
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Действия с целью"
        onClick={() => {
          setOpen((value) => !value);
          setConfirm(false);
        }}
        className="flex size-9 items-center justify-center rounded-[10px] text-muted transition-colors hover:bg-surface-hover hover:text-text"
      >
        ⋯
      </button>

      {open && (
        <div
          role="menu"
          className="ios-menu-in absolute top-10 right-0 z-30 min-w-[180px] overflow-hidden rounded-card border border-border bg-bg-elevated py-1 shadow-lg shadow-black/30"
        >
          <MenuItem
            onClick={() => {
              setOpen(false);
              onEdit();
            }}
          >
            Редактировать
          </MenuItem>

          {confirm ? (
            <MenuItem
              danger
              onClick={() => {
                if (!deleting) onDelete();
              }}
            >
              {deleting ? 'Удаляю…' : 'Точно удалить?'}
            </MenuItem>
          ) : (
            <MenuItem danger onClick={() => setConfirm(true)}>
              Удалить
            </MenuItem>
          )}
        </div>
      )}
    </div>
  );
}

function MenuItem({
  children,
  onClick,
  danger,
}: {
  children: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={cn(
        'flex w-full px-3 py-2.5 text-left text-sm transition-colors hover:bg-surface-hover',
        danger ? 'text-negative' : 'text-text',
      )}
    >
      {children}
    </button>
  );
}
