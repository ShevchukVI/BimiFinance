import { useEffect, useState } from 'react';
import { Transaction, Category } from '../types';
import { dmy, money } from '../format';
import { Button, Card, KV, Row, Sheet } from '../ui';
import { TxAmount, catIcon } from './TransactionCard';
import { LinkTarget, payApi } from '../payments/api';

export default function TxDetailsSheet({ tx, categories, familyId, onClose, onEdit, onCopy, onLink }: {
  tx: Transaction; categories: Category[]; familyId: number; onClose: () => void; onEdit: () => void;
  onCopy: (text: string) => void; onLink: () => void;
}) {
  const cat = categories.find(c => c.id === tx.category_id);
  const linkable = tx.type === 'Витрати' && !tx.jar_id;
  const [current, setCurrent] = useState<LinkTarget | null | undefined>(undefined);
  useEffect(() => {
    if (linkable) payApi.link(familyId, tx.id).then(r => setCurrent(r.current)).catch(() => setCurrent(null));
  }, [familyId, tx.id, linkable]);

  return (
    <Sheet title="Операція" onClose={onClose}
      footer={<div className="btn-row">
        <Button variant="secondary" onClick={() => onCopy(`${tx.title} — ${money(tx.amount, tx.currency)}`)}>Копіювати</Button>
        {tx.type !== 'Переказ' && !tx.jar_id && <Button onClick={onEdit}>Редагувати</Button>}
      </div>}>
      <div className="center" style={{ padding: '4px 0 8px' }}>
        <div style={{ fontSize: 40 }}>{tx.type === 'Переказ' ? '↔️' : catIcon(cat)}</div>
        <div style={{ marginTop: 4 }}><TxAmount tx={tx} big /></div>
        <div className="muted" style={{ marginTop: 4 }}>{tx.title}</div>
      </div>
      <Card>
        <KV k="Категорія" v={tx.type === 'Переказ' ? 'Переказ' : (cat?.name || 'Інше')} />
        <KV k="Дата" v={dmy(tx.date)} />
        <KV k="Рахунок" v={tx.account} />
        {tx.user_name && <KV k="Хто" v={tx.user_name} />}
        {tx.note && <KV k="Коментар" v={<span style={{ fontWeight: 400, wordBreak: 'break-word' }}>{tx.note}</span>} />}
      </Card>
      {linkable && current !== undefined && (
        <Card flush>
          <Row icon={current ? current.icon : '🔗'} iconAccent
            title={current ? current.name : "Пов'язати"}
            sub={current ? (current.progress ? `Платіж ${current.progress}` : current.type === 'provider' ? 'Оплата в «Житлі»' : 'Платіж підписки')
              : 'З кредитом, підпискою чи комуналкою'}
            chevron onClick={onLink} />
        </Card>
      )}
    </Sheet>
  );
}
