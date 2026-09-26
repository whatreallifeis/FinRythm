import { createSlot } from './bridge';
import type { MainButtonConfig, Platform } from './types';

const STORAGE_PREFIX = 'fin:';

/** Реализация платформы для обычного браузера. */
export function createWebPlatform(): Platform {
  const mainButton = createSlot<MainButtonConfig | null>(null);
  const backButton = createSlot<(() => void) | null>(null);

  const prefersDark =
    typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
      : true;

  return {
    name: 'web',
    // Мобильная вёрстка на узких экранах, desktop-навигация на широких.
    isCompact: window.innerWidth < 768,
    colorScheme: prefersDark ? 'dark' : 'light',
    insets: { top: 0, bottom: 0 },
    fileInputMode: 'native',
    userHint: null,

    getAuthPayload: () => ({ kind: 'demo' }),

    setBackButton: (handler) => backButton.set(handler),
    setMainButton: (config) => mainButton.set(config),
    subscribeMainButton: (listener) => mainButton.subscribe(listener),
    subscribeBackButton: (listener) => backButton.subscribe(listener),

    haptic: () => {
      // В браузере тактильной отдачи нет — намеренно no-op.
    },

    openExternal: (url) => window.open(url, '_blank', 'noopener,noreferrer'),

    share: (text, url) => {
      const payload = url ? `${text} ${url}` : text;
      if (navigator.share) {
        void navigator.share({ text: payload });
        return;
      }
      void navigator.clipboard?.writeText(payload);
    },

    storage: {
      get: async (key) => localStorage.getItem(STORAGE_PREFIX + key),
      set: async (key, value) => localStorage.setItem(STORAGE_PREFIX + key, value),
      remove: async (key) => localStorage.removeItem(STORAGE_PREFIX + key),
    },

    close: () => {
      // Сайт закрыть нельзя.
    },
  };
}
