import { useState } from 'react';
import { toast } from '../toast';
import { parseNum } from '../format';
import { confirmAsync, haptic } from '../tg';
import { Button, Card, Chips, Field, Row, Segmented, Sheet } from '../ui';
import { errText, housingApi } from './api';
import type { Billing, MeterSummary, Provider } from './types';
import { SERVICE_LABELS } from './types';

const ICONS: Record<string, string> = { electricity: '⚡', gas: '🔥', gas_delivery: '🚚', water: '💧', heating: '♨️', maintenance: '🏢', waste: '🗑', internet: '🌐', rent: '🏠', mortgage: '🏦', other: '📄' };
const UNITS: Record<string, string> = { electricity: 'кВт·год', gas: 'м³', water: 'м³', heating: 'Гкал' };

type MeterDraft = { id?: number; name: string; unit: string; zone: string; tariff: string; remove?: boolean };

export default function ProviderForm({ familyId, provider, meters, onClose, onSaved }: {
  familyId: number; provider?: Provider; meters: MeterSummary[]; onClose: () => void; onSaved: () => void;
}) {
  const [service, setService] = useState(provider?.service || 'electricity');
  const [name, setName] = useState(provider?.name || SERVICE_LABELS.electricity);
  const [icon, setIcon] = useState(provider?.icon || ICONS.electricity);
  const [billing, setBilling] = useState<Billing>(provider?.billing || 'metered');
  const [fixed, setFixed] = useState(provider?.fixed_amount ? String(provider.fixed_amount) : '');
  const [dueDay, setDueDay] = useState(provider?.due_day ? String(provider.due_day) : '');
  const [account, setAccount] = useState(provider?.account_number || '');
  const [payUrl, setPayUrl] = useState(provider?.pay_url || '');
  const [start, setStart] = useState(provider?.start_date || '');
  const [opening, setOpening] = useState(provider?.opening_balance ? String(provider.opening_balance) : '');
  const [note, setNote] = useState(provider?.note || '');
  const [pattern, setPattern] = useState(provider?.match_pattern || '');
  const [ms, setMs] = useState<MeterDraft[]>(meters.map(m => ({ id: m.id, name: m.name, unit: m.unit, zone: m.zone || '', tariff: m.tariff ? String(m.tariff) : '' })));
  const [more, setMore] = useState(!!provider);
  const [busy, setBusy] = useState(false);
  const [createdId, setCreatedId] = useState<number | null>(null);  // retry after a partial failure updates, never duplicates
  const isRent = service === 'rent' || service === 'mortgage';

  const pickService = (s: string) => {
    if (!provider || name === SERVICE_LABELS[service]) setName(SERVICE_LABELS[s]);
    setIcon(ICONS[s] || '📄');
    setService(s);
    if (s === 'rent' || s === 'mortgage' || s === 'maintenance' || s === 'waste' || s === 'internet' || s === 'gas_delivery') setBilling('fixed');
    else if (s === 'heating' || s === 'other') setBilling('manual');
    else setBilling('metered');
    if (!provider && UNITS[s] && ms.length === 0) setMs([{ name: SERVICE_LABELS[s], unit: UNITS[s], zone: '', tariff: '' }]);
  };

  const save = async () => {
    if (!name.trim()) return;
    setBusy(true);
    const body = {
      name: name.trim(), service, icon, billing, fixed_amount: parseNum(fixed) || null, due_day: Number(dueDay) || null,
      account_number: account.trim(), pay_url: payUrl.trim(), start_date: start || null, opening_balance: parseNum(opening) || 0, note: note.trim(), match_pattern: pattern.trim(),
    };
    try {
      const id = provider?.id ?? createdId;
      const saved = id ? await housingApi.updateProvider(familyId, id, body) : await housingApi.createProvider(familyId, body);
      if (!id) setCreatedId(saved.id);
      if (billing === 'metered') {
        const done: MeterDraft[] = [];
        for (const m of ms) {
          const mb = { name: m.name.trim() || name, unit: m.unit || UNITS[service] || 'од.', zone: m.zone || null, tariff: parseNum(m.tariff) || 0,
            utility_type: service === 'electricity' || service === 'gas' || service === 'water' || service === 'heating' ? service : 'other', provider_id: saved.id };
          if (m.id && m.remove) await housingApi.deleteMeter(familyId, m.id);
          else if (m.id) await housingApi.updateMeter(familyId, m.id, mb);
          else if (!m.remove) { const r = await housingApi.createMeter(familyId, mb); done.push({ ...m, id: r.id }); continue; }
          if (!m.remove) done.push(m);
        }
        setMs(done);
      }
      haptic('success');
      toast(provider ? 'Збережено' : 'Послугу додано');
      onSaved();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  const archive = async () => {
    if (!provider || !(await confirmAsync(`Прибрати «${provider.name}»? Історія збережеться.`))) return;
    try { const r = await housingApi.deleteProvider(familyId, provider.id); toast(r.archived ? 'Перенесено в архів' : 'Видалено'); onSaved(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <Sheet title={provider ? 'Налаштування послуги' : 'Нова послуга'} icon={icon} onClose={onClose} confirmClose
      footer={<>
        <Button onClick={save} disabled={!name.trim()} busy={busy}>Зберегти</Button>
        {provider && <Button variant="danger" onClick={archive}>Прибрати послугу</Button>}
      </>}>
      <Field label="Тип">
        <Chips scroll small value={service} onChange={pickService} options={Object.keys(SERVICE_LABELS).map(k => ({ value: k, label: `${ICONS[k]} ${SERVICE_LABELS[k]}` }))} />
      </Field>
      <div className="hstack">
        <input className="input" style={{ width: 64, textAlign: 'center', fontSize: 22 }} value={icon} maxLength={4} onChange={e => setIcon(e.target.value)} aria-label="Іконка" />
        <input className="input grow" placeholder="Назва (ONDO, Нафтогаз…)" value={name} onChange={e => setName(e.target.value)} />
      </div>
      {!isRent && (
        <Field label="Як нараховують">
          <Segmented value={billing} onChange={setBilling} options={[{ value: 'metered', label: 'Лічильник' }, { value: 'fixed', label: 'Фіксовано' }, { value: 'manual', label: 'За платіжкою' }]} />
        </Field>
      )}
      <div className="grid2">
        {(billing === 'fixed' || isRent) && <Field label={isRent ? 'Сума на місяць' : 'Щомісяця'}><input className="input tnum" inputMode="decimal" placeholder="0 ₴" value={fixed} onChange={e => setFixed(e.target.value)} /></Field>}
        <Field label="Сплатити до (число)"><input className="input tnum" inputMode="numeric" placeholder="20" value={dueDay} onChange={e => setDueDay(String(Math.min(Number(e.target.value.replace(/\D/g, '').slice(0, 2)) || 0, 31) || ''))} /></Field>
      </div>

      {billing === 'metered' && (
        <Card>
          <div className="stack-s">
            <div className="muted small">Лічильники (тариф — ціна за одиницю)</div>
            {ms.map((m, i) => m.remove ? null : (
              <div key={i} className="hstack">
                <input className="input grow" placeholder="Назва" value={m.name} onChange={e => setMs(x => x.map((y, j) => j === i ? { ...y, name: e.target.value } : y))} />
                <input className="input tnum" style={{ width: 84 }} inputMode="decimal" placeholder="тариф" value={m.tariff} onChange={e => setMs(x => x.map((y, j) => j === i ? { ...y, tariff: e.target.value } : y))} />
                <button className="btn btn--icon" aria-label="Прибрати" onClick={() => setMs(x => x.map((y, j) => j === i ? { ...y, remove: true } : y))}>✕</button>
              </div>
            ))}
            <div className="hstack">
              <button className="link" onClick={() => setMs(x => [...x, { name: `${SERVICE_LABELS[service]}${x.length ? ` ${x.length + 1}` : ''}`, unit: UNITS[service] || 'од.', zone: '', tariff: '' }])}>+ Лічильник</button>
              {service === 'electricity' && ms.filter(m => !m.remove).length < 2 && (
                <button className="link" onClick={() => setMs([{ ...(ms[0] || { name: '', unit: 'кВт·год', tariff: '4.32' }), name: 'Світло · день', zone: 'day' },
                  { name: 'Світло · ніч', unit: 'кВт·год', zone: 'night', tariff: '2.16' }])}>Двозонний (день/ніч)</button>
              )}
            </div>
          </div>
        </Card>
      )}

      {more ? (
        <>
          <Field label="Як виглядає оплата в банку" hint="Слово з опису операції в Monobank (напр. «Електроенергія»). Нові оплати зарахуються самі.">
            <input className="input" placeholder="Електроенергія | ONDO" value={pattern} onChange={e => setPattern(e.target.value)} />
          </Field>
          <Field label="Особовий рахунок"><input className="input" value={account} onChange={e => setAccount(e.target.value)} /></Field>
          <Field label="Посилання на оплату" hint="Сайт або застосунок постачальника"><input className="input" inputMode="url" placeholder="https://" value={payUrl} onChange={e => setPayUrl(e.target.value)} /></Field>
          <div className="grid2">
            <Field label="Облік з"><input className="input" type="date" value={start} onChange={e => setStart(e.target.value)} /></Field>
            <Field label="Борг на старті" hint="мінус — переплата"><input className="input tnum" inputMode="decimal" value={opening} onChange={e => setOpening(e.target.value)} /></Field>
          </div>
          <Field label="Примітка"><input className="input" value={note} onChange={e => setNote(e.target.value)} /></Field>
        </>
      ) : <Row compact title="Як виглядає в банку, рахунок, посилання, борг на старті" chevron onClick={() => setMore(true)} />}
    </Sheet>
  );
}
