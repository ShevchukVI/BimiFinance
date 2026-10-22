import { Fragment, ReactNode, useEffect, useState } from 'react';
import { toast } from '../toast';
import { approx, day, hm, hoursText, money, monthYear, plural } from '../format';
import { Badge, Banner, Button, Card, Empty, Row, Section, Segmented, Spinner } from '../ui';
import { errText, housingApi } from './api';
import type { Bill, HousingAlert, MeterSummary, Overview, Payment, ProviderOverview } from './types';
import { isFixedService } from './types';
import Onboarding from './Onboarding';
import ReadingsSheet from './ReadingsSheet';
import BillSheet from './BillSheet';
import PaymentSheet from './PaymentSheet';
import ProviderSheet from './ProviderSheet';
import ProviderForm from './ProviderForm';
import SettingsSheet from './SettingsSheet';
import MeterSheet from './MeterSheet';
import LooseSheet from './LooseSheet';
import { confirmAsync } from '../tg';
import StatsView from './StatsView';

type Seg = 'overview' | 'meters' | 'bills' | 'stats';
type SheetState = ({ kind: 'readings' } | { kind: 'settings' } | { kind: 'bill'; providerId?: number; bill?: Bill; period?: string }
  | { kind: 'pay'; providerId?: number } | { kind: 'provider'; id: number } | { kind: 'providerForm'; id?: number }
  | { kind: 'meter'; id: number } | { kind: 'loose'; providerId?: number }) & { back?: SheetState };
export type HousingAction = 'readings' | 'settings' | { pay: number } | null;

const meterIcon = (t: string) => ({ electricity: '⚡', gas: '🔥', water: '💧', heating: '♨️' } as Record<string, string>)[t] || '🔢';

export function providerStatus(p: ProviderOverview): { sub: string; end: ReactNode } {
  const b = p.balance;
  if (isFixedService(p.service)) {
    const overdue = (b.history || []).some(h => h.status === 'overdue') && b.debt > 1;
    const next = b.next_charge ? `${money(b.next_charge.amount, 'UAH', 0)} до ${day(b.next_charge.due)}` : null;
    const sub = b.paid_until ? [`Оплачено до ${day(b.paid_until)}`, next && `далі ${next}`].filter(Boolean).join(' · ')
      : next ? `Наступний платіж ${next}` : 'Платежів ще немає';
    return { sub, end: overdue ? <Badge tone="danger">{money(b.debt, 'UAH', 0)}</Badge> : <Badge tone="ok">✓</Badge> };
  }
  const parts: string[] = [];
  if (b.debt > 1) parts.push(`Борг ${money(b.debt)}`);
  else if (b.debt < -1) parts.push(`Переплата ${money(-b.debt)}`);
  else if (b.basis === 'bill') parts.push('Сплачено');
  if (b.accrued_since > 1) parts.push(`набігло ${approx(b.accrued_since)}`);
  if (!parts.length) parts.push(p.billing === 'fixed' && p.fixed_amount ? `${money(p.fixed_amount)} / міс` : 'Немає платіжок');
  const end = b.to_pay_now > 1 ? <b className="tnum">{approx(b.to_pay_now)}</b> : <Badge tone="ok">✓</Badge>;
  return { sub: parts.join(' · '), end };
}

export default function HousingPage({ familyId, overview, setOverview, accounts, onFinanceChanged, action, onActionDone }: {
  familyId: number; overview: Overview | null; setOverview: (o: Overview) => void; accounts: string[];
  onFinanceChanged: () => void; action: HousingAction; onActionDone: () => void;
}) {
  const [seg, setSeg] = useState<Seg>('overview');
  const [loading, setLoading] = useState(!overview);
  const [sheet, setSheetState] = useState<SheetState | null>(null);
  // child sheets (pay / bill / edit opened from a provider card) return to their parent on close
  const setSheet = (next: SheetState | null) => setSheetState(next);
  const openChild = (next: SheetState) => setSheetState(cur => ({ ...next, back: cur || undefined } as SheetState));
  const close = () => setSheetState(cur => cur?.back || null);
  const [showAllAlerts, setShowAllAlerts] = useState(false);
  const [bills, setBills] = useState<Bill[] | null>(null);
  const [payments, setPayments] = useState<Payment[] | null>(null);

  const reload = async () => {
    try { setOverview(await housingApi.overview(familyId)); } catch (e) { toast(errText(e, 'Не вдалося завантажити «Житло»'), 'err'); }
    setLoading(false);
  };
  const reloadLists = async () => {
    try {
      const [b, p] = await Promise.all([housingApi.bills(familyId), housingApi.payments(familyId)]);
      setBills(b); setPayments(p);
    } catch { /* lists are secondary */ }
  };

  useEffect(() => { if (!overview) reload(); else setLoading(false); }, [familyId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (seg === 'bills' && bills === null) reloadLists(); }, [seg]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!action || !overview?.profile) return;
    setSheet(action === 'readings' ? { kind: 'readings' } : action === 'settings' ? { kind: 'settings' } : { kind: 'pay', providerId: action.pay });
    onActionDone();
  }, [action, overview?.profile]); // eslint-disable-line react-hooks/exhaustive-deps

  const changed = (o?: Overview) => { if (o) setOverview(o); else reload(); if (bills !== null) reloadLists(); };

  if (loading) return <div className="page"><Spinner label="Завантаження «Житла»…" /></div>;
  if (!overview) return <div className="page"><Empty icon="🏡" title="Не вдалося завантажити" action="Спробувати ще" onAction={reload} /></div>;
  if (!overview.profile || (overview.profile.mode === 'off' && !overview.providers.length)) {
    return <div className="page"><Onboarding familyId={familyId} onDone={setOverview} /></div>;
  }

  const o = overview;
  const t = o.totals;
  const providers = o.providers;
  const hasMeters = o.meters.length > 0;
  const alerts = showAllAlerts ? o.alerts : o.alerts.slice(0, 3);
  const onAlert = async (a: HousingAlert) => {
    if (a.kind === 'heating') {
      const on = !o.heating.on;
      if (!(await confirmAsync(on ? 'Позначити початок опалювального сезону з сьогодні? Прогнози рахуватимуть зимове споживання.' : 'Завершити опалювальний сезон сьогодні?'))) return;
      try { await housingApi.heating(familyId, on); toast(on ? 'Опалювальний сезон позначено' : 'Сезон завершено'); changed(); } catch (e) { toast(errText(e), 'err'); }
      return;
    }
    if (a.kind === 'link') setSheet({ kind: 'loose' });
    else if (a.kind === 'readings') setSheet({ kind: 'readings' });
    else if (a.kind === 'pay' && a.provider_id) setSheet({ kind: 'pay', providerId: a.provider_id });
    else if (a.provider_id) setSheet({ kind: 'provider', id: a.provider_id });
    else setSheet({ kind: 'bill' });
  };

  const actions = [
    hasMeters ? { icon: '📸', label: 'Показники', onClick: () => setSheet({ kind: 'readings' }) } : null,
    { icon: '🧾', label: 'Платіжка', onClick: () => setSheet({ kind: 'bill' }) },
    { icon: '💳', label: 'Оплатити', onClick: () => setSheet({ kind: 'pay' }) },
    { icon: '⚙️', label: 'Налаштування', onClick: () => setSheet({ kind: 'settings' }) },
  ].filter(Boolean) as { icon: string; label: string; onClick: () => void }[];

  return (
    <div className="page">
      <div className="spread">
        <h1 className="page-title">{o.profile?.title || 'Житло'}</h1>
      </div>

      <Card className="hero">
        <div className="hero__label">До сплати зараз</div>
        <div className="hero__value tnum">{t.to_pay_now > 1 ? approx(t.to_pay_now) : 'Все сплачено ✓'}</div>
        <div className="hero__sub">
          {Math.abs(t.debt) > 1 && <span>за платіжками {money(t.debt, 'UAH', 0)}</span>}
          {t.accrued_since > 1 && <span>набігло {approx(t.accrued_since)}</span>}
          {t.next_month_forecast > 1 && <span>за місяць {approx(t.next_month_forecast)}</span>}
        </div>
        <div className="actions" style={{ marginTop: 16, gridTemplateColumns: `repeat(${actions.length}, 1fr)` }}>
          {actions.map(a => (
            <button key={a.label} className="action" onClick={a.onClick}><span className="action__icon">{a.icon}</span>{a.label}</button>
          ))}
        </div>
      </Card>

      {o.alerts.length > 0 && (
        <div className="stack-s">
          {alerts.map((a, i) => (
            <Banner key={i} tone={a.level === 'warn' ? 'warn' : undefined} icon={({ readings: '📸', pay: '💳', heating: '♨️', link: '🔗' } as Record<string, string>)[a.kind] || (a.level === 'warn' ? '⚠️' : '🧾')} onClick={() => onAlert(a)}>
              {a.text}
            </Banner>
          ))}
          {o.alerts.length > 3 && <button className="link" style={{ alignSelf: 'center' }} onClick={() => setShowAllAlerts(v => !v)}>{showAllAlerts ? 'Згорнути' : `Ще ${o.alerts.length - 3}`}</button>}
        </div>
      )}

      <Segmented value={seg} onChange={setSeg} options={[
        { value: 'overview', label: 'Огляд' }, ...(hasMeters ? [{ value: 'meters' as Seg, label: 'Лічильники' }] : []),
        { value: 'bills', label: 'Платіжки' }, { value: 'stats', label: 'Графіки' },
      ]} />

      {seg === 'overview' && <OverviewSeg o={o} onProvider={id => setSheet({ kind: 'provider', id })}
        onAddProvider={() => setSheet({ kind: 'providerForm' })} onStats={() => setSeg('stats')} />}
      {seg === 'meters' && <MetersSeg meters={o.meters} onReadings={() => setSheet({ kind: 'readings' })} onMeter={id => setSheet({ kind: 'meter', id })} />}
      {seg === 'bills' && <BillsSeg o={o} bills={bills} payments={payments} onBill={b => setSheet({ kind: 'bill', bill: b, providerId: b.provider_id })}
        onAdd={() => setSheet({ kind: 'bill' })} onPay={() => setSheet({ kind: 'pay' })} onProvider={id => setSheet({ kind: 'provider', id })} />}
      {seg === 'stats' && <StatsView familyId={familyId} overview={o} onChanged={() => changed()} />}

      {sheet?.kind === 'readings' && <ReadingsSheet familyId={familyId} meters={o.meters} onClose={close} onSaved={changed} />}
      {sheet?.kind === 'bill' && <BillSheet familyId={familyId} overview={o} providerId={sheet.providerId} bill={sheet.bill} period={sheet.period}
        onClose={close} onSaved={() => changed()} />}
      {sheet?.kind === 'pay' && <PaymentSheet familyId={familyId} overview={o} providerId={sheet.providerId} accounts={accounts}
        onClose={close} onSaved={(ov, withTx) => { changed(ov); if (withTx) onFinanceChanged(); }} />}
      {sheet?.kind === 'provider' && (() => {
        const p = providers.find(x => x.id === sheet.id);
        return p ? <ProviderSheet familyId={familyId} provider={p} meters={o.meters.filter(m => m.provider_id === p.id)}
          onClose={close} onPay={() => openChild({ kind: 'pay', providerId: p.id })}
          onBill={(b, period) => openChild({ kind: 'bill', providerId: p.id, bill: b, period })}
          onEdit={() => openChild({ kind: 'providerForm', id: p.id })} onChanged={withTx => { changed(); if (withTx) onFinanceChanged(); }}
          onLoose={() => openChild({ kind: 'loose', providerId: p.id })} /> : null;
      })()}
      {sheet?.kind === 'providerForm' && <ProviderForm familyId={familyId} provider={providers.find(p => p.id === sheet.id)}
        meters={o.meters.filter(m => m.provider_id === sheet.id)} onClose={close} onSaved={() => { close(); changed(); }} />}
      {sheet?.kind === 'settings' && <SettingsSheet familyId={familyId} overview={o} onClose={close}
        onChanged={() => changed()} onEditProvider={id => openChild({ kind: 'providerForm', id })} onAddProvider={() => openChild({ kind: 'providerForm' })} />}
      {sheet?.kind === 'loose' && <LooseSheet familyId={familyId} overview={o} providerId={sheet.providerId} onClose={close} onChanged={() => changed()} />}
      {sheet?.kind === 'meter' && (() => {
        const m = o.meters.find(x => x.id === sheet.id);
        return m ? <MeterSheet familyId={familyId} meter={m} onClose={close} onChanged={() => changed()} /> : null;
      })()}
    </div>
  );
}

function OverviewSeg({ o, onProvider, onAddProvider, onStats }: {
  o: Overview; onProvider: (id: number) => void; onAddProvider: () => void; onStats: () => void;
}) {
  const p = o.power;
  const since = p?.since ? (Date.now() - new Date(p.since).getTime()) / 3600000 : null;
  return (
    <>
      {p && (
        <Card flush>
          <Row icon={p.state === 'off' ? '🔴' : p.state === 'on' ? '🟢' : '⚪'}
            title={p.state === 'off' ? `Немає світла з ${hm(p.since)}` : p.state === 'on' ? `Світло є з ${hm(p.since)}` : 'Світлобот'}
            sub={p.state === 'off' && since !== null ? `вже ${hoursText(since)} · цього місяця без світла ${hoursText(p.month_off_hours)}`
              : `Цього місяця без світла ${hoursText(p.month_off_hours)} · ${p.month_outages} ${plural(p.month_outages, 'відключення', 'відключення', 'відключень')}`}
            chevron onClick={onStats} />
        </Card>
      )}
      <Section title="Послуги" action="+ Додати" onAction={onAddProvider}>
        {o.providers.length === 0 ? <Empty icon="🧾" title="Ще немає послуг" action="Додати послугу" onAction={onAddProvider} /> : (
          <Card flush>
            {o.providers.map(pr => {
              const s = providerStatus(pr);
              return <Row key={pr.id} icon={pr.icon} title={<>{pr.name}{pr.warnings > 0 && <span className="warn"> ⚠️</span>}{pr.suggested > 0 && <span style={{ color: 'var(--link)' }}> 🔗</span>}</>} sub={s.sub} end={s.end} onClick={() => onProvider(pr.id)} />;
            })}
          </Card>
        )}
      </Section>
    </>
  );
}

function MetersSeg({ meters, onReadings, onMeter }: { meters: MeterSummary[]; onReadings: () => void; onMeter: (id: number) => void }) {
  return (
    <>
      <Button onClick={onReadings}>📸 Внести показники</Button>
      {meters.map(m => (
        <Card key={m.id} onClick={() => onMeter(m.id)}>
          <div className="stack-s">
            <div className="spread">
              <div className="hstack grow"><span style={{ fontSize: 20 }}>{meterIcon(m.utility_type)}</span><b className="ellipsis">{m.name}</b></div>
              {m.daily_rate !== null && <span className="muted small tnum">≈ {m.daily_rate} {m.unit}/день</span>}
            </div>
            <div className="small">
              {m.last_value !== null ? <>Останній <b className="tnum">{m.last_value.toLocaleString('uk-UA')}</b> <span className="muted">· {day(m.last_date)}{m.days_since_reading ? ` (${m.days_since_reading} дн. тому)` : ''}</span></> : <span className="muted">Показників ще немає</span>}
            </div>
            <div className="grid2">
              <div className="tile">
                <div className="tile__label">З останньої платіжки</div>
                <div className="tile__value">{m.since_billed_volume !== null ? `+${m.since_billed_volume} ${m.unit}` : '—'}</div>
                {m.since_billed_cost !== null && <div className="muted xsmall">{approx(m.since_billed_cost)}</div>}
              </div>
              <div className="tile">
                <div className="tile__label">Прогноз на місяць</div>
                <div className="tile__value">{m.month_forecast !== null ? `${Math.round(m.month_forecast)} ${m.unit}` : '—'}</div>
                {m.month_forecast_cost !== null && <div className="muted xsmall">{approx(m.month_forecast_cost)}{m.last_year_month ? ` · торік ${Math.round(m.last_year_month)}` : ''}</div>}
              </div>
            </div>
          </div>
        </Card>
      ))}
    </>
  );
}

function BillsSeg({ o, bills, payments, onBill, onAdd, onPay, onProvider }: {
  o: Overview; bills: Bill[] | null; payments: Payment[] | null; onBill: (b: Bill) => void; onAdd: () => void; onPay: () => void; onProvider: (id: number) => void;
}) {
  const [view, setView] = useState<'bills' | 'payments'>('bills');
  const pName = (id: number) => o.providers.find(p => p.id === id);
  if (bills === null || payments === null) return <Spinner />;
  const byMonth: { period: string; items: Bill[] }[] = [];
  for (const b of bills) {
    const g = byMonth[byMonth.length - 1];
    if (g && g.period === b.period) g.items.push(b); else byMonth.push({ period: b.period, items: [b] });
  }
  return (
    <>
      <div className="btn-row">
        <Button onClick={onAdd}>🧾 Платіжка</Button>
        <Button variant="secondary" onClick={onPay}>💳 Оплата</Button>
      </div>
      <Segmented value={view} onChange={setView} options={[{ value: 'bills', label: `Платіжки · ${bills.length}` }, { value: 'payments', label: `Оплати · ${payments.length}` }]} />
      {view === 'bills' && (bills.length === 0 ? <Empty icon="🧾" title="Ще немає платіжок" text="Внесіть платіжку — поля підставляться самі з попередньої та ваших показників." /> :
        byMonth.map(g => (
          <Fragment key={g.period}>
            <div className="date-head">{monthYear(g.period)}</div>
            <Card flush>
              {g.items.map(b => {
                const p = pName(b.provider_id);
                const warn = b.flags.filter(f => f.level === 'warn').length;
                return <Row key={b.id} icon={p?.icon || '🧾'} title={p?.name || 'Послуга'}
                  sub={`нараховано ${money(b.accrued)} · до сплати ${money(b.to_pay)}`}
                  end={warn ? <Badge tone="warn">⚠️ {warn}</Badge> : <Badge tone="ok">✓</Badge>} onClick={() => onBill(b)} />;
              })}
            </Card>
          </Fragment>
        )))}
      {view === 'payments' && (payments.length === 0 ? <Empty icon="💳" title="Ще немає оплат" /> : (
        <Card flush>
          {payments.map(p => {
            const pr = pName(p.provider_id);
            return <Row key={p.id} icon={pr?.icon || '💳'} title={pr?.name || 'Оплата'}
              sub={[day(p.date), p.user_name, p.note, p.transaction_id ? 'у фінансах' : null].filter(Boolean).join(' · ')}
              end={<b className="tnum">{money(p.amount)}</b>} onClick={() => onProvider(p.provider_id)} />;
          })}
        </Card>
      ))}
    </>
  );
}
