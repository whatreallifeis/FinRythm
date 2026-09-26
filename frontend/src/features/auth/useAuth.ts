import { useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { usePlatform } from '@/platform';
import { api } from '@/shared/api/client';
import { useDatasetStore } from '@/shared/api/dataset';
import { sessionSchema } from '@/shared/api/schemas';
import { useSessionStore } from './session';

const STORAGE_KEY = 'session';

/** Содержимое хранилища могло быть испорчено вручную — не роняем приложение. */
function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Восстановление и вход.
 *
 * В Telegram вход происходит сам: initData уже есть, спрашивать нечего.
 * В браузере пользователь выбирает демо-режим — это важно для проверяющего,
 * у которого нет нашего аккаунта, но который должен увидеть работающий продукт.
 */
export function useAuth() {
  const platform = usePlatform();
  const queryClient = useQueryClient();
  const { signIn, signOut, setStatus, fail } = useSessionStore();
  const bootstrapped = useRef(false);

  const signInDemo = useCallback(async () => {
    setStatus('authenticating');
    try {
      const session = await api.authDemo();
      signIn(session);
      await platform.storage.set(STORAGE_KEY, JSON.stringify(session));
    } catch (error) {
      fail(error instanceof Error ? error.message : 'Не удалось войти');
    }
  }, [platform, signIn, setStatus, fail]);

  const logout = useCallback(async () => {
    await api.clearDataset();
    useDatasetStore.getState().setReady(false);
    queryClient.clear();
    await platform.storage.remove(STORAGE_KEY);
    signOut();
  }, [platform, queryClient, signOut]);

  useEffect(() => {
    // Бутстрап выполняется строго один раз, иначе StrictMode залогинит дважды.
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    void (async () => {
      const auth = platform.getAuthPayload();

      if (auth.kind === 'telegram') {
        setStatus('authenticating');
        try {
          const session = await api.authTelegram(
            auth.initData,
            platform.userHint?.displayName ?? 'Пользователь',
          );
          signIn(session);
          await platform.storage.set(STORAGE_KEY, JSON.stringify(session));
        } catch (error) {
          fail(error instanceof Error ? error.message : 'Telegram не подтвердил вход');
        }
        return;
      }

      const saved = await platform.storage.get(STORAGE_KEY);
      if (saved) {
        const parsed = sessionSchema.safeParse(safeJsonParse(saved));
        if (parsed.success) {
          signIn(parsed.data);
          return;
        }
        // Формат сессии изменился — чистим, чтобы не залипнуть на старой схеме.
        await platform.storage.remove(STORAGE_KEY);
      }
      setStatus('anonymous');
    })();
  }, [platform, signIn, setStatus, fail]);

  return { signInDemo, logout };
}
