import { Transaction, Category } from '../types';
import TransactionCard from '../components/TransactionCard';

export default function TransactionsPage({
  transactions, categories, hasMore, onLoadMore, onView
}: {
  transactions: Transaction[];
  categories: Category[];
  hasMore: boolean;
  onLoadMore: () => void;
  onView: (tx: Transaction) => void;
}) {
  if (transactions.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 20px', backgroundColor: '#fff', borderRadius: '16px' }}>
        <p style={{ color: '#7f8c8d' }}>Немає транзакцій.</p>
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {transactions.map(tx => (
        <TransactionCard key={tx.id} tx={tx} categories={categories} onClick={() => onView(tx)} />
      ))}
      {hasMore && <button onClick={onLoadMore} style={{ width: '100%', padding: '12px', marginTop: '10px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '14px' }}>⬇️ Завантажити ще</button>}
    </div>
  );
}
