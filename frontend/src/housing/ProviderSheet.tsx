import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { approx, day, money, monthShort, monthYear } from '../format';
import { confirmAsync, copyText } from '../tg';
import { Badge, Banner, Button, Card, KV, Row, Segmented, Sheet, Spinner, Tile } from '../ui';
import { errText, housingApi } from './api';
import type { Bill, MeterSummary, Payment, ProviderOverview } from './types';
import { isFixedService, SERVICE_LABELS } from './types';

export default function ProviderSheet({ familyId, provider: p, meters, onClose, onPay, onBill, onEdit, onChanged }: {
  familyId: number; provider: ProviderOverview; meters: MeterSummary[]; onClose: () => void; onPay: () => void;
  onBill: (b?: Bill, period?: string) => void; onEdit: () => void; onChanged: () => void;
}) {
  const [bills, setBills] = useState<Bill[] | null>(null);
  const [payments, setPayments] = useState<Payment[] | null>(null);
  const [tab, setTab] = useState<'bills' | 'payments'>(isFixedService(p.service) ? 'payments' : 'bills');
  const b = p.balance;
  const fixed = isFixedService(p.service);

  const load = async () => {
    try {
      const [bs, ps] = await Promise.all([housingApi.bills(familyId, p.id), housingApi.payments(familyId, p.id)]);
      setBills(bs); setPayments(ps);
    } catch (e) { toast(errText(e), 'err'); }
  };
  useEffect(() => { load(); }, [p.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const delPayment = async (pay: Payment) => {
    if (!(await confirmAsync(`Видалити оплату ${money(pay.amount)} від ${day(pay.date)}?`))) return;
    const withTx = pay.transaction_id ? await confirmAsync('Видалити і пов\'язану витрату у фінансах?') : false;
    try { await housingApi.deletePayment(familyId, pay.id, withTx); toast('Оплату видалено'); load(); onChanged(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <Sheet title={p.name} icon={p.icon} onClose={onClose}
      footer={<div className="btn-row">
        {!fixed && <Button variant="secondary" onClick={() => onBill()}>🧾 Платіжка</Button>}
        <Button onClick={onPay}>💳 Оплатити</Button>
      </div>}>
      <div className="muted small" style={{ marginTop: -8 }}>{SERVICE_LABELS[p.service] || p.service}
        {p.account_number && <> · о/р <button className="link small" onClick={() => { copyText(p.account_number); toast('Скопійовано'); }}>{p.account_number}</button></>}
        {' · '}<button className="link small" onClick={onEdit}>Налаштувати</button></div>

      {fixed ? (
        <div className="grid2">
          <Tile label="Оплачено до" value={b.paid_until ? day(b.paid_until) : '—'} tone={b.debt > 1 ? 'danger' : 'pos'} />
          <Tile label="Наступний платіж" value={b.next_charge ? `${money(b.next_charge.amount, 'UAH', 0)} · ${day(b.next_charge.due)}` : '—'} />
          {b.debt > 1 && <Tile label="Прострочено" value={money(b.debt)} tone="danger" />}
          {b.punctuality && b.punctuality.months > 0 && <Tile label="Вчасно" value={`${b.punctuality.months - b.punctuality.late} з ${b.punctuality.months}`} tone={b.punctuality.late ? 'warn' : 'pos'} />}
        </div>
      ) : (
        <div className="grid2">
          <Tile label="За платіжкою" value={b.debt < -1 ? `−${money(-b.debt)}` : money(b.debt)} tone={b.debt > 1 ? 'danger' : b.debt < -1 ? 'pos' : undefined} />
          <Tile label="Набігло з того часу" value={b.accrued_since > 1 ? approx(b.accrued_since) : '—'} />
          <Tile label="До сплати зараз" value={b.to_pay_now > 1 ? approx(b.to_pay_now) : '✓'} tone={b.to_pay_now > 1 ? 'warn' : 'pos'} />
          <Tile label="Наступна платіжка" value={b.next_bill_forecast ? approx(b.next_bill_forecast) : '—'} />
        </div>
      )}
      {b.debt < -1 && !fixed && <Banner icon="💚">Переплата {money(-b.debt)} — наступна платіжка буде меншою.</Banner>}

      {fixed && b.history && b.history.length > 0 && (
        <Card>
          <div className="muted small" style={{ marginBottom: 8 }}>Історія оплат</div>
          <div className="chips">
            {b.history.map(h => (
              <Badge key={h.month} tone={h.status === 'paid' ? (h.days_late ? 'warn' : 'ok') : h.status === 'overdue' ? 'danger' : undefined}>
                {monthShort(h.month)} {h.status === 'paid' ? (h.days_late ? `+${h.days_late} дн` : '✓') : h.status === 'overdue' ? '!' : '…'}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {meters.length > 0 && (
        <Card flush>
          {meters.map(m => <Row key={m.id} compact title={m.name} sub={m.last_value !== null ? `${m.last_value.toLocaleString('uk-UA')} · ${day(m.last_date)}` : 'немає показників'}
            end={m.tariff ? <span className="muted small">{m.tariff} ₴/{m.unit}</span> : undefined} />)}
        </Card>
      )}

      {!fixed && <Segmented value={tab} onChange={setTab} options={[{ value: 'bills', label: 'Платіжки' }, { value: 'payments', label: 'Оплати' }]} />}
      {bills === null || payments === null ? <Spinner /> : tab === 'bills' && !fixed ? (
        bills.length === 0 ? <div className="muted small center">Платіжок ще немає</div> : (
          <Card flush>
            {bills.map(x => {
              const warn = x.flags.filter(f => f.level === 'warn').length;
              return <Row key={x.id} icon="🧾" title={monthYear(x.period)} sub={`нараховано ${money(x.accrued)}${x.consumption ? ` · ${x.consumption}` : ''} · до сплати ${money(x.to_pay)}`}
                end={warn ? <Badge tone="warn">⚠️ {warn}</Badge> : <Badge tone="ok">✓</Badge>} onClick={() => onBill(x)} />;
            })}
          </Card>
        )
      ) : (
        payments.length === 0 ? <div className="muted small center">Оплат ще немає</div> : (
          <Card flush>
            {payments.map(x => <Row key={x.id} icon="💳" title={money(x.amount)} sub={[day(x.date), x.user_name, x.note].filter(Boolean).join(' · ')}
              end={<button className="link danger small" onClick={() => delPayment(x)}>Видалити</button>} />)}
          </Card>
        )
      )}
      {p.note && <Card><KV k="Примітка" v={<span style={{ fontWeight: 400 }}>{p.note}</span>} /></Card>}
    </Sheet>
  );
}
