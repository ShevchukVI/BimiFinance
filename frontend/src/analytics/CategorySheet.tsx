import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { money, monthYear } from '../format';
import type { Category, Transaction } from '../types';
import { Progress, Sheet, Spinner, Tile } from '../ui';
import { errText } from '../housing/api';
import { TxList } from '../components/TransactionCard';
import { anApi, BudgetRow, CatRow } from './api';

export default function CategorySheet({ familyId, month, row, budget, categories, onClose, onView }: {
  familyId: number; month: string; row: CatRow; budget?: BudgetRow; categories: Category[]; onClose: () => void; onView: (t: Transaction) => void;
}) {
  const [txs, setTxs] = useState<Transaction[] | null>(null);
  useEffect(() => {
    anApi.categoryTx(familyId, month, row.category_id)
      .then(list => setTxs(row.category_id === null ? list.filter(t => !t.category_id) : list.filter(t => !t.jar_id)))
      .catch(e => toast(errText(e), 'err'));
  }, [familyId, month, row.category_id]);
  const delta = row.avg3 ? Math.round((row.amount / row.avg3 - 1) * 100) : null;

  return (
    <Sheet title={row.name} onClose={onClose}>
      <div className="muted small" style={{ marginTop: -8 }}>{monthYear(month)} · {row.share}% усіх витрат</div>
      <div className="grid2">
        <Tile label="Цього місяця" value={money(row.amount, 'UAH', 0)} />
        <Tile label="Минулого місяця" value={money(row.prev, 'UAH', 0)} />
        <Tile label="Середнє за 3 міс" value={money(row.avg3, 'UAH', 0)} tone={delta !== null && delta > 20 ? 'warn' : undefined} />
        <Tile label="До середнього" value={delta === null ? '—' : `${delta > 0 ? '+' : ''}${delta}%`} tone={delta !== null && delta > 20 ? 'danger' : delta !== null && delta < -10 ? 'pos' : undefined} />
      </div>
      {budget && (
        <div className="stack-s">
          <div className="spread small"><span className="muted">Бюджет {money(budget.amount, 'UAH', 0)}</span>
            <b className={budget.status === 'over' ? 'danger' : budget.status === 'warn' ? 'warn' : 'pos'}>{budget.remaining >= 0 ? `лишилось ${money(budget.remaining, 'UAH', 0)}` : `перевищено на ${money(-budget.remaining, 'UAH', 0)}`}</b></div>
          <Progress value={budget.pct} tone={budget.status === 'over' ? 'danger' : budget.status === 'warn' ? 'warn' : undefined} />
        </div>
      )}
      {txs === null ? <Spinner /> : txs.length === 0 ? <div className="muted small center">Операцій немає</div>
        : <TxList transactions={txs} categories={categories} onView={t => { onClose(); onView(t); }} />}
    </Sheet>
  );
}
