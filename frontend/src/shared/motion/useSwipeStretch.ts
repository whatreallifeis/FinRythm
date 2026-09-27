import { useEffect, useRef } from 'react';

/** Обычный жест — едва заметно. У края экрана резинка чуть сильнее. */
const MAX = 0.012;
const RUBBER = 0.02;

/**
 * Пока палец или колесо ведут жест, карточки внутри сцены слегка тянутся
 * вдоль движения и сжимаются поперёк. На отпускании пружина возвращает их.
 * Жест не перехватывается: страница скроллится как раньше.
 */
export function useSwipeStretch<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let pointerId: number | null = null;
    let startX = 0;
    let startY = 0;
    let tracking = false;
    let settleTimer = 0;
    let wheelUntil = 0;
    let generation = 0;

    const paint = (sx: number, sy: number) => {
      el.style.setProperty('--sx', sx.toFixed(4));
      el.style.setProperty('--sy', sy.toFixed(4));
    };

    const release = () => {
      const ticket = ++generation;
      el.dataset.dragging = 'false';
      requestAnimationFrame(() => {
        if (ticket !== generation) return;
        paint(1, 1);
      });
    };

    const follow = (dx: number, dy: number, rubber: boolean) => {
      generation += 1;
      const distance = Math.min(Math.hypot(dx, dy), 180);
      const amount = (distance / 180) * (rubber ? RUBBER : MAX);
      el.dataset.dragging = 'true';
      if (Math.abs(dy) >= Math.abs(dx)) paint(1 - amount * 0.35, 1 + amount);
      else paint(1 + amount, 1 - amount * 0.35);
    };

    const onDown = (event: PointerEvent) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      const target = event.target;
      if (target instanceof Element && target.closest('input, textarea, select')) return;
      pointerId = event.pointerId;
      startX = event.clientX;
      startY = event.clientY;
      tracking = true;
    };

    const onMove = (event: PointerEvent) => {
      if (!tracking || event.pointerId !== pointerId) return;
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      if (Math.hypot(dx, dy) < 10) return;

      const atTop = window.scrollY <= 0;
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const atBottom = window.scrollY >= Math.max(0, maxScroll) - 1;
      const rubber = (atTop && dy > 16) || (atBottom && dy < -16);
      follow(dx, dy, rubber);
    };

    const onUp = (event: PointerEvent) => {
      if (event.pointerId !== pointerId) return;
      pointerId = null;
      tracking = false;
      release();
    };

    let lastScroll = window.scrollY;
    let lastTime = performance.now();

    const onScroll = () => {
      if (tracking || performance.now() < wheelUntil) return;
      const now = performance.now();
      const dy = window.scrollY - lastScroll;
      const dt = Math.max(now - lastTime, 16);
      lastScroll = window.scrollY;
      lastTime = now;
      const amount = Math.min((Math.abs(dy) / dt) * 0.006, MAX);
      if (amount < 0.0025) return;
      generation += 1;
      el.dataset.dragging = 'true';
      paint(1 - amount * 0.35, 1 + amount);
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(release, 80);
    };

    const onWheel = (event: WheelEvent) => {
      if (tracking) return;
      const dominantX = Math.abs(event.deltaX) > Math.abs(event.deltaY);
      const delta = dominantX ? event.deltaX : event.deltaY;
      const amount = Math.min(Math.abs(delta) / 160, 1) * 0.01;
      if (amount < 0.002) return;
      generation += 1;
      wheelUntil = performance.now() + 160;
      el.dataset.dragging = 'true';
      if (dominantX) paint(1 + amount, 1 - amount * 0.35);
      else paint(1 - amount * 0.35, 1 + amount);
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(release, 110);
    };

    el.addEventListener('pointerdown', onDown);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    window.addEventListener('scroll', onScroll, { passive: true });
    el.addEventListener('wheel', onWheel, { passive: true });

    return () => {
      el.removeEventListener('pointerdown', onDown);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      window.removeEventListener('scroll', onScroll);
      el.removeEventListener('wheel', onWheel);
      window.clearTimeout(settleTimer);
    };
  }, []);

  return ref;
}
