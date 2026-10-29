import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { toast } from '../toast';
import { day, money, monthShort, qty } from '../format';
import { Card, Chips, Empty, Progress, Row, Section, Spinner } from '../ui';
import { errText } from '../housing/api';
import { cssVar } from '../housing/chart';
import { autoApi } from './api';
import { Fuel, FUELS, KINDS, Vehicle, VehicleStats, VLog } from './types';

const kfmt = (v: number) => (v >= 1000 ? `${qty(v / 1000, 1)}к` : String(v));

const GROUPS = [
  { key: 'fuel', label: 'Пальне', color: '#3b82f6' },
  { key: 'maintenance', label: 'ТО й ремонт', color: '#f97316' },
  { key: 'other', label: 'Мийка, парковка, інше', color: '#8b5cf6' },
] as const;

export default function AutoStats({ familyId, vehicle, logs }: { familyId: number; vehicle: Vehicle; logs: VLog[] | null }) {
  const [months, setMonths] = useState(12);
  const [stats, setStats] = useState<VehicleStats | null>(null);
  useEffect(() => {
    setStats(null);
    autoApi.stats(familyId, vehicle.id, months).then(setStats).catch(e => toast(errText(e), 'err'));
  }, [familyId, vehicle.id, months, logs]);

  const from = stats?.months[0]?.month || '';
  const byKind = useMemo(() => {
    const sums: Record<string, number> = {};
    for (const l of logs || []) if (l.date >= from && l.kind !== 'odometer') sums[l.kind] = (sums[l.kind] || 0) + l.amount;
    const total = Object.values(sums).reduce((a, b) => a + b, 0);
    return { total, rows: KINDS.filter(k => sums[k.value] > 0).map(k => ({ ...k, sum: sums[k.value] })).sort((a, b) => b.sum - a.sum) };
  }, [logs, from]);
  const segments = (logs || []).filter(l => l.segment).slice(0, 8);

  if (!stats) return <Spinner />;
  const hint = cssVar('--hint');
  const data = stats.months.map(m => ({ ...m, label: monthShort(m.month) }));
  const hasKm = data.some(m => m.km);
  const priceFuels = Array.from(new Set((stats.prices || []).map(p => p.fuel))) as Fuel[];
  const priceData = (stats.prices || []).filter(p => p.date >= from).map(p => ({ date: p.date, [p.fuel]: p.price }));

  return (
    <>
      <Chips scroll small value={months} onChange={setMonths} options={[{ value: 3, label: '3 міс' }, { value: 6, label: '6 міс' }, { value: 12, label: 'Рік' }, { value: 24, label: '2 роки' }]} />
      {byKind.total === 0 ? <Empty icon="📊" title="За цей період витрат немає" /> : (
        <>
          <Card>
            <div className="spread" style={{ marginBottom: 6 }}>
              <span className="muted small">Витрати по місяцях</span>
              <b className="tnum">{money(byKind.total, 'UAH', 0)}</b>
            </div>
            <div style={{ height: 190 }}>
              <ResponsiveContainer>
                <BarChart data={data} margin={{ top: 6, right: 0, left: -6, bottom: 0 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: hint }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={34} tickFormatter={kfmt} />
                  <Tooltip cursor={{ fill: 'transparent' }} formatter={(v: any, n: any) => [money(v, 'UAH', 0), GROUPS.find(g => g.key === n)?.label || n]} />
                  {GROUPS.map((g, i) => <Bar key={g.key} isAnimationActive={false} dataKey={g.key} stackId="a" fill={g.color}
                    radius={i === GROUPS.length - 1 ? [5, 5, 0, 0] : undefined} />)}
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="chart-legend" style={{ marginTop: 6 }}>
              {GROUPS.map(g => <span key={g.key}><i className="dot" style={{ background: g.color }} />{g.label}</span>)}
            </div>
          </Card>
          <Section title="На що йдуть гроші">
            <Card flush>
              {byKind.rows.map(r => (
                <Row key={r.value} icon={r.icon} title={r.label}
                  sub={<Progress value={r.sum / byKind.total * 100} />}
                  end={<div className="end-stack"><b className="tnum">{money(r.sum, 'UAH', 0)}</b><span className="muted xsmall">{Math.round(r.sum / byKind.total * 100)}%</span></div>} />
              ))}
            </Card>
          </Section>
        </>
      )}

      {hasKm && (
        <Card>
          <div className="muted small" style={{ marginBottom: 6 }}>Пробіг по місяцях, км{stats.km_per_month ? ` · у середньому ${qty(stats.km_per_month, 0)}` : ''}</div>
          <div style={{ height: 150 }}>
            <ResponsiveContainer>
              <BarChart data={data} margin={{ top: 6, right: 0, left: -6, bottom: 0 }}>
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: hint }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={34} tickFormatter={kfmt} />
                <Tooltip cursor={{ fill: 'transparent' }} formatter={(v: any, _n: any, it: any) => [`${qty(v, 0)} км${it.payload.partial ? ' (поки що)' : ''}`, 'Пробіг']} />
                <Bar isAnimationActive={false} dataKey="km" radius={[5, 5, 0, 0]} fill="#10b981" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {priceData.length > 1 && (
        <Card>
          <div className="muted small" style={{ marginBottom: 6 }}>Ціна пального, ₴ за літр</div>
          <div style={{ height: 160 }}>
            <ResponsiveContainer>
              <LineChart data={priceData} margin={{ top: 6, right: 6, left: -6, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke={cssVar('--fill', '#eee')} />
                <XAxis dataKey="date" tickFormatter={d => day(d)} tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={30} />
                <Tooltip labelFormatter={d => day(String(d))} formatter={(v: any, n: any) => [`${qty(v)} ₴`, FUELS[n as Fuel]?.label || n]} />
                {priceFuels.map(f => <Line key={f} isAnimationActive={false} dataKey={f} stroke={FUELS[f].color} strokeWidth={2} dot={{ r: 3 }} connectNulls />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
          {priceFuels.length > 1 && <div className="chart-legend">{priceFuels.map(f => <span key={f}><i className="dot" style={{ background: FUELS[f].color }} />{FUELS[f].label}</span>)}</div>}
        </Card>
      )}

      {segments.length > 0 && (
        <Section title="Від повного до повного">
          <Card flush>
            {segments.map(l => (
              <Row key={l.id} compact icon={l.fuel ? FUELS[l.fuel].icon : '⛽'} title={`${qty(l.segment!.per100, 1)} л/100 км`}
                sub={`${day(l.date)} · ${qty(l.segment!.km, 0)} км${l.segment!.estimated ? ' · частину літрів оцінено за ціною' : ''}`}
                end={<span className="muted small">{l.fuel ? FUELS[l.fuel].label : ''}</span>} />
            ))}
          </Card>
        </Section>
      )}
    </>
  );
}
