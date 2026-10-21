import { useState } from 'react';
import { toast } from '../toast';
import { approx, day, parseNum, qty, todayIso } from '../format';
import { haptic } from '../tg';
import { Button, Field, Sheet } from '../ui';
import { errText, housingApi } from './api';
import type { MeterSummary, Overview } from './types';

// One screen for all meters: last value as a hint, live delta & cost, validation.
export default function ReadingsSheet({ familyId, meters, onClose, onSaved }: {
  familyId: number; meters: MeterSummary[]; onClose: () => void; onSaved: (o: Overview) => void;
}) {
  const [values, setValues] = useState<Record<number, string>>({});
  const [date, setDate] = useState(todayIso());
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [replaced, setReplaced] = useState(false);

  const rows = meters.map(m => {
    const raw = values[m.id] ?? '';
    const v = parseNum(raw);
    const has = raw.trim() !== '' && Number.isFinite(v);
    const delta = has && m.last_value !== null ? v - m.last_value : null;
    const error = has && delta !== null && delta < 0 && !replaced ? `Менше за останній (${qty(m.last_value)})` : null;
    const big = has && delta !== null && m.daily_rate && m.days_since_reading !== null
      && delta > Math.max(m.daily_rate * Math.max(m.days_since_reading, 1) * 4, 50);
    return { m, raw, v, has, delta, error, big };
  });
  const filled = rows.filter(r => r.has);
  const valid = filled.length > 0 && rows.every(r => !r.error);

  const save = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      const r = await housingApi.addReadings(familyId, {
        date, note: note.trim(), allow_decrease: replaced, items: filled.map(x => ({ meter_id: x.m.id, value: x.v })),
      });
      haptic('success');
      toast(`Збережено ${filled.length} ${filled.length === 1 ? 'показник' : 'показники'}`);
      onSaved(r.overview);
      onClose();
    } catch (e) { toast(errText(e, 'Не вдалося зберегти'), 'err'); }
    setBusy(false);
  };

  return (
    <Sheet title="Показники лічильників" icon="📸" onClose={onClose}
      footer={<Button onClick={save} disabled={!valid} busy={busy}>Зберегти{filled.length ? ` · ${filled.length}` : ''}</Button>}>
      {rows.map(({ m, raw, delta, error, big }, i) => (
        <Field key={m.id} label={<span className="spread"><span>{m.name}</span>
          <span className="tnum">{m.last_value !== null ? `${qty(m.last_value)} · ${day(m.last_date)}` : 'перший показник'}</span></span>}
          error={error}
          hint={delta !== null && !error ? <>+{qty(delta)} {m.unit}{m.tariff ? ` · ${approx(delta * m.tariff)}` : ''}
            {big ? <span className="warn"> · незвично багато, перевірте</span> : null}</> : m.daily_rate ? `≈ ${m.daily_rate} ${m.unit}/день` : undefined}>
          <input className={`input tnum ${error ? 'input--error' : ''}`} inputMode="decimal" autoFocus={i === 0}
            placeholder={m.last_value !== null ? `більше ${qty(m.last_value)}` : m.unit} value={raw}
            onChange={e => setValues(s => ({ ...s, [m.id]: e.target.value }))} />
        </Field>
      ))}
      <div className="grid2">
        <Field label="Дата"><input className="input" type="date" value={date} max={todayIso()} onChange={e => setDate(e.target.value)} /></Field>
        <Field label="Примітка"><input className="input" placeholder="необов'язково" value={note} onChange={e => setNote(e.target.value)} /></Field>
      </div>
      {rows.some(r => r.delta !== null && r.delta < 0) && (
        <label className="hstack small"><input type="checkbox" checked={replaced} onChange={e => setReplaced(e.target.checked)} /> Лічильник замінили / показник виправлено</label>
      )}
    </Sheet>
  );
}
