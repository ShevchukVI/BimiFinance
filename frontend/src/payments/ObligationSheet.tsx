import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { day, dmy, money, parseNum, todayIso } from '../format';
import { confirmAsync, haptic } from '../tg';
import type { Transaction } from '../types';
import { Badge, Banner, Button, Card, Field, Progress, Row, Segmented, Sheet, Spinner, Tile } from '../ui';
import TxPicker from './TxPicker';
import { errText } from '../housing/api';
import { KIND_LABEL, Obligation, payApi } from './api';
import { statusBadge, statusLine } from './PaymentsPage';

export default function ObligationSheet({ familyId, item, onClose, onEdit, onChanged }: {
  familyId: number; item: Obligation; onClose: () => void; onEdit: () => void; onChanged: () => void;
}) {
  const [txs, setTxs] = useState<Transaction[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [add, setAdd] = useState<'bank' | 'cash' | null>(null);
  const [cash, setCash] = useState(String(item.amount));
  const [cashDate, setCashDate] = useState(todayIso());
  const s = item.state;
  const credit = item.kind !== 'subscription';
  const load = () => payApi.transactions(familyId, item.id).then(setTxs).catch(e => toast(errText(e), 'err'));
  useEffect(() => { load(); }, [item.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const linkAll = async () => {
    if (busy) return;
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

  const added = () => { setAdd(null); onChanged(); load(); };
  const payCash = async () => {
    const n = parseNum(cash);
    if (!(n > 0) || busy) return;
    setBusy(true);
    try { await payApi.payCash(familyId, item.id, { amount: n, date: cashDate }); haptic('success'); toast(`Платіж ${money(n)} записано`); added(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  return (
    <Sheet title={item.name} icon={item.icon} onClose={onClose}
      footer={<div className="btn-row">
        <Button variant="secondary" onClick={onEdit}>Налаштувати</Button>
        {item.is_active && <Button onClick={() => setAdd(add ? null : 'bank')}>{add ? 'Сховати' : '➕ Платіж'}</Button>}
      </div>}>
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
      {s.status === 'overdue' && <Banner icon="💡" tone="warn">Якщо платіж уже був — натисніть «➕ Платіж» і оберіть операцію (або «Готівкою»), чи вкажіть у налаштуваннях, скільки платежів сплачено поза Bimi.</Banner>}
      {add && (
        <Card>
          <div className="stack-s">
            <Segmented value={add} onChange={setAdd} options={[{ value: 'bank', label: '🔗 Обрати операцію' }, { value: 'cash', label: '💵 Готівкою' }]} />
            {add === 'bank' ? <TxPicker familyId={familyId} type="obligation" id={item.id} onLinked={added} /> : <>
              <div className="grid2">
                <Field label="Сума"><input className="input tnum" inputMode="decimal" value={cash} onChange={e => setCash(e.target.value)} /></Field>
                <Field label="Дата"><input className="input" type="date" value={cashDate} max={todayIso()} onChange={e => setCashDate(e.target.value)} /></Field>
              </div>
              <Button onClick={payCash} busy={busy} disabled={!(parseNum(cash) > 0)}>Записати · витрата з «Готівки»</Button>
            </>}
          </div>
        </Card>
      )}
      {busy && !add && <Spinner />}
      {!item.match_pattern && <Banner icon="💡">Вкажіть у налаштуваннях «Як виглядає в банку» — тоді нові списання прив'язуватимуться самі.</Banner>}
      <div className="section-head"><span className="section-title">Платежі · {txs?.length ?? '…'}</span>{statusBadge(item)}</div>
      {txs === null ? <Spinner /> : txs.length === 0 ? <div className="muted small center">Ще немає пов'язаних операцій</div> : (
        <Card flush>
          {txs.map(t => <Row key={t.id} icon="💳" title={money(t.amount, t.currency)} sub={`${dmy(t.date)} · ${t.title.replace('❓ ', '')}${t.user_name ? ` · ${t.user_name}` : ''}`}
            end={<button className="btn btn--icon" aria-label="Відв'язати" onClick={() => unlink(t)}>✕</button>} />)}
        </Card>
      )}
      {item.note && <div className="muted small">{item.note}</div>}
      {!item.is_active && <Badge>В архіві</Badge>}
    </Sheet>
  );
}
