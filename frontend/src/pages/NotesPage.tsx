import { money } from '../format';
import { Card, Chips } from '../ui';

// Чернетка: вільний текст, суми з «грн/₴/$» рахуються автоматично, можна поділити на N.
export default function NotesPage({ noteText, setNoteText, onBlur, onClear, splitBy, setSplitBy }: {
  noteText: string; setNoteText: (s: string) => void; onBlur: () => void; onClear: () => void;
  splitBy: number; setSplitBy: (n: number) => void;
}) {
  let total = 0;
  const re = /(\d+([.,]\d{1,2})?)\s*(грн|uah|₴|\$|дол|eur|€)/gi;
  let m;
  while ((m = re.exec(noteText)) !== null) total += parseFloat(m[1].replace(',', '.'));

  return (
    <div className="stack">
      <div className="muted small">Пишіть суми з <b>грн, ₴, $</b> — вони порахуються самі.</div>
      <textarea className="input" rows={10} value={noteText} maxLength={2000} onChange={e => setNoteText(e.target.value)} onBlur={onBlur}
        placeholder={"М'ясо 500 грн\nПиво 350.50 ₴"} style={{ minHeight: '40vh' }} />
      <Card>
        <div className="spread"><span className="muted">Сума</span><span className="bold tnum" style={{ fontSize: 22 }}>{money(total)}</span></div>
        <div className="spread" style={{ marginTop: 10 }}>
          <span className="muted small">Поділити на</span>
          <Chips small value={splitBy} onChange={setSplitBy} options={[1, 2, 3, 4].map(k => ({ value: k, label: k === 1 ? '—' : String(k) }))} />
        </div>
        {splitBy > 1 && <div className="spread" style={{ marginTop: 8 }}><span className="muted small">Кожному</span><b className="tnum">{money(total / splitBy)}</b></div>}
      </Card>
      {noteText && <button className="link danger" style={{ alignSelf: 'center' }} onClick={onClear}>Очистити чернетку</button>}
    </div>
  );
}
