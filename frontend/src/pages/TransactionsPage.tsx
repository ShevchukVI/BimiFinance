import { useMemo, useState } from 'react';
import { Transaction, Category } from '../types';
import { Button, Chips, Empty } from '../ui';
import { TxList } from '../components/TransactionCard';

type Filter = 'all' | 'Витрати' | 'Поповнення' | 'Переказ' | 'pending';

export default function TransactionsPage({ transactions, categories, hasMore, onLoadMore, onView, onAdd }: {
  transactions: Transaction[]; categories: Category[]; hasMore: boolean;
  onLoadMore: () => void; onView: (tx: Transaction) => void; onAdd: () => void;
}) {
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const pendingIds = useMemo(() => new Set(categories.filter(c => c.name.includes('Очікує')).map(c => c.id)), [categories]);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return transactions.filter(t => {
      if (filter === 'pending' ? !pendingIds.has(t.category_id) : filter !== 'all' && t.type !== filter) return false;
      if (!s) return true;
      const cat = categories.find(c => c.id === t.category_id)?.name || '';
      return `${t.title} ${t.note} ${cat} ${t.user_name || ''} ${t.amount}`.toLowerCase().includes(s);
    });
  }, [transactions, categories, q, filter, pendingIds]);

  if (transactions.length === 0) {
    return <div className="page"><Empty icon="💸" title="Ще немає операцій" text="Додайте першу — або напишіть боту «150 таксі»." action="Додати" onAction={onAdd} /></div>;
  }
  return (
    <div className="page">
      <h1 className="page-title">Історія</h1>
      <input className="input" type="search" placeholder="🔍 Пошук: назва, категорія, сума" value={q} onChange={e => setQ(e.target.value)} />
      <Chips scroll small value={filter} onChange={setFilter} options={[
        { value: 'all', label: 'Усі' }, { value: 'Витрати', label: 'Витрати' }, { value: 'Поповнення', label: 'Доходи' },
        { value: 'Переказ', label: 'Перекази' }, { value: 'pending', label: '❓ Без категорії' },
      ]} />
      {list.length === 0 ? <div className="muted center small" style={{ padding: 24 }}>Нічого не знайдено серед завантажених операцій</div>
        : <TxList transactions={list} categories={categories} onView={onView} />}
      {hasMore && <Button variant="secondary" onClick={onLoadMore}>Показати ще</Button>}
    </div>
  );
}
