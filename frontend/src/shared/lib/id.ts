/**
 * Идентификатор для сущностей, создаваемых на клиенте (например, диалога).
 *
 * crypto.randomUUID доступен только в защищённом контексте, поэтому есть
 * запасной вариант — в webview Telegram это не лишняя осторожность.
 */
export function createId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
