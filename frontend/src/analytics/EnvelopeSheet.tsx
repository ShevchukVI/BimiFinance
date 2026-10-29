import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { money, todayIso } from '../format';
import type { Category, Transaction } from '../types';
import { Button, Progress, Sheet, Spinner, Tile } from '../ui';
import { errText } from '../housing/api';
import { TxList } from '../components/TransactionCard';
import { anApi, BudgetRow } from './api';

// Конверт = бюджет категорії на поточний місяць: скільки лишилось, на день, що вже витрачено.
export default function EnvelopeSheet({ familyId, env, categories, daysLeft, onClose, onView, onEdit }: {
  familyId: number; env: BudgetRow; categories: Category[]; daysLeft: number; onClose: () => void;
  onView: (t: Transaction) => void; onEdit: () => void;
}) {
  const [txs, setTxs] = useState<Transaction[] | null>(null);
  const month = todayIso().slice(0, 7) + '-01';
  useEffect(() => {
    anApi.categoryTx(familyId, month, env.category_id).then(l => setTxs(l.filter(t => !t.jar_id))).catch(e => toast(errText(e), 'err'));
  }, [familyId, env.category_id, month]);
  const dim = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0).getDate();
  const over = env.status === 'over';

  return (
    <Sheet title={env.name} onClose={onClose} footer={<Button variant="secondary" onClick={onEdit}>Змінити ліміти</Button>}>
      <div className="center" style={{ padding: '2px 0 4px' }}>
        <div className="muted small">{over ? 'Перевищено на' : 'Лишилось у конверті'}</div>
        <div className={`tnum ${over ? 'danger' : ''}`} style={{ fontSize: 34, fontWeight: 800 }}>{money(Math.abs(env.remaining), 'UAH', 0)}</div>
        <div className="muted small">з {money(env.amount, 'UAH', 0)} на місяць</div>
      </div>
      <Progress value={env.pct} tone={over ? 'danger' : env.status === 'warn' ? 'warn' : undefined} mark={((dim - daysLeft) / dim) * 100} />
      <div className="grid2">
        <Tile label="Витрачено" value={money(env.spent, 'UAH', 0)} />
        <Tile label="Можна на день" value={env.per_day_left ? money(env.per_day_left, 'UAH', 0) : over ? '0 ₴' : '—'} tone={over ? 'danger' : undefined} />
        <Tile label="Прогноз на місяць" value={money(env.forecast, 'UAH', 0)} tone={env.forecast > env.amount ? 'warn' : undefined} />
        <Tile label="До кінця місяця" value={`${daysLeft} дн.`} />
      </div>
      {txs === null ? <Spinner /> : txs.length === 0 ? <div className="muted small center">Цього місяця ще нічого не витрачено</div>
        : <TxList transactions={txs} categories={categories} onView={t => { onClose(); onView(t); }} />}
    </Sheet>
  );
}
