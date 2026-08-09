// Крихітний toast-бус: будь-який модуль може показати повідомлення без alert().
export type ToastKind = 'ok' | 'err';

type Listener = (msg: string, kind: ToastKind) => void;

let listener: Listener | null = null;

export function _subscribeToast(fn: Listener) {
  listener = fn;
}

export function toast(msg: string, kind: ToastKind = 'ok') {
  listener?.(msg, kind);
}
