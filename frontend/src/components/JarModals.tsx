import { useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { Jar } from '../types';

const sheet: React.CSSProperties = {
  position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)',
  zIndex: 110, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
};
const card: React.CSSProperties = {
  backgroundColor: '#fff', borderTopLeftRadius: '24px', borderTopRightRadius: '24px',
  padding: '25px', paddingBottom: 'calc(25px + env(safe-area-inset-bottom))',
};
const input: React.CSSProperties = {
  width: '100%', padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9',
  fontSize: '16px', boxSizing: 'border-box', marginBottom: '15px',
};
const closeBtn: React.CSSProperties = { border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6', cursor: 'pointer' };

export function CreateJarModal({ familyId, onClose, onCreated }: {
  familyId: number; onClose: () => void; onCreated: (j: Jar) => void;
}) {
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const valid = name.trim() && parseFloat(goal.replace(',', '.')) > 0;

  const create = async () => {
    if (!valid) return;
    try {
      const r = await api.post('/jars', { family_id: familyId, name: name.trim(), goal: parseFloat(goal.replace(',', '.')) });
      onCreated(r.data);
      toast('✅ Скарбничку створено');
      onClose();
    } catch {
      toast('Помилка створення', 'err');
    }
  };

  return (
    <div style={sheet}>
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color: '#2c3e50' }}>Нова ціль</h3>
          <button onClick={onClose} style={closeBtn}>×</button>
        </div>
        <input type="text" placeholder="Назва (напр. Відпустка)" value={name} onChange={e => setName(e.target.value)} style={input} />
        <input inputMode="decimal" placeholder="Потрібна сума" value={goal} onChange={e => setGoal(e.target.value)} style={input} />
        <button onClick={create} disabled={!valid} style={{ width: '100%', padding: '15px', backgroundColor: valid ? '#3498db' : '#bdc3c7', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '16px' }}>Створити</button>
      </div>
    </div>
  );
}

export function TopUpJarModal({ jar, onClose, onToppedUp }: {
  jar: Jar; onClose: () => void; onToppedUp: (j: Jar, amount: number) => void;
}) {
  const [amount, setAmount] = useState('');
  const num = parseFloat(amount.replace(',', '.'));
  const valid = !isNaN(num) && num > 0;

  const topup = async () => {
    if (!valid) return;
    try {
      const r = await api.post(`/jars/${jar.id}/topup`, { amount: num });
      onToppedUp(r.data, num);
      toast('✅ Поповнено');
      onClose();
    } catch {
      toast('Помилка поповнення', 'err');
    }
  };

  return (
    <div style={sheet}>
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color: '#2c3e50' }}>Поповнити «{jar.name}»</h3>
          <button onClick={onClose} style={closeBtn}>×</button>
        </div>
        <input inputMode="decimal" placeholder="Сума поповнення" value={amount} autoFocus onChange={e => setAmount(e.target.value)} style={input} />
        <button onClick={topup} disabled={!valid} style={{ width: '100%', padding: '15px', backgroundColor: valid ? '#2ecc71' : '#bdc3c7', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '16px' }}>Закинути гроші</button>
      </div>
    </div>
  );
}
