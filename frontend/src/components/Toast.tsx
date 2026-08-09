import { useEffect, useState } from 'react';
import { _subscribeToast, ToastKind } from '../toast';

export default function ToastHost() {
  const [item, setItem] = useState<{ msg: string; kind: ToastKind; key: number } | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    _subscribeToast((msg, kind) => {
      setItem({ msg, kind, key: Date.now() });
      clearTimeout(timer);
      timer = setTimeout(() => setItem(null), 2600);
    });
    return () => clearTimeout(timer);
  }, []);

  if (!item) return null;
  return (
    <div key={item.key} style={{
      position: 'fixed', top: 'calc(12px + env(safe-area-inset-top))', left: '50%', transform: 'translateX(-50%)',
      backgroundColor: item.kind === 'ok' ? '#2ecc71' : '#e74c3c', color: '#fff',
      padding: '12px 20px', borderRadius: '14px', fontWeight: 'bold', fontSize: '14px',
      boxShadow: '0 6px 20px rgba(0,0,0,0.18)', zIndex: 300, maxWidth: '88vw', textAlign: 'center',
      animation: 'toastIn 0.18s ease-out',
    }}>
      {item.msg}
      <style>{`@keyframes toastIn { from { opacity: 0; transform: translate(-50%, -8px); } to { opacity: 1; transform: translate(-50%, 0); } }`}</style>
    </div>
  );
}
