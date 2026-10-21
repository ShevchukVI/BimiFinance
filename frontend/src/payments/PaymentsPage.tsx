import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { day, money } from '../format';
import type { Category } from '../types';
import { Badge, Button, Card, Empty, Progress, Row, Segmented, Spinner } from '../ui';
import { errText } from '../housing/api';
import { ObList, Obligation, payApi } from './api';
import ObligationSheet from './ObligationSheet';
import ObligationForm, { ObDraft } from './ObligationForm';

export function statusLine(o: Obligation): string {
  const s = o.state;
  if (s.status === 'finished') return 'Виплачено ✓';
  if (o.kind === 'subscription') {
    if (s.status === 'missing') return `очікували ${day(s.expected)} — списання не бачимо`;
    if (s.status === 'stale') return `давно немає списань (останнє ${day(s.last_date)})`;
    return s.next_due ? `наступне ${day(s.next_due)}` : 'без дати';
  }
  const prog = s.payments_total ? `${s.paid_count} з ${s.payments_total}` : `${s.paid_count ?? 0} сплачено`;
  if (s.status === 'overdue') return `${prog} · прострочено з ${day(s.next_due)}`;
  return `${prog} · наступний ${day(s.next_due)}`;
}

export function statusBadge(o: Obligation) {
  const st = o.state.status;
  if (st === 'overdue') return <Badge tone="danger">Прострочено</Badge>;
  if (st === 'due_soon') return <Badge tone="warn">Скоро</Badge>;
  if (st === 'finished') return <Badge tone="ok">Виплачено</Badge>;
  if (st === 'charged') return <Badge tone="ok">✓ Списано</Badge>;
  if (st === 'missing' || st === 'stale') return <Badge tone="warn">Немає списання</Badge>;
  return null;
}

export default function PaymentsPage({ familyId, categories, initialDraft, onChanged }: {
  familyId: number; categories: Category[]; initialDraft?: ObDraft | null; onChanged?: () => void;
}) {
  const [data, setData] = useState<ObList | null>(null);
  const [seg, setSeg] = useState<'credits' | 'subs'>(initialDraft?.kind === 'subscription' ? 'subs' : 'credits');
  const [open, setOpen] = useState<number | null>(null);
  const [form, setForm] = useState<{ item?: Obligation; draft?: ObDraft } | null>(initialDraft ? { draft: initialDraft } : null);
  const load = () => payApi.list(familyId).then(setData).catch(e => toast(errText(e, 'Не вдалося завантажити'), 'err'));
  useEffect(() => { load(); }, [familyId]); // eslint-disable-line react-hooks/exhaustive-deps
  const changed = () => { load(); onChanged?.(); };

  if (!data) return <Spinner />;
  const credits = data.items.filter(i => i.kind !== 'subscription');
  const subs = data.items.filter(i => i.kind === 'subscription');
  const active = credits.filter(i => i.state.status !== 'finished');
  const done = credits.filter(i => i.state.status === 'finished');
  const t = data.totals;
  const current = data.items.find(i => i.id === open) || null;

  return (
    <>
      <Card className="hero">
        <div className="hero__label">Регулярні платежі щомісяця</div>
        <div className="hero__value tnum">{money(t.credits_monthly + t.subscriptions_monthly, 'UAH', 0)}</div>
        <div className="hero__sub">
          <span>кредити {money(t.credits_monthly, 'UAH', 0)}</span><span>підписки {money(t.subscriptions_monthly, 'UAH', 0)}</span>
          {t.remaining_total > 0 && <span>лишилось виплатити {money(t.remaining_total, 'UAH', 0)}</span>}
        </div>
      </Card>
      <Segmented value={seg} onChange={setSeg} options={[{ value: 'credits', label: `Кредити · ${active.length}` }, { value: 'subs', label: `Підписки · ${subs.length}` }]} />

      {seg === 'credits' && (active.length === 0 && done.length === 0
        ? <Empty icon="🧾" title="Немає розстрочок і кредитів" text="Додайте «оплату частинами» — побачите, скільки лишилось і коли наступний платіж." action="Додати" onAction={() => setForm({ draft: { kind: 'installment' } })} />
        : <>
          {active.map(o => (
            <Card key={o.id} onClick={() => setOpen(o.id)}>
              <div className="stack-s">
                <div className="spread">
                  <span className="hstack grow"><span style={{ fontSize: 22 }}>{o.icon}</span><b className="ellipsis">{o.name}</b></span>
                  <b className="tnum">{money(o.amount, o.currency, 0)}</b>
                </div>
                {o.state.payments_total ? <Progress value={((o.state.paid_count || 0) / o.state.payments_total) * 100} /> : null}
                <div className="spread small">
                  <span className={o.state.status === 'overdue' ? 'danger' : 'muted'}>{statusLine(o)}</span>
                  {o.state.remaining_amount ? <span className="muted tnum">лишилось {money(o.state.remaining_amount, o.currency, 0)}</span> : statusBadge(o)}
                </div>
                {o.suggested.length > 0 && <div className="small" style={{ color: 'var(--link)' }}>🔗 Знайдено {o.suggested.length} схожих платежів</div>}
              </div>
            </Card>
          ))}
          {done.length > 0 && (
            <Card flush>
              {done.map(o => <Row key={o.id} icon={o.icon} title={o.name} sub={`Виплачено · ${o.state.paid_count} платежів`} end={<Badge tone="ok">✓</Badge>} onClick={() => setOpen(o.id)} />)}
            </Card>
          )}
        </>)}

      {seg === 'subs' && (subs.length === 0
        ? <Empty icon="🔁" title="Немає підписок" text="YouTube, iCloud, інтернет — побачите, скільки йде на підписки щомісяця." action="Додати" onAction={() => setForm({ draft: { kind: 'subscription' } })} />
        : <Card flush>
          {subs.map(o => (
            <Row key={o.id} icon={o.icon} title={<>{o.name}{o.suggested.length > 0 && <span style={{ color: 'var(--link)' }}> · 🔗 {o.suggested.length}</span>}</>}
              sub={<span className={o.state.status === 'missing' || o.state.status === 'stale' ? 'warn' : ''}>{statusLine(o)}</span>}
              end={<b className="tnum">{money(o.amount, o.currency)}<span className="muted xsmall">/{o.period === 'year' ? 'рік' : 'міс'}</span></b>}
              onClick={() => setOpen(o.id)} />
          ))}
        </Card>)}

      <Button variant="secondary" onClick={() => setForm({ draft: { kind: seg === 'subs' ? 'subscription' : 'installment' } })}>
        + {seg === 'subs' ? 'Підписка' : 'Розстрочка або кредит'}
      </Button>

      {current && !form && <ObligationSheet familyId={familyId} item={current} onClose={() => setOpen(null)}
        onEdit={() => setForm({ item: current })} onChanged={changed} />}
      {form && <ObligationForm familyId={familyId} item={form.item} draft={form.draft} categories={categories}
        onClose={() => setForm(null)} onSaved={o => { setForm(null); if (!o) setOpen(null); changed(); }} />}
    </>
  );
}
