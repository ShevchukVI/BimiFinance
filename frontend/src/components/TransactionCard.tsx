import { Fragment } from 'react';
import { Transaction, Category, cleanCatName } from '../types';
import { dateHeader, money } from '../format';
import { Card, Row } from '../ui';

export const catIcon = (cat?: Category) => {
  const m = (cat?.name || '').match(/^\p{Extended_Pictographic}[️‍\p{Extended_Pictographic}]*/u);
  return cat?.icon && cat.icon !== '•' ? cat.icon : (m ? m[0] : '💸');
};

export function TxAmount({ tx, big }: { tx: Transaction; big?: boolean }) {
  const cur = tx.currency || 'UAH';
  const style = big ? { fontSize: 34, fontWeight: 800 } : { fontWeight: 600 };
  if (tx.type === 'Переказ') return <span className="muted" style={style}>↔ {money(Math.abs(tx.amount), cur)}</span>;
  const income = tx.type !== 'Витрати';
  return <span className={income ? 'pos' : ''} style={style}>{income ? '+' : '−'}{money(tx.amount, cur)}</span>;
}

export function TxRow({ tx, categories, onClick }: { tx: Transaction; categories: Category[]; onClick: () => void }) {
  const cat = categories.find(c => c.id === tx.category_id);
  const pending = (cat?.name || '').includes('Очікує');
  const sub = [tx.type === 'Переказ' ? 'Переказ' : cleanCatName(cat?.name), tx.user_name, tx.account !== 'Готівка' ? tx.account : null]
    .filter(Boolean).join(' · ');
  return (
    <Row icon={tx.type === 'Переказ' ? '↔️' : catIcon(cat)} title={tx.title}
      sub={pending ? <span className="warn">Очікує категорію · {tx.account}</span> : sub}
      end={<TxAmount tx={tx} />} onClick={onClick} />
  );
}

/** Transactions grouped by day under «Сьогодні / Вчора / 15 жовтня» headers. */
export function TxList({ transactions, categories, onView }: { transactions: Transaction[]; categories: Category[]; onView: (t: Transaction) => void }) {
  const groups: { date: string; items: Transaction[] }[] = [];
  for (const tx of transactions) {
    const g = groups[groups.length - 1];
    if (g && g.date === tx.date) g.items.push(tx); else groups.push({ date: tx.date, items: [tx] });
  }
  return (
    <div>
      {groups.map(g => (
        <Fragment key={g.date}>
          <div className="date-head">{dateHeader(g.date)}</div>
          <Card flush>
            {g.items.map(tx => <TxRow key={tx.id} tx={tx} categories={categories} onClick={() => onView(tx)} />)}
          </Card>
        </Fragment>
      ))}
    </div>
  );
}
