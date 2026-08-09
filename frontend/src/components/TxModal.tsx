import { useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { Transaction, Category, cleanCatName } from '../types';

const sheet: React.CSSProperties = {
  position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)',
  zIndex: 110, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
};
const card: React.CSSProperties = {
  backgroundColor: '#fff', borderTopLeftRadius: '24px', borderTopRightRadius: '24px',
  padding: '25px', paddingBottom: 'calc(25px + env(safe-area-inset-bottom))',
  maxHeight: '90vh', overflowY: 'auto',
};
const input: React.CSSProperties = {
  width: '100%', padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9',
  fontSize: '16px', boxSizing: 'border-box',
};
const closeBtn: React.CSSProperties = { border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6', cursor: 'pointer' };

// Додавання/редагування транзакції. editingTx == null → режим створення.
export default function TxModal({
  editingTx, categories, familyId, dbUserId, onClose, onSaved, onDeleted, haptic,
}: {
  editingTx: Transaction | null;
  categories: Category[];
  familyId: number;
  dbUserId: number;
  onClose: () => void;
  onSaved: (tx: Transaction) => void;
  onDeleted: (id: number) => void;
  haptic: (s: 'light' | 'medium' | 'heavy' | 'success') => void;
}) {
  const [txType, setTxType] = useState<'Витрати' | 'Поповнення'>((editingTx?.type as any) || 'Витрати');
  const [txAmount, setTxAmount] = useState(editingTx ? String(editingTx.amount) : '');
  const [txTitle, setTxTitle] = useState(editingTx?.title || '');
  const [txDate, setTxDate] = useState(editingTx?.date || new Date().toISOString().split('T')[0]);
  const [txCategoryId, setTxCategoryId] = useState<number | null>(editingTx?.category_id || null);
  const [busy, setBusy] = useState(false);

  const filtered = categories.filter(c => c.type === (txType === 'Витрати' ? 'expense' : 'income') && !c.name.includes('Очікує'));
  const amountNum = parseFloat(txAmount.replace(',', '.'));
  const valid = !isNaN(amountNum) && amountNum > 0 && txCategoryId !== null && (txTitle.trim() || txCategoryId);

  const save = async () => {
    if (!valid || busy) return;
    setBusy(true);
    const payload = {
      amount: amountNum, type: txType, category_id: txCategoryId,
      title: txTitle.trim() || cleanCatName(categories.find(c => c.id === txCategoryId)?.name),
      date: txDate,
    };
    try {
      const r = editingTx
        ? await api.put(`/transactions/${editingTx.id}`, payload)
        : await api.post('/transactions', { ...payload, family_id: familyId, user_id: dbUserId, account: 'Готівка' });
      onSaved(r.data);
      haptic('success');
      toast(editingTx ? '✅ Оновлено' : '✅ Записано');
      onClose();
    } catch {
      toast('Помилка збереження', 'err');
    }
    setBusy(false);
  };

  const remove = async () => {
    if (!editingTx || busy || !window.confirm('Видалити транзакцію?')) return;
    setBusy(true);
    try {
      await api.delete(`/transactions/${editingTx.id}`);
      onDeleted(editingTx.id);
      haptic('success');
      toast('🗑 Видалено');
      onClose();
    } catch {
      toast('Помилка видалення', 'err');
    }
    setBusy(false);
  };

  return (
    <div style={sheet}>
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color: '#2c3e50' }}>{editingTx ? 'Редагування' : 'Нова транзакція'}</h3>
          <button onClick={onClose} style={closeBtn}>×</button>
        </div>

        <div style={{ display: 'flex', backgroundColor: '#f1f2f6', borderRadius: '12px', padding: '4px', marginBottom: '15px' }}>
          {(['Витрати', 'Поповнення'] as const).map(t => (
            <div key={t} onClick={() => { setTxType(t); setTxCategoryId(null); }}
              style={{ flex: 1, textAlign: 'center', padding: '10px', borderRadius: '10px', cursor: 'pointer', backgroundColor: txType === t ? '#fff' : 'transparent', fontWeight: txType === t ? 'bold' : 'normal', color: txType === t ? (t === 'Витрати' ? '#e74c3c' : '#27ae60') : '#7f8c8d', boxShadow: txType === t ? '0 2px 5px rgba(0,0,0,0.05)' : 'none' }}>
              {t === 'Витрати' ? 'Витрата' : 'Дохід'}
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
          <input inputMode="decimal" placeholder="Сума" value={txAmount} autoFocus={!editingTx}
            onChange={e => setTxAmount(e.target.value)}
            style={{ ...input, flex: 2, fontSize: '20px', fontWeight: 'bold' }} />
          <input type="date" value={txDate} onChange={e => setTxDate(e.target.value)}
            style={{ ...input, flex: 1, backgroundColor: '#fff' }} />
        </div>

        <input type="text" placeholder="Що купили? (необов'язково)" value={txTitle} onChange={e => setTxTitle(e.target.value)}
          style={{ ...input, marginBottom: '15px' }} />

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '20px', maxHeight: '180px', overflowY: 'auto' }}>
          {filtered.map(c => (
            <button key={c.id} onClick={() => { setTxCategoryId(c.id); haptic('light'); }}
              style={{ padding: '10px 14px', borderRadius: '20px', border: txCategoryId === c.id ? '2px solid #3498db' : '1px solid #dfe6e9', backgroundColor: txCategoryId === c.id ? '#ebf5fb' : '#f8f9fa', fontSize: '14px', cursor: 'pointer', color: '#2c3e50', fontWeight: txCategoryId === c.id ? 'bold' : 'normal' }}>
              {c.name}
            </button>
          ))}
        </div>

        <button onClick={save} disabled={!valid || busy}
          style={{ width: '100%', padding: '15px', backgroundColor: valid ? '#3498db' : '#bdc3c7', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '16px', marginBottom: editingTx ? '10px' : '0', cursor: valid ? 'pointer' : 'default' }}>
          {busy ? '⏳ Зберігаю...' : 'Зберегти'}
        </button>
        {editingTx && (
          <button onClick={remove} disabled={busy}
            style={{ width: '100%', padding: '15px', backgroundColor: '#fff', color: '#e74c3c', border: '1px solid #e74c3c', borderRadius: '12px', fontWeight: 'bold', fontSize: '16px', cursor: 'pointer' }}>
            Видалити транзакцію
          </button>
        )}
      </div>
    </div>
  );
}
