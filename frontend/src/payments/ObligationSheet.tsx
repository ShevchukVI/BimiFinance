import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { day, dmy, money } from '../format';
import { confirmAsync, haptic } from '../tg';
import type { Transaction } from '../types';
import { Badge, Banner, Button, Card, Progress, Row, Sheet, Spinner, Tile } from '../ui';
import { errText } from '../housing/api';
import { KIND_LABEL, Obligation, payApi } from './api';
import { statusBadge, statusLine } from './PaymentsPage';

export default function ObligationSheet({ familyId, item, onClose, onEdit, onChanged }: {
  familyId: number; item: Obligation; onClose: () => void; onEdit: () => void; onChanged: () => void;
}) {
  const [txs, setTxs] = useState<Transaction[] | null>(null);
  const [busy, setBusy] = useState(false);
  const s = item.state;
  const credit = item.kind !== 'subscription';
  const load = () => payApi.transactions(familyId, item.id).then(setTxs).catch(e => toast(errText(e), 'err'));
  useEffect(() => { load(); }, [item.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const linkAll = async () => {
    setBusy(true);
    try { const r = await payApi.linkSuggested(familyId, item.id); haptic('success'); toast(`Пов'язано: ${r.linked}`); onChanged(); load(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const unlink = async (t: Transaction) => {
    if (!(await confirmAsync(`Відв'язати платіж ${money(t.amount)} від ${dmy(t.date)}?`))) return;
    try { await payApi.unlink(familyId, t.id); toast('Відв\'язано'); onChanged(); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <Sheet title={item.name} icon={item.icon} onClose={onClose}
      footer={<Button variant="secondary" onClick={onEdit}>Налаштувати</Button>}>
      <div className="muted small" style={{ marginTop: -8 }}>{KIND_LABEL[item.kind]} · {statusLine(item)}</div>
      {credit ? (
        <>
          <div className="grid2">
            <Tile label="Сплачено" value={s.payments_total ? `${s.paid_count} з ${s.payments_total}` : String(s.paid_count ?? 0)} />
            <Tile label="Залишилось" value={s.remaining_amount !== null ? money(s.remaining_amount, item.currency, 0) : '—'} tone={s.status === 'finished' ? 'pos' : undefined} />
            <Tile label="Наступний" value={s.next_due ? `${day(s.next_due)} · ${money(item.amount, item.currency, 0)}` : '—'} tone={s.status === 'overdue' ? 'danger' : undefined} />
            <Tile label="Останній платіж" value={s.end ? dmy(s.end) : '—'} />
          </div>
          {s.payments_total ? <Progress value={((s.paid_count || 0) / s.payments_total) * 100} /> : null}
        </>
      ) : (
        <div className="grid2">
          <Tile label="Ціна" value={`${money(item.amount, item.currency)}/${item.period === 'year' ? 'рік' : 'міс'}`} />
          <Tile label={s.status === 'missing' ? 'Очікували' : 'Наступне списання'} value={day(s.status === 'missing' ? s.expected : s.next_due)} tone={s.status === 'missing' || s.status === 'stale' ? 'warn' : undefined} />
          <Tile label="На рік" value={money(item.period === 'year' ? item.amount : item.amount * 12, item.currency, 0)} />
          <Tile label="Останнє списання" value={s.last_date ? day(s.last_date) : '—'} />
        </div>
      )}
      {item.suggested.length > 0 && (
        <Banner icon="🔗" onClick={linkAll}>
          <b>Знайдено {item.suggested.length} схожих платежів</b>
          <div className="muted small">{item.suggested.slice(0, 3).map(t => `${day(t.date)} ${money(t.amount)}`).join(' · ')} — натисніть, щоб пов'язати</div>
        </Banner>
      )}
      {s.status === 'overdue' && <Banner icon="💡" tone="warn">Якщо платіж уже був — відкрийте операцію в «Історії» і натисніть «Пов'язати», або вкажіть у налаштуваннях, скільки платежів сплачено поза Bimi.</Banner>}
      {busy && <Spinner />}
      {!item.match_pattern && <Banner icon="💡">Вкажіть у налаштуваннях «Як виглядає в банку» — тоді нові списання прив'язуватимуться самі.</Banner>}
      <div className="section-head"><span className="section-title">Платежі · {txs?.length ?? '…'}</span>{statusBadge(item)}</div>
      {txs === null ? <Spinner /> : txs.length === 0 ? <div className="muted small center">Ще немає пов'язаних операцій</div> : (
        <Card flush>
          {txs.map(t => <Row key={t.id} icon="💳" title={money(t.amount, t.currency)} sub={`${dmy(t.date)} · ${t.title.replace('❓ ', '')}${t.user_name ? ` · ${t.user_name}` : ''}`}
            end={<button className="link danger small" onClick={() => unlink(t)}>Відв'язати</button>} />)}
        </Card>
      )}
      {item.note && <div className="muted small">{item.note}</div>}
      {!item.is_active && <Badge>В архіві</Badge>}
    </Sheet>
  );
}
