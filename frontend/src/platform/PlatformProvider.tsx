import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPlatform } from './detect';
import type { ColorScheme, MainButtonConfig, Platform } from './types';

interface PlatformContextValue extends Platform {
  /** Реактивная версия Platform.isCompact: пересчитывается при ресайзе. */
  isCompact: boolean;
  theme: ColorScheme;
  setTheme(theme: ColorScheme): void;
}

const PlatformContext = createContext<PlatformContextValue | null>(null);

const COMPACT_BREAKPOINT = 768;

export function PlatformProvider({ children }: { children: ReactNode }) {
  // Платформа создаётся один раз за жизнь приложения.
  const platformRef = useRef<Platform>();
  if (!platformRef.current) platformRef.current = createPlatform();
  const platform = platformRef.current;

  const [theme, setTheme] = useState<ColorScheme>(platform.colorScheme);
  const [isCompact, setIsCompact] = useState(
    platform.name === 'telegram' || window.innerWidth < COMPACT_BREAKPOINT,
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    document.documentElement.style.setProperty('--inset-top', `${platform.insets.top}px`);
    document.documentElement.style.setProperty('--inset-bottom', `${platform.insets.bottom}px`);
  }, [platform]);

  useEffect(() => {
    if (platform.name === 'telegram') return;
    const onResize = () => setIsCompact(window.innerWidth < COMPACT_BREAKPOINT);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [platform]);

  const value = useMemo<PlatformContextValue>(
    () => ({ ...platform, isCompact, theme, setTheme }),
    [platform, isCompact, theme],
  );

  return <PlatformContext.Provider value={value}>{children}</PlatformContext.Provider>;
}

export function usePlatform(): PlatformContextValue {
  const ctx = useContext(PlatformContext);
  if (!ctx) throw new Error('usePlatform вызван вне PlatformProvider');
  return ctx;
}

/**
 * Объявляет главную кнопку экрана. В Telegram это нативный MainButton,
 * в браузере — кнопка, которую рисует AppLayout. Экран об этом не знает.
 */
export function useMainButton(config: MainButtonConfig | null) {
  const { setMainButton } = usePlatform();
  const { text, loading, disabled, onClick } = config ?? {};
  const onClickRef = useRef(onClick);
  onClickRef.current = onClick;

  useEffect(() => {
    if (!text) {
      setMainButton(null);
      return;
    }
    setMainButton({ text, loading, disabled, onClick: () => onClickRef.current?.() });
    return () => setMainButton(null);
  }, [setMainButton, text, loading, disabled]);
}

/** Объявляет кнопку «Назад»: нативную в Telegram, свою в хедере на сайте. */
export function useBackButton(handler: (() => void) | null) {
  const { setBackButton } = usePlatform();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  const enabled = Boolean(handler);

  useEffect(() => {
    if (!enabled) {
      setBackButton(null);
      return;
    }
    setBackButton(() => handlerRef.current?.());
    return () => setBackButton(null);
  }, [setBackButton, enabled]);
}
