import { useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { Jar } from '../types';
import { money, parseNum } from '../format';
import { haptic } from '../tg';
import { Button, Chips, Field, Sheet } from '../ui';

export function CreateJarModal({ familyId, onClose, onCreated }: {
  familyId: number; onClose: () => void; onCreated: (j: Jar) => void;
}) {
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const [busy, setBusy] = useState(false);
  const valid = name.trim() && parseNum(goal) > 0;

  const create = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      const r = await api.post('/jars', { family_id: familyId, name: name.trim(), goal: parseNum(goal) });
      onCreated(r.data);
      haptic('success');
      toast('Ціль створено');
      onClose();
    } catch {
      toast('Помилка створення', 'err');
    }
    setBusy(false);
  };

  return (
    <Sheet title="Нова ціль" icon="🎯" onClose={onClose}
      footer={<Button onClick={create} disabled={!valid} busy={busy}>Створити</Button>}>
      <Field label="Назва"><input className="input" placeholder="Напр. Відпустка" value={name} autoFocus onChange={e => setName(e.target.value)} /></Field>
      <Field label="Скільки потрібно"><input className="input tnum" inputMode="decimal" placeholder="0 ₴" value={goal} onChange={e => setGoal(e.target.value)} /></Field>
    </Sheet>
  );
}

export function TopUpJarModal({ jar, onClose, onToppedUp }: {
  jar: Jar; onClose: () => void; onToppedUp: (j: Jar) => void;
}) {
  const [mode, setMode] = useState<'topup' | 'withdraw'>('topup');
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const num = parseNum(amount);
  const valid = Number.isFinite(num) && num > 0 && (mode === 'topup' || num <= jar.balance);
  const left = Math.max(jar.goal - jar.balance, 0);

  const submit = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      // Бекенд сам створює jar-транзакцію (готівка ↔ скарбничка) — окремої витрати не потрібно.
      const r = await api.post(`/jars/${jar.id}/${mode}`, { amount: num });
      onToppedUp(r.data);
      haptic('success');
      toast(mode === 'topup' ? 'Поповнено' : 'Знято');
      onClose();
    } catch {
      toast('Помилка операції', 'err');
    }
    setBusy(false);
  };

  return (
    <Sheet title={jar.name} icon="🎯" onClose={onClose}
      footer={<Button onClick={submit} disabled={!valid} busy={busy}>{mode === 'topup' ? 'Закинути' : 'Зняти'}</Button>}>
      <Chips value={mode} onChange={setMode} options={[{ value: 'topup', label: '⬆️ Поповнити' }, { value: 'withdraw', label: '⬇️ Зняти' }]} />
      <input className="input input--big tnum" inputMode="decimal" placeholder="0 ₴" value={amount} autoFocus onChange={e => setAmount(e.target.value)} />
      <div className="muted small">
        Зараз {money(jar.balance, jar.currency)} з {money(jar.goal, jar.currency)}
        {mode === 'topup' && left > 0 && <> · до цілі {money(left, jar.currency)} <button className="link" onClick={() => setAmount(String(left))}>закинути все</button></>}
      </div>
    </Sheet>
  );
}
