import { useState } from 'react';
import { Jar } from '../types';
import { money } from '../format';
import { Button, Card, Empty, Progress } from '../ui';
import JarHistoryModal from '../components/JarHistoryModal';

export default function JarsPage({ jars, familyId, onTopUp, onCreate }: {
  jars: Jar[]; familyId: number; onTopUp: (jar: Jar) => void; onCreate: () => void;
}) {
  const [historyJar, setHistoryJar] = useState<Jar | null>(null);
  if (jars.length === 0) {
    return <Empty icon="🎯" title="Ще немає цілей" text="Скарбничка допомагає відкладати на мрію — відпустку, техніку чи подушку безпеки." action="Створити ціль" onAction={onCreate} />;
  }
  return (
    <div className="stack">
      {jars.map(jar => {
        const pct = jar.goal ? (jar.balance / jar.goal) * 100 : 0;
        return (
          <Card key={jar.id}>
            <div className="stack-s">
              <div className="spread">
                <span className="bold">🎯 {jar.name}</span>
                <span className="small tnum"><b>{money(jar.balance, jar.currency)}</b> <span className="muted">/ {money(jar.goal, jar.currency)}</span></span>
              </div>
              <Progress value={pct} />
              <div className="muted xsmall">{pct >= 100 ? 'Ціль досягнута 🎉' : `${Math.round(pct)}% · ще ${money(Math.max(jar.goal - jar.balance, 0), jar.currency)}`}</div>
              <div className="btn-row" style={{ marginTop: 4 }}>
                <Button size="sm" onClick={() => onTopUp(jar)}>Поповнити / зняти</Button>
                <Button size="sm" variant="secondary" onClick={() => setHistoryJar(jar)}>Історія</Button>
              </div>
            </div>
          </Card>
        );
      })}
      <Button variant="secondary" onClick={onCreate}>+ Нова ціль</Button>
      {historyJar && <JarHistoryModal jar={historyJar} familyId={familyId} onClose={() => setHistoryJar(null)} />}
    </div>
  );
}
