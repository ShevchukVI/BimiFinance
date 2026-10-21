import { useEffect, useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { Transaction, Jar } from '../types';
import { day, money } from '../format';
import { Card, Empty, Progress, Row, Sheet, Spinner } from '../ui';

// Історія скарбнички: депозити/зняття (хто, скільки, коли).
export default function JarHistoryModal({ jar, familyId, onClose }: { jar: Jar; familyId: number; onClose: () => void }) {
  const [items, setItems] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try { setItems((await api.get(`/families/${familyId}/jars/${jar.id}/transactions`)).data); }
      catch { toast('Не вдалося завантажити історію', 'err'); }
      setLoading(false);
    })();
  }, [familyId, jar.id]);

  return (
    <Sheet title={jar.name} icon="📜" onClose={onClose}>
      <Card>
        <div className="spread small"><span className="muted">Зібрано</span><b>{money(jar.balance, jar.currency)} з {money(jar.goal, jar.currency)}</b></div>
        <div style={{ marginTop: 8 }}><Progress value={jar.goal ? (jar.balance / jar.goal) * 100 : 0} /></div>
      </Card>
      {loading && <Spinner />}
      {!loading && items.length === 0 && <Empty icon="🫙" title="Історія порожня" />}
      {items.length > 0 && (
        <Card flush>
          {items.map(tx => {
            const dep = tx.type === 'Поповнення';
            return <Row key={tx.id} icon={dep ? '⬆️' : '⬇️'} title={dep ? 'Поповнення' : 'Зняття'}
              sub={`${day(tx.date)}${tx.user_name ? ` · ${tx.user_name}` : ''}`}
              end={<span className={dep ? 'pos bold' : 'bold'}>{dep ? '+' : '−'}{money(tx.amount, tx.currency)}</span>} />;
          })}
        </Card>
      )}
    </Sheet>
  );
}
