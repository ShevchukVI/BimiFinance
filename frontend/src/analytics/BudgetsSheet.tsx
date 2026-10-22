import { useEffect, useMemo, useState } from 'react';
import { toast } from '../toast';
import { money, parseNum } from '../format';
import { haptic } from '../tg';
import type { Category } from '../types';
import { Button, Card, Sheet, Spinner } from '../ui';
import { errText } from '../housing/api';
import { catIcon } from '../components/TransactionCard';
import { anApi, Budgets, Suggestion } from './api';

// Ліміти на місяць по категоріях витрат: одна форма, «Заповнити за середнім» — в один дотик.
export default function BudgetsSheet({ familyId, categories, budgets, onClose, onSaved }: {
  familyId: number; categories: Category[]; budgets: Budgets | null; onClose: () => void; onSaved: (b: Budgets) => void;
}) {
  const cats = useMemo(() => categories.filter(c => c.type === 'expense' && !/Очікує|Балансування|Переказ/.test(c.name)), [categories]);
  const [values, setValues] = useState<Record<number, string>>(() =>
    Object.fromEntries((budgets?.items || []).map(b => [b.category_id, String(b.amount)])));
  const [sug, setSug] = useState<Suggestion[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { anApi.suggest(familyId).then(setSug).catch(() => setSug([])); }, [familyId]);

  const avg = (cid: number) => sug?.find(s => s.category_id === cid);
  const ordered = [...cats].sort((a, b) => (avg(b.id)?.avg3 || 0) - (avg(a.id)?.avg3 || 0) || a.name.localeCompare(b.name));
  const total = Object.values(values).reduce((s, v) => s + (parseNum(v) || 0), 0);

  const fill = () => {
    if (!sug?.length) return;
    haptic('success');
    setValues(v => ({ ...v, ...Object.fromEntries(sug.filter(s => !v[s.category_id]).map(s => [s.category_id, String(s.suggested)])) }));
  };
  const save = async () => {
    setBusy(true);
    try {
      const items = cats.map(c => ({ category_id: c.id, amount: parseNum(values[c.id] || '') || null }))
        .filter(i => i.amount !== null || budgets?.items.some(b => b.category_id === i.category_id));
      const r = await anApi.saveBulk(familyId, items);
      haptic('success');
      toast('Бюджети збережено');
      onSaved(r);
      onClose();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  return (
    <Sheet title="Бюджети на місяць" icon="🎯" onClose={onClose} confirmClose
      footer={<Button onClick={save} busy={busy}>Зберегти{total ? ` · ${money(total, 'UAH', 0)} на місяць` : ''}</Button>}>
      <div className="muted small" style={{ marginTop: -8 }}>Ліміт на кожну категорію. Порожнє поле — без ліміту. Bimi попередить у боті на 80% і при перевищенні.</div>
      {sug === null ? <Spinner /> : sug.length > 0 && (
        <Button variant="secondary" size="sm" onClick={fill}>✨ Заповнити за середнім за 3 місяці</Button>
      )}
      <Card flush>
        {ordered.map(c => {
          const a = avg(c.id);
          return (
            <div key={c.id} className="row row--compact">
              <div className="row__icon">{catIcon(c)}</div>
              <div className="row__body">
                <div className="row__title">{c.name.replace(/^\S+\s/, '')}</div>
                <div className="row__sub">{a ? `в середньому ${money(a.avg3, 'UAH', 0)}` : 'останнім часом без витрат'}</div>
              </div>
              <input className="input tnum" style={{ width: 110, height: 40, textAlign: 'right' }} inputMode="decimal"
                placeholder={a ? String(a.suggested) : '—'} value={values[c.id] || ''} aria-label={`Ліміт ${c.name}`}
                onChange={e => setValues(v => ({ ...v, [c.id]: e.target.value }))} />
            </div>
          );
        })}
      </Card>
    </Sheet>
  );
}
