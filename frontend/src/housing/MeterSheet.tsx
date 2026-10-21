import { useEffect, useState } from 'react';
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import { toast } from '../toast';
import { approx, day, dmy, qty } from '../format';
import { confirmAsync } from '../tg';
import { Badge, Card, Row, Sheet, Spinner, Tile } from '../ui';
import { errText, housingApi } from './api';
import type { MeterSummary, Reading } from './types';
import { cssVar } from './chart';

const SOURCE: Record<string, string> = { manual: 'вручну', bill: 'з платіжки', import: 'імпорт' };

export default function MeterSheet({ familyId, meter: m, onClose, onChanged }: {
  familyId: number; meter: MeterSummary; onClose: () => void; onChanged: () => void;
}) {
  const [items, setItems] = useState<Reading[] | null>(null);
  const load = async () => { try { setItems(await housingApi.readings(familyId, m.id)); } catch (e) { toast(errText(e), 'err'); } };
  useEffect(() => { load(); }, [m.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const del = async (r: Reading) => {
    if (!(await confirmAsync(`Видалити показник ${qty(r.value)} від ${dmy(r.date)}?`))) return;
    try { await housingApi.deleteReading(familyId, r.id); toast('Видалено'); load(); onChanged(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const chart = (items || []).filter(r => r.rate !== null).slice(0, 12).reverse().map(r => ({ d: day(r.date), rate: r.rate }));

  return (
    <Sheet title={m.name} icon="🔢" onClose={onClose}>
      <div className="grid2">
        <Tile label="Останній" value={m.last_value !== null ? qty(m.last_value) : '—'} />
        <Tile label="Середньо на день" value={m.daily_rate !== null ? `${m.daily_rate} ${m.unit}` : '—'} />
        <Tile label="Цей місяць (прогноз)" value={m.month_forecast !== null ? `${Math.round(m.month_forecast)} ${m.unit}` : '—'} />
        <Tile label="Вартість місяця" value={m.month_forecast_cost !== null ? approx(m.month_forecast_cost) : '—'} />
      </div>
      {chart.length > 1 && (
        <Card>
          <div className="muted small" style={{ marginBottom: 6 }}>Споживання на день між показниками</div>
          <div style={{ height: 140 }}>
            <ResponsiveContainer>
              <BarChart data={chart} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                <XAxis dataKey="d" tick={{ fontSize: 10, fill: cssVar('--hint') }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <Tooltip cursor={{ fill: 'transparent' }} formatter={(v: any) => [`${v} ${m.unit}/день`, '']} />
                <Bar isAnimationActive={false} dataKey="rate" fill={cssVar('--accent')} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
      {items === null ? <Spinner /> : (
        <Card flush>
          {items.map(r => (
            <Row key={r.id} compact title={<span className="tnum">{qty(r.value)}</span>}
              sub={[dmy(r.date), r.rate !== null ? `${r.rate} ${m.unit}/день` : null, r.note].filter(Boolean).join(' · ')}
              end={<span className="hstack"><Badge>{SOURCE[r.source] || r.source}</Badge><button className="link danger small" onClick={() => del(r)}>✕</button></span>} />
          ))}
        </Card>
      )}
    </Sheet>
  );
}
