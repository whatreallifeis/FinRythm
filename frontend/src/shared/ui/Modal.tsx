import { useEffect, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useBackButton } from '@/platform';

/**
 * Модальное окно по центру экрана.
 *
 * Рисуется в document.body, чтобы затемнение накрывало таббар и боковое меню,
 * а не только область контента. Закрывается по крестику, по фону, по Escape
 * и нативной кнопкой «назад» в Telegram.
 */
export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const [present, setPresent] = useState(open);
  const [phase, setPhase] = useState<'in' | 'out'>(open ? 'in' : 'out');

  useBackButton(open ? onClose : null);

  useEffect(() => {
    if (open) {
      setPresent(true);
      setPhase('in');
      return;
    }

    setPhase('out');
    const timeout = window.setTimeout(() => setPresent(false), 200);
    return () => window.clearTimeout(timeout);
  }, [open]);

  useEffect(() => {
    if (!present) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', onKey);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKey);
    };
  }, [present, onClose]);

  if (!present) return null;

  return createPortal(
    <div
      role="presentation"
      className={
        phase === 'in'
          ? 'ios-fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-10'
          : 'ios-fade-out fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-10'
      }
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className={
          phase === 'in'
            ? 'ios-pop-in flex max-h-[min(72dvh,560px)] w-full max-w-[420px] flex-col rounded-card border border-border bg-surface shadow-xl shadow-black/50'
            : 'ios-pop-out flex max-h-[min(72dvh,560px)] w-full max-w-[420px] flex-col rounded-card border border-border bg-surface shadow-xl shadow-black/50'
        }
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
          <h2 id="modal-title" className="text-lg font-semibold">
            {title}
          </h2>
          <button
            type="button"
            aria-label="Закрыть"
            onClick={onClose}
            className="flex size-8 shrink-0 items-center justify-center rounded-[10px] text-muted transition-colors hover:bg-surface-hover hover:text-text"
          >
            ×
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
