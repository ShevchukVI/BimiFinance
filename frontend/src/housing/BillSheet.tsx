import { useEffect, useMemo, useState } from 'react';
import { toast } from '../toast';
import { addMonthsIso, money, monthYear, parseNum, qty, todayIso } from '../format';
import { confirmAsync, haptic } from '../tg';
import { Banner, Button, Card, Chips, Field, Sheet, Spinner } from '../ui';
import { errText, housingApi } from './api';
import type { Bill, BillFlag, BillLine, Overview } from './types';
import { isFixedService } from './types';

type LineForm = { meter_id: number | null; label: string; prev: string; curr: string; tariff: string; amount: string; vol: string };

const s = (v: number | null | undefined) => (v === null || v === undefined ? '' : String(v));
const n = (v: string) => { const x = parseNum(v); return Number.isFinite(x) ? x : null; };
const r2 = (v: number) => Math.round(v * 100) / 100;

function lineCalc(l: LineForm) {
  const prev = n(l.prev), curr = n(l.curr), tariff = n(l.tariff);
  // bills without meter values (e.g. Нафтогаз) still carry the consumed volume
  const volume = prev !== null && curr !== null ? curr - prev : n(l.vol);
  const amount = l.meter_id !== null && volume !== null && tariff !== null ? r2(volume * tariff) : n(l.amount);
  return { prev, curr, tariff, volume, amount };
}

export default function BillSheet({ familyId, overview, providerId, bill, period, onClose, onSaved }: {
  familyId: number; overview: Overview; providerId?: number; bill?: Bill; period?: string; onClose: () => void; onSaved: () => void;
}) {
  const choices = overview.providers.filter(p => !isFixedService(p.service));
  const [pid, setPid] = useState<number | null>(providerId ?? (choices.length === 1 ? choices[0].id : null));
  const [per, setPer] = useState((bill?.period || period || addMonthsIso(todayIso(), -1)).slice(0, 7));
  const [editing, setEditing] = useState<Bill | null>(bill || null);
  const [loading, setLoading] = useState(false);
  const [opening, setOpening] = useState('');
  const [paid, setPaid] = useState('');
  const [accrued, setAccrued] = useState('');
  const [adjustment, setAdjustment] = useState('');
  const [toPay, setToPay] = useState('');
  const [manualToPay, setManualToPay] = useState(false);
  const [issued, setIssued] = useState(todayIso());
  const [note, setNote] = useState('');
  const [lines, setLines] = useState<LineForm[]>([]);
  const [busy, setBusy] = useState(false);
  const [flags, setFlags] = useState<BillFlag[] | null>(bill ? bill.flags : null);
  const provider = overview.providers.find(p => p.id === pid);

  const fill = (src: { opening_balance: number; paid: number; accrued: number; adjustment: number; to_pay: number; issued_on?: string | null; note?: string; lines: BillLine[] }, isBill: boolean) => {
    setOpening(s(src.opening_balance)); setPaid(s(src.paid)); setAccrued(s(src.accrued)); setAdjustment(src.adjustment ? s(src.adjustment) : '');
    setIssued(src.issued_on || todayIso()); setNote(src.note || '');
    setLines(src.lines.map(l => ({ meter_id: l.meter_id, label: l.label, prev: s(l.prev_value), curr: s(l.curr_value), tariff: s(l.tariff), amount: s(l.amount), vol: s(l.volume) })));
    const expected = r2((src.opening_balance || 0) - (src.paid || 0) + (src.accrued || 0) + (src.adjustment || 0));
    setManualToPay(isBill && Math.abs(expected - src.to_pay) > 0.005);
    setToPay(s(src.to_pay));
  };

  useEffect(() => { if (bill) fill(bill, true); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!pid || bill) return;  // opened on a concrete bill → no auto-switching
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const d = await housingApi.draft(familyId, pid, per);
        if (cancelled) return;
        if (d.existing_id) {
          const all = await housingApi.bills(familyId, pid);
          const ex = all.find(b => b.id === d.existing_id);
          if (ex && !cancelled) { setEditing(ex); setFlags(ex.flags); fill(ex, true); }
        } else { setEditing(null); setFlags(null); fill(d, false); }
      } catch (e) { toast(errText(e), 'err'); }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [pid, per]); // eslint-disable-line react-hooks/exhaustive-deps

  const calc = useMemo(() => lines.map(lineCalc), [lines]);
  const linesSum = r2(calc.reduce((acc, c) => acc + (c.amount || 0), 0));
  const accruedNum = lines.length ? linesSum : (n(accrued) ?? 0);
  const expectedToPay = r2((n(opening) ?? 0) - (n(paid) ?? 0) + accruedNum + (n(adjustment) ?? 0));
  const toPayNum = manualToPay ? (n(toPay) ?? expectedToPay) : expectedToPay;
  const valid = !!pid && /^\d{4}-\d{2}$/.test(per) && calc.every(c => c.volume === null || c.volume >= 0);

  const setLine = (i: number, patch: Partial<LineForm>) => setLines(ls => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  const save = async () => {
    if (!valid || !pid) return;
    setBusy(true);
    const body = {
      provider_id: pid, period: per, issued_on: issued || null,
      opening_balance: n(opening) ?? 0, paid: n(paid) ?? 0, accrued: accruedNum, adjustment: n(adjustment) ?? 0,
      to_pay: toPayNum, note: note.trim(),
      lines: lines.map((l, i) => ({ meter_id: l.meter_id, label: l.label, prev_value: calc[i].prev, curr_value: calc[i].curr,
        volume: calc[i].volume, tariff: calc[i].tariff, amount: calc[i].amount })),
    };
    try {
      const saved = editing ? await housingApi.updateBill(familyId, editing.id, body) : await housingApi.createBill(familyId, body);
      onSaved();
      const warn = saved.flags.filter(f => f.level === 'warn');
      if (warn.length) { haptic('error'); setEditing(saved); setFlags(saved.flags); toast('Збережено — є розбіжності', 'err'); }
      else { haptic('success'); toast('Платіжку збережено'); onClose(); }
    } catch (e) { toast(errText(e, 'Не вдалося зберегти'), 'err'); }
    setBusy(false);
  };

  const remove = async () => {
    if (!editing || !(await confirmAsync('Видалити платіжку?'))) return;
    try { await housingApi.deleteBill(familyId, editing.id); toast('Видалено'); onSaved(); onClose(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <Sheet title={editing ? `Платіжка · ${monthYear(editing.period)}` : 'Нова платіжка'} icon={provider?.icon || '🧾'} onClose={onClose} confirmClose
      footer={<>
        <Button onClick={save} disabled={!valid || loading} busy={busy}>Зберегти · до сплати {money(toPayNum)}</Button>
        {editing && <Button variant="danger" onClick={remove}>Видалити платіжку</Button>}
      </>}>
      {flags && flags.length > 0 && (
        <div className="stack-s">
          {flags.map((f, i) => <Banner key={i} tone={f.level === 'warn' ? 'warn' : undefined} icon={f.level === 'warn' ? '⚠️' : 'ℹ️'}>{f.text}</Banner>)}
        </div>
      )}
      {!bill && (
        <>
          <Field label="Послуга">
            <Chips value={pid} onChange={id => { setPid(id); setFlags(null); }} options={choices.map(p => ({ value: p.id, label: `${p.icon} ${p.name}` }))} />
          </Field>
          <Field label="За місяць"><input className="input" type="month" value={per} onChange={e => setPer(e.target.value)} /></Field>
          {editing && <Banner icon="✏️">Платіжка за {monthYear(editing.period)} уже є — ви її редагуєте. Оберіть інший місяць, щоб додати нову.</Banner>}
        </>
      )}
      {!pid ? <div className="muted small center">Оберіть послугу — решта підставиться автоматично</div> : loading ? <Spinner /> : (
        <>
          {lines.length > 0 && (
            <Card>
              <div className="stack">
                {lines.map((l, i) => l.meter_id !== null ? (
                  <div key={i} className="stack-s">
                    <div className="spread small"><b>{l.label}</b>
                      <span className="muted tnum">{calc[i].volume !== null ? `${qty(calc[i].volume)} × ${l.tariff || '?'} = ${money(calc[i].amount ?? 0)}` : ''}</span></div>
                    <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr 0.8fr' }}>
                      <input className="input tnum" inputMode="decimal" placeholder="Попередній" value={l.prev} onChange={e => setLine(i, { prev: e.target.value })} aria-label="Попередній показник" />
                      <input className="input tnum" inputMode="decimal" placeholder="Поточний" value={l.curr} onChange={e => setLine(i, { curr: e.target.value })} aria-label="Поточний показник" />
                      <input className="input tnum" inputMode="decimal" placeholder="Тариф" value={l.tariff} onChange={e => setLine(i, { tariff: e.target.value })} aria-label="Тариф" />
                    </div>
                    {calc[i].volume !== null && calc[i].volume < 0 && <div className="field__error">Поточний показник менший за попередній — перевірте цифри</div>}
                  </div>
                ) : (
                  <div key={i} className="hstack">
                    <input className="input grow" placeholder="Назва (перерахунок, пеня…)" value={l.label} onChange={e => setLine(i, { label: e.target.value })} />
                    <input className="input tnum" style={{ width: 110 }} inputMode="decimal" placeholder="Сума" value={l.amount} onChange={e => setLine(i, { amount: e.target.value })} />
                    <button className="btn btn--icon" aria-label="Прибрати" onClick={() => setLines(ls => ls.filter((_, j) => j !== i))}>✕</button>
                  </div>
                ))}
                <div className="spread small"><span className="muted">Нараховано разом</span><b className="tnum">{money(linesSum)}</b></div>
              </div>
            </Card>
          )}
          <button className="link" style={{ alignSelf: 'flex-start' }} onClick={() => {
            const base = lines.length ? [] : (n(accrued) ? [{ meter_id: null, label: 'Нараховано', prev: '', curr: '', tariff: '', amount: accrued, vol: '' }] : []);
            setLines(ls => [...ls, ...base, { meter_id: null, label: '', prev: '', curr: '', tariff: '', amount: '', vol: '' }]);
          }}>+ Свій рядок (перерахунок, пеня, послуга)</button>

          <div className="grid2">
            <Field label="Борг на початок" hint="мінус — переплата"><input className="input tnum" inputMode="decimal" value={opening} onChange={e => setOpening(e.target.value)} /></Field>
            <Field label="Сплачено за місяць"><input className="input tnum" inputMode="decimal" value={paid} onChange={e => setPaid(e.target.value)} /></Field>
            {!lines.length && <Field label="Нараховано"><input className="input tnum" inputMode="decimal" value={accrued} onChange={e => setAccrued(e.target.value)} /></Field>}
            <Field label="Перерахунок"><input className="input tnum" inputMode="decimal" placeholder="0" value={adjustment} onChange={e => setAdjustment(e.target.value)} /></Field>
          </div>
          <Card>
            <div className="spread">
              <span className="muted">До сплати</span>
              {manualToPay
                ? <input className="input tnum" style={{ width: 140, height: 40 }} inputMode="decimal" value={toPay} onChange={e => setToPay(e.target.value)} />
                : <b className="tnum" style={{ fontSize: 20 }}>{money(expectedToPay)}</b>}
            </div>
            <label className="hstack small muted" style={{ marginTop: 8 }}>
              <input type="checkbox" checked={manualToPay} onChange={e => { setManualToPay(e.target.checked); if (e.target.checked) setToPay(String(expectedToPay)); }} />
              У платіжці інша сума (перевіримо розбіжність)
            </label>
            {manualToPay && Math.abs((n(toPay) ?? 0) - expectedToPay) > 0.5 && (
              <div className="warn small" style={{ marginTop: 6 }}>Розрахунок дає {money(expectedToPay)} — різниця {money((n(toPay) ?? 0) - expectedToPay)}</div>
            )}
          </Card>
          <div className="grid2">
            <Field label="Дата платіжки"><input className="input" type="date" value={issued} onChange={e => setIssued(e.target.value)} /></Field>
            <Field label="Примітка"><input className="input" value={note} placeholder="необов'язково" onChange={e => setNote(e.target.value)} /></Field>
          </div>
        </>
      )}
    </Sheet>
  );
}
