import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { parseNum } from '../format';
import { haptic } from '../tg';
import { Button, Card, Field, Row } from '../ui';
import { errText, housingApi } from './api';
import type { HousingMode, Overview, Template } from './types';

const MODES: { value: HousingMode; icon: string; title: string; sub: string }[] = [
  { value: 'rent', icon: '🏠', title: 'Орендую', sub: 'Оренда + комуналка, нагадування про оплату' },
  { value: 'mortgage', icon: '🏦', title: 'Іпотека / кредит', sub: 'Щомісячний платіж + комуналка' },
  { value: 'own', icon: '🔑', title: 'Власне житло', sub: 'Тільки комуналка і лічильники' },
  { value: 'off', icon: '🙈', title: 'Не потрібно', sub: 'Сховати вкладку «Житло»' },
];
const DEFAULT_PICK = ['electricity_2zone', 'gas', 'water', 'maintenance', 'waste'];

export default function Onboarding({ familyId, onDone }: { familyId: number; onDone: (o: Overview) => void }) {
  const [step, setStep] = useState<1 | 2>(1);
  const [mode, setMode] = useState<HousingMode>('rent');
  const [templates, setTemplates] = useState<Template[]>([]);
  const [picked, setPicked] = useState<string[]>(DEFAULT_PICK);
  const [rent, setRent] = useState('');
  const [rentDay, setRentDay] = useState('1');
  const [busy, setBusy] = useState(false);

  useEffect(() => { housingApi.templates().then(setTemplates).catch(() => { /**/ }); }, []);

  const submit = async (m: HousingMode = mode) => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = { mode: m, templates: m === 'off' ? [] : picked.filter(k => k !== 'rent' && k !== 'mortgage') };
      if ((m === 'rent' || m === 'mortgage') && parseNum(rent) > 0) { body.rent_amount = parseNum(rent); body.rent_day = Number(rentDay) || 1; }
      const o = await housingApi.setup(familyId, body);
      haptic('success');
      toast(m === 'off' ? 'Вкладку можна увімкнути в «Ще»' : 'Готово! Внесіть перші показники');
      onDone(o);
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  if (step === 1) return (
    <div className="stack">
      <h1 className="page-title">Житло</h1>
      <div className="muted">Комуналка, оренда і лічильники в одному місці: скільки треба сплатити, скільки набігло, прогноз і перевірка платіжок на помилки.</div>
      <Card flush>
        {MODES.map(m => <Row key={m.value} icon={m.icon} title={m.title} sub={m.sub} chevron
          onClick={() => { setMode(m.value); if (m.value === 'off') submit('off'); else setStep(2); }} />)}
      </Card>
    </div>
  );

  const choices = templates.filter(t => t.key !== 'rent' && t.key !== 'mortgage');
  return (
    <div className="stack">
      <h1 className="page-title">Що оплачуєте?</h1>
      <div className="muted small">Позначте послуги — назви, тарифи й лічильники можна змінити будь-коли.</div>
      <Card flush>
        {choices.map(t => {
          const on = picked.includes(t.key);
          return <Row key={t.key} icon={t.icon} title={t.title} sub={t.meters ? `${t.meters} ${t.meters === 1 ? 'лічильник' : 'лічильники'}` : 'без лічильника'}
            end={<span style={{ fontSize: 20 }}>{on ? '✅' : '⬜️'}</span>}
            onClick={() => setPicked(p => on ? p.filter(k => k !== t.key) : [...p, t.key])} />;
        })}
      </Card>
      {(mode === 'rent' || mode === 'mortgage') && (
        <div className="grid2">
          <Field label={mode === 'rent' ? 'Оренда на місяць' : 'Платіж на місяць'}><input className="input tnum" inputMode="decimal" placeholder="0 ₴" value={rent} onChange={e => setRent(e.target.value)} /></Field>
          <Field label="Платимо до (число)"><input className="input tnum" inputMode="numeric" value={rentDay} onChange={e => setRentDay(e.target.value.replace(/\D/g, '').slice(0, 2))} /></Field>
        </div>
      )}
      <div className="btn-row">
        <Button variant="secondary" onClick={() => setStep(1)}>Назад</Button>
        <Button onClick={() => submit()} busy={busy}>Готово</Button>
      </div>
    </div>
  );
}
