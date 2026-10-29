import { useRef, useState } from 'react';
import { toast } from '../toast';
import { dmy, money, parseNum, qty, todayIso } from '../format';
import { confirmAsync, haptic } from '../tg';
import { Button, Card, Chips, Field, KV, Sheet, Switch } from '../ui';
import { errText } from '../housing/api';
import { autoApi } from './api';
import { Fuel, FUELS, KINDS, LogDraft, LogKind, TxBrief, Vehicle, vehicleFuels, VLog } from './types';

const str = (n: number | null | undefined) => (n || n === 0 ? String(n).replace('.', ',') : '');
const round2 = (n: number) => Math.round(n * 100) / 100;

// Запис журналу: заправка (літри × ціна = сума, пробіг, «до повного»), ТО, мийка… Можна одразу записати витрату.
export default function LogSheet({ familyId, vehicles, vehicleId, log, draft, tx, accounts, initialKind, onClose, onSaved }: {
  familyId: number; vehicles: Vehicle[]; vehicleId: number; log?: VLog; draft?: LogDraft; tx?: TxBrief | null;
  accounts: string[]; initialKind?: LogKind; onClose: () => void; onSaved: (withTx: boolean) => void;
}) {
  const src = log || draft;
  const linked = log?.transaction || tx || null;
  const [vid, setVid] = useState(src?.vehicle_id || vehicleId);
  const v = vehicles.find(x => x.id === vid) || vehicles[0];
  const [kind, setKind] = useState<LogKind>(src?.kind || initialKind || 'fuel');
  const [date, setDate] = useState(src?.date || todayIso());
  const [fuel, setFuel] = useState<Fuel>(src?.fuel || v.fuel);
  const [liters, setLiters] = useState(str(src?.liters));
  const [price, setPrice] = useState(str(src?.price));
  const [amount, setAmount] = useState(src?.amount ? str(round2(src.amount)) : '');
  const [odo, setOdo] = useState(str(src?.odometer));
  const [full, setFull] = useState(!!src?.full_tank);
  const [title, setTitle] = useState(src?.kind !== 'fuel' ? (src?.title || '') : '');
  const [note, setNote] = useState(log?.note || '');
  const [withTx, setWithTx] = useState(!linked);
  const [account, setAccount] = useState(accounts[0] || 'Готівка');
  const [busy, setBusy] = useState(false);
  const computed = useRef<'amount' | 'liters' | null>(null);  // the field filled from the other two

  const fuels = Array.from(new Set([...vehicleFuels(v), ...(src?.fuel ? [src.fuel] : [])]));
  const L = parseNum(liters), P = parseNum(price), A = parseNum(amount), O = Number(odo.replace(/\D/g, ''));
  const last = v.stats.odometer;
  const isFuel = kind === 'fuel', isOdo = kind === 'odometer';
  const valid = isOdo ? O > 0 : isFuel ? (A > 0 || L > 0) : A > 0 || !!linked;

  // two of (liters, price, amount) fill the third
  const onLiters = (s: string) => {
    setLiters(s);
    const l = parseNum(s);
    if (P > 0 && l > 0 && (!amount || computed.current === 'amount')) { setAmount(str(round2(l * P))); computed.current = 'amount'; }
  };
  const onPrice = (s: string) => {
    setPrice(s);
    const p = parseNum(s);
    if (p > 0 && L > 0 && computed.current !== 'liters' && (!amount || computed.current === 'amount')) { setAmount(str(round2(L * p))); computed.current = 'amount'; }
    else if (p > 0 && A > 0 && (!liters || computed.current === 'liters')) { setLiters(str(round2(A / p))); computed.current = 'liters'; }
  };
  const onAmount = (s: string) => {
    setAmount(s);
    computed.current = computed.current === 'amount' ? null : computed.current;
    const a = parseNum(s);
    if (P > 0 && a > 0 && (!liters || computed.current === 'liters')) { setLiters(str(round2(a / P))); computed.current = 'liters'; }
  };

  const save = async () => {
    if (!valid) return;
    setBusy(true);
    const body: Record<string, unknown> = {
      vehicle_id: vid, kind, date, odometer: O || null, note: note.trim(),
      amount: isOdo ? 0 : (A > 0 ? A : (linked ? linked.amount : 0)),
      title: isFuel || isOdo ? '' : title.trim(),
      ...(isFuel ? { fuel, liters: L > 0 ? L : null, price: P > 0 ? P : null, full_tank: full } : {}),
    };
    try {
      if (log) await autoApi.updateLog(familyId, log.id, body);
      else await autoApi.addLog(familyId, { ...body, transaction_id: linked?.id ?? null,
        create_transaction: !linked && withTx && !isOdo, account });
      haptic('success');
      toast(log ? 'Збережено' : isFuel ? 'Заправку записано' : isOdo ? 'Пробіг записано' : 'Записано');
      onSaved(!linked && withTx && !isOdo && !log);
      onClose();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const remove = async () => {
    if (!log || !(await confirmAsync('Видалити запис з журналу?'))) return;
    const withTxDel = !!log.transaction_id && await confirmAsync('Видалити також витрату з «Історії»?');
    try { await autoApi.deleteLog(familyId, log.id, withTxDel); toast('Видалено'); onSaved(withTxDel); onClose(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  const odoHint = last ? (O > last ? `+${qty(O - last, 0)} км від ${qty(last, 0)}` : `останній ${qty(last, 0)} км`) : undefined;
  const sheetTitle = log ? KINDS.find(k => k.value === kind)?.label || 'Запис' : 'Новий запис';
  return (
    <Sheet title={sheetTitle} icon={KINDS.find(k => k.value === kind)?.icon} onClose={onClose} confirmClose
      footer={<>
        <Button onClick={save} disabled={!valid} busy={busy}>{log ? 'Зберегти' : `Записати${A > 0 && !isOdo ? ` · ${money(A)}` : ''}`}</Button>
        {log && <Button variant="danger" onClick={remove}>Видалити</Button>}
      </>}>
      {vehicles.length > 1 && <Chips small value={vid} onChange={setVid} options={vehicles.map(x => ({ value: x.id, label: `${x.icon} ${x.name}` }))} />}
      <Chips scroll small value={kind} onChange={setKind} options={KINDS.map(k => ({ value: k.value, label: `${k.icon} ${k.label}` }))} />
      {draft?.foreign_fuel && <div className="banner banner--warn"><span className="banner__body">Паливо «{FUELS[draft.fuel as Fuel]?.label}» — не цього авто. Можливо, це інша машина?</span></div>}

      {isFuel && (
        <>
          {fuels.length > 1 && <Chips value={fuel} onChange={setFuel} options={fuels.map(f => ({ value: f, label: `${FUELS[f].icon} ${FUELS[f].label}` }))} />}
          <div className="grid2">
            <Field label={`Скільки, ${FUELS[fuel].unit}`}><input className="input input--big tnum" inputMode="decimal" placeholder="0" value={liters} onChange={e => onLiters(e.target.value)} /></Field>
            <Field label={`Ціна за ${FUELS[fuel].unit}`}><input className="input input--big tnum" inputMode="decimal" placeholder={v.stats.fuels[fuel]?.last_price ? str(v.stats.fuels[fuel]!.last_price) : '0'} value={price} onChange={e => onPrice(e.target.value)} /></Field>
          </div>
          <div className="card">
            <div className="spread">
              <div><div className="bold">До повного бака</div><div className="muted small">Між двома повними баками витрата рахується точно</div></div>
              <Switch on={full} onChange={setFull} label="До повного" />
            </div>
          </div>
        </>
      )}
      {!isFuel && !isOdo && <Field label="Що саме"><input className="input" placeholder={KINDS.find(k => k.value === kind)?.label} value={title} onChange={e => setTitle(e.target.value)} /></Field>}

      <div className="grid2">
        {!isOdo && <Field label="Сума"><input className="input tnum" inputMode="decimal" placeholder="0 ₴" value={amount} onChange={e => onAmount(e.target.value)} /></Field>}
        <Field label="Пробіг, км" hint={odoHint}><input className="input tnum" inputMode="numeric" placeholder={last ? qty(last, 0) : 'км'} value={odo} onChange={e => setOdo(e.target.value.replace(/[^\d ]/g, ''))} /></Field>
        {isOdo && <Field label="Дата"><input className="input" type="date" value={date} max={todayIso()} onChange={e => setDate(e.target.value)} /></Field>}
      </div>
      {!isOdo && !linked && <Field label="Дата"><input className="input" type="date" value={date} max={todayIso()} onChange={e => setDate(e.target.value)} /></Field>}
      <Field label="Примітка"><input className="input" placeholder="АЗС, СТО, що міняли… необов'язково" value={note} onChange={e => setNote(e.target.value)} /></Field>

      {linked ? (
        <Card>
          <div className="muted small" style={{ marginBottom: 4 }}>🔗 Оплачено операцією</div>
          <KV k={linked.title} v={money(linked.amount)} />
          <div className="muted xsmall">{dmy(linked.date)} · {linked.account}{linked.note ? ` · ${linked.note}` : ''}</div>
        </Card>
      ) : !isOdo && !log && (
        <div className="card">
          <div className="spread">
            <div><div className="bold">Записати витрату у фінанси</div><div className="muted small">Потрапить в «Історію» з категорією авто</div></div>
            <Switch on={withTx} onChange={setWithTx} label="Записати витрату" />
          </div>
          {withTx && accounts.length > 1 && (
            <div style={{ marginTop: 10 }}>
              <Chips small value={account} onChange={setAccount} options={accounts.map(a => ({ value: a, label: a === 'Готівка' ? '💵 Готівка' : `💳 ${a}` }))} />
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}
