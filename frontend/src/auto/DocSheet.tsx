import { useRef, useState } from 'react';
import { toast } from '../toast';
import { dmy, money, parseNum, plural, todayIso } from '../format';
import { confirmAsync, haptic, openUrl } from '../tg';
import { Button, Card, Chips, Field, Row, Sheet, Switch } from '../ui';
import { errText } from '../housing/api';
import { autoApi } from './api';
import { DOC_KINDS, DocKind, VDoc } from './types';

const yearAfter = (iso: string) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setFullYear(d.getFullYear() + 1); d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
};

export const docWhen = (d: VDoc) => {
  if (!d.end_date || d.days_left === null) return 'без дати закінчення';
  if (d.days_left < 0) return `закінчився ${dmy(d.end_date)}`;
  if (d.days_left === 0) return 'закінчується сьогодні';
  return `до ${dmy(d.end_date)} · ще ${d.days_left} ${plural(d.days_left, 'день', 'дні', 'днів')}`;
};

// Поліс: тип, страховик, номер, дати, ціна (+ витрата у фінанси), PDF/фото і посилання на онлайн-перегляд.
export default function DocSheet({ familyId, vehicleId, doc, accounts, onClose, onSaved }: {
  familyId: number; vehicleId: number; doc?: VDoc; accounts: string[]; onClose: () => void; onSaved: (financeToo: boolean) => void;
}) {
  const [kind, setKind] = useState<DocKind>(doc?.kind || 'osago');
  const [company, setCompany] = useState(doc?.company || '');
  const [number, setNumber] = useState(doc?.number || '');
  const [start, setStart] = useState(doc?.start_date || todayIso());
  const [end, setEnd] = useState(doc?.end_date || yearAfter(todayIso()));
  const [endTouched, setEndTouched] = useState(!!doc);
  const [amount, setAmount] = useState(doc?.amount ? String(doc.amount).replace('.', ',') : '');
  const [url, setUrl] = useState(doc?.url || '');
  const [note, setNote] = useState(doc?.note || '');
  const [file, setFile] = useState<File | null>(null);
  const [hasFile, setHasFile] = useState(!!doc?.has_file);
  const [withTx, setWithTx] = useState(!doc?.log_id);
  const [account, setAccount] = useState(accounts[0] || 'Готівка');
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const A = parseNum(amount);
  const urlBad = !!url.trim() && !/^https?:\/\//i.test(url.trim());

  const pickFile = (f: File | undefined) => {
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) { toast('Файл більший за 10 МБ', 'err'); return; }
    setFile(f);
  };
  const save = async () => {
    if (urlBad) return;
    setBusy(true);
    const body = { vehicle_id: vehicleId, kind, company: company.trim(), number: number.trim(), start_date: start || null,
      end_date: end || null, amount: A > 0 ? A : null, url: url.trim(), note: note.trim(),
      create_expense: withTx && A > 0 && !doc?.log_id, account };
    try {
      const saved = doc ? await autoApi.updateDoc(familyId, doc.id, body) : await autoApi.createDoc(familyId, body);
      if (file) await autoApi.uploadFile(familyId, saved.id, file);
      haptic('success');
      toast(doc ? 'Збережено' : 'Поліс додано');
      onSaved(body.create_expense);
      onClose();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const remove = async () => {
    if (!doc || !(await confirmAsync('Видалити поліс? Оплата лишиться в журналі й фінансах.'))) return;
    try { await autoApi.deleteDoc(familyId, doc.id); toast('Видалено'); onSaved(false); onClose(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const openFile = async () => {
    if (!doc) return;
    try { openUrl(await autoApi.fileUrl(familyId, doc.id)); } catch (e) { toast(errText(e), 'err'); }
  };
  const dropFile = async () => {
    if (!doc || !(await confirmAsync('Видалити файл поліса?'))) return;
    try { await autoApi.deleteFile(familyId, doc.id); setHasFile(false); toast('Файл видалено'); onSaved(false); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <Sheet title={doc ? DOC_KINDS.find(k => k.value === kind)?.label || 'Поліс' : 'Новий поліс'} icon={DOC_KINDS.find(k => k.value === kind)?.icon}
      onClose={onClose} confirmClose
      footer={<>
        <Button onClick={save} disabled={urlBad} busy={busy}>{doc ? 'Зберегти' : 'Додати поліс'}</Button>
        {doc && <Button variant="danger" onClick={remove}>Видалити</Button>}
      </>}>
      {doc && (doc.has_file || doc.url) && (
        <div className="grid2">
          {hasFile && <Button variant="secondary" onClick={openFile}>📄 Відкрити поліс</Button>}
          {doc.url && <Button variant="secondary" onClick={() => openUrl(doc.url)}>🌐 Онлайн</Button>}
        </div>
      )}
      <Chips scroll small value={kind} onChange={setKind} options={DOC_KINDS.map(k => ({ value: k.value, label: `${k.icon} ${k.short}` }))} />
      <div className="grid2">
        <Field label="Страховик"><input className="input" placeholder="ARX, ТАС, Уніка…" value={company} onChange={e => setCompany(e.target.value)} /></Field>
        <Field label="Номер поліса"><input className="input" placeholder="необов'язково" value={number} onChange={e => setNumber(e.target.value)} /></Field>
      </div>
      <div className="grid2">
        <Field label="Діє з"><input className="input" type="date" value={start} onChange={e => { setStart(e.target.value); if (!endTouched && e.target.value) setEnd(yearAfter(e.target.value)); }} /></Field>
        <Field label="Діє до" hint={!endTouched ? 'рік — змініть, якщо інакше' : undefined}>
          <input className="input" type="date" value={end} min={start} onChange={e => { setEnd(e.target.value); setEndTouched(true); }} />
        </Field>
      </div>
      <Field label="Вартість"><input className="input tnum" inputMode="decimal" placeholder="0 ₴" value={amount} onChange={e => setAmount(e.target.value)} /></Field>

      <Field label="Файл поліса" hint="PDF або фото, до 10 МБ. Зберігається в Bimi, відкривається лише з застосунку.">
        <input ref={input} type="file" accept="application/pdf,image/*" hidden onChange={e => pickFile(e.target.files?.[0])} />
        {file || hasFile ? (
          <Card flush>
            <Row icon="📄" title={file ? file.name : doc?.file_name || 'Поліс'} sub={file ? `${file.size < 1024 ? '< 1' : Math.round(file.size / 1024)} КБ · завантажиться при збереженні` : 'Завантажено'}
              end={<div className="hstack" style={{ gap: 6 }}>
                <Button size="sm" variant="secondary" onClick={() => input.current?.click()}>Замінити</Button>
                {!file && <Button size="sm" variant="secondary" onClick={dropFile}>✕</Button>}
              </div>} />
          </Card>
        ) : (
          <Button variant="secondary" onClick={() => input.current?.click()}>📎 Додати PDF або фото</Button>
        )}
      </Field>
      <Field label="Посилання на онлайн-перегляд" hint="Сторінка поліса у страховика чи на policy.mtsbu.ua" error={urlBad ? 'Має починатися з https://' : undefined}>
        <input className="input" inputMode="url" placeholder="https://…" value={url} onChange={e => setUrl(e.target.value)} />
      </Field>
      <Field label="Примітка"><input className="input" placeholder="франшиза, що покриває… необов'язково" value={note} onChange={e => setNote(e.target.value)} /></Field>

      {doc?.log_id ? (
        <div className="muted small">🔗 Оплата є в журналі{doc.amount ? ` · ${money(doc.amount, 'UAH', 0)}` : ''}</div>
      ) : A > 0 && (
        <div className="card">
          <div className="spread">
            <div><div className="bold">Записати оплату</div><div className="muted small">У журнал авто й в «Історію»</div></div>
            <Switch on={withTx} onChange={setWithTx} label="Записати оплату" />
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
