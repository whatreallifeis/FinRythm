import { cn } from '../lib/cn';

/** Скелетон, а не спиннер: меньше «прыжков» лэйаута при загрузке. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-[10px] bg-surface-hover', className)} />;
}

export function SkeletonCard() {
  return (
    <div className="ios-surface rounded-card border border-border bg-surface p-4">
      <Skeleton className="mb-3 h-4 w-1/3" />
      <Skeleton className="mb-2 h-8 w-1/2" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}
