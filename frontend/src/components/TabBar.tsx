import { Tab } from '../types';
import { haptic } from '../tg';

const TABS: { key: Tab; icon: string; label: string }[] = [
  { key: 'home', icon: '🏠', label: 'Головна' },
  { key: 'transactions', icon: '💸', label: 'Історія' },
  { key: 'housing', icon: '🏡', label: 'Житло' },
  { key: 'analytics', icon: '📊', label: 'Аналітика' },
  { key: 'more', icon: '☰', label: 'Ще' },
];

export default function TabBar({ activeTab, onTab, hidden = [] }: { activeTab: Tab; onTab: (t: Tab) => void; hidden?: Tab[] }) {
  return (
    <nav className="tabbar">
      {TABS.filter(t => !hidden.includes(t.key)).map(t => (
        <button key={t.key} className={`tab ${activeTab === t.key ? 'tab--on' : ''}`}
          onClick={() => { if (t.key !== activeTab) { haptic('select'); onTab(t.key); window.scrollTo(0, 0); } }}>
          <span className="tab__icon">{t.icon}</span>
          <span>{t.label}</span>
        </button>
      ))}
    </nav>
  );
}
