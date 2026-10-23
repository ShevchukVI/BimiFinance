import { useState } from 'react';
import { day } from '../format';
import { Jar } from '../types';
import { money } from '../format';
import { Button, Card, Empty, Progress } from '../ui';
import JarHistoryModal from '../components/JarHistoryModal';

export default function JarsPage({ jars, familyId, onTopUp, onCreate, onSync, syncing }: {
  jars: Jar[]; familyId: number; onTopUp: (jar: Jar) => void; onCreate: () => void; onSync?: () => void; syncing?: boolean;
}) {
  const [historyJar, setHistoryJar] = useState<Jar | null>(null);
  if (jars.length === 0) {
    return (
      <div className="stack">
        <Empty icon="🎯" title="Ще немає цілей" text="Створіть банку в Monobank (GTA 6, ДБЖ, подарунок…) — Bimi підтягне її сюди й рахуватиме перекази в неї як накопичення, а не витрати." action={onSync ? 'Підтягнути банки з Monobank' : 'Створити ціль'} onAction={onSync || onCreate} />
        {onSync && <Button variant="ghost" onClick={onCreate}>+ Ціль без банки (готівка)</Button>}
      </div>
    );
  }
  return (
    <div className="stack">
      {jars.map(jar => {
        const pct = jar.goal ? (jar.balance / jar.goal) * 100 : 0;
        return (
          <Card key={jar.id}>
            <div className="stack-s">
              <div className="spread">
                <span className="bold">{jar.mono_jar_id ? '🏦' : '🎯'} {jar.name}{jar.mono_jar_id && <span className="badge badge--accent" style={{ marginLeft: 6 }}>Моно</span>}</span>
                <span className="small tnum"><b>{money(jar.balance, jar.currency)}</b> <span className="muted">/ {money(jar.goal, jar.currency)}</span></span>
              </div>
              <Progress value={pct} />
              <div className="muted xsmall">{jar.goal ? (pct >= 100 ? 'Ціль досягнута 🎉' : `${Math.round(pct)}% · ще ${money(Math.max(jar.goal - jar.balance, 0), jar.currency)}`) : 'Без цілі — задайте суму в банці Monobank'}
                {jar.mono_jar_id && jar.synced_at ? ` · оновлено ${day(jar.synced_at)}` : ''}</div>
              <div className="btn-row" style={{ marginTop: 4 }}>
                {!jar.mono_jar_id && <Button size="sm" onClick={() => onTopUp(jar)}>Поповнити / зняти</Button>}
                <Button size="sm" variant="secondary" onClick={() => setHistoryJar(jar)}>Історія</Button>
              </div>
              {jar.mono_jar_id && <div className="muted xsmall">Поповнюйте й знімайте в застосунку Monobank — Bimi бачить це сам і не рахує як витрату.</div>}
            </div>
          </Card>
        );
      })}
      {onSync && <Button variant="secondary" onClick={onSync} busy={syncing}>🏦 Оновити банки з Monobank</Button>}
      <Button variant="ghost" onClick={onCreate}>+ Ціль без банки (готівка)</Button>
      {historyJar && <JarHistoryModal jar={historyJar} familyId={familyId} onClose={() => setHistoryJar(null)} />}
    </div>
  );
}
