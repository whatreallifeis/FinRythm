import { createSlot } from './bridge';
import type { MainButtonConfig, Platform } from './types';
import type { TelegramWebApp } from './telegram-global';

const STORAGE_PREFIX = 'fin:';

/**
 * Реализация платформы для Telegram Mini App.
 *
 * Здесь же — единственное место, где мы подстраиваем нативный хедер под наш
 * фон, чтобы стык между Telegram и приложением был незаметен.
 */
export function createTelegramPlatform(tg: TelegramWebApp): Platform {
  const mainButton = createSlot<MainButtonConfig | null>(null);
  const backButton = createSlot<(() => void) | null>(null);

  tg.ready();
  tg.expand();

  // Свайп вниз внутри скроллящегося контента случайно закрывает Mini App.
  tg.disableVerticalSwipes?.();

  const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
  if (bg) {
    tg.setHeaderColor(bg);
    tg.setBackgroundColor(bg);
  }

  const safeArea = tg.contentSafeAreaInset ?? tg.safeAreaInset ?? { top: 0, bottom: 0 };

  const user = tg.initDataUnsafe.user;

  /** Текущий обработчик нативной кнопки, чтобы корректно его отцеплять. */
  let mainClickHandler: (() => void) | null = null;
  let backClickHandler: (() => void) | null = null;

  return {
    name: 'telegram',
    isCompact: true,
    colorScheme: tg.colorScheme,
    insets: { top: safeArea.top, bottom: safeArea.bottom },
    // Выбор файла в webview Telegram ненадёжен на iOS — просим вставить текст.
    fileInputMode: 'paste',

    userHint: user
      ? {
          id: String(user.id),
          displayName: [user.first_name, user.last_name].filter(Boolean).join(' ') || 'Пользователь',
        }
      : null,

    // Подпись initData проверяет ТОЛЬКО бэкенд (HMAC с токеном бота).
    // На фронте initDataUnsafe годится максимум для показа имени.
    getAuthPayload: () => ({ kind: 'telegram', initData: tg.initData }),

    setBackButton: (handler) => {
      if (backClickHandler) {
        tg.BackButton.offClick(backClickHandler);
        backClickHandler = null;
      }
      if (handler) {
        backClickHandler = handler;
        tg.BackButton.onClick(handler);
        tg.BackButton.show();
      } else {
        tg.BackButton.hide();
      }
      backButton.set(null);
    },

    setMainButton: (config) => {
      if (mainClickHandler) {
        tg.MainButton.offClick(mainClickHandler);
        mainClickHandler = null;
      }

      if (!config) {
        tg.MainButton.hideProgress();
        tg.MainButton.hide();
        mainButton.set(null);
        return;
      }

      const styles = getComputedStyle(document.documentElement);
      tg.MainButton.setParams({
        text: config.text,
        color: styles.getPropertyValue('--accent').trim() || undefined,
        text_color: styles.getPropertyValue('--accent-text').trim() || undefined,
        is_active: !config.disabled && !config.loading,
        is_visible: true,
      });

      if (config.loading) tg.MainButton.showProgress(false);
      else tg.MainButton.hideProgress();

      mainClickHandler = config.onClick;
      tg.MainButton.onClick(mainClickHandler);

      // В Telegram кнопку рисует мессенджер, поэтому своя не нужна.
      mainButton.set(null);
    },

    subscribeMainButton: (listener) => mainButton.subscribe(listener),
    subscribeBackButton: (listener) => backButton.subscribe(listener),

    haptic: (type) => {
      const h = tg.HapticFeedback;
      if (type === 'success' || type === 'error' || type === 'warning') {
        h.notificationOccurred(type);
      } else {
        h.impactOccurred(type === 'medium' ? 'medium' : 'light');
      }
    },

    // window.open в webview заблокирован — только через API Telegram.
    openExternal: (url) => {
      if (url.startsWith('https://t.me')) tg.openTelegramLink(url);
      else tg.openLink(url);
    },

    share: (text, url) => {
      const target = url ?? window.location.href;
      tg.openTelegramLink(
        `https://t.me/share/url?url=${encodeURIComponent(target)}&text=${encodeURIComponent(text)}`,
      );
    },

    // CloudStorage синхронизируется между всеми устройствами пользователя.
    storage: {
      get: (key) =>
        new Promise((resolve) => {
          tg.CloudStorage.getItem(STORAGE_PREFIX + key, (err, value) =>
            resolve(err ? null : (value ?? null)),
          );
        }),
      set: (key, value) =>
        new Promise((resolve) => {
          tg.CloudStorage.setItem(STORAGE_PREFIX + key, value, () => resolve());
        }),
      remove: (key) =>
        new Promise((resolve) => {
          tg.CloudStorage.removeItem(STORAGE_PREFIX + key, () => resolve());
        }),
    },

    close: () => tg.close(),
  };
}
