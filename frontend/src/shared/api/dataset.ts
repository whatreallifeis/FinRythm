import { create } from 'zustand';

const KEY = 'fin:dataset';

/** Данные уже подставлены в этой браузерной сессии. */
export function readDatasetReady() {
  try {
    return localStorage.getItem(KEY) === 'ready';
  } catch {
    return false;
  }
}

function writeDatasetReady(ready: boolean) {
  try {
    if (ready) localStorage.setItem(KEY, 'ready');
    else localStorage.removeItem(KEY);
  } catch {
    // Приватный режим: флаг живёт только до перезагрузки.
  }
}

interface DatasetState {
  ready: boolean;
  setReady: (ready: boolean) => void;
}

export const useDatasetStore = create<DatasetState>((set) => ({
  ready: readDatasetReady(),
  setReady: (ready) => {
    writeDatasetReady(ready);
    set({ ready });
  },
}));

export const useDatasetReady = () => useDatasetStore((state) => state.ready);
