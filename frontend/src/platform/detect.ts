import { createTelegramPlatform } from './telegram';
import { createWebPlatform } from './web';
import type { Platform } from './types';

/**
 * Скрипт telegram-web-app.js создаёт window.Telegram.WebApp даже в обычном
 * браузере, поэтому наличие объекта — не признак Mini App. Надёжные признаки:
 * непустой initData либо platform, отличный от 'unknown'.
 */
export function createPlatform(): Platform {
  const tg = window.Telegram?.WebApp;
  const insideTelegram = Boolean(tg && (tg.initData !== '' || tg.platform !== 'unknown'));

  if (tg && insideTelegram) {
    return createTelegramPlatform(tg);
  }

  return createWebPlatform();
}
