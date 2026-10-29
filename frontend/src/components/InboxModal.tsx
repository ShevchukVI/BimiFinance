import { useEffect, useMemo, useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { Transaction, Category, cleanCatName } from '../types';
import { day, money, plural } from '../format';
import { haptic } from '../tg';
import { Button, Card, Chips, Empty, Section, Sheet, Spinner } from '../ui';
import { TxAmount, catIcon } from './TransactionCard';

type Hint = { category_id: number; confidence: 'sure' | 'likely'; source: 'history' | 'mcc' | 'chain'; reason: string };
type Group = { title: string; category_id: number; confidence: 'sure' | 'likely'; source: string; reason: string; count: number;
  min: number; max: number; total: number; transaction_ids: number[]; type: string };
type Smart = { pending: number; suggested: number; sure: number; by_tx: Record<string, Hint>; groups: Group[] };

const range = (g: Group) => g.min === g.max ? money(g.min, 'UAH', 0) : `${money(g.min, 'UAH', 0)}–${money(g.max, 'UAH', 0)}`;

// Inbox Zero: нерозібрані транзакції (категорія «Очікує»). Bimi пропонує категорію з історії (та ж назва й схожа сума),
// MCC-коду банку чи відомої мережі; впевнені групи — одним дотиком, решта — по одній з підказкою першою.
export default function InboxModal({ familyId, categories, onClose, onCategorized, onBulk }: {
  familyId: number;
  categories: Category[];
  onClose: () => void;
  onCategorized: (tx: Transaction) => void;
  onBulk: () => void;  // several operations categorised at once → refresh history & stats
}) {
  const [items, setItems] = useState<Transaction[]>([]);
  const [smart, setSmart] = useState<Smart | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [busyGroup, setBusyGroup] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [hidden, setHidden] = useState<string[]>([]);
  const [showLikely, setShowLikely] = useState(false);
  const pickable = (tx: Transaction) => categories.filter(
    c => c.type === (tx.type === 'Витрати' ? 'expense' : 'income') && !c.name.includes('Очікує') && !c.name.includes('Балансування'));
  const cat = (id: number) => categories.find(c => c.id === id);

  const load = async () => {
    try {
      const [p, s] = await Promise.all([api.get(`/families/${familyId}/pending`), api.get<Smart>(`/families/${familyId}/inbox/suggestions`)]);
      setItems(p.data); setSmart(s.data);
    } catch { toast('Не вдалося завантажити', 'err'); }
    setLoading(false);
  };
  useEffect(() => { load(); }, [familyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const gkey = (g: Group) => `${g.title}|${g.category_id}|${g.confidence}`;
  const doneIds = useMemo(() => new Set<number>(), []);
  const groups = (smart?.groups || []).filter(g => !hidden.includes(gkey(g)) && g.transaction_ids.some(id => !doneIds.has(id)));
  const sure = groups.filter(g => g.confidence === 'sure');
  const likely = groups.filter(g => g.confidence === 'likely');
  const sureCount = sure.reduce((n, g) => n + g.transaction_ids.filter(id => !doneIds.has(id)).length, 0);

  const applyIds = async (pairs: { transaction_id: number; category_id: number }[], key: string) => {
    setBusyGroup(key);
    try {
      const r = await api.post<{ applied: number; pending: number }>(`/families/${familyId}/inbox/apply`, { items: pairs });
      pairs.forEach(p => doneIds.add(p.transaction_id));
      setItems(prev => prev.filter(t => !doneIds.has(t.id)));
      setSmart(s => s && { ...s, pending: r.data.pending });
      haptic('success');
      toast(`Розкладено ${r.data.applied} ${plural(r.data.applied, 'операцію', 'операції', 'операцій')}`);
      onBulk();
    } catch { toast('Помилка збереження', 'err'); }
    setBusyGroup(null);
  };
  const acceptGroup = (g: Group) => applyIds(g.transaction_ids.filter(id => !doneIds.has(id)).map(id => ({ transaction_id: id, category_id: g.category_id })), gkey(g));
  const acceptAllSure = () => applyIds(sure.flatMap(g => g.transaction_ids.filter(id => !doneIds.has(id)).map(id => ({ transaction_id: id, category_id: g.category_id }))), 'all');

  const assign = async (tx: Transaction, catId: number) => {
    if (savingId !== null) return;
    setSavingId(tx.id);
    try {
      const r = await api.put(`/transactions/${tx.id}`, { category_id: catId });
      doneIds.add(tx.id);
      setItems(prev => prev.filter(t => t.id !== tx.id));
      setSmart(s => s && { ...s, pending: Math.max(0, s.pending - 1) });
      haptic('success');
      toast('Категорію призначено');
      onCategorized(r.data);
    } catch {
      toast('Помилка збереження', 'err');
    }
    setSavingId(null);
  };

  const groupCard = (g: Group) => {
    const k = gkey(g);
    const c = cat(g.category_id);
    const ids = g.transaction_ids.filter(id => !doneIds.has(id));
    const txs = items.filter(t => ids.includes(t.id));
    return (
      <Card key={k}>
        <div className="stack-s">
          <div className="spread" style={{ alignItems: 'flex-start' }}>
            <div className="grow" style={{ minWidth: 0 }}>
              <div className="bold ellipsis">{g.title}</div>
              <div className="muted small">{ids.length} {plural(ids.length, 'операція', 'операції', 'операцій')} · {range(g)}</div>
            </div>
            <span className="badge badge--accent" style={{ marginLeft: 8 }}>{catIcon(c)} {cleanCatName(c?.name)}</span>
          </div>
          <div className="muted xsmall">{g.source === 'history' ? `✨ ${g.reason}` : g.source === 'mcc' ? `🏷️ За типом продавця: ${g.reason}` : `🏪 Відома мережа: ${g.reason}`}</div>
          {open === k && txs.length > 0 && (
            <div className="inbox-peek">
              {txs.map(t => <div key={t.id} className="spread small"><span className="muted">{day(t.date)}{t.user_name ? ` · ${t.user_name}` : ''}</span><span className="tnum">{money(t.amount)}</span></div>)}
            </div>
          )}
          <div className="hstack" style={{ gap: 8 }}>
            <Button size="sm" onClick={() => acceptGroup(g)} busy={busyGroup === k}>Так, {ids.length > 1 ? `усі ${ids.length}` : 'розкласти'}</Button>
            {txs.length > 0 && <Button size="sm" variant="secondary" onClick={() => setOpen(open === k ? null : k)}>{open === k ? 'Згорнути' : 'Переглянути'}</Button>}
            <Button size="sm" variant="secondary" onClick={() => setHidden(h => [...h, k])}>Ні</Button>
          </div>
        </div>
      </Card>
    );
  };

  const total = smart?.pending ?? items.length;
  return (
    <Sheet title={`Розібрати${total ? ` · ${total}` : ''}`} icon="🧹" onClose={onClose}>
      {loading && <Spinner />}
      {!loading && items.length === 0 && (
        <Empty icon="🎉" title="Все розібрано!" text="Нові операції з Monobank з'являться тут автоматично." />
      )}
      {!loading && sure.length > 0 && (
        <Section title="Bimi пропонує">
          <Card>
            <div className="spread">
              <div><div className="bold">{sureCount} {plural(sureCount, 'операцію', 'операції', 'операцій')} можна розкласти одразу</div>
                <div className="muted small">Так ви вже розкладали ці місця з такими сумами</div></div>
            </div>
            <div style={{ marginTop: 10 }}><Button onClick={acceptAllSure} busy={busyGroup === 'all'}>Прийняти всі {sureCount}</Button></div>
          </Card>
          {sure.map(groupCard)}
        </Section>
      )}
      {!loading && likely.length > 0 && (
        <Section title="Можливо" action={showLikely ? 'Згорнути' : `Показати ${likely.length}`} onAction={() => setShowLikely(x => !x)}>
          {showLikely ? likely.map(groupCard) : (
            <div className="muted small" style={{ padding: '0 4px' }}>Здогадки за однією попередньою операцією, типом продавця чи відомою мережею — перевірте перед тим, як прийняти.</div>
          )}
        </Section>
      )}
      {!loading && items.length > 0 && (
        <Section title="По одній">
          {items.map(tx => {
            const h = smart?.by_tx[String(tx.id)];
            const opts = pickable(tx);
            const ordered = h ? [...opts.filter(c => c.id === h.category_id), ...opts.filter(c => c.id !== h.category_id)] : opts;
            return (
              <Card key={tx.id}>
                <div style={{ opacity: savingId === tx.id ? 0.5 : 1 }} className="stack-s">
                  <div className="spread">
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div className="bold ellipsis">{tx.title.replace(/^❓\s*/, '')}</div>
                      <div className="muted small">{day(tx.date)} · {tx.account}{tx.user_name ? ` · ${tx.user_name}` : ''}</div>
                    </div>
                    <TxAmount tx={tx} />
                  </div>
                  <Chips scroll small value={null} onChange={id => assign(tx, id)}
                    options={ordered.map(c => ({ value: c.id, label: h && c.id === h.category_id ? `✨ ${c.name}` : c.name }))} />
                </div>
              </Card>
            );
          })}
        </Section>
      )}
    </Sheet>
  );
}
