import { useTransactions } from './hooks';

/**
 * Есть ли у пользователя данные — решает бэкенд: набор загружен, если есть операции.
 *
 * Раньше это был флаг в localStorage, и он расходился с сервером: другой браузер,
 * очищенная база или импорт CSV без демо давали неверное состояние экранов.
 */
export function useDatasetStatus() {
  const transactions = useTransactions();
  return {
    ready: (transactions.data?.length ?? 0) > 0,
    loading: transactions.isPending,
  };
}

export const useDatasetReady = () => useDatasetStatus().ready;
