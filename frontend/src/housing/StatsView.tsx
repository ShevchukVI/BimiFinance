import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, Cell, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { toast } from '../toast';
import { day, dmy, hm, hoursText, money, monthShort, monthYear, qty, todayIso } from '../format';
import { confirmAsync, haptic } from '../tg';
import { Banner, Button, Card, Chips, Empty, Field, Row, Section, Sheet, Spinner, Tile } from '../ui';
import { errText, housingApi } from './api';
import type { HousingNote, Outages, Overview, Stats } from './types';
import { cssVar, HEAT, SERIES } from './chart';

type Metric = `m${number}` | 'money' | 'power';
const NOTE_KINDS = [{ value: 'note', label: '📝 Нотатка' }, { value: 'heating', label: '♨️ Опалення' }, { value: 'away', label: '🧳 Не було вдома' }, { value: 'repair', label: '🔧 Ремонт' }];
const NOTE_ICON: Record<string, string> = { note: '📝', heating: '♨️', away: '🧳', repair: '🔧' };

export default function StatsView({ familyId, overview }: { familyId: number; overview: Overview }) {
  const [months, setMonths] = useState(12);
  const [stats, setStats] = useState<Stats | null>(null);
  const [metric, setMetric] = useState<Metric>('money');
  const [outages, setOutages] = useState<Outages | null>(null);
  const [notes, setNotes] = useState<HousingNote[] | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [allNotes, setAllNotes] = useState(false);

  useEffect(() => {
    setStats(null);
    housingApi.stats(familyId, months).then(s => {
      setStats(s);
      setMetric(m => (m === 'money' && s.meters.length ? (`m${s.meters[0].meter_id}` as Metric) : m));
    }).catch(e => toast(errText(e), 'err'));
  }, [familyId, months]);
  useEffect(() => { housingApi.notes(familyId).then(setNotes).catch(() => setNotes([])); }, [familyId]);
  useEffect(() => {
    if (metric === 'power' && !outages) housingApi.outages(familyId, 30).then(setOutages).catch(() => { /**/ });
  }, [metric]); // eslint-disable-line react-hooks/exhaustive-deps

  const options = useMemo(() => [
    ...(stats?.meters || []).map(m => ({ value: `m${m.meter_id}` as Metric, label: m.name })),
    { value: 'money' as Metric, label: '💰 Гроші' },
    ...(overview.power ? [{ value: 'power' as Metric, label: '🔌 Відключення' }] : []),
  ], [stats, overview.power]);

  if (!stats) return <Spinner />;
  const hint = cssVar('--hint');
  const accent = cssVar('--accent', '#3b82f6');

  return (
    <>
      <Chips scroll small value={months} onChange={setMonths} options={[{ value: 3, label: '3 міс' }, { value: 6, label: '6 міс' }, { value: 12, label: 'Рік' }, { value: 24, label: '2 роки' }]} />
      <Chips scroll small value={metric} onChange={setMetric} options={options} />

      {stats.insights.length > 0 && <div className="stack-s">{stats.insights.map((t, i) => <Banner key={i} icon="💡">{t}</Banner>)}</div>}

      {metric.startsWith('m') && (() => {
        const ms = stats.meters.find(x => `m${x.meter_id}` === metric);
        if (!ms) return null;
        const data = ms.points.map(p => ({ ...p, label: monthShort(p.month), v: p.volume ?? 0 }));
        const known = ms.points.filter(p => p.volume !== null && !p.partial);
        const avg = known.length ? known.reduce((a, p) => a + (p.volume || 0), 0) / known.length : null;
        const heatAvg = known.filter(p => p.heating);
        const coldAvg = known.filter(p => !p.heating);
        const avgOf = (xs: typeof known) => xs.length ? xs.reduce((a, p) => a + (p.volume || 0), 0) / xs.length : null;
        const hasPph = ms.points.some(p => p.per_powered_hour !== undefined);
        return (
          <>
            <Card>
              <div className="muted small" style={{ marginBottom: 6 }}>{ms.name}, {ms.unit} на місяць</div>
              <div style={{ height: 190 }}>
                <ResponsiveContainer>
                  <BarChart data={data} margin={{ top: 6, right: 0, left: -18, bottom: 0 }}>
                    <XAxis dataKey="label" tick={{ fontSize: 11, fill: hint }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={44} />
                    <Tooltip cursor={{ fill: 'transparent' }} formatter={(v: any, _n: any, item: any) => [
                      `${qty(v)} ${ms.unit}${item.payload.cost ? ` · ${money(item.payload.cost, 'UAH', 0)}` : ''}`,
                      item.payload.source === 'bill' ? 'з платіжки' : item.payload.partial ? 'поточний місяць' : 'за показниками']} />
                    <Bar isAnimationActive={false} dataKey="v" radius={[5, 5, 0, 0]}>
                      {data.map((p, i) => <Cell key={i} fill={p.heating ? HEAT : accent} fillOpacity={p.source === 'bill' ? 1 : p.partial ? 0.35 : 0.6} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-legend" style={{ marginTop: 6 }}>
                <span><i className="dot" style={{ background: accent }} />з платіжки</span>
                <span><i className="dot" style={{ background: accent, opacity: 0.6 }} />за показниками</span>
                <span><i className="dot" style={{ background: HEAT }} />опалення</span>
              </div>
            </Card>
            <div className="grid2">
              <Tile label="Середньо на місяць" value={avg !== null ? `${qty(avg, 0)} ${ms.unit}` : '—'} />
              <Tile label="Найбільше" value={known.length ? `${qty(Math.max(...known.map(p => p.volume || 0)), 0)} ${ms.unit}` : '—'} />
              {avgOf(heatAvg) !== null && avgOf(coldAvg) !== null && <>
                <Tile label="З опаленням" value={`${qty(avgOf(heatAvg)!, 0)} ${ms.unit}`} tone="warn" />
                <Tile label="Без опалення" value={`${qty(avgOf(coldAvg)!, 0)} ${ms.unit}`} />
              </>}
            </div>
            {hasPph && (
              <Card>
                <div className="muted small" style={{ marginBottom: 6 }}>{ms.unit} за годину, коли світло було</div>
                <div style={{ height: 150 }}>
                  <ResponsiveContainer>
                    <ComposedChart data={data} margin={{ top: 6, right: 0, left: -18, bottom: 0 }}>
                      <XAxis dataKey="label" tick={{ fontSize: 11, fill: hint }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={44} />
                      <Tooltip formatter={(v: any) => [`${v} ${ms.unit}/год`, '']} />
                      <Line isAnimationActive={false} dataKey="per_powered_hour" stroke={SERIES[1]} strokeWidth={2} dot={{ r: 3 }} connectNulls />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <div className="muted xsmall">Нормалізує споживання на відключення: якщо світла було менше — видно реальне навантаження обігрівачів.</div>
              </Card>
            )}
          </>
        );
      })()}

      {metric === 'money' && (() => {
        const provs = stats.providers.filter(p => p.points.some(x => x.accrued || x.paid));
        if (!provs.length) return <Empty icon="💰" title="Ще немає платіжок і оплат" />;
        const data = stats.months.map((m, i) => {
          const row: Record<string, number | string> = { label: monthShort(m), month: m, paid: 0 };
          for (const p of provs) { row[`p${p.provider_id}`] = p.points[i].accrued || 0; row.paid = (row.paid as number) + (p.points[i].paid || 0); }
          return row;
        });
        const totalPaid = data.reduce((a, r) => a + (r.paid as number), 0);
        return (
          <>
            <Card>
              <div className="muted small" style={{ marginBottom: 6 }}>Нараховано по послугах і сплачено (лінія), ₴</div>
              <div style={{ height: 210 }}>
                <ResponsiveContainer>
                  <ComposedChart data={data} margin={{ top: 6, right: 0, left: -12, bottom: 0 }}>
                    <XAxis dataKey="label" tick={{ fontSize: 11, fill: hint }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={48} />
                    <Tooltip formatter={(v: any, name: any) => [money(v, 'UAH', 0), name === 'paid' ? 'Сплачено' : provs.find(p => `p${p.provider_id}` === name)?.name || name]} />
                    {provs.map((p, i) => <Bar isAnimationActive={false} key={p.provider_id} dataKey={`p${p.provider_id}`} stackId="a" fill={SERIES[i % SERIES.length]} />)}
                    <Line isAnimationActive={false} dataKey="paid" stroke={cssVar('--text', '#111')} strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-legend" style={{ marginTop: 6 }}>
                {provs.map((p, i) => <span key={p.provider_id}><i className="dot" style={{ background: SERIES[i % SERIES.length] }} />{p.name}</span>)}
              </div>
            </Card>
            <Tile label={`Сплачено за ${months} міс`} value={money(totalPaid, 'UAH', 0)} />
          </>
        );
      })()}

      {metric === 'power' && <PowerBlock familyId={familyId} stats={stats} outages={outages} onSynced={() => housingApi.outages(familyId, 30).then(setOutages)} />}

      <Section title="Примітки" action="+ Додати" onAction={() => setNoteOpen(true)}>
        {notes === null ? <Spinner /> : notes.length === 0 ? <div className="muted small center">Позначайте, що змінювалось: увімкнули обігрівач, поїхали, ремонт — так легше пояснити стрибки.</div> : (
          <Card flush>
            {notes.slice(0, allNotes ? 200 : 5).map(n => (
              <Row key={n.id} compact icon={NOTE_ICON[n.kind] || '📝'} title={n.text || '—'}
                sub={`${dmy(n.date)}${n.end_date ? ` – ${dmy(n.end_date)}` : n.kind === 'heating' ? ' – досі' : ''}`}
                end={<button className="link danger small" onClick={async () => {
                  if (!(await confirmAsync('Видалити примітку?'))) return;
                  try { await housingApi.deleteNote(familyId, n.id); setNotes(x => (x || []).filter(y => y.id !== n.id)); } catch (e) { toast(errText(e), 'err'); }
                }}>✕</button>} />
            ))}
            {notes.length > 5 && <Row compact title={<span className="link">{allNotes ? 'Згорнути' : `Показати всі (${notes.length})`}</span>} onClick={() => setAllNotes(v => !v)} />}
          </Card>
        )}
      </Section>
      {noteOpen && <NoteSheet familyId={familyId} onClose={() => setNoteOpen(false)} onSaved={n => setNotes(x => [n, ...(x || [])])} />}
    </>
  );
}

function PowerBlock({ familyId, stats, outages, onSynced }: { familyId: number; stats: Stats; outages: Outages | null; onSynced: () => void }) {
  const [busy, setBusy] = useState(false);
  const hint = cssVar('--hint');
  const sync = async () => {
    setBusy(true);
    try { const r = await housingApi.syncOutages(familyId); toast(r.skipped ? 'Щойно оновлено' : `Оновлено: ${r.events} подій`); onSynced(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const monthly = stats.power.map(p => ({ label: monthShort(p.month), h: p.off_hours ?? 0, n: p.outages ?? 0, share: p.hours ? Math.round(((p.off_hours || 0) / p.hours) * 100) : 0 }));
  const daily = (outages?.daily || []).map(d => ({ label: day(d.date), h: d.off_hours }));
  return (
    <>
      <Card>
        <div className="muted small" style={{ marginBottom: 6 }}>Годин без світла на місяць</div>
        <div style={{ height: 170 }}>
          <ResponsiveContainer>
            <BarChart data={monthly} margin={{ top: 6, right: 0, left: -8, bottom: 0 }}>
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: hint }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={40} />
              <Tooltip cursor={{ fill: 'transparent' }} formatter={(v: any, _n: any, item: any) => [`${hoursText(v)} · ${item.payload.n} відкл. · ${item.payload.share}% часу`, '']} />
              <Bar isAnimationActive={false} dataKey="h" fill="#64748b" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      {daily.length > 0 && (
        <Card>
          <div className="muted small" style={{ marginBottom: 6 }}>Останні 30 днів, год/день</div>
          <div style={{ height: 120 }}>
            <ResponsiveContainer>
              <BarChart data={daily} margin={{ top: 4, right: 0, left: -24, bottom: 0 }}>
                <XAxis dataKey="label" tick={{ fontSize: 9, fill: hint }} axisLine={false} tickLine={false} interval={6} />
                <YAxis tick={{ fontSize: 9, fill: hint }} axisLine={false} tickLine={false} width={32} domain={[0, 24]} />
                <Tooltip cursor={{ fill: 'transparent' }} formatter={(v: any) => [hoursText(v), 'без світла']} />
                <Bar isAnimationActive={false} dataKey="h" fill="#94a3b8" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
      {outages && outages.items.length > 0 && (
        <Card flush>
          {outages.items.slice(0, 10).map(o => (
            <Row key={o.id} compact icon={o.ended_at ? '⚫' : '🔴'} title={`${day(o.started_at)}, ${hm(o.started_at)} – ${o.ended_at ? hm(o.ended_at) : 'досі'}`}
              end={<span className="muted small">{hoursText(o.minutes / 60)}</span>} />
          ))}
        </Card>
      )}
      <Button variant="secondary" size="sm" onClick={sync} busy={busy}>Оновити зі світлобота</Button>
      <div className="muted xsmall center">Джерело: {outages?.channel ? `t.me/${outages.channel}` : 'світлобот'} · {monthYear(todayIso())}</div>
    </>
  );
}

function NoteSheet({ familyId, onClose, onSaved }: { familyId: number; onClose: () => void; onSaved: (n: HousingNote) => void }) {
  const [kind, setKind] = useState('note');
  const [text, setText] = useState('');
  const [date, setDate] = useState(todayIso());
  const [end, setEnd] = useState('');
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { const n = await housingApi.addNote(familyId, { kind, text: text.trim(), date, end_date: end || null }); haptic('success'); onSaved(n); onClose(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return (
    <Sheet title="Примітка" icon="📝" onClose={onClose} footer={<Button onClick={save} busy={busy} disabled={!text.trim() && kind === 'note'}>Зберегти</Button>}>
      <Chips small value={kind} onChange={setKind} options={NOTE_KINDS} />
      <input className="input" autoFocus placeholder="Напр. Увімкнули масляний обігрівач у спальні" value={text} onChange={e => setText(e.target.value)} />
      <div className="grid2">
        <Field label="З"><input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} /></Field>
        <Field label="По (необов'язково)"><input className="input" type="date" value={end} onChange={e => setEnd(e.target.value)} /></Field>
      </div>
    </Sheet>
  );
}
