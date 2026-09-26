import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDatasetStore } from './dataset';
import { api } from './client';
import type { GoalDraft, Transaction } from './types';

function invalidateGoals(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.profile });
  void queryClient.invalidateQueries({ queryKey: ['goals'] });
}

/** Ключи кэша в одном месте — чтобы инвалидация не разъезжалась по файлам. */
export const queryKeys = {
  profile: ['profile'] as const,
  transactions: ['transactions'] as const,
  overview: ['analysis', 'overview'] as const,
  forecast: ['analysis', 'forecast'] as const,
  runway: ['analysis', 'runway'] as const,
  goalPlan: (goalId: string) => ['goals', goalId, 'plan'] as const,
  history: ['history'] as const,
};

export const useProfile = () => useQuery({ queryKey: queryKeys.profile, queryFn: api.profile });

export const useTransactions = () =>
  useQuery({ queryKey: queryKeys.transactions, queryFn: api.transactions });

export const useOverview = () =>
  useQuery({ queryKey: queryKeys.overview, queryFn: api.overview });

export const useForecast = () =>
  useQuery({ queryKey: queryKeys.forecast, queryFn: api.forecast });

export const useRunway = () => useQuery({ queryKey: queryKeys.runway, queryFn: api.runway });

export const useImpulseCheck = () => useMutation({ mutationFn: api.impulse });

export const useGoalPlan = (goalId: string | null) =>
  useQuery({
    queryKey: queryKeys.goalPlan(goalId ?? 'none'),
    queryFn: () => api.goalPlan(goalId!),
    enabled: Boolean(goalId),
  });

export const useAsk = () => useMutation({ mutationFn: api.ask });

export function useCreateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draft: GoalDraft) => api.createGoal(draft),
    onSuccess: () => invalidateGoals(queryClient),
  });
}

export function useUpdateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, draft }: { id: string; draft: GoalDraft }) => api.updateGoal(id, draft),
    onSuccess: () => invalidateGoals(queryClient),
  });
}

export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteGoal(id),
    onSuccess: () => invalidateGoals(queryClient),
  });
}

export const useHistory = () => useQuery({ queryKey: queryKeys.history, queryFn: api.history });

/**
 * Сохранение диалога в историю.
 *
 * Диалог отправляется целиком после каждого обмена репликами: запрос
 * идемпотентный, поэтому повторы и гонки неопасны.
 */
export function useSaveHistory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.saveHistory,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.history }),
  });
}

export function useClearHistory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.clearHistory,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.history }),
  });
}

/**
 * Загрузка демо-набора.
 *
 * Сначала ждём «сеть», затем кладём в кэш обзор, календарь и профиль,
 * и только после этого открываем остальные разделы — без вспышки скелетонов.
 */
export function useSeedDemo() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      await api.seedDemo();
      queryClient.removeQueries();
      await Promise.all([
        queryClient.prefetchQuery({ queryKey: queryKeys.profile, queryFn: api.profile }),
        queryClient.prefetchQuery({ queryKey: queryKeys.transactions, queryFn: api.transactions }),
        queryClient.prefetchQuery({ queryKey: queryKeys.overview, queryFn: api.overview }),
        queryClient.prefetchQuery({ queryKey: queryKeys.runway, queryFn: api.runway }),
        queryClient.prefetchQuery({ queryKey: queryKeys.history, queryFn: api.history }),
      ]);
      useDatasetStore.getState().setReady(true);
    },
  });
}

export function useImportTransactions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (rows: Array<Omit<Transaction, 'id' | 'isRecurring'>>) =>
      api.importTransactions(rows),
    // Новые операции меняют все производные расчёты — сбрасываем их кэш.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.transactions });
      void queryClient.invalidateQueries({ queryKey: ['analysis'] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runway });
      void queryClient.invalidateQueries({ queryKey: queryKeys.profile });
    },
  });
}
