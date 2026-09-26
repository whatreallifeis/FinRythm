import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { PlatformProvider } from '@/platform';
import { App } from '@/app/App';
import { ErrorBoundary } from '@/app/ErrorBoundary';
import { Providers } from '@/app/providers';
import '@/styles/index.css';

/**
 * HashRouter выбран намеренно: маршруты живут в хэше, поэтому статический
 * хостинг не нужно настраивать на SPA-fallback, а webview Telegram не путается
 * в истории при возврате из внешних ссылок.
 */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <PlatformProvider>
        <Providers>
          <HashRouter>
            <App />
          </HashRouter>
        </Providers>
      </PlatformProvider>
    </ErrorBoundary>
  </StrictMode>,
);
