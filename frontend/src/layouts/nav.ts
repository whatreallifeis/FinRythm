import { useDatasetReady } from '@/shared/api/dataset';

/** Единый список разделов: и таббар, и desktop-меню читают его. */
export const NAV_ITEMS = [
  { to: '/app', label: 'Обзор', icon: '◎' },
  { to: '/app/assistant', label: 'Помощник', icon: '✦' },
  { to: '/app/goals', label: 'Цели', icon: '◆' },
  { to: '/app/import', label: 'Данные', icon: '↑' },
] as const;

/** Пока набор пуст, открыт только импорт — остальные экраны считать не из чего. */
export function useNavItems() {
  const ready = useDatasetReady();
  if (ready) return NAV_ITEMS;
  return NAV_ITEMS.filter((item) => item.to === '/app/import');
}
