import { useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { Transaction, Category, CURRENCIES, cleanCatName } from '../types';
import { parseNum, todayIso } from '../format';
import { confirmAsync, haptic } from '../tg';
import { Button, Chips, Field, Segmented, Sheet, Switch } from '../ui';

type TxType = 'Витрати' | 'Поповнення';

// Додавання/редагування транзакції. editingTx == null → режим створення.
export default function TxModal({
  editingTx, categories, familyId, dbUserId, accounts, onClose, onSaved, onDeleted, initialType = 'Витрати', usage = {},
}: {
  usage?: Record<number, number>;  // category id → how often it was used lately (most used first)
  editingTx: Transaction | null;
  categories: Category[];
  familyId: number;
  dbUserId: number;
  accounts: string[]; // «Готівка» + підключені банки
  onClose: () => void;
  onSaved: (tx: Transaction) => void;
  onDeleted: (id: number) => void;
  initialType?: TxType;
}) {
  const [txType, setTxType] = useState<TxType>((editingTx?.type as TxType) || initialType);
  const [amount, setAmount] = useState(editingTx ? String(editingTx.amount) : '');
  const [title, setTitle] = useState(editingTx?.title || '');
  const [date, setDate] = useState(editingTx?.date || todayIso());
  const [categoryId, setCategoryId] = useState<number | null>(editingTx?.category_id || null);
  const [note, setNote] = useState(editingTx?.note || '');
  const [account, setAccount] = useState<string>(editingTx?.account || (accounts.includes('Готівка') ? 'Готівка' : accounts[0] || 'Готівка'));
  const [currency, setCurrency] = useState<string>(editingTx?.currency || 'UAH');
  const [more, setMore] = useState(!!(editingTx && (editingTx.note || editingTx.currency !== 'UAH')));
  const [busy, setBusy] = useState(false);
  const [allCats, setAllCats] = useState(false);
  // ↩️ money back for a purchase (friends paid their share, a return): income filed under the expense category it lowers
  const [refund, setRefund] = useState(!!editingTx?.refund);

  // most used first; service categories («Балансування» — corrections of the cash balance) at the end
  const service = (c: Category) => c.name.includes('Балансування');
  const filtered = categories.filter(c => c.type === (txType === 'Витрати' || refund ? 'expense' : 'income') && !c.name.includes('Очікує') && !(refund && service(c)))
    .map((c, i) => ({ c, i })).sort((a, b) => Number(service(a.c)) - Number(service(b.c)) || (usage[b.c.id] || 0) - (usage[a.c.id] || 0) || a.i - b.i)
    .map(x => x.c);
  const TOP = 8;
  const shown = allCats || filtered.length <= TOP + 1 ? filtered
    : [...filtered.slice(0, TOP), ...filtered.slice(TOP).filter(c => c.id === categoryId)];
  const amountNum = parseNum(amount);
  const valid = Number.isFinite(amountNum) && amountNum > 0 && categoryId !== null;

  const save = async () => {
    if (!valid || busy) return;
    setBusy(true);
    const payload = {
      amount: amountNum, type: txType, category_id: categoryId,
      title: title.trim() || cleanCatName(categories.find(c => c.id === categoryId)?.name),
      date, note: note.trim(), currency, refund: txType === 'Поповнення' && refund,
    };
    try {
      const r = editingTx
        ? await api.put(`/transactions/${editingTx.id}`, { ...payload, account })
        : await api.post('/transactions', { ...payload, family_id: familyId, user_id: dbUserId, account });
      onSaved(r.data);
      haptic('success');
      toast(editingTx ? 'Оновлено' : 'Записано');
      onClose();
    } catch {
      toast('Помилка збереження', 'err');
    }
    setBusy(false);
  };

  const remove = async () => {
    if (!editingTx || busy || !(await confirmAsync('Видалити транзакцію?'))) return;
    setBusy(true);
    try {
      await api.delete(`/transactions/${editingTx.id}`);
      onDeleted(editingTx.id);
      haptic('success');
      toast('Видалено');
      onClose();
    } catch {
      toast('Помилка видалення', 'err');
    }
    setBusy(false);
  };

  return (
    <Sheet title={editingTx ? 'Редагування' : 'Нова операція'} onClose={onClose} confirmClose
      footer={<>
        <Button onClick={save} disabled={!valid} busy={busy}>{editingTx ? 'Зберегти' : 'Записати'}</Button>
        {editingTx && <Button variant="danger" onClick={remove} disabled={busy}>Видалити</Button>}
      </>}>
      <Segmented value={txType} onChange={t => { setTxType(t); setCategoryId(null); setRefund(false); }}
        options={[{ value: 'Витрати', label: 'Витрата' }, { value: 'Поповнення', label: 'Дохід' }]} />

      <input className="input input--big tnum" inputMode="decimal" placeholder="0 ₴" value={amount}
        autoFocus={!editingTx} onChange={e => setAmount(e.target.value)} aria-label="Сума" />

      {txType === 'Поповнення' && (
        <div className="spread">
          <div style={{ minWidth: 0 }}><div className="bold">↩️ Повернення за покупку</div>
            <div className="muted small">Друзі віддали свою частку, повернули товар — зменшує витрати категорії й конверт, а не дохід</div></div>
          <Switch on={refund} onChange={v => { setRefund(v); setCategoryId(null); }} label="Повернення за покупку" />
        </div>
      )}
      <Field label={refund ? 'За що повернули' : 'Категорія'}>
        <Chips value={categoryId} onChange={setCategoryId} options={shown.map(c => ({ value: c.id, label: c.name }))} />
        {shown.length < filtered.length && (
          <button className="link" style={{ alignSelf: 'flex-start', marginTop: 4 }} onClick={() => setAllCats(true)}>Усі категорії ({filtered.length}) ›</button>
        )}
      </Field>

      <input className="input" placeholder="Що купили? (необов'язково)" value={title} onChange={e => setTitle(e.target.value)} />

      {accounts.length > 1 && (
        <Field label="Рахунок">
          <Chips value={account} onChange={setAccount} small
            options={accounts.map(a => ({ value: a, label: a === 'Готівка' ? '💵 Готівка' : `💳 ${a}` }))} />
        </Field>
      )}

      {more ? (
        <>
          <div className="grid2">
            <Field label="Дата"><input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} /></Field>
            <Field label="Валюта">
              <Chips value={currency} onChange={setCurrency} small options={CURRENCIES.map(c => ({ value: c, label: c }))} />
            </Field>
          </div>
          <input className="input" placeholder="Коментар" value={note} onChange={e => setNote(e.target.value)} />
        </>
      ) : (
        <button className="link" style={{ alignSelf: 'flex-start' }} onClick={() => setMore(true)}>
          Дата {date !== todayIso() ? `(${date})` : 'сьогодні'} · валюта · коментар ›
        </button>
      )}
    </Sheet>
  );
}
