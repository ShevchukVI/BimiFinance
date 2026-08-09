import { Transaction, Category } from '../types';
import TransactionCard from '../components/TransactionCard';

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
      <div style={{ textAlign: 'center', padding: '40px 20px', backgroundColor: '#fff', borderRadius: '16px' }}>
        <div style={{ fontSize: '42px', marginBottom: '10px' }}>💸</div>
        <p style={{ color: '#2c3e50', fontWeight: 'bold', margin: '0 0 6px 0' }}>Транзакцій ще немає</p>
        <p style={{ color: '#7f8c8d', fontSize: '13px', margin: '0 0 15px 0' }}>Додай першу — або напиши боту «150 такси»</p>
        <button onClick={onAdd} style={{ padding: '12px 24px', backgroundColor: '#3498db', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '15px', cursor: 'pointer' }}>+ Додати</button>
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {transactions.map(tx => (
        <TransactionCard key={tx.id} tx={tx} categories={categories} onClick={() => onView(tx)} />
      ))}
      {hasMore && <button onClick={onLoadMore} style={{ width: '100%', padding: '12px', marginTop: '10px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>⬇️ Завантажити ще</button>}
    </div>
  );
}
