import { Transaction, Category } from '../types';

export default function TransactionCard({ tx, categories, onClick }: { tx: Transaction; categories: Category[]; onClick: () => void }) {
  const cat = categories.find(c => c.id === tx.category_id);
  const cleanCatName = cat ? cat.name.replace(/^[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ0-9]+/, '').trim() : 'Інше';
  return (
    <div onClick={onClick} style={{ backgroundColor: '#fff', padding: '16px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}>
      <div style={{ overflow: 'hidden', paddingRight: '10px' }}>
        <div style={{ fontWeight: 'bold', fontSize: '15px', color: '#2c3e50', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tx.title}</div>
        <div style={{ fontSize: '12px', color: '#95a5a6', marginTop: '4px' }}>{cleanCatName} • {tx.account} • {tx.date}</div>
      </div>
      <div style={{ fontWeight: 'bold', fontSize: '16px', whiteSpace: 'nowrap', color: tx.type === 'Витрати' ? '#e74c3c' : '#27ae60' }}>{tx.type === 'Витрати' ? '-' : '+'}{tx.amount} ₴</div>
    </div>
  );
}
