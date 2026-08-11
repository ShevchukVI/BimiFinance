import { Stats, Transaction, Category, BankUserBalances, fmtCur, sortCurrencies } from '../types';
import TransactionCard from '../components/TransactionCard';
import EmptyState from '../components/EmptyState';

const _num = (v: any) => (Number.isFinite(Number(v)) ? Number(v) : 0);

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

  // --- Місячні дохід/витрати по валютах ---
  const byCurrency = stats?.by_currency || {};
  const currencyCodes = sortCurrencies(Object.keys(byCurrency));
  // UAH завжди головна, якщо є; інакше перша за порядком.
  const mainCur = currencyCodes[0] || 'UAH';
  const mainStats = byCurrency[mainCur]
    ? { income: _num(byCurrency[mainCur].income), expense: _num(byCurrency[mainCur].expense) }
    : { income: _num(stats?.income), expense: _num(stats?.expense) };
  const secondaryCurs = currencyCodes.filter(c => c !== mainCur);

  // --- Готівка: по (user, currency), групуємо по user_id ---
  const cashUsers = stats?.cash_by_user || [];
  const cashByUser: { user_id: number; user_name: string; byCur: Record<string, number> }[] = [];
  const map = new Map<number, { user_name: string; byCur: Record<string, number> }>();
  for (const u of cashUsers) {
    const cur = u.currency || 'UAH';
    const entry = map.get(u.user_id) || { user_name: u.user_name, byCur: {} };
    entry.byCur[cur] = _num(entry.byCur[cur]) + _num(u.balance);
    map.set(u.user_id, entry);
  }
  for (const [uid, entry] of map) cashByUser.push({ user_id: uid, ...entry });
  cashByUser.sort((a, b) => a.user_name.localeCompare(b.user_name));

  const fmtByCur = (byCur: Record<string, number>) =>
    sortCurrencies(Object.keys(byCur)).map(cur => fmtCur(byCur[cur], cur));

  const statCard = (label: string, value: number, color: string, sign: string) => (
    <div style={{ flex: 1, backgroundColor: '#fff', padding: '14px 12px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
      <p style={{ margin: 0, color: '#95a5a6', fontSize: '11px', fontWeight: '600', letterSpacing: '0.3px' }}>{label}</p>
      <div style={{ color, fontWeight: '700', fontSize: '16px', marginTop: '4px', letterSpacing: '-0.2px' }}>{sign}{fmtCur(value, mainCur)}</div>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
      {stats && (
        <>
          <div style={{ display: 'flex', gap: '10px' }}>
            {statCard('Дохід', mainStats.income, '#27ae60', '+')}
            {statCard('Витрати', mainStats.expense, '#e74c3c', '-')}
            {statCard('Залишок', (mainStats.income - mainStats.expense), '#2c3e50', '')}
          </div>

          {secondaryCurs.length > 0 && (
            <div style={{ backgroundColor: '#fff', padding: '10px 14px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {secondaryCurs.map(cur => {
                const v = byCurrency[cur] || { income: 0, expense: 0 };
                return (
                  <div key={cur} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '12px', color: '#7f8c8d', fontWeight: '600' }}>{cur}</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontSize: '12px', color: '#27ae60', fontWeight: '600' }}>+{fmtCur(v.income, cur)}</span>
                      <span style={{ fontSize: '12px', color: '#e74c3c', fontWeight: '600' }}>−{fmtCur(v.expense, cur)}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {cashByUser.length > 0 && (
        <div style={{ backgroundColor: '#fff', padding: '14px 16px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <span style={{ color: '#2c3e50', fontSize: '14px', fontWeight: '700' }}>💵 Готівка</span>
            <span style={{ fontWeight: '600', fontSize: '13px', color: '#7f8c8d', textAlign: 'right' }}>
              {fmtByCur(cashByUser.reduce((acc, u) => {
                for (const [c, v] of Object.entries(u.byCur)) acc[c] = _num(acc[c]) + _num(v);
                return acc;
              }, {} as Record<string, number>)).join('  •  ')}
            </span>
          </div>
          <div style={{ borderTop: '1px solid #f1f2f6', paddingTop: '6px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            {cashByUser.map(u => (
              <div key={u.user_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0' }}>
                <span style={{ fontSize: '13px', color: '#34495e', fontWeight: '600' }}>👤 {u.user_name}</span>
                <span style={{ fontSize: '12px', color: '#2c3e50', fontWeight: '600' }}>
                  {fmtByCur(u.byCur).join('  •  ')}
                </span>
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
          subtitle="Додайте першу витрату або дохід — натисніть кнопку нижче, або напишіть боту «150 таксі»."
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
