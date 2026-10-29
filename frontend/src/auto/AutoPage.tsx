import { Fragment, useEffect, useMemo, useState } from 'react';
import { toast } from '../toast';
import { day, money, monthYear, plural, qty } from '../format';
import { confirmAsync, haptic } from '../tg';
import type { FamilyUser } from '../types';
import { Badge, Banner, Button, Card, Chips, Empty, Row, Section, Segmented, Spinner } from '../ui';
import { errText } from '../housing/api';
import { autoApi } from './api';
import AutoStats from './AutoStats';
import DocSheet, { docWhen } from './DocSheet';
import LogSheet from './LogSheet';
import SuggestSheet from './SuggestSheet';
import VehicleForm from './VehicleForm';
import { AutoOverview, Fuel, FUELS, LogDraft, LogKind, TxBrief, VDoc, Vehicle, VLog } from './types';

export type AutoAction = { txId: number; vehicleId: number } | null;
type SheetState = { kind: 'log'; log?: VLog; draft?: LogDraft; tx?: TxBrief | null; initialKind?: LogKind }
  | { kind: 'vehicle'; vehicle?: Vehicle } | { kind: 'suggest' } | { kind: 'doc'; doc?: VDoc };
type Filter = 'all' | 'fuel' | 'care' | 'other';
const CARE: LogKind[] = ['service', 'repair', 'tires'];

const logTitle = (l: VLog) => {
  if (l.kind === 'fuel') {
    const f = l.fuel ? FUELS[l.fuel] : null;
    return [f?.label || 'Заправка', l.liters ? `${qty(l.liters, 1)} ${f?.unit || 'л'}` : null].filter(Boolean).join(' ');
  }
  if (l.kind === 'odometer') return 'Пробіг';
  return l.title || l.transaction?.title || l.label;
};

function Stat({ label, value, unit, sub, onClick }: { label: string; value: string; unit?: string; sub?: string | null; onClick?: () => void }) {
  const Tag: any = onClick ? 'button' : 'div';
  return (
    <Tag className="stat" onClick={onClick}>
      <div className="stat__label">{label}</div>
      <div className="stat__value tnum">{value}{unit && <span className="stat__unit"> {unit}</span>}</div>
      {sub && <div className="stat__sub">{sub}</div>}
    </Tag>
  );
}

export default function AutoPage({ familyId, overview, setOverview, accounts, familyUsers, onFinanceChanged, action, onActionDone }: {
  familyId: number; overview: AutoOverview | null; setOverview: (o: AutoOverview) => void; accounts: string[];
  familyUsers: FamilyUser[]; onFinanceChanged: () => void; action: AutoAction; onActionDone: () => void;
}) {
  const [loading, setLoading] = useState(!overview);
  const [vid, setVid] = useState<number | null>(null);
  const [seg, setSeg] = useState<'log' | 'stats'>('log');
  const [filter, setFilter] = useState<Filter>('all');
  const [logs, setLogs] = useState<VLog[] | null>(null);
  const [sheet, setSheet] = useState<SheetState | null>(null);
  const [importing, setImporting] = useState(false);

  const vehicles = overview?.vehicles || [];
  const v = vehicles.find(x => x.id === vid) || vehicles[0] || null;

  const reload = async () => {
    try { setOverview(await autoApi.overview(familyId)); } catch (e) { toast(errText(e, 'Не вдалося завантажити «Авто»'), 'err'); }
    setLoading(false);
  };
  const reloadLogs = () => { if (v) autoApi.logs(familyId, v.id).then(setLogs).catch(e => toast(errText(e), 'err')); };
  const changed = (financeToo = false) => { reload(); reloadLogs(); if (financeToo) onFinanceChanged(); };

  useEffect(() => { if (!overview) reload(); else setLoading(false); }, [familyId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setLogs(null); reloadLogs(); }, [familyId, v?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {  // «Пов'язати» → авто: відкриваємо запис, заповнений з операції
    if (!action || !overview) return;
    autoApi.draft(familyId, action.txId, action.vehicleId)
      .then(r => { setVid(action.vehicleId); setSheet({ kind: 'log', draft: r.draft, tx: r.transaction }); })
      .catch(e => toast(errText(e), 'err'));
    onActionDone();
  }, [action, !!overview]); // eslint-disable-line react-hooks/exhaustive-deps

  const groups = useMemo(() => {
    const shown = (logs || []).filter(l => filter === 'all' || (filter === 'fuel' ? l.kind === 'fuel' : filter === 'care' ? CARE.includes(l.kind) : l.kind !== 'fuel' && !CARE.includes(l.kind)));
    const out: { month: string; total: number; items: VLog[] }[] = [];
    for (const l of shown) {
      const m = l.date.slice(0, 7);
      const g = out[out.length - 1];
      if (g && g.month === m) { g.items.push(l); g.total += l.amount; } else out.push({ month: m, total: l.amount, items: [l] });
    }
    return out;
  }, [logs, filter]);

  if (loading) return <div className="page"><Spinner label="Завантаження «Авто»…" /></div>;
  if (!overview) return <div className="page"><Empty icon="🚗" title="Не вдалося завантажити" action="Спробувати ще" onAction={reload} /></div>;

  if (!v) return (
    <div className="page">
      <h1 className="page-title">Авто</h1>
      <Card className="hero">
        <div style={{ fontSize: 44 }}>🚗</div>
        <div className="bold" style={{ fontSize: 18, marginTop: 6 }}>Журнал авто</div>
        <div className="muted small" style={{ marginTop: 6, lineHeight: 1.45 }}>
          Заправки, ТО, ремонти й мийки в одному місці: витрата л/100 км (окремо газ і бензин), гривні на кілометр,
          пробіг за місяць. Операції з категорій «Паливо» та «Авто» потрапляють у журнал самі — літри, ціну й пробіг
          Bimi читає з коментаря («Газ 30 л по 42,9. Пробіг: 281100»).
        </div>
        <div style={{ marginTop: 14 }}><Button onClick={() => setSheet({ kind: 'vehicle' })}>Додати авто</Button></div>
      </Card>
      {sheet?.kind === 'vehicle' && <VehicleForm familyId={familyId} familyUsers={familyUsers} onClose={() => setSheet(null)}
        onSaved={nv => { setSheet(null); if (nv) setVid(nv.id); reload(); }} />}
    </div>
  );

  const s = v.stats;
  // the last reading is weeks old → where the odometer probably is now (usual km per day since)
  const staleDays = s.odometer_date ? (Date.now() - new Date(s.odometer_date).getTime()) / 864e5 : 0;
  const odoNow = s.odometer && s.km_per_month && staleDays > 10 ? Math.round((s.odometer + s.km_per_month / 30.44 * staleDays) / 10) * 10 : null;
  const fuels = Object.entries(s.fuels) as [Fuel, NonNullable<typeof s.fuels[Fuel]>][];
  const importHistory = async () => {
    if (!(await confirmAsync(`Перенести в журнал «${v.name}» усі витрати з категорій «Паливо» й «Авто»? Літри, ціну й пробіг візьмемо з коментарів.`))) return;
    setImporting(true);
    try {
      const r = await autoApi.importHistory(familyId, v.id);
      haptic('success');
      toast(`Перенесено ${r.linked} ${plural(r.linked, 'операцію', 'операції', 'операцій')}${r.skipped.length ? ` · ${r.skipped.length} з іншим паливом — у «Схожих»` : ''}`);
      changed();
    } catch (e) { toast(errText(e), 'err'); }
    setImporting(false);
  };
  const actions = [
    { icon: '⛽', label: 'Заправка', onClick: () => setSheet({ kind: 'log', initialKind: 'fuel' }) },
    { icon: '🔧', label: 'Витрата', onClick: () => setSheet({ kind: 'log', initialKind: 'repair' }) },
    { icon: '📍', label: 'Пробіг', onClick: () => setSheet({ kind: 'log', initialKind: 'odometer' }) },
    { icon: '⚙️', label: 'Авто', onClick: () => setSheet({ kind: 'vehicle', vehicle: v }) },
  ];

  return (
    <div className="page">
      <div className="spread">
        <h1 className="page-title">{v.icon} {v.name}</h1>
        <div className="hstack">
          {v.plate && <Badge>{v.plate}</Badge>}
          <button className="link" onClick={() => setSheet({ kind: 'vehicle' })}>+ Авто</button>
        </div>
      </div>
      {vehicles.length > 1 && <Chips scroll small value={v.id} onChange={setVid} options={vehicles.map(x => ({ value: x.id, label: `${x.icon} ${x.name}` }))} />}

      <Card className="hero">
        <div className="hero__label">Пробіг{s.odometer_date ? ` на ${day(s.odometer_date)}` : ''}</div>
        <div className="hero__value tnum">{s.odometer ? <>{qty(s.odometer, 0)} <span className="hero__unit">км</span></> : '—'}</div>
        <div className="hero__sub">
          {odoNow && <span>зараз ≈ {qty(odoNow, 0)} км</span>}
          {s.km_per_month && <span>{qty(s.km_per_month, 0)} км/міс</span>}
          <span>{money(s.month_spend, 'UAH', 0)} цього місяця</span>
        </div>
        <div className="actions" style={{ marginTop: 16, gridTemplateColumns: `repeat(${actions.length}, 1fr)` }}>
          {actions.map(a => <button key={a.label} className="action" onClick={a.onClick}><span className="action__icon">{a.icon}</span>{a.label}</button>)}
        </div>
      </Card>

      {s.logs === 0 && overview.suggested > 0 ? (
        <Banner icon="📥" onClick={importing ? undefined : importHistory}>
          {importing ? 'Переносимо…' : <>Перенести історію: <b>{overview.suggested}</b> {plural(overview.suggested, 'операція', 'операції', 'операцій')} з «Паливо» й «Авто» — з літрами й пробігом з коментарів</>}
        </Banner>
      ) : overview.suggested > 0 && (
        <Banner icon={overview.suggested_sure ? '⛽' : '🔗'} onClick={() => setSheet({ kind: 'suggest' })}>
          {overview.suggested_sure
            ? <><b>{overview.suggested_sure} {plural(overview.suggested_sure, 'нова заправка', 'нові заправки', 'нових заправок')}</b> з банку{overview.suggested > overview.suggested_sure ? ` і ще ${overview.suggested - overview.suggested_sure} на перевірку` : ''} — додати в журнал</>
            : <>{overview.suggested} {plural(overview.suggested, 'операція схожа', 'операції схожі', 'операцій схожі')} на авто — перевірити</>}
        </Banner>
      )}

      {(fuels.length > 0 || s.cost_per_km !== null) && (
        <div className="grid2">
          {fuels.map(([f, st]) => st.secondary ? (
            <Stat key={f} label={`${FUELS[f].label} · рідко`} value={st.per_month_l !== null ? `≈ ${qty(st.per_month_l, 0)}` : '—'} unit="л/міс"
              sub={`${st.fills} ${plural(st.fills, 'заправка', 'заправки', 'заправок')} · ${money(st.per_month_money, 'UAH', 0)}/міс`} />
          ) : (
            <Stat key={f} label={`${FUELS[f].label}, витрата`} value={st.avg_per100 !== null ? st.avg_per100.toFixed(1).replace('.', ',') : '—'} unit={st.avg_per100 !== null ? 'л/100' : undefined}
              sub={st.last_per100 !== null ? `повний бак — ${qty(st.last_per100, 1)}` : st.avg_per100 === null ? 'потрібні 2 заправки з пробігом' : st.last_price ? `${qty(st.last_price)} ₴/л` : null}
              onClick={() => setSeg('stats')} />
          ))}
          {s.cost_per_km !== null && (
            <Stat label="Кілометр коштує" value={qty(s.cost_per_km, 2)} unit="₴" sub={`з них пальне ${qty(s.fuel_cost_per_km)} ₴`} onClick={() => setSeg('stats')} />
          )}
          <Stat label="За рік" value={money(s.year_spend, 'UAH', 0)} sub={s.km_tracked ? `${qty(s.km_tracked, 0)} км у журналі` : null} onClick={() => setSeg('stats')} />
        </div>
      )}

      {(() => {
        const docs = v.documents || [];
        const urgent = docs.filter(d => d.status !== 'active');
        return (
          <Section title="Страховка" action={docs.length ? '+ Поліс' : undefined} onAction={() => setSheet({ kind: 'doc' })}>
            <Card flush>
              {docs.map(d => (
                <Row key={d.id} icon={d.icon} title={[d.label.replace(' (ОСЦПВ)', ''), d.company].filter(Boolean).join(' · ')}
                  sub={<span className={d.status === 'expired' ? 'danger' : d.status === 'soon' ? 'warn' : ''}>{docWhen(d)}</span>}
                  end={<span className="hstack" style={{ gap: 6 }}>{d.has_file && <span title="Є файл">📎</span>}{d.url && <span title="Є посилання">🌐</span>}
                    {d.status !== 'active' && <Badge tone={d.status === 'expired' ? 'danger' : 'warn'}>{d.status === 'expired' ? 'закінчився' : 'скоро'}</Badge>}</span>}
                  chevron onClick={() => setSheet({ kind: 'doc', doc: d })} />
              ))}
              {docs.length === 0 && <Row icon="🛡️" title="Додати автоцивілку" sub="Нагадаю за місяць до кінця · PDF чи посилання завжди під рукою" chevron onClick={() => setSheet({ kind: 'doc' })} />}
            </Card>
            {urgent.length > 0 && <div className="muted xsmall" style={{ padding: '0 4px' }}>Новий поліс додайте окремо — старий лишиться в історії.</div>}
          </Section>
        );
      })()}

      <Segmented value={seg} onChange={setSeg} options={[{ value: 'log', label: 'Журнал' }, { value: 'stats', label: 'Графіки' }]} />

      {seg === 'log' && (logs === null ? <Spinner /> : logs.length === 0 ? (
        <Empty icon="⛽" title="Журнал порожній" text="Додайте заправку або перенесіть історію з категорій «Паливо» й «Авто»." action="⛽ Заправка" onAction={() => setSheet({ kind: 'log', initialKind: 'fuel' })} />
      ) : (
        <>
          <Chips scroll small value={filter} onChange={setFilter} options={[{ value: 'all', label: 'Усе' }, { value: 'fuel', label: '⛽ Пальне' }, { value: 'care', label: '🔧 ТО й ремонт' }, { value: 'other', label: '🧽 Інше' }]} />
          {groups.map(g => (
            <Fragment key={g.month}>
              <div className="date-head spread"><span>{monthYear(`${g.month}-01`)}</span>{g.total > 0 && <span className="tnum">{money(g.total, 'UAH', 0)}</span>}</div>
              <Card flush>
                {g.items.map(l => (
                  <Row key={l.id} icon={l.icon} title={<>{logTitle(l)}{l.place && !logTitle(l).toLowerCase().includes(l.place.toLowerCase()) && <span className="muted"> · {l.place}</span>}{l.full_tank && <span className="badge-mini">повний</span>}</>}
                    sub={[day(l.date), l.odometer ? `${qty(l.odometer, 0)} км` : null, l.km_since ? `+${qty(l.km_since, 0)} км` : null,
                      l.segment ? `${qty(l.segment.per100, 1)} л/100` : null, v.driver_ids.length > 1 ? l.user_name : null, l.kind !== 'fuel' && l.note ? l.note : null,
                      !l.transaction_id && l.kind !== 'odometer' && l.amount > 0 ? 'не у фінансах' : null].filter(Boolean).join(' · ')}
                    end={l.amount > 0 ? <div className="end-stack"><b className="tnum">{money(l.amount, 'UAH', 0)}</b>{l.kind === 'fuel' && l.price ? <span className="muted xsmall tnum">{qty(l.price)} ₴/л</span> : null}</div> : undefined}
                    onClick={() => setSheet({ kind: 'log', log: l })} />
                ))}
              </Card>
            </Fragment>
          ))}
        </>
      ))}
      {seg === 'stats' && <AutoStats familyId={familyId} vehicle={v} logs={logs} />}

      {sheet?.kind === 'log' && <LogSheet familyId={familyId} vehicles={vehicles} vehicleId={v.id} log={sheet.log} draft={sheet.draft} tx={sheet.tx}
        initialKind={sheet.initialKind} accounts={accounts} onClose={() => setSheet(null)} onSaved={withTx => changed(withTx || !!sheet.tx)} />}
      {sheet?.kind === 'vehicle' && <VehicleForm familyId={familyId} vehicle={sheet.vehicle} familyUsers={familyUsers} onClose={() => setSheet(null)}
        onSaved={nv => { setSheet(null); setVid(nv ? nv.id : null); reload(); }} />}
      {sheet?.kind === 'doc' && <DocSheet familyId={familyId} vehicleId={v.id} doc={sheet.doc} accounts={accounts} onClose={() => setSheet(null)}
        onSaved={financeToo => changed(financeToo)} />}
      {sheet?.kind === 'suggest' && <SuggestSheet familyId={familyId} onClose={() => { setSheet(null); reload(); }}
        onPick={sg => setSheet({ kind: 'log', draft: sg.draft, tx: sg.transaction })} onChanged={() => { /* reloaded on close */ }} />}
    </div>
  );
}

