import { NavLink } from 'react-router-dom';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui';
import { useAuth } from '@/features/auth/useAuth';
import { useSession } from '@/features/auth/session';
import { useNavItems } from './nav';

/**
 * Боковое меню для широких экранов.
 *
 * Разделы те же самые, что и в таббаре, — меняется только раскладка.
 * Отдельного «десктопного дизайна» нет: это один продукт в двух ширинах.
 */
export function SideNav() {
  const session = useSession();
  const { logout } = useAuth();
  const items = useNavItems();

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-bg-elevated p-4">
      <div className="mb-6 px-2">
        <p className="font-semibold">Финансовый помощник</p>
        <p className="text-xs text-muted">{session?.displayName}</p>
      </div>

      <nav className="flex-1">
        <ul key={items.length} className="screen-in space-y-1">
          {items.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === '/app'}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-card px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-surface text-text'
                      : 'text-muted hover:bg-surface-hover hover:text-text',
                  )
                }
              >
                <span aria-hidden>{item.icon}</span>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <Button variant="ghost" size="sm" onClick={() => void logout()}>
        Выйти
      </Button>
    </aside>
  );
}
