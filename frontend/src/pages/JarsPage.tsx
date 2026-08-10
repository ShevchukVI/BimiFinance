import { Jar, fmt } from '../types';
import EmptyState from '../components/EmptyState';

export default function JarsPage({
  jars, onTopUp, onCreate
}: {
  jars: Jar[];
  onTopUp: (id: number) => void;
  onCreate: () => void;
}) {
  if (jars.length === 0) {
    return (
      <EmptyState
        emoji="🏦"
        title="У вас ще немає цілей"
        subtitle="Скарбничка допомагає відкладати на конкретну мрію — відпустку, техніку чи подушку безпеки."
        actionLabel="+ Створити ціль"
        onAction={onCreate}
      />
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
      {jars.map(jar => {
        const pct = Math.min((jar.balance / jar.goal) * 100, 100);
        return (
          <div key={jar.id} style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ fontWeight: 'bold', fontSize: '16px', color: '#2c3e50' }}>{jar.name}</div>
              <div style={{ fontWeight: 'bold', fontSize: '14px', color: '#27ae60' }}>{fmt(jar.balance)} / {fmt(jar.goal)}</div>
            </div>
            <div style={{ height: '8px', backgroundColor: '#ecf0f1', borderRadius: '4px', overflow: 'hidden', marginBottom: '15px' }}>
              <div style={{ width: `${pct}%`, height: '100%', backgroundColor: '#2ecc71', borderRadius: '4px', transition: 'width 0.5s' }}></div>
            </div>
            <button onClick={() => onTopUp(jar.id)} style={{ width: '100%', padding: '10px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '10px', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>📥 Поповнити</button>
          </div>
        );
      })}
    </div>
  );
}
