import { useEffect, useState } from 'react';
import { _subscribeToast, ToastKind } from '../toast';
import { haptic } from '../tg';

export default function ToastHost() {
  const [item, setItem] = useState<{ msg: string; kind: ToastKind; key: number } | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    _subscribeToast((msg, kind) => {
      if (kind === 'err') haptic('error');
      setItem({ msg, kind, key: Date.now() });
      clearTimeout(timer);
      timer = setTimeout(() => setItem(null), kind === 'err' ? 3600 : 2400);
    });
    return () => clearTimeout(timer);
  }, []);

  if (!item) return null;
  return <div key={item.key} className={`toast toast--${item.kind}`} role="status" onClick={() => setItem(null)}>{item.msg}</div>;
}
