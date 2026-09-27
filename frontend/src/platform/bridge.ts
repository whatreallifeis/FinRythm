/** Крошечный наблюдаемый слот: платформа пишет значение, лэйаут его читает. */
export function createSlot<T>(initial: T) {
  let value = initial;
  const listeners = new Set<(v: T) => void>();

  return {
    get: () => value,
    set(next: T) {
      value = next;
      listeners.forEach((listener) => listener(next));
    },
    subscribe(listener: (v: T) => void) {
      listeners.add(listener);
      listener(value);
      return () => listeners.delete(listener);
    },
  };
}
