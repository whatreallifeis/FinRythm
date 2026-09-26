import type { ReactNode } from 'react';
import { cn } from '../lib/cn';

type Tone = 'neutral' | 'positive' | 'negative' | 'warning' | 'info';

const TONES: Record<Tone, string> = {
  neutral: 'bg-surface-hover text-muted',
  positive: 'bg-positive/15 text-positive',
  negative: 'bg-negative/15 text-negative',
  warning: 'bg-warning/15 text-warning',
  info: 'bg-info/15 text-info',
};

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        TONES[tone],
      )}
    >
      {children}
    </span>
  );
}
