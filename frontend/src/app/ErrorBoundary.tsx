import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '@/shared/ui';

/**
 * Последняя линия обороны: белый экран вместо приложения — это провал демо.
 * Любая необработанная ошибка рендера превращается в понятный экран с выходом.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Необработанная ошибка рендера:', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="mx-auto flex min-h-dvh max-w-[480px] flex-col justify-center px-4">
        <h1 className="mb-2 text-lg font-semibold">Что-то сломалось</h1>
        <p className="mb-4 text-sm text-muted">{this.state.error.message}</p>
        <Button onClick={() => window.location.reload()}>Перезагрузить</Button>
      </div>
    );
  }
}
