import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { useSwipeStretch } from './useSwipeStretch';

/** Сцена экрана: короткий вход и резинка карточек на жест. */
export function MotionStage({ children }: { children: ReactNode }) {
  const ref = useSwipeStretch<HTMLDivElement>();
  const { pathname } = useLocation();

  return (
    <div ref={ref} className="motion-stage">
      <div key={pathname} className="screen-in">
        {children}
      </div>
    </div>
  );
}
