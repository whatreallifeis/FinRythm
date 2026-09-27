import { NavLink } from 'react-router-dom';
import { cn } from '@/shared/lib/cn';
import { usePlatform } from '@/platform';
import { useNavItems } from './nav';

/** Нижняя навигация для Mini App и узких экранов. */
export function TabBar() {
  const { haptic } = usePlatform();
  const items = useNavItems();

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-bg-elevated"
      style={{ paddingBottom: 'max(var(--inset-bottom), env(safe-area-inset-bottom, 0px))' }}
    >
      <ul key={items.length} className="screen-in mx-auto flex max-w-[480px]">
        {items.map((item) => (
          <li key={item.to} className="flex-1">
            <NavLink
              to={item.to}
              end={item.to === '/app'}
              onClick={() => haptic('light')}
              className={({ isActive }) =>
                cn(
                  'flex h-14 flex-col items-center justify-center gap-0.5 text-[11px]',
                  isActive ? 'text-accent' : 'text-muted',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    aria-hidden
                    className={cn('tab-icon text-base leading-none', isActive && 'tab-icon-active')}
                  >
                    {item.icon}
                  </span>
                  {item.label}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
