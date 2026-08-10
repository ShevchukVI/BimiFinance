import { useCallback, useEffect, useState } from 'react';
import api, { setAuthToken } from './api';
import { toast } from './toast';
import Avatar from './components/Avatar';
import TabBar from './components/TabBar';
import ToastHost from './components/Toast';
import TxModal from './components/TxModal';
import InboxModal from './components/InboxModal';
import { CreateJarModal, TopUpJarModal } from './components/JarModals';
import HomePage from './pages/HomePage';
import TransactionsPage from './pages/TransactionsPage';
import JarsPage from './pages/JarsPage';
import NotesPage from './pages/NotesPage';
import AnalyticsPage from './pages/AnalyticsPage';
import SettingsPage from './pages/SettingsPage';
import type { Transaction, Category, Stats, Note, Jar, Tab, FamilyMembership, FamilyUser, Me } from './types';

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [families, setFamilies] = useState<FamilyMembership[]>([]);
  const [familyId, setFamilyId] = useState<number | null>(null);
  const [familyName, setFamilyName] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [familyUsers, setFamilyUsers] = useState<FamilyUser[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [jars, setJars] = useState<Jar[]>([]);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [tgUser, setTgUser] = useState<any>(null);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const LIMIT = 50;

  const [activeTab, setActiveTab] = useState<Tab>('home');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [viewingTx, setViewingTx] = useState<Transaction | null>(null);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [isInboxOpen, setIsInboxOpen] = useState(false);
  const [isJarModalOpen, setIsJarModalOpen] = useState(false);
  const [topupJar, setTopupJar] = useState<Jar | null>(null);
  const [noteText, setNoteText] = useState('');
  const [splitBy, setSplitBy] = useState(1);

  const triggerHaptic = (style: 'light' | 'medium' | 'heavy' | 'success') => {
    const tg = (window as any).Telegram?.WebApp;
    if (tg?.HapticFeedback) {
      style === 'success' ? tg.HapticFeedback.notificationOccurred('success') : tg.HapticFeedback.impactOccurred(style);
    }
  };
  const copyToClipboard = (text: string) => { navigator.clipboard.writeText(text); triggerHaptic('success'); toast('📋 Скопійовано'); };

  // Завантаження всіх family-scoped даних (викликається і при перемиканні сім'ї).
  const loadFamilyData = useCallback(async (fId: number) => {
    const [txRes, catRes, statsRes, usersRes, notesRes, jarsRes, famRes] = await Promise.all([
      api.get(`/families/${fId}/transactions?skip=0&limit=${LIMIT}`),
      api.get(`/families/${fId}/categories`),
      api.get(`/families/${fId}/stats`),
      api.get(`/families/${fId}/users`),
      api.get(`/families/${fId}/notes`),
      api.get(`/families/${fId}/jars`),
      api.get('/families'),
    ]);
    setTransactions(txRes.data);
    setSkip(0);
    setHasMore(txRes.data.length >= LIMIT);
    setCategories(catRes.data);
    setStats(statsRes.data);
    setFamilyUsers(usersRes.data.filter((u: any) => u.name?.trim()));
    setJars(jarsRes.data);
    setNotes(notesRes.data);
    if (notesRes.data.length > 0) setNoteText(notesRes.data[0].content);
    else setNoteText('');
    const myFam = famRes.data.find((f: any) => f.id === fId) || famRes.data[0];
    if (myFam) { setFamilyName(myFam.name); setInviteCode(myFam.invite_code); }
  }, []);

  useEffect(() => {
    const webApp = (window as any).Telegram?.WebApp;
    if (!webApp || !webApp.initData) { setAuthError("Відкрийте застосунок через Telegram-бота."); setLoading(false); return; }
    webApp.ready(); webApp.expand();
    setTgUser(webApp.initDataUnsafe?.user || null);
    (async () => {
      try {
        const authRes = await api.post('/auth/token', { init_data: webApp.initData });
        setAuthToken(authRes.data.access_token);
        const meData: Me = authRes.data.user;
        setMe(meData);
        const fId = meData.current_active_family_id;
        if (!fId) { setAuthError("Немає активної сім'ї. Натисніть /start у боті."); setLoading(false); return; }
        setFamilyId(fId);
        const famsRes = await api.get('/users/me/families');
        setFamilies(famsRes.data);
        await loadFamilyData(fId);
        setLoading(false);
      } catch (error: any) {
        const s = error?.response?.status;
        const detail = error?.response?.data?.detail;
        // Якщо бекенд повернув конкретну причину (напр. "Invalid initData signature"),
        // показуємо її — це допомагає знайти місконфіг (DEV замість PROD тощо).
        if (s === 401) setAuthError(detail && typeof detail === 'string' ? `Сесія не підтверджена: ${detail}` : "Сесія не підтверджена. Закрийте та відкрийте застосунок ще раз.");
        else if (s === 404) setAuthError("Акаунт не знайдено. Натисніть /start у боті.");
        else setAuthError("Помилка з'єднання. Спробуйте пізніше.");
        setLoading(false);
      }
    })();
  }, [loadFamilyData]);

  const refreshStats = async () => {
    if (!familyId) return;
    try { const r = await api.get(`/families/${familyId}/stats`); setStats(r.data); } catch { /**/ }
  };

  const loadMoreTransactions = async () => {
    if (!familyId) return;
    const next = skip + LIMIT;
    try {
      const r = await api.get(`/families/${familyId}/transactions?skip=${next}&limit=${LIMIT}`);
      if (r.data.length < LIMIT) setHasMore(false);
      setTransactions(prev => [...prev, ...r.data]);
      setSkip(next);
    } catch { toast('Помилка завантаження', 'err'); }
  };

  const sortTx = (list: Transaction[]) => [...list].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  const onTxSaved = (tx: Transaction) => {
    setTransactions(prev => sortTx([tx, ...prev.filter(t => t.id !== tx.id)]));
    refreshStats();
  };
  const onTxDeleted = (id: number) => {
    setTransactions(prev => prev.filter(t => t.id !== id));
    refreshStats();
  };

  const switchFamily = async (newFamilyId: number) => {
    setFamilyId(newFamilyId);
    setLoading(true);
    try {
      await loadFamilyData(newFamilyId);
      setFamilies(prev => prev.map(f => ({ ...f, is_active: f.family_id === newFamilyId })));
      const meRes = await api.get('/users/me/families'); // sync role for new family
      const active = meRes.data.find((f: FamilyMembership) => f.family_id === newFamilyId);
      if (active && me) setMe({ ...me, role: active.role, current_active_family_id: newFamilyId });
    } catch { toast('Помилка завантаження сім\'ї', 'err'); }
    setLoading(false);
  };

  const saveNote = async () => {
    if (!familyId) return;
    try {
      if (notes.length > 0) {
        await api.put(`/notes/${notes[0].id}`, { family_id: familyId, content: noteText });
      } else if (noteText.trim()) {
        const r = await api.post('/notes', { family_id: familyId, content: noteText });
        setNotes([r.data]);
      }
    } catch { /**/ }
  };
  const clearNote = () => {
    if (!window.confirm('Очистити чернетку?')) return;
    setNoteText('');
    if (notes.length > 0 && familyId) api.put(`/notes/${notes[0].id}`, { family_id: familyId, content: '' });
    triggerHaptic('success');
  };

  const onJarTopUp = async (updated: Jar, amount: number) => {
    setJars(prev => prev.map(j => j.id === updated.id ? updated : j));
    // Поповнення скарбнички = витрата з готівки (як і раніше)
    if (familyId && me) {
      try {
        await api.post('/transactions', { family_id: familyId, user_id: me.id, category_id: categories.find(c => c.name.includes('Інше'))?.id || categories[0]?.id, amount, type: 'Витрати', title: `Поповнення банки: ${updated.name}`, account: 'Готівка', date: new Date().toISOString().split('T')[0] });
        refreshStats();
      } catch { /**/ }
    }
  };

  if (authError) return <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100vh', backgroundColor: '#f5f7fa', padding: '20px', textAlign: 'center' }}><span style={{ fontSize: '60px', marginBottom: '20px' }}>🛑</span><h2 style={{ color: '#e74c3c' }}>Доступ заборонено</h2><p style={{ color: '#7f8c8d' }}>{authError}</p></div>;
  if (loading) return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', backgroundColor: '#f5f7fa' }}><h3 style={{ color: '#7f8c8d' }}>⏳ Завантаження...</h3></div>;

  return (
    <div style={{ fontFamily: 'sans-serif', backgroundColor: '#f5f7fa', minHeight: '100vh', paddingBottom: '80px', position: 'relative' }}>
      <ToastHost />
      <div style={{ backgroundColor: '#fff', padding: '20px', borderBottomLeftRadius: '24px', borderBottomRightRadius: '24px', boxShadow: '0 4px 15px rgba(0,0,0,0.03)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <Avatar name={tgUser?.first_name || 'User'} url={tgUser?.photo_url} />
          <div>
            <h3 style={{ margin: 0, color: '#2c3e50', fontSize: '18px' }}>Привіт, {tgUser?.first_name || 'Гість'}! 👋</h3>
            <p style={{ margin: 0, color: '#95a5a6', fontSize: '13px', marginTop: '2px' }}>{familyName || 'Твоя фінансова панель'}</p>
          </div>
        </div>
      </div>

      <div style={{ padding: '20px' }}>
        {activeTab === 'home' && (
          <HomePage stats={stats} transactions={transactions} categories={categories}
            onOpenInbox={() => setIsInboxOpen(true)} onSeeAll={() => setActiveTab('transactions')}
            onAdd={() => setIsAddModalOpen(true)} onView={setViewingTx} />
        )}

        {activeTab === 'transactions' && <>
          <h2 style={{ color: '#2c3e50', marginBottom: '15px', fontSize: '20px' }}>💸 Останні транзакції</h2>
          <TransactionsPage transactions={transactions} categories={categories} hasMore={hasMore}
            onLoadMore={loadMoreTransactions} onView={setViewingTx} onAdd={() => setIsAddModalOpen(true)} />
        </>}

        {activeTab === 'jars' && <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
            <h2 style={{ color: '#2c3e50', margin: 0, fontSize: '20px' }}>🏦 Скарбнички</h2>
            <button onClick={() => setIsJarModalOpen(true)} style={{ border: 'none', background: 'transparent', color: '#3498db', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>+ Створити</button>
          </div>
          <JarsPage jars={jars} onTopUp={(id) => setTopupJar(jars.find(j => j.id === id) || null)} onCreate={() => setIsJarModalOpen(true)} />
        </>}

        {activeTab === 'notes' && (
          <NotesPage noteText={noteText} setNoteText={setNoteText} onBlur={saveNote} onClear={clearNote} splitBy={splitBy} setSplitBy={setSplitBy} />
        )}

        {activeTab === 'analytics' && stats && <AnalyticsPage stats={stats} />}
        {activeTab === 'analytics' && !stats && (
          <div style={{ textAlign: 'center', padding: '40px 20px', backgroundColor: '#fff', borderRadius: '16px' }}>
            <p style={{ color: '#7f8c8d' }}>Немає даних для аналітики.</p>
          </div>
        )}

        {activeTab === 'settings' && me && familyId && (
          <SettingsPage
            me={{ id: me.id, name: me.name, role: me.role || 'member' }}
            families={families} familyId={familyId} familyName={familyName} inviteCode={inviteCode}
            familyUsers={familyUsers} hasMonoToken={me.has_mono_token}
            onSwitchFamily={switchFamily}
            onInviteRegenerated={setInviteCode}
            onMemberRemoved={(uid) => setFamilyUsers(prev => prev.filter(u => u.id !== uid))}
            onTokenSaved={() => setMe({ ...me, has_mono_token: true })}
            copyToClipboard={copyToClipboard}
          />
        )}
      </div>

      {['home', 'transactions', 'jars'].includes(activeTab) && (
        <div onClick={activeTab === 'jars' ? (() => setIsJarModalOpen(true)) : (() => setIsAddModalOpen(true))}
          style={{ position: 'fixed', bottom: '90px', right: '20px', width: '60px', height: '60px', backgroundColor: '#3498db', color: '#fff', borderRadius: '50%', display: 'flex', justifyContent: 'center', alignItems: 'center', fontSize: '32px', boxShadow: '0 4px 15px rgba(52,152,219,0.4)', cursor: 'pointer', zIndex: 10 }}>+</div>
      )}

      <TabBar activeTab={activeTab} onTab={setActiveTab} />

      {isJarModalOpen && familyId && (
        <CreateJarModal familyId={familyId} onClose={() => setIsJarModalOpen(false)} onCreated={(j) => setJars(prev => [...prev, j])} />
      )}
      {topupJar && (
        <TopUpJarModal jar={topupJar} onClose={() => setTopupJar(null)} onToppedUp={onJarTopUp} />
      )}
      {isInboxOpen && familyId && (
        <InboxModal familyId={familyId} categories={categories} onClose={() => setIsInboxOpen(false)} onDone={refreshStats} />
      )}

      {viewingTx && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 100, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
          <div style={{ backgroundColor: '#fff', borderTopLeftRadius: '24px', borderTopRightRadius: '24px', padding: '25px', paddingBottom: 'calc(25px + env(safe-area-inset-bottom))' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#2c3e50' }}>Деталі транзакції</h3>
              <button onClick={() => setViewingTx(null)} style={{ border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6', cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <div style={{ fontSize: '32px', fontWeight: 'bold', color: viewingTx.type === 'Витрати' ? '#e74c3c' : '#27ae60' }}>{viewingTx.type === 'Витрати' ? '-' : '+'}{viewingTx.amount} ₴</div>
              <div style={{ color: '#7f8c8d', marginTop: '5px' }}>{categories.find(c => c.id === viewingTx.category_id)?.name || 'Інше'}</div>
            </div>
            <div style={{ backgroundColor: '#f8f9fa', padding: '15px', borderRadius: '12px', marginBottom: '20px' }}>
              <p style={{ margin: '0 0 10px 0', color: '#2c3e50', fontSize: '15px', wordBreak: 'break-word' }}><b>Опис:</b> {viewingTx.title}</p>
              <p style={{ margin: '0 0 5px 0', color: '#7f8c8d', fontSize: '13px' }}><b>Рахунок:</b> {viewingTx.account}</p>
              <p style={{ margin: '0', color: '#7f8c8d', fontSize: '13px' }}><b>Дата:</b> {viewingTx.date}</p>
            </div>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button onClick={() => copyToClipboard(`${viewingTx.title} - ${viewingTx.amount}₴`)} style={{ flex: 1, padding: '15px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '15px', cursor: 'pointer' }}>📋 Копіювати</button>
              <button onClick={() => { setEditingTx(viewingTx); setViewingTx(null); }} style={{ flex: 1, padding: '15px', backgroundColor: '#3498db', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '15px', cursor: 'pointer' }}>✏️ Редагувати</button>
            </div>
          </div>
        </div>
      )}

      {(isAddModalOpen || editingTx) && familyId && me && (
        <TxModal
          editingTx={editingTx} categories={categories} familyId={familyId} dbUserId={me.id}
          onClose={() => { setIsAddModalOpen(false); setEditingTx(null); }}
          onSaved={onTxSaved} onDeleted={onTxDeleted} haptic={triggerHaptic}
        />
      )}
    </div>
  );
}
