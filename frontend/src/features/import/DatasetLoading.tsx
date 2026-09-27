import { SkeletonCard } from '@/shared/ui';

/** Сцена ожидания: и для примера, и для будущей загрузки файла. */
export function DatasetLoading() {
  return (
    <section aria-busy="true" aria-live="polite">
      <header className="mb-4">
        <h1 className="text-xl font-semibold">Данные</h1>
        <p className="mt-0.5 text-sm text-muted">Читаем операции</p>
      </header>
      <div className="ios-progress mb-4" aria-hidden>
        <span />
      </div>
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </section>
  );
}
