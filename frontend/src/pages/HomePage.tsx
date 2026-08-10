import { Stats, Transaction, Category, fmt } from '../types';
import TransactionCard from '../components/TransactionCard';
import EmptyState from '../components/EmptyState';

export default function HomePage({
  stats, transactions, categories, onOpenInbox, onSeeAll, onAdd, onView,
}: {
  stats: Stats | null;
  transactions: Transaction[];
  categories: Category[];
  onOpenInbox: () => void;
  onSeeAll: () => void;
  onAdd: () => void;
  onView: (tx: Transaction) => void;
}) {
  const pending = stats?.pending_count || 0;
  const recent = transactions.slice(0, 5);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
      {stats && (
        <div style={{ display: 'flex', gap: '10px' }}>
          <div style={{ flex: 1, backgroundColor: '#fff', padding: '14px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <p style={{ margin: 0, color: '#7f8c8d', fontSize: '11px' }}>📈 Дохід</p>
            <div style={{ color: '#27ae60', fontWeight: 'bold', fontSize: '15px', marginTop: '4px' }}>+{fmt(stats.income)}</div>
          </div>
          <div style={{ flex: 1, backgroundColor: '#fff', padding: '14px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <p style={{ margin: 0, color: '#7f8c8d', fontSize: '11px' }}>📉 Витрати</p>
            <div style={{ color: '#e74c3c', fontWeight: 'bold', fontSize: '15px', marginTop: '4px' }}>-{fmt(stats.expense)}</div>
          </div>
          <div style={{ flex: 1, backgroundColor: '#fff', padding: '14px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <p style={{ margin: 0, color: '#7f8c8d', fontSize: '11px' }}>💰 Залишок</p>
            <div style={{ color: stats.balance >= 0 ? '#2c3e50' : '#e74c3c', fontWeight: 'bold', fontSize: '15px', marginTop: '4px' }}>{fmt(stats.balance)}</div>
          </div>
        </div>
      )}

      {stats && stats.balances && stats.balances['Готівка'] !== undefined && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#fff', padding: '14px 16px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
          <span style={{ color: '#7f8c8d', fontSize: '14px' }}>💵 Готівка (баланс)</span>
          <span style={{ fontWeight: 'bold', fontSize: '15px', color: stats.balances['Готівка'] >= 0 ? '#2c3e50' : '#e74c3c' }}>{fmt(stats.balances['Готівка'])}</span>
        </div>
      )}

      {pending > 0 && (
        <div onClick={onOpenInbox} style={{ backgroundColor: '#fff8e1', border: '1px solid #f1c40f', padding: '16px', borderRadius: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}>
          <div>
            <div style={{ fontWeight: 'bold', color: '#2c3e50', fontSize: '15px' }}>🧹 Очікує розбору: {pending}</div>
            <div style={{ color: '#7f8c8d', fontSize: '12px', marginTop: '2px' }}>Транзакції з Monobank без категорії</div>
          </div>
          <div style={{ color: '#f39c12', fontWeight: 'bold', fontSize: '20px' }}>›</div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '5px' }}>
        <h2 style={{ color: '#2c3e50', margin: 0, fontSize: '18px' }}>Останні операції</h2>
        <button onClick={onSeeAll} style={{ border: 'none', background: 'transparent', color: '#3498db', fontWeight: 'bold', fontSize: '13px', cursor: 'pointer' }}>Всі →</button>
      </div>

      {recent.length === 0 ? (
        <EmptyState
          emoji="💸"
          title="Тут з'являться ваші операції"
          subtitle="Додайте першу витрату або дохід — натисніть кнопку нижче, або напишіть боту «150 такси»."
          actionLabel="+ Додати транзакцію"
          onAction={onAdd}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {recent.map(tx => <TransactionCard key={tx.id} tx={tx} categories={categories} onClick={() => onView(tx)} />)}
        </div>
      )}
    </div>
  );
}
