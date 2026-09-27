/**
 * Контракт платформы.
 *
 * Весь код приложения (features/, layouts/, shared/) обращается только к этому
 * интерфейсу и НИКОГДА не трогает window.Telegram напрямую. Проверить это
 * можно грепом: вхождений `Telegram` вне папки src/platform быть не должно.
 *
 * Добавляете новую платформу (например, мобильную обёртку) — пишете ещё одну
 * реализацию этого интерфейса, экраны не меняются.
 */

export type PlatformName = 'web' | 'telegram';

export type ColorScheme = 'light' | 'dark';

export type HapticType = 'light' | 'medium' | 'success' | 'warning' | 'error';

/** Как на этой платформе пользователь может отдать нам файл с транзакциями. */
export type FileInputMode =
  /** Полноценный <input type="file"> + drag&drop (браузер). */
  | 'native'
  /** Вставка текста CSV: в webview Telegram выбор файла нестабилен на iOS. */
  | 'paste';

export interface MainButtonConfig {
  text: string;
  loading?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

/** Данные для авторизации, которые бэкенд обязан проверить на своей стороне. */
export type AuthPayload =
  | { kind: 'telegram'; initData: string }
  | { kind: 'demo' };

export interface PlatformStorage {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

export interface Platform {
  name: PlatformName;

  /** Признак того, что UI надо рисовать в мобильной колонке без desktop-навигации. */
  isCompact: boolean;

  colorScheme: ColorScheme;

  /** safe-area + высота нативного хедера Telegram. */
  insets: { top: number; bottom: number };

  fileInputMode: FileInputMode;

  /** Профиль пользователя, если платформа его уже знает (Telegram). */
  userHint: { id: string; displayName: string } | null;

  getAuthPayload(): AuthPayload;

  /** Нативная кнопка «Назад» в Telegram; в web — своя кнопка в хедере. */
  setBackButton(handler: (() => void) | null): void;

  /** Нативный MainButton в Telegram; в web — обычная кнопка внизу экрана. */
  setMainButton(config: MainButtonConfig | null): void;

  /**
   * В web кнопки рисуем сами, поэтому лэйауту нужно знать текущее состояние.
   * В Telegram подписки сразу отдают null: кнопки рисует сам мессенджер.
   */
  subscribeMainButton(listener: (config: MainButtonConfig | null) => void): () => void;
  subscribeBackButton(listener: (handler: (() => void) | null) => void): () => void;

  haptic(type: HapticType): void;

  openExternal(url: string): void;

  share(text: string, url?: string): void;

  storage: PlatformStorage;

  /** Закрыть приложение: имеет смысл только в Telegram. */
  close(): void;
}
