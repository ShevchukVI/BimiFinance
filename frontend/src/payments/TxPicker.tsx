import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { day, money } from '../format';
import { haptic } from '../tg';
import { Badge, Button, Card, Row, Spinner } from '../ui';
import { errText } from '../housing/api';
import { payApi, PickTx } from './api';

// «Обрати операцію»: ще не пов'язані витрати за 4 міс., схожі (шаблон банку / сума) — зверху. Дата й сума беруться з операції.
export default function TxPicker({ familyId, type, id, onLinked }: {
  familyId: number; type: 'provider' | 'obligation'; id: number; onLinked: (tx: PickTx) => void;
}) {
  const [items, setItems] = useState<PickTx[] | null>(null);
  const [q, setQ] = useState('');
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  useEffect(() => { setItems(null); payApi.candidates(familyId, type, id).then(setItems).catch(e => { toast(errText(e), 'err'); setItems([]); }); }, [familyId, type, id]);

  const pick = async (t: PickTx) => {
    if (busy !== null) return;
    setBusy(t.id);
    try { await payApi.setLink(familyId, t.id, type, id); haptic('success'); toast(`Пов'язано: ${money(t.amount)} від ${day(t.date)}`); setItems(x => (x || []).filter(i => i.id !== t.id)); onLinked(t); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(null);
  };

  if (items === null) return <Spinner />;
  const needle = q.trim().toLowerCase();
  const found = needle ? items.filter(t => `${t.title} ${t.amount} ${t.user_name || ''}`.toLowerCase().includes(needle)) : items;
  const matches = found.filter(t => t.match).length;
  const shown = needle || all ? found : found.slice(0, Math.max(matches, 0) + 5);
  return (
    <div className="stack-s">
      <input className="input" type="search" placeholder="🔍 Назва або сума" value={q} onChange={e => setQ(e.target.value)} />
      {shown.length === 0 ? <div className="muted small center">Немає непов'язаних витрат{needle ? ' за пошуком' : ' за 4 місяці'}</div> : (
        <Card flush>
          {shown.map(t => <Row key={t.id} icon={busy === t.id ? '⏳' : t.account === 'Готівка' ? '💵' : '💳'} title={t.title}
            sub={`${day(t.date)} · ${t.account}${t.user_name ? ` · ${t.user_name}` : ''}`}
            end={<span className="hstack"><b className="tnum">{money(t.amount)}</b>{t.match && <Badge tone="ok">схоже</Badge>}</span>}
            onClick={() => pick(t)} />)}
        </Card>
      )}
      {!needle && !all && found.length > shown.length && <Button variant="secondary" size="sm" onClick={() => setAll(true)}>Показати всі · {found.length}</Button>}
    </div>
  );
}
