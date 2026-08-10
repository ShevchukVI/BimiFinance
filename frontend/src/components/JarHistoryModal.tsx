import { useEffect, useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { Transaction, Jar, fmtCur } from '../types';

// Історія скарбнички: депозити/зняття (хто, скільки, коли).
export default function JarHistoryModal({
  jar, familyId, onClose,
}: {
  jar: Jar;
  familyId: number;
  onClose: () => void;
}) {
  const [items, setItems] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get(`/families/${familyId}/jars/${jar.id}/transactions`);
        setItems(r.data);
      } catch {
        toast('Не вдалося завантажити історію', 'err');
      }
      setLoading(false);
    })();
  }, [familyId, jar.id]);

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 120, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <div style={{ backgroundColor: '#fff', borderTopLeftRadius: '24px', borderTopRightRadius: '24px', padding: '20px', paddingBottom: 'calc(20px + env(safe-area-inset-bottom))', maxHeight: '82vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
          <h3 style={{ margin: 0, color: '#2c3e50' }}>📜 {jar.name}</h3>
          <button onClick={onClose} style={{ border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6', cursor: 'pointer' }}>×</button>
        </div>
        <div style={{ fontSize: '13px', color: '#7f8c8d', marginBottom: '14px' }}>
          Баланс: <b>{fmtCur(jar.balance, jar.currency || 'UAH')}</b> з {fmtCur(jar.goal, jar.currency || 'UAH')}
        </div>

        {loading && <p style={{ textAlign: 'center', color: '#7f8c8d' }}>⏳ Завантаження...</p>}

        {!loading && items.length === 0 && (
          <p style={{ textAlign: 'center', color: '#7f8c8d', padding: '20px 0' }}>Історія порожня.</p>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {items.map(tx => {
            const isDeposit = tx.type === 'Поповнення';
            return (
              <div key={tx.id} style={{ backgroundColor: '#f8f9fa', padding: '12px 14px', borderRadius: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ overflow: 'hidden', paddingRight: '8px' }}>
                  <div style={{ fontWeight: 'bold', fontSize: '13px', color: '#2c3e50', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {isDeposit ? '⬆️ Поповнення' : '⬇️ Зняття'}
                  </div>
                  <div style={{ fontSize: '11px', color: '#95a5a6', marginTop: '2px' }}>
                    {tx.date} {tx.user_name ? `• 👤 ${tx.user_name}` : ''}
                  </div>
                </div>
                <div style={{ fontWeight: 'bold', fontSize: '14px', whiteSpace: 'nowrap', color: isDeposit ? '#27ae60' : '#e74c3c' }}>
                  {isDeposit ? '+' : '-'}{fmtCur(tx.amount, tx.currency || 'UAH')}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
