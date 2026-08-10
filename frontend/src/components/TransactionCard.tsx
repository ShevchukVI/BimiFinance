import { Transaction, Category, cleanCatName } from '../types';

export default function TransactionCard({ tx, categories, onClick }: { tx: Transaction; categories: Category[]; onClick: () => void }) {
  const cat = categories.find(c => c.id === tx.category_id);
  const catName = cleanCatName(cat?.name);
  return (
    <div onClick={onClick} style={{ backgroundColor: '#fff', padding: '16px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}>
      <div style={{ overflow: 'hidden', paddingRight: '10px' }}>
        <div style={{ fontWeight: 'bold', fontSize: '15px', color: '#2c3e50', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tx.title}</div>
        <div style={{ fontSize: '12px', color: '#95a5a6', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span>{catName}</span>
          {tx.user_name && <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>• 👤 {tx.user_name}</span>}
          <span>• {tx.account}</span>
          <span>• {tx.date}</span>
        </div>
      </div>
      {tx.type === 'Переказ' ? (
        <div style={{ fontWeight: 'bold', fontSize: '15px', whiteSpace: 'nowrap', color: '#7f8c8d' }}>↔️ {tx.amount} ₴</div>
      ) : (
        <div style={{ fontWeight: 'bold', fontSize: '16px', whiteSpace: 'nowrap', color: tx.type === 'Витрати' ? '#e74c3c' : '#27ae60' }}>{tx.type === 'Витрати' ? '-' : '+'}{tx.amount} ₴</div>
      )}
    </div>
  );
}
