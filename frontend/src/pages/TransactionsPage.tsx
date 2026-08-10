import { Transaction, Category } from '../types';
import TransactionCard from '../components/TransactionCard';
import EmptyState from '../components/EmptyState';

export default function TransactionsPage({
  transactions, categories, hasMore, onLoadMore, onView, onAdd
}: {
  transactions: Transaction[];
  categories: Category[];
  hasMore: boolean;
  onLoadMore: () => void;
  onView: (tx: Transaction) => void;
  onAdd: () => void;
}) {
  if (transactions.length === 0) {
    return (
      <EmptyState
        emoji="💸"
        title="У вас ще немає транзакцій"
        subtitle="Додайте першу — або просто напишіть боту «150 такси», і він усе запише."
        actionLabel="+ Додати транзакцію"
        onAction={onAdd}
      />
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {transactions.map(tx => (
        <TransactionCard key={tx.id} tx={tx} categories={categories} onClick={() => onView(tx)} />
      ))}
      {hasMore && <button onClick={onLoadMore} style={{ width: '100%', padding: '13px', marginTop: '10px', backgroundColor: '#fff', color: '#3498db', border: '1px solid #3498db', borderRadius: '12px', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>⬇️ Показати ще</button>}
    </div>
  );
}
