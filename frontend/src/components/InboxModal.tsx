import { useEffect, useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { Transaction, Category } from '../types';
import { day } from '../format';
import { haptic } from '../tg';
import { Card, Chips, Empty, Sheet, Spinner } from '../ui';
import { TxAmount } from './TransactionCard';

// Inbox Zero: нерозібрані транзакції (категорія «Очікує») — категорія в один дотик.
export default function InboxModal({ familyId, categories, onClose, onCategorized }: {
  familyId: number;
  categories: Category[];
  onClose: () => void;
  onCategorized: (tx: Transaction) => void;
}) {
  const [items, setItems] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const pickable = (tx: Transaction) => categories.filter(
    c => c.type === (tx.type === 'Витрати' ? 'expense' : 'income') && !c.name.includes('Очікує'));

  useEffect(() => {
    (async () => {
      try { setItems((await api.get(`/families/${familyId}/pending`)).data); }
      catch { toast('Не вдалося завантажити', 'err'); }
      setLoading(false);
    })();
  }, [familyId]);

  const assign = async (tx: Transaction, catId: number) => {
    if (savingId !== null) return;
    setSavingId(tx.id);
    try {
      const r = await api.put(`/transactions/${tx.id}`, { category_id: catId });
      setItems(prev => prev.filter(t => t.id !== tx.id));
      haptic('success');
      toast('Категорію призначено');
      onCategorized(r.data);
    } catch {
      toast('Помилка збереження', 'err');
    }
    setSavingId(null);
  };

  return (
    <Sheet title={`Розібрати${items.length ? ` · ${items.length}` : ''}`} icon="🧹" onClose={onClose}>
      {loading && <Spinner />}
      {!loading && items.length === 0 && (
        <Empty icon="🎉" title="Все розібрано!" text="Нові операції з Monobank з'являться тут автоматично." />
      )}
      {items.map(tx => (
        <Card key={tx.id}>
          <div style={{ opacity: savingId === tx.id ? 0.5 : 1 }} className="stack-s">
            <div className="spread">
              <div className="grow">
                <div className="bold ellipsis">{tx.title}</div>
                <div className="muted small">{day(tx.date)} · {tx.account}{tx.user_name ? ` · ${tx.user_name}` : ''}</div>
              </div>
              <TxAmount tx={tx} />
            </div>
            <Chips small value={null} onChange={id => assign(tx, id)}
              options={pickable(tx).map(c => ({ value: c.id, label: c.name }))} />
          </div>
        </Card>
      ))}
    </Sheet>
  );
}
