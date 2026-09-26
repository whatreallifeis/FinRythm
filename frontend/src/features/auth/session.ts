import { create } from 'zustand';
import { setAuthToken } from '@/shared/api/client';
import type { Session } from '@/shared/api/types';

/**
 * Сессия пользователя.
 *
 * Экраны знают только про userId/displayName/mode и не различают, вошёл
 * пользователь через Telegram или открыл демо в браузере.
 */

export type AuthStatus =
  /** Ещё не знаем: читаем сохранённую сессию из хранилища платформы. */
  | 'restoring'
  | 'anonymous'
  | 'authenticating'
  | 'authenticated'
  | 'failed';

interface SessionState {
  status: AuthStatus;
  session: Session | null;
  error: string | null;
  setStatus(status: AuthStatus): void;
  signIn(session: Session): void;
  fail(error: string): void;
  signOut(): void;
}

export const useSessionStore = create<SessionState>((set) => ({
  status: 'restoring',
  session: null,
  error: null,

  setStatus: (status) => set({ status }),

  signIn: (session) => {
    setAuthToken(session.token);
    set({ session, status: 'authenticated', error: null });
  },

  fail: (error) => set({ status: 'failed', error }),

  signOut: () => {
    setAuthToken(null);
    set({ session: null, status: 'anonymous', error: null });
  },
}));

export const useSession = () => useSessionStore((s) => s.session);
export const useAuthStatus = () => useSessionStore((s) => s.status);
