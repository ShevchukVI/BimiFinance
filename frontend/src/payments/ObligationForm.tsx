import { useState } from 'react';
import { toast } from '../toast';
import { parseNum } from '../format';
import { confirmAsync, haptic } from '../tg';
import type { Category } from '../types';
import { Button, Chips, Field, Segmented, Sheet, Switch } from '../ui';
import { errText } from '../housing/api';
import { KIND_LABEL, ObKind, Obligation, payApi } from './api';

export interface ObDraft { kind?: ObKind; name?: string; amount?: number; due_day?: number; first_due?: string; match_pattern?: string; txId?: number; }

const ICONS: Record<ObKind, string> = { installment: '🧾', loan: '🏦', subscription: '🔁' };

export default function ObligationForm({ familyId, item, draft, categories, onClose, onSaved }: {
  familyId: number; item?: Obligation; draft?: ObDraft; categories: Category[]; onClose: () => void; onSaved: (o: Obligation | null) => void;
}) {
  const src = item || null;
  const [kind, setKind] = useState<ObKind>(src?.kind || draft?.kind || 'installment');
  const [name, setName] = useState(src?.name || draft?.name || '');
  const [icon, setIcon] = useState(src?.icon || ICONS[draft?.kind || 'installment']);
  const [amount, setAmount] = useState(src ? String(src.amount) : draft?.amount ? String(draft.amount) : '');
  const [dueDay, setDueDay] = useState(String(src?.due_day || draft?.due_day || ''));
  const [firstDue, setFirstDue] = useState(src?.first_due || draft?.first_due || '');
  const [total, setTotal] = useState(src?.payments_total ? String(src.payments_total) : '');
  const [paidBefore, setPaidBefore] = useState(src?.paid_before ? String(src.paid_before) : '');
  const [endDate, setEndDate] = useState(src?.end_date || '');
  const [fullPrice, setFullPrice] = useState(src?.total_amount ? String(src.total_amount) : '');
  const [period, setPeriod] = useState<'month' | 'year'>(src?.period || 'month');
  const [pattern, setPattern] = useState(src?.match_pattern ?? draft?.match_pattern ?? '');
  const [categoryId, setCategoryId] = useState<number | null>(src?.category_id ?? null);
  const [remind, setRemind] = useState(src ? src.remind : true);
  const [note, setNote] = useState(src?.note || '');
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<Obligation | null>(null);
  const credit = kind !== 'subscription';
  const num = parseNum(amount);
  const valid = name.trim() && Number.isFinite(num) && num > 0;
  const expenseCats = categories.filter(c => c.type === 'expense' && !c.name.includes('Очікує'));

  const save = async () => {
    if (!valid) return;
    setBusy(true);
    const body: Record<string, unknown> = {
      kind, name: name.trim(), icon, amount: num, due_day: Number(dueDay) || null, match_pattern: pattern.trim(),
      category_id: categoryId, remind: credit ? remind : false, note: note.trim(), period: credit ? 'month' : period,
      first_due: firstDue || null, payments_total: credit ? (Number(total) || null) : null,
      paid_before: credit ? (Number(paidBefore) || 0) : 0, end_date: endDate || null,
      total_amount: credit ? (parseNum(fullPrice) || null) : null,
    };
    try {
      let saved: Obligation;
      const existing = src || created;
      if (existing) saved = await payApi.update(familyId, existing.id, body);
      else { saved = await payApi.create(familyId, { ...body, link_suggested: true }); setCreated(saved); }
      if (!src && draft?.txId) await payApi.setLink(familyId, draft.txId, 'obligation', saved.id);
      haptic('success');
      toast(src ? 'Збережено' : `${KIND_LABEL[kind]} додано`);
      onSaved(saved);
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  const archive = async () => {
    if (!src || !(await confirmAsync(`Прибрати «${src.name}»? Пов'язані платежі залишаться в історії.`))) return;
    try { const r = await payApi.remove(familyId, src.id); toast(r.archived ? 'Перенесено в архів' : 'Видалено'); onSaved(null); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <Sheet title={src ? src.name : 'Новий платіж'} icon={icon} onClose={onClose} confirmClose
      footer={<>
        <Button onClick={save} disabled={!valid} busy={busy}>Зберегти</Button>
        {src && <Button variant="danger" onClick={archive}>{src.state.status === 'finished' ? 'В архів' : 'Прибрати'}</Button>}
      </>}>
      <Segmented value={kind} onChange={k => { setKind(k); if (Object.values(ICONS).includes(icon)) setIcon(ICONS[k]); }}
        options={[{ value: 'installment', label: 'Розстрочка' }, { value: 'loan', label: 'Кредит' }, { value: 'subscription', label: 'Підписка' }]} />
      <div className="hstack">
        <input className="input" style={{ width: 64, textAlign: 'center', fontSize: 22 }} value={icon} maxLength={4} onChange={e => setIcon(e.target.value)} aria-label="Іконка" />
        <input className="input grow" placeholder={credit ? 'Напр. Телевізор' : 'Напр. YouTube Premium'} value={name} autoFocus={!src} onChange={e => setName(e.target.value)} />
      </div>
      <div className="grid2">
        <Field label={credit ? 'Щомісячний платіж' : 'Ціна'}><input className="input tnum" inputMode="decimal" placeholder="0 ₴" value={amount} onChange={e => setAmount(e.target.value)} /></Field>
        <Field label="Число списання"><input className="input tnum" inputMode="numeric" placeholder="13" value={dueDay} onChange={e => setDueDay(String(Math.min(Number(e.target.value.replace(/\D/g, '').slice(0, 2)) || 0, 31) || ''))} /></Field>
      </div>
      {credit ? (
        <>
          <div className="grid2">
            <Field label="Перший платіж"><input className="input" type="date" value={firstDue} onChange={e => setFirstDue(e.target.value)} /></Field>
            <Field label="Усього платежів"><input className="input tnum" inputMode="numeric" placeholder="10" value={total} onChange={e => setTotal(e.target.value.replace(/\D/g, '').slice(0, 3))} /></Field>
          </div>
          <div className="grid2">
            <Field label="Вже сплачено поза Bimi" hint="платежів, яких немає в історії"><input className="input tnum" inputMode="numeric" placeholder="0" value={paidBefore} onChange={e => setPaidBefore(e.target.value.replace(/\D/g, '').slice(0, 3))} /></Field>
            {kind === 'loan'
              ? <Field label="Останній платіж" hint="якщо кількість невідома"><input className="input" type="date" value={endDate} onChange={e => setEndDate(e.target.value)} /></Field>
              : <Field label="Повна ціна"><input className="input tnum" inputMode="decimal" placeholder="необов'язково" value={fullPrice} onChange={e => setFullPrice(e.target.value)} /></Field>}
          </div>
        </>
      ) : (
        <Field label="Як часто"><Chips small value={period} onChange={setPeriod} options={[{ value: 'month', label: 'Щомісяця' }, { value: 'year', label: 'Щороку' }]} /></Field>
      )}
      <Field label="Як виглядає в банку" hint="Слово з опису операції, напр. «Citrus» чи «YouTube». Нові списання з Monobank прив'яжуться самі (сума ±5%).">
        <input className="input" placeholder="Citrus | monomarket" value={pattern} onChange={e => setPattern(e.target.value)} />
      </Field>
      <Field label="Категорія для таких операцій">
        <div style={{ maxHeight: 120, overflowY: 'auto' }}>
          <Chips small value={categoryId} onChange={id => setCategoryId(id === categoryId ? null : id)} options={expenseCats.map(c => ({ value: c.id, label: c.name }))} />
        </div>
      </Field>
      {credit && (
        <div className="card">
          <div className="spread"><div><div className="bold">Нагадувати в боті</div><div className="muted small">За день і в день платежу</div></div>
            <Switch on={remind} onChange={setRemind} label="Нагадувати" /></div>
        </div>
      )}
      <Field label="Примітка"><input className="input" placeholder="необов'язково" value={note} onChange={e => setNote(e.target.value)} /></Field>
    </Sheet>
  );
}
