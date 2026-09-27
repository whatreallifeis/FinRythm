import type { CategoryId } from '../api/types';

/** Человеческие названия и цвета категорий. Единственный источник правды для UI. */
export const CATEGORY_META: Record<CategoryId, { label: string; color: string }> = {
  food: { label: 'Еда', color: '#F5A623' },
  transport: { label: 'Транспорт', color: '#4A90D9' },
  subscriptions: { label: 'Подписки и связь', color: '#9B7BE8' },
  entertainment: { label: 'Развлечения', color: '#E5484D' },
  health: { label: 'Здоровье', color: '#3BA55D' },
  education: { label: 'Образование', color: '#20B2AA' },
  rent: { label: 'Жильё', color: '#D97706' },
  other: { label: 'Прочее', color: '#8E95A3' },
};

export const categoryLabel = (id: CategoryId) => CATEGORY_META[id].label;
export const categoryColor = (id: CategoryId) => CATEGORY_META[id].color;
