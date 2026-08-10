import { useState } from 'react';
import { Jar, fmtCur } from '../types';
import EmptyState from '../components/EmptyState';
import JarHistoryModal from '../components/JarHistoryModal';

export default function JarsPage({
  jars, familyId, onTopUp, onCreate
}: {
  jars: Jar[];
  familyId: number;
  onTopUp: (id: number) => void;
  onCreate: () => void;
}) {
  const [historyJar, setHistoryJar] = useState<Jar | null>(null);

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
              <div style={{ fontWeight: 'bold', fontSize: '16px', color: '#2c3e50' }}>
                {jar.name} {jar.currency && jar.currency !== 'UAH' ? <span style={{ fontSize: '11px', color: '#95a5a6' }}>({jar.currency})</span> : null}
              </div>
              <div style={{ fontWeight: 'bold', fontSize: '14px', color: '#27ae60' }}>{fmtCur(jar.balance, jar.currency || 'UAH')} / {fmtCur(jar.goal, jar.currency || 'UAH')}</div>
            </div>
            <div style={{ height: '8px', backgroundColor: '#ecf0f1', borderRadius: '4px', overflow: 'hidden', marginBottom: '15px' }}>
              <div style={{ width: `${pct}%`, height: '100%', backgroundColor: '#2ecc71', borderRadius: '4px', transition: 'width 0.5s' }}></div>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button onClick={() => onTopUp(jar.id)} style={{ flex: 1, padding: '10px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '10px', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>📥 Поповнити</button>
              <button onClick={() => setHistoryJar(jar)} style={{ flex: 1, padding: '10px', backgroundColor: '#fff', color: '#3498db', border: '1px solid #3498db', borderRadius: '10px', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>📜 Історія</button>
            </div>
          </div>
        );
      })}

      {historyJar && (
        <JarHistoryModal jar={historyJar} familyId={familyId} onClose={() => setHistoryJar(null)} />
      )}
    </div>
  );
}
