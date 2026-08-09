import { Tab } from '../types';

export default function TabBar({ activeTab, onTab }: { activeTab: Tab; onTab: (t: Tab) => void }) {
  const tabs: { key: Tab; emoji: string; label: string }[] = [
    { key: 'home', emoji: '🏠', label: 'Головна' },
    { key: 'transactions', emoji: '💸', label: 'Історія' },
    { key: 'jars', emoji: '🏦', label: 'Цілі' },
    { key: 'notes', emoji: '📝', label: 'Чернетка' },
    { key: 'analytics', emoji: '📊', label: 'Аналітика' },
    { key: 'settings', emoji: '⚙️', label: 'Меню' },
  ];
  return (
    <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: '70px', backgroundColor: '#fff', display: 'flex', justifyContent: 'space-around', alignItems: 'center', boxShadow: '0 -2px 10px rgba(0,0,0,0.05)', paddingBottom: 'env(safe-area-inset-bottom)', zIndex: 5 }}>
      {tabs.map(t => (
        <div key={t.key} onClick={() => onTab(t.key)} style={{ textAlign: 'center', cursor: 'pointer', color: activeTab === t.key ? '#3498db' : '#95a5a6', width: `${100 / tabs.length}%` }}>
          <div style={{ fontSize: '22px' }}>{t.emoji}</div>
          <div style={{ fontSize: '10px', fontWeight: activeTab === t.key ? 'bold' : 'normal', marginTop: '4px' }}>{t.label}</div>
        </div>
      ))}
    </div>
  );
}
