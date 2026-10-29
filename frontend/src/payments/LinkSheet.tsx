import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { dmy, money } from '../format';
import { haptic } from '../tg';
import type { Transaction } from '../types';
import { Badge, Button, Card, Row, Section, Sheet, Spinner } from '../ui';
import { errText } from '../housing/api';
import { LinkTarget, payApi } from './api';
import type { ObDraft } from './ObligationForm';

// «Пов'язати» операцію з кредитом / підпискою / послугою «Житла» / авто.
export default function LinkSheet({ familyId, tx, onClose, onChanged, onCreate, onVehicle }: {
  familyId: number; tx: Transaction; onClose: () => void; onChanged: (current: LinkTarget | null) => void;
  onCreate: (draft: ObDraft) => void; onVehicle: (vehicleId: number) => void;  // car: open the journal entry to add liters / odometer
}) {
  const [data, setData] = useState<{ current: LinkTarget | null; candidates: LinkTarget[] } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { payApi.link(familyId, tx.id).then(setData).catch(e => toast(errText(e), 'err')); }, [familyId, tx.id]);

  const pick = async (c: LinkTarget) => {
    if (c.type === 'vehicle') { onVehicle(c.id); return; }
    setBusy(true);
    try { const r = await payApi.setLink(familyId, tx.id, c.type, c.id); haptic('success'); toast(`Пов'язано з «${c.name}»`); onChanged(r.current); onClose(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const unlink = async () => {
    setBusy(true);
    try { await payApi.unlink(familyId, tx.id); toast('Відв\'язано'); onChanged(null); onClose(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const title = tx.title.replace('❓ ', '');
  const draft = (kind: ObDraft['kind']): ObDraft => ({ kind, name: title, amount: tx.amount, due_day: Number(tx.date.slice(8, 10)),
    first_due: kind === 'subscription' ? undefined : tx.date, match_pattern: title, txId: tx.id });

  const matches = data?.candidates.filter(c => c.match) || [];
  const obs = data?.candidates.filter(c => !c.match && c.type === 'obligation') || [];
  const provs = data?.candidates.filter(c => !c.match && c.type === 'provider') || [];
  const cars = data?.candidates.filter(c => !c.match && c.type === 'vehicle') || [];
  const row = (c: LinkTarget) => <Row key={`${c.type}${c.id}`} icon={c.icon} title={c.name} sub={c.type === 'provider' ? `Житло · ${c.hint}` : c.type === 'vehicle' ? 'Авто · заправка, ремонт, мийка…' : c.hint}
    end={data?.current?.type === c.type && data.current.id === c.id ? <Badge tone="ok">✓</Badge> : undefined} onClick={() => pick(c)} />;

  return (
    <Sheet title="Пов'язати операцію" icon="🔗" onClose={onClose}>
      <div className="muted small" style={{ marginTop: -8 }}>{title} · {money(tx.amount, tx.currency)} · {dmy(tx.date)}</div>
      {!data || busy ? <Spinner /> : (
        <>
          {data.current && (
            <Card>
              <div className="spread">
                <span className="hstack"><span style={{ fontSize: 20 }}>{data.current.icon}</span><span><b>{data.current.name}</b>
                  {data.current.progress && <div className="muted small">платіж {data.current.progress}</div>}
                  {data.current.sub && <div className="muted small">{data.current.sub}</div>}</span></span>
                <Button size="sm" variant="danger" onClick={unlink}>Відв'язати</Button>
              </div>
            </Card>
          )}
          {matches.length > 0 && <Section title="Схоже"><Card flush>{matches.map(row)}</Card></Section>}
          {obs.length > 0 && <Section title="Кредити й підписки"><Card flush>{obs.map(row)}</Card></Section>}
          {provs.length > 0 && <Section title="Житло"><Card flush>{provs.map(row)}</Card></Section>}
          {cars.length > 0 && <Section title="Авто"><Card flush>{cars.map(row)}</Card></Section>}
          <Section title="Створити з цієї операції">
            <div className="btn-row">
              <Button variant="secondary" size="sm" onClick={() => onCreate(draft('subscription'))}>🔁 Підписка</Button>
              <Button variant="secondary" size="sm" onClick={() => onCreate(draft('installment'))}>🧾 Розстрочка</Button>
            </div>
          </Section>
        </>
      )}
    </Sheet>
  );
}
