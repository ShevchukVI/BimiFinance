import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { day, money } from '../format';
import { haptic } from '../tg';
import { Card, Chips, Empty, Sheet, Spinner } from '../ui';
import { errText } from './api';
import { payApi, TxBrief } from '../payments/api';
import type { Overview } from './types';

// Оплати, схожі на комуналку, але не пов'язані з послугою: один дотик — і це оплата послуги.
export default function LooseSheet({ familyId, overview, providerId, onClose, onChanged }: {
  familyId: number; overview: Overview; providerId?: number; onClose: () => void; onChanged: () => void;
}) {
  const [items, setItems] = useState<{ tx: TxBrief; guess: number | null }[] | null>(null);
  const load = async () => {
    try {
      const r = await payApi.looseHousing(familyId);
      const list = Object.entries(r.providers).flatMap(([pid, txs]) => txs.map(tx => ({ tx, guess: Number(pid) })));
      setItems([...list.filter(x => !providerId || x.guess === providerId),
        ...(providerId ? [] : r.unassigned.map(tx => ({ tx, guess: null })))].sort((a, b) => b.tx.date.localeCompare(a.tx.date)));
    } catch (e) { toast(errText(e), 'err'); setItems([]); }
  };
  useEffect(() => { load(); }, [familyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const link = async (txId: number, pid: number) => {
    try { await payApi.setLink(familyId, txId, 'provider', pid); haptic('success'); toast('Записано як оплату'); setItems(x => (x || []).filter(i => i.tx.id !== txId)); onChanged(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const provs = overview.providers;

  return (
    <Sheet title="Розкласти оплати" icon="🔗" onClose={onClose}>
      <div className="muted small" style={{ marginTop: -8 }}>Операції з банку, схожі на комуналку чи оренду. Оберіть послугу — оплата зарахується в «Житло».</div>
      {items === null ? <Spinner /> : items.length === 0 ? <Empty icon="🎉" title="Усе розкладено" /> : items.map(({ tx, guess }) => (
        <Card key={tx.id}>
          <div className="stack-s">
            <div className="spread"><div className="grow"><b className="ellipsis">{tx.title}</b><div className="muted small">{day(tx.date)} · {tx.account}</div></div>
              <b className="tnum">{money(tx.amount)}</b></div>
            <Chips small value={null} onChange={pid => link(tx.id, pid)}
              options={[...provs.filter(p => p.id === guess), ...provs.filter(p => p.id !== guess)].map(p => ({ value: p.id, label: `${p.id === guess ? '⭐ ' : ''}${p.icon} ${p.name}` }))} />
          </div>
        </Card>
      ))}
    </Sheet>
  );
}
