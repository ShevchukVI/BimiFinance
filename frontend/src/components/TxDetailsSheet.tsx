import { Transaction, Category } from '../types';
import { dmy, money } from '../format';
import { Button, Card, KV, Sheet } from '../ui';
import { TxAmount, catIcon } from './TransactionCard';

export default function TxDetailsSheet({ tx, categories, onClose, onEdit, onCopy }: {
  tx: Transaction; categories: Category[]; onClose: () => void; onEdit: () => void; onCopy: (text: string) => void;
}) {
  const cat = categories.find(c => c.id === tx.category_id);
  return (
    <Sheet title="Операція" onClose={onClose}
      footer={<div className="btn-row">
        <Button variant="secondary" onClick={() => onCopy(`${tx.title} — ${money(tx.amount, tx.currency)}`)}>Копіювати</Button>
        <Button onClick={onEdit}>Редагувати</Button>
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
    </Sheet>
  );
}
