import { useState } from 'react';
import { toast } from '../toast';
import { money, parseNum, todayIso } from '../format';
import { haptic } from '../tg';
import { Button, Chips, Field, Sheet, Switch } from '../ui';
import { errText, housingApi } from './api';
import type { Overview } from './types';
import { isFixedService } from './types';

export default function PaymentSheet({ familyId, overview, providerId, accounts, onClose, onSaved }: {
  familyId: number; overview: Overview; providerId?: number; accounts: string[];
  onClose: () => void; onSaved: (o: Overview, withTx: boolean) => void;
}) {
  const providers = overview.providers;
  const suggested = (id: number | null) => {
    const p = providers.find(x => x.id === id);
    if (!p) return '';
    const b = p.balance;
    const v = isFixedService(p.service) ? (b.debt > 1 ? b.debt : b.next_charge?.amount || p.fixed_amount || 0)
      : (b.debt > 1 ? b.debt : b.to_pay_now);
    return v > 0 ? String(Math.round(v * 100) / 100) : '';
  };
  const [pid, setPid] = useState<number | null>(providerId ?? null);
  const [amount, setAmount] = useState(suggested(providerId ?? null));
  const [date, setDate] = useState(todayIso());
  const [note, setNote] = useState('');
  const [withTx, setWithTx] = useState(true);
  const [account, setAccount] = useState(accounts[0] || 'Готівка');
  const [busy, setBusy] = useState(false);
  const p = providers.find(x => x.id === pid);
  const num = parseNum(amount);
  const valid = !!pid && Number.isFinite(num) && num > 0;

  const save = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      const r = await housingApi.pay(familyId, { provider_id: pid, amount: num, date, note: note.trim(), create_transaction: withTx, account });
      haptic('success');
      toast(`Оплату ${money(num)} записано`);
      onSaved(r.overview, withTx);
      onClose();
    } catch (e) { toast(errText(e, 'Не вдалося записати оплату'), 'err'); }
    setBusy(false);
  };

  const hints = p ? [
    p.balance.debt > 1 ? { label: `Борг ${money(p.balance.debt)}`, v: p.balance.debt } : null,
    !isFixedService(p.service) && p.balance.to_pay_now > p.balance.debt + 1 ? { label: `З набіглим ≈ ${Math.round(p.balance.to_pay_now)}`, v: Math.round(p.balance.to_pay_now) } : null,
    isFixedService(p.service) && p.balance.next_charge ? { label: `${money(p.balance.next_charge.amount, 'UAH', 0)}`, v: p.balance.next_charge.amount } : null,
  ].filter(Boolean) as { label: string; v: number }[] : [];

  return (
    <Sheet title="Оплата" icon="💳" onClose={onClose}
      footer={<Button onClick={save} disabled={!valid} busy={busy}>Записати оплату{valid ? ` · ${money(num)}` : ''}</Button>}>
      <Field label="За що">
        <Chips value={pid} onChange={id => { setPid(id); setAmount(suggested(id)); }} options={providers.map(x => ({ value: x.id, label: `${x.icon} ${x.name}` }))} />
      </Field>
      <input className="input input--big tnum" inputMode="decimal" placeholder="0 ₴" value={amount} onChange={e => setAmount(e.target.value)} aria-label="Сума" />
      {hints.length > 0 && <Chips small value={null} onChange={v => setAmount(String(v))} options={hints.map(h => ({ value: h.v, label: h.label }))} />}
      {p?.pay_url && <a className="link" href={p.pay_url} target="_blank" rel="noreferrer">Відкрити оплату {p.name} ↗</a>}
      <div className="grid2">
        <Field label="Дата"><input className="input" type="date" value={date} max={todayIso()} onChange={e => setDate(e.target.value)} /></Field>
        <Field label="Примітка"><input className="input" placeholder="необов'язково" value={note} onChange={e => setNote(e.target.value)} /></Field>
      </div>
      <div className="card">
        <div className="spread">
          <div><div className="bold">Записати витрату у фінанси</div><div className="muted small">Щоб оплата потрапила в «Історію» й аналітику</div></div>
          <Switch on={withTx} onChange={setWithTx} label="Записати витрату" />
        </div>
        {withTx && accounts.length > 1 && (
          <div style={{ marginTop: 10 }}>
            <Chips small value={account} onChange={setAccount} options={accounts.map(a => ({ value: a, label: a === 'Готівка' ? '💵 Готівка' : `💳 ${a}` }))} />
          </div>
        )}
      </div>
    </Sheet>
  );
}
