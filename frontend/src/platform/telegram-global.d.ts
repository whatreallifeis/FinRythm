/**
 * Минимальная типизация window.Telegram.WebApp — ровно те поля, которые
 * использует platform/telegram.ts.
 *
 * Здесь сознательно используется глобальный скрипт telegram-web-app.js, а не
 * npm-пакет: у скелета меньше зависимостей и нечему ломаться при установке.
 * Если позже захотите @telegram-apps/sdk-react — менять придётся ровно один
 * файл, platform/telegram.ts, потому что остальное приложение о Telegram
 * ничего не знает.
 */

export interface TelegramWebAppUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
}

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: TelegramWebAppUser;
    start_param?: string;
  };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  viewportStableHeight: number;
  safeAreaInset?: { top: number; bottom: number; left: number; right: number };
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number };

  ready(): void;
  expand(): void;
  close(): void;
  isVersionAtLeast(version: string): boolean;

  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  disableVerticalSwipes?(): void;

  onEvent(event: string, handler: () => void): void;
  offEvent(event: string, handler: () => void): void;

  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;

  BackButton: {
    isVisible: boolean;
    show(): void;
    hide(): void;
    onClick(handler: () => void): void;
    offClick(handler: () => void): void;
  };

  MainButton: {
    text: string;
    color: string;
    textColor: string;
    isVisible: boolean;
    isActive: boolean;
    show(): void;
    hide(): void;
    enable(): void;
    disable(): void;
    showProgress(leaveActive?: boolean): void;
    hideProgress(): void;
    setParams(params: {
      text?: string;
      color?: string;
      text_color?: string;
      is_active?: boolean;
      is_visible?: boolean;
    }): void;
    onClick(handler: () => void): void;
    offClick(handler: () => void): void;
  };

  HapticFeedback: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(type: 'error' | 'success' | 'warning'): void;
  };

  CloudStorage: {
    getItem(key: string, cb: (err: string | null, value?: string) => void): void;
    setItem(key: string, value: string, cb?: (err: string | null, ok?: boolean) => void): void;
    removeItem(key: string, cb?: (err: string | null, ok?: boolean) => void): void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}
