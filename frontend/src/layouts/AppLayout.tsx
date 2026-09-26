import { useEffect, useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { usePlatform } from '@/platform';
import { useDatasetStatus } from '@/shared/api/dataset';
import type { MainButtonConfig } from '@/platform';
import { Button } from '@/shared/ui';
import { Disclaimer } from '@/features/explain/Disclaimer';
import { MotionStage } from '@/shared/motion/MotionStage';
import { SideNav } from './SideNav';
import { TabBar } from './TabBar';

/**
 * Один лэйаут на обе платформы.
 *
 * Разница только в обвязке: в Mini App и на узком экране — нижний таббар,
 * на широком — боковое меню. Сами экраны (Outlet) одни и те же, поэтому
 * оформление совпадает.
 */
export function AppLayout() {
  const platform = usePlatform();
  const { isCompact, subscribeMainButton, subscribeBackButton, insets } = platform;

  // В браузере главную кнопку и «назад» рисуем сами; в Telegram они нативные
  // и подписки отдают null.
  const [mainButton, setMainButton] = useState<MainButtonConfig | null>(null);
  const [backHandler, setBackHandler] = useState<(() => void) | null>(null);

  useEffect(() => subscribeMainButton(setMainButton), [subscribeMainButton]);
  useEffect(() => subscribeBackButton((h) => setBackHandler(() => h)), [subscribeBackButton]);

  const hasOwnMainButton = mainButton !== null;
  const { ready, loading } = useDatasetStatus();
  const { pathname } = useLocation();
  const content = loading ? null : !ready && pathname !== '/app/import' ? (
    <Navigate to="/app/import" replace />
  ) : (
    <MotionStage>
      <Outlet />
      <Disclaimer />
    </MotionStage>
  );

  if (!isCompact) {
    return (
      <div className="flex min-h-dvh">
        <SideNav />
        <main className="flex flex-1 flex-col overflow-x-hidden">
          <div className="flex-1">
            <div className="mx-auto w-full max-w-[720px] px-6 py-8">
              {content}
            </div>
          </div>
          {hasOwnMainButton && <WebMainButton config={mainButton} floating={false} />}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-dvh" style={{ paddingTop: insets.top }}>
      <div
        className="mx-auto w-full max-w-[480px] px-4 pt-4"
        // Запас снизу: таббар 56px + главная кнопка, если она своя.
        style={{ paddingBottom: hasOwnMainButton ? 140 : 84 }}
      >
        {backHandler && (
          <button
            type="button"
            onClick={backHandler}
            className="mb-3 -ml-1 flex items-center gap-1 text-sm text-muted transition-colors hover:text-text"
          >
            <span aria-hidden>‹</span> Назад
          </button>
        )}
        {content}
      </div>

      {hasOwnMainButton && <WebMainButton config={mainButton} floating />}
      <TabBar />
    </div>
  );
}

/**
 * Главная кнопка экрана в браузере.
 *
 * Экраны её не рисуют сами — они объявляют действие через useMainButton.
 * Так одно и то же объявление превращается в нативный MainButton в Telegram
 * и в кнопку здесь, и действие не может продублироваться.
 */
function WebMainButton({
  config,
  floating,
}: {
  config: MainButtonConfig;
  floating: boolean;
}) {
  if (!floating) {
    return (
      <div className="sticky bottom-0 border-t border-border bg-bg-elevated/95 backdrop-blur">
        <div className="mx-auto w-full max-w-[720px] px-6 py-3">
          <Button
            size="lg"
            fullWidth
            loading={config.loading}
            disabled={config.disabled}
            onClick={config.onClick}
          >
            {config.text}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-x-0 z-20 mx-auto max-w-[480px] px-4"
      style={{ bottom: 'calc(56px + max(var(--inset-bottom), env(safe-area-inset-bottom, 0px)) + 12px)' }}
    >
      <Button
        size="lg"
        fullWidth
        loading={config.loading}
        disabled={config.disabled}
        onClick={config.onClick}
        className="shadow-lg shadow-black/25"
      >
        {config.text}
      </Button>
    </div>
  );
}
