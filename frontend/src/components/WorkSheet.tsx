import { useEffect, useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { day, money, parseNum } from '../format';
import type { Category, Transaction } from '../types';
import { Button, Card, Field, Row, Sheet, Spinner } from '../ui';
import { errText } from '../housing/api';
import { TxList } from './TransactionCard';

type Work = { payer: string; owed: number; since: string; opening: number; transactions: Transaction[] };

// «Прего винне»: з чого складається сума (залишок на старт + робочі операції) і виправлення до фактичної.
export default function WorkSheet({ familyId, categories, onClose, onView, onChanged }: {
  familyId: number; categories: Category[]; onClose: () => void; onView: (t: Transaction) => void; onChanged: () => void;
}) {
  const [w, setW] = useState<Work | null>(null);
  const [fix, setFix] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get(`/families/${familyId}/work`).then(r => setW(r.data)).catch(e => toast(errText(e), 'err')); }, [familyId]);

  const save = async () => {
    const owed = parseNum(fix || '');
    if (!Number.isFinite(owed)) { toast('Введіть суму', 'err'); return; }
    setBusy(true);
    try { setW((await api.put(`/families/${familyId}/work`, { owed })).data); setFix(null); onChanged(); toast('Суму виправлено'); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  if (!w) return <Sheet title="Робочий баланс" icon="💼" onClose={onClose}><Spinner /></Sheet>;
  const sign = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${money(Math.abs(v), 'UAH', 2)}`;
  return (
    <Sheet title={`${w.payer} винне`} icon="💼" onClose={onClose} footer={fix === null
      ? <Button variant="secondary" onClick={() => setFix(String(w.owed))}>Виправити суму</Button>
      : <Button onClick={save} busy={busy}>Зберегти</Button>}>
      <div className="center" style={{ padding: '2px 0 4px' }}>
        <div className="muted small">{w.owed < 0 ? 'Їхній запас у вас' : 'Мають повернути'}</div>
        <div className="tnum" style={{ fontSize: 34, fontWeight: 800 }}>{money(Math.abs(w.owed), 'UAH', 2)}</div>
        <div className="muted small">з {day(w.since)} · кожна «Робоча витрата» додає до боргу, ↩️ їхнє повернення віднімає</div>
      </div>
      {fix !== null && (
        <Field label={`Скільки ${w.payer} винне насправді`} hint="Мінус — якщо їхні гроші лишились у вас. Різниця піде в залишок на старт, операції не зміняться.">
          <input className="input input--big tnum" inputMode="decimal" value={fix} autoFocus onChange={e => setFix(e.target.value)} />
        </Field>
      )}
      <Card flush>
        <Row icon="🏁" title="Залишок на старт" sub={day(w.since)} end={<b className="tnum">{sign(w.opening)}</b>} />
      </Card>
      {w.transactions.length === 0 ? <div className="muted small center">Робочих операцій ще немає</div>
        : <TxList transactions={w.transactions} categories={categories} onView={t => { onClose(); onView(t); }} />}
    </Sheet>
  );
}
