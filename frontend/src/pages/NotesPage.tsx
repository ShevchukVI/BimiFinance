import { Note } from '../types';

export default function NotesPage({
  noteText, setNoteText, onBlur, onClear, splitBy, setSplitBy,
}: {
  noteText: string;
  setNoteText: (s: string) => void;
  onBlur: () => void;
  onClear: () => void;
  splitBy: number;
  setSplitBy: (n: number) => void;
}) {
  const calculateSum = () => {
    let total = 0;
    let match;
    const regex = /(\d+([.,]\d{1,2})?)\s*(грн|uah|₴|\$|дол|eur|€)/gi;
    while ((match = regex.exec(noteText)) !== null) total += parseFloat(match[1].replace(',', '.'));
    return total;
  };
  const totalSum = calculateSum();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '65vh' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
        <h2 style={{ color: '#2c3e50', margin: 0, fontSize: '20px' }}>📝 Чернетка</h2>
        <button onClick={onClear} style={{ border: 'none', background: 'transparent', color: '#e74c3c', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>🗑 Очистити</button>
      </div>
      <p style={{ margin: '0 0 10px 0', color: '#7f8c8d', fontSize: '13px' }}>Додавайте <b>грн, uah, ₴, $, дол</b> біля суми, щоб вона порахувалась!</p>
      <textarea value={noteText} maxLength={2000} onChange={e => setNoteText(e.target.value)} onBlur={onBlur} placeholder={"Наприклад:\nМ'ясо 500 грн\nПиво 350.50 ₴"} style={{ flex: 1, padding: '15px', borderRadius: '16px', border: 'none', backgroundColor: '#fff', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', fontSize: '15px', resize: 'none', outline: 'none' }} />
      <div style={{ marginTop: '15px', padding: '15px', backgroundColor: '#3498db', borderRadius: '16px', color: '#fff', boxShadow: '0 4px 15px rgba(52,152,219,0.3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: splitBy > 1 ? '10px' : '0' }}>
          <span style={{ fontSize: '16px', fontWeight: 'bold' }}>Сума (Авто):</span><span style={{ fontSize: '24px', fontWeight: 'bold' }}>{totalSum.toLocaleString()} ₴</span>
        </div>
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', paddingTop: '10px', marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><span style={{ fontSize: '14px' }}>👤 Ділити на:</span><input type="number" min="1" max="50" value={splitBy} onChange={e => setSplitBy(Number(e.target.value))} style={{ width: '40px', padding: '5px', borderRadius: '6px', border: 'none', textAlign: 'center', fontWeight: 'bold', color: '#2c3e50' }} /></div>
          {splitBy > 1 && <span style={{ fontSize: '16px', fontWeight: 'bold' }}>По {(totalSum / splitBy).toFixed(2)} ₴</span>}
        </div>
      </div>
    </div>
  );
}
