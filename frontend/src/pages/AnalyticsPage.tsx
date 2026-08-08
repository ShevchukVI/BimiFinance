import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { Stats, COLORS } from '../types';

export default function AnalyticsPage({ stats }: { stats: Stats }) {
  const cleanStats = stats.top_categories.map(c => ({
    ...c, cleanName: c.name.replace(/^[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ0-9]+/, '').trim() || c.name
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', display: 'flex', justifyContent: 'space-between' }}>
        <div><p style={{ margin: 0, color: '#7f8c8d', fontSize: '12px' }}>Дохід (Місяць)</p><h3 style={{ margin: '5px 0 0 0', color: '#27ae60' }}>+{stats.income.toLocaleString()} ₴</h3></div>
        <div><p style={{ margin: 0, color: '#7f8c8d', fontSize: '12px' }}>Витрати (Місяць)</p><h3 style={{ margin: '5px 0 0 0', color: '#e74c3c' }}>-{stats.expense.toLocaleString()} ₴</h3></div>
      </div>
      <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <h3 style={{ margin: '0 0 10px 0', color: '#2c3e50' }}>📊 Структура витрат</h3>
        {cleanStats.length > 0 ? (
          <>
            <div style={{ width: '100%', height: '220px' }}>
              <ResponsiveContainer><PieChart><Pie data={cleanStats} dataKey="amount" nameKey="cleanName" cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={2}>{cleanStats.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip formatter={(v: number) => `${v} ₴`} /></PieChart></ResponsiveContainer>
            </div>
            <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
              {cleanStats.map((cat, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><span style={{ display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%', backgroundColor: COLORS[i % COLORS.length] }}></span><span style={{ color: '#2c3e50' }}>{cat.cleanName}</span></div>
                  <span style={{ fontWeight: 'bold', color: '#7f8c8d' }}>{cat.amount.toLocaleString()} ₴</span>
                </div>
              ))}
            </div>
          </>
        ) : <p style={{ textAlign: 'center', color: '#7f8c8d' }}>Немає витрат.</p>}
      </div>
    </div>
  );
}
