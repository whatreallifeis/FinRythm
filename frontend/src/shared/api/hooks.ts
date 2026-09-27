import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDatasetStore } from './dataset';
import { api } from './client';
import type { AutopaymentDraft, DatasetReplace, GoalDraft, OperationRef, Transaction } from './types';

function invalidateGoals(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.profile });
  void queryClient.invalidateQueries({ queryKey: ['goals'] });
}

/**
 * Операции и автоплатежи меняют календарь, прогноз и справки по дням —
 * сбрасываем всё, что из них считается.
 */
function invalidateMoney(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.profile });
  void queryClient.invalidateQueries({ queryKey: queryKeys.transactions });
  void queryClient.invalidateQueries({ queryKey: ['analysis'] });
}

/** Ключи кэша в одном месте — чтобы инвалидация не разъезжалась по файлам. */
export const queryKeys = {
  profile: ['profile'] as const,
  transactions: ['transactions'] as const,
  overview: ['analysis', 'overview'] as const,
  forecast: ['analysis', 'forecast'] as const,
  runway: ['analysis', 'runway'] as const,
  day: (date: string) => ['analysis', 'day', date] as const,
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

export const useDayInsight = (date: string | null) =>
  useQuery({
    queryKey: queryKeys.day(date ?? 'none'),
    queryFn: () => api.dayInsight(date!),
    enabled: Boolean(date),
  });

export const useImpulseCheck = () => useMutation({ mutationFn: api.impulse });

export const useGoalPlan = (goalId: string | null) =>
  useQuery({
    queryKey: queryKeys.goalPlan(goalId ?? 'none'),
    queryFn: () => api.goalPlan(goalId!),
    enabled: Boolean(goalId),
  });

export const useAsk = () => useMutation({ mutationFn: api.ask });

/** Переименование операции дня: запрос зависит от того, откуда операция взялась. */
export function useRenameOperation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ ref, title }: { ref: OperationRef; title: string }) => {
      if (ref.kind === 'transaction') await api.renameTransaction(ref.id, title);
      else if (ref.kind === 'autopayment') await api.renameAutopayment(ref.id, title);
      else await api.renameIncome(ref.id, title);
    },
    onSuccess: () => invalidateMoney(queryClient),
  });
}

export function useCreateAutopayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draft: AutopaymentDraft) => api.createAutopayment(draft),
    onSuccess: () => invalidateMoney(queryClient),
  });
}

export function useDeleteAutopayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteAutopayment(id),
    onSuccess: () => invalidateMoney(queryClient),
  });
}

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
      await warmUp(queryClient);
    },
  });
}

/**
 * Загрузка готовой выписки целиком: операции и баланс заменяют текущие,
 * затем создаются цели из набора. Как и с демо, экраны открываются только
 * после того, как кэш заполнен.
 */
export function useLoadDataset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ dataset, goals }: { dataset: DatasetReplace; goals: GoalDraft[] }) => {
      const result = await api.replaceDataset(dataset);
      for (const goal of goals) await api.createGoal(goal);
      await warmUp(queryClient);
      return result;
    },
  });
}

/** Сбрасывает кэш и заранее загружает то, что нужно главному экрану. */
async function warmUp(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.removeQueries();
  await Promise.all([
    queryClient.prefetchQuery({ queryKey: queryKeys.profile, queryFn: api.profile }),
    queryClient.prefetchQuery({ queryKey: queryKeys.transactions, queryFn: api.transactions }),
    queryClient.prefetchQuery({ queryKey: queryKeys.runway, queryFn: api.runway }),
    queryClient.prefetchQuery({ queryKey: queryKeys.history, queryFn: api.history }),
  ]);
  useDatasetStore.getState().setReady(true);
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
