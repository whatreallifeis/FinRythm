import { Skeleton } from '@/shared/ui';

/** Экран между запуском и готовой сессией. Скелетон, чтобы не мигать пустотой. */
export function Splash() {
  return (
    <div className="screen-in mx-auto w-full max-w-[480px] space-y-4 px-4 py-6">
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-24" />
      <Skeleton className="h-40" />
    </div>
  );
}
