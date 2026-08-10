import { Stats, Transaction, Category, BankUserBalances, fmtCur, curSym } from '../types';
import TransactionCard from '../components/TransactionCard';
import EmptyState from '../components/EmptyState';

export default function HomePage({
  stats, transactions, categories, bankBalances, onOpenInbox, onSeeAll, onAdd, onView,
}: {
  stats: Stats | null;
  transactions: Transaction[];
  categories: Category[];
  bankBalances: BankUserBalances[];
  onOpenInbox: () => void;
  onSeeAll: () => void;
  onAdd: () => void;
  onView: (tx: Transaction) => void;
}) {
  const pending = stats?.pending_count || 0;
  const recent = transactions.slice(0, 5);
  const hasBank = bankBalances.length > 0;

  // Валютний брейкдаун місяця: by_currency {code: {income, expense}} або UAH-only fallback.
  const byCurrency = stats?.by_currency || {};
  const hasMultiCurrency = Object.keys(byCurrency).length > 1;
  const mainCur = (Object.keys(byCurrency)[0] || 'UAH');
  const mainStats = byCurrency[mainCur] || { income: stats?.income || 0, expense: stats?.expense || 0 };

  // Готівка: групуємо по (user, currency).
  const cashUsers = stats?.cash_by_user || [];

  const statCard = (label: string, value: number, color: string, sign: string) => (
    <div style={{ flex: 1, backgroundColor: '#fff', padding: '14px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
      <p style={{ margin: 0, color: '#7f8c8d', fontSize: '11px' }}>{label}</p>
      <div style={{ color, fontWeight: 'bold', fontSize: '15px', marginTop: '4px' }}>{sign}{fmtCur(value, mainCur)}</div>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
      {stats && (
        <>
          <div style={{ display: 'flex', gap: '10px' }}>
            {statCard('📈 Дохід', mainStats.income, '#27ae60', '+')}
            {statCard('📉 Витрати', mainStats.expense, '#e74c3c', '-')}
            {statCard('💰 Залишок', (mainStats.income - mainStats.expense), '#2c3e50', '')}
          </div>
          {hasMultiCurrency && (
            <div style={{ backgroundColor: '#fff', padding: '12px 16px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
              {Object.entries(byCurrency).filter(([cur]) => cur !== mainCur).map(([cur, v]) => (
                <div key={cur} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
                  <span style={{ fontSize: '12px', color: '#7f8c8d' }}>{cur}</span>
                  <span style={{ fontSize: '12px', color: '#2c3e50' }}>
                    <span style={{ color: '#27ae60' }}>+{fmtCur(v.income, cur)}</span>
                    {'  '}
                    <span style={{ color: '#e74c3c' }}>-{fmtCur(v.expense, cur)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {cashUsers.length > 0 && (
        <div style={{ backgroundColor: '#fff', padding: '16px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <span style={{ color: '#7f8c8d', fontSize: '14px' }}>💵 Готівка</span>
            <span style={{ fontWeight: 'bold', fontSize: '15px', color: '#2c3e50' }}>
              {fmtCur(cashUsers.reduce((s, u) => s + u.balance, 0), mainCur)}
            </span>
          </div>
          <div style={{ borderTop: '1px solid #f1f2f6', paddingTop: '8px' }}>
            {cashUsers.map(u => (
              <div key={`${u.user_id}-${u.currency || 'UAH'}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
                <span style={{ fontSize: '13px', color: '#7f8c8d' }}>👤 {u.user_name}</span>
                <span style={{ fontWeight: 'bold', fontSize: '13px', color: '#2c3e50' }}>{fmtCur(u.balance, u.currency || 'UAH')}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {hasBank && (
        <div style={{ backgroundColor: '#fff', padding: '16px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
          <div style={{ fontWeight: 'bold', fontSize: '14px', color: '#2c3e50', marginBottom: '10px' }}>💳 Банки</div>
          {bankBalances.map(u => (
            <div key={u.user_id} style={{ marginBottom: '8px' }}>
              <div style={{ fontSize: '12px', color: '#7f8c8d', marginBottom: '4px' }}>👤 {u.user_name}</div>
              {u.accounts.map((a, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
                  <span style={{ fontSize: '13px', color: '#2c3e50' }}>{a.name}</span>
                  <span style={{ fontWeight: 'bold', fontSize: '14px', color: a.balance >= 0 ? '#2c3e50' : '#e74c3c' }}>{fmtCur(a.balance, a.currency || 'UAH')}</span>
                </div>
              ))}
            </div>
          ))}
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
