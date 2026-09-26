import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { ApiError } from '@/shared/api/client';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Данные не «моргают» при возврате в приложение из другого чата Telegram.
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // Ошибку формата или 4xx повторять бессмысленно — покажем её сразу.
        if (error instanceof ApiError && error.kind !== 'network') return false;
        return failureCount < 2;
      },
    },
  },
});

export function Providers({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
