// Telegram WebApp helpers: haptics, native confirm, BackButton stack.
const tg = () => (window as any).Telegram?.WebApp;

export type Haptic = 'light' | 'medium' | 'heavy' | 'success' | 'error' | 'select';

export function haptic(kind: Haptic = 'light') {
  const h = tg()?.HapticFeedback;
  if (!h) return;
  try {
    if (kind === 'success' || kind === 'error') h.notificationOccurred(kind);
    else if (kind === 'select') h.selectionChanged();
    else h.impactOccurred(kind);
  } catch { /* old clients */ }
}

/** Native Telegram confirm when available, window.confirm otherwise. */
export function confirmAsync(message: string): Promise<boolean> {
  const w = tg();
  if (w?.showConfirm && w.isVersionAtLeast?.('6.2')) {
    return new Promise(resolve => {
      try { w.showConfirm(message, (ok: boolean) => resolve(!!ok)); } catch { resolve(window.confirm(message)); }
    });
  }
  return Promise.resolve(window.confirm(message));
}

// BackButton stack: the top-most open sheet / sub-screen closes on «Назад».
const stack: Array<() => void> = [];
let bound = false;

function onBack() {
  const top = stack[stack.length - 1];
  top?.();
}

function sync() {
  const bb = tg()?.BackButton;
  if (!bb) return;
  if (!bound) { bb.onClick(onBack); bound = true; }
  if (stack.length) bb.show(); else bb.hide();
}

export function pushBack(handler: () => void): () => void {
  stack.push(handler);
  sync();
  return () => {
    const i = stack.lastIndexOf(handler);
    if (i >= 0) stack.splice(i, 1);
    sync();
  };
}

export function copyText(text: string) {
  try { navigator.clipboard?.writeText(text); } catch { /**/ }
}

export function startParam(): string | null {
  const w = tg();
  const fromTg = w?.initDataUnsafe?.start_param;
  if (fromTg) return String(fromTg);
  try { return new URLSearchParams(window.location.search).get('tab'); } catch { return null; }
}
