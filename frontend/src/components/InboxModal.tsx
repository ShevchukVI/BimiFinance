import { useEffect, useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import EmptyState from './EmptyState';
import { Transaction, Category, fmt } from '../types';

// Inbox Zero у Mini App: нерозібрані транзакції (категорія «Очікує»)
// з швидким призначенням категорії в один дотик.
export default function InboxModal({
  familyId, categories, onClose, onCategorized,
}: {
  familyId: number;
  categories: Category[];
  onClose: () => void;
  onCategorized: (tx: Transaction) => void; // повертає оновлену транзакцію
}) {
  const [items, setItems] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const expenseCats = categories.filter(c => c.type === 'expense' && !c.name.includes('Очікує'));

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get(`/families/${familyId}/pending`);
        setItems(r.data);
      } catch {
        toast('Не вдалося завантажити', 'err');
      }
      setLoading(false);
    })();
  }, [familyId]);

  const assign = async (tx: Transaction, catId: number) => {
    setSavingId(tx.id);
    try {
      const r = await api.put(`/transactions/${tx.id}`, { category_id: catId });
      const updated = r.data;
      setItems(prev => prev.filter(t => t.id !== tx.id));
      toast('✅ Категорію призначено');
      onCategorized(updated); // оновити списки + відкрити деталі
    } catch {
      toast('Помилка збереження', 'err');
    }
    setSavingId(null);
  };

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 120, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <div style={{ backgroundColor: '#f5f7fa', borderTopLeftRadius: '24px', borderTopRightRadius: '24px', padding: '20px', paddingBottom: 'calc(20px + env(safe-area-inset-bottom))', maxHeight: '88vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <h3 style={{ margin: 0, color: '#2c3e50' }}>🧹 Розібрати ({items.length})</h3>
          <button onClick={onClose} style={{ border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6', cursor: 'pointer' }}>×</button>
        </div>

        {loading && <p style={{ textAlign: 'center', color: '#7f8c8d' }}>⏳ Завантаження...</p>}

        {!loading && items.length === 0 && (
          <EmptyState
            emoji="🎉"
            title="Все розібрано!"
            subtitle="Нерозібраних транзакцій немає. Нові витрати з Monobank з'являться тут автоматично."
          />
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {items.map(tx => (
            <div key={tx.id} style={{ backgroundColor: '#fff', padding: '14px', borderRadius: '14px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', opacity: savingId === tx.id ? 0.5 : 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                <div style={{ fontWeight: 'bold', fontSize: '14px', color: '#2c3e50', paddingRight: '8px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tx.title}</div>
                <div style={{ fontWeight: 'bold', color: '#e74c3c', whiteSpace: 'nowrap' }}>-{fmt(tx.amount)}</div>
              </div>
              <div style={{ fontSize: '11px', color: '#95a5a6', marginBottom: '10px' }}>{tx.date} • {tx.account}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {expenseCats.map(c => (
                  <button key={c.id} onClick={() => assign(tx, c.id)} disabled={savingId === tx.id}
                    style={{ padding: '7px 12px', borderRadius: '20px', border: '1px solid #dfe6e9', backgroundColor: '#f8f9fa', fontSize: '12px', cursor: 'pointer', color: '#2c3e50' }}>
                    {c.name}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
