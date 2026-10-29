import { useCallback, useEffect, useRef, useState } from 'react';
import api, { setAuthToken } from './api';
import { toast } from './toast';
import { copyText, haptic, startParam } from './tg';
import Avatar from './components/Avatar';
import TabBar from './components/TabBar';
import ToastHost from './components/Toast';
import TxModal from './components/TxModal';
import TxDetailsSheet from './components/TxDetailsSheet';
import InboxModal from './components/InboxModal';
import { CreateJarModal, TopUpJarModal } from './components/JarModals';
import HomePage from './pages/HomePage';
import TransactionsPage from './pages/TransactionsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import MorePage, { MoreScreen } from './pages/MorePage';
import LinkSheet from './payments/LinkSheet';
import { payApi, Upcoming } from './payments/api';
import type { ObDraft } from './payments/ObligationForm';
import { anApi, Budgets, BudgetRow } from './analytics/api';
import EnvelopeSheet from './analytics/EnvelopeSheet';
import BudgetsSheet from './analytics/BudgetsSheet';
import JarHistoryModal from './components/JarHistoryModal';
import HousingPage, { HousingAction } from './housing/HousingPage';
import { housingApi } from './housing/api';
import type { Overview } from './housing/types';
import AutoPage, { AutoAction } from './auto/AutoPage';
import { autoApi } from './auto/api';
import type { AutoOverview } from './auto/types';
import type { Transaction, Category, Stats, Note, Jar, Tab, FamilyMembership, FamilyUser, Me, BankUserBalances } from './types';
import { Spinner } from './ui';

const LIMIT = 50;
const TABS: Tab[] = ['home', 'transactions', 'housing', 'auto', 'analytics', 'more'];

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
  const [bankBalances, setBankBalances] = useState<BankUserBalances[]>([]);
  const [housing, setHousing] = useState<Overview | null>(null);
  const [auto, setAuto] = useState<AutoOverview | null>(null);
  const [autoAction, setAutoAction] = useState<AutoAction>(null);
  const [upcoming, setUpcoming] = useState<Upcoming[]>([]);
  const [budgets, setBudgets] = useState<Budgets | null>(null);
  const [envelope, setEnvelope] = useState<BudgetRow | null>(null);
  const [editBudgets, setEditBudgets] = useState(false);
  const [historyJar, setHistoryJar] = useState<Jar | null>(null);
  const [jarsSyncing, setJarsSyncing] = useState(false);
  const [linkTx, setLinkTx] = useState<Transaction | null>(null);
  const [paymentsDraft, setPaymentsDraft] = useState<ObDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [tgUser, setTgUser] = useState<any>(null);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const initial = startParam();
  const [activeTab, setActiveTab] = useState<Tab>(TABS.includes(initial as Tab) ? (initial as Tab) : initial === 'readings' ? 'housing' : initial === 'payments' ? 'more' : 'home');
  const [housingAction, setHousingAction] = useState<HousingAction>(initial === 'readings' ? 'readings' : null);
  const [moreScreen, setMoreScreen] = useState<{ screen: MoreScreen; key: number }>({ screen: initial === 'payments' ? 'payments' : null, key: 0 });
  const [addType, setAddType] = useState<'Витрати' | 'Поповнення' | null>(null);
  const [viewingTx, setViewingTx] = useState<Transaction | null>(null);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [isInboxOpen, setIsInboxOpen] = useState(false);
  const [isJarModalOpen, setIsJarModalOpen] = useState(false);
  const [topupJar, setTopupJar] = useState<Jar | null>(null);
  const [noteText, setNoteText] = useState('');
  const [splitBy, setSplitBy] = useState(1);

  const famRef = useRef<number | null>(null);  // ignore late responses of a previously active family
  const loadingMore = useRef(false);
  const copyToClipboard = (text: string) => { copyText(text); haptic('success'); toast('Скопійовано'); };

  // Усі family-scoped дані (і при перемиканні сім'ї). «Житло» — не блокує решту.
  const loadFamilyData = useCallback(async (fId: number) => {
    famRef.current = fId;
    const [txRes, catRes, statsRes, usersRes, notesRes, jarsRes, famRes, bankRes] = await Promise.all([
      api.get(`/families/${fId}/transactions?skip=0&limit=${LIMIT}`),
      api.get(`/families/${fId}/categories`),
      api.get(`/families/${fId}/stats`),
      api.get(`/families/${fId}/users`),
      api.get(`/families/${fId}/notes`),
      api.get(`/families/${fId}/jars`),
      api.get('/families'),
      api.get(`/banking/families/${fId}/bank-balances`),
    ]);
    setTransactions(txRes.data);
    setSkip(0);
    setHasMore(txRes.data.length >= LIMIT);
    setCategories(catRes.data);
    setStats(statsRes.data);
    setFamilyUsers(usersRes.data.filter((u: any) => u.name?.trim()));
    setJars(jarsRes.data);
    setNotes(notesRes.data);
    setBankBalances(bankRes.data || []);
    setNoteText(notesRes.data.length > 0 ? notesRes.data[0].content : '');
    const myFam = famRes.data.find((f: any) => f.id === fId) || famRes.data[0];
    if (myFam) { setFamilyName(myFam.name); setInviteCode(myFam.invite_code); }
    setHousing(null);
    setUpcoming([]);
    housingApi.overview(fId).then(o => { if (famRef.current === fId) setHousing(o); }).catch(() => { /* housing is optional */ });
    setAuto(null);
    autoApi.overview(fId).then(o => { if (famRef.current === fId) setAuto(o); }).catch(() => { /* auto is optional */ });
    payApi.upcoming(fId, 10).then(u => { if (famRef.current === fId) setUpcoming(u); }).catch(() => { /**/ });
    setBudgets(null);
    anApi.budgets(fId).then(b => { if (famRef.current === fId) setBudgets(b); }).catch(() => { /**/ });
    if ((bankRes.data || []).length) {
      // Monobank jars → goals; transfers to them stop counting as spending
      api.post(`/families/${fId}/jars/sync`).then(r => {
        if (famRef.current !== fId) return;
        setJars(r.data);
        api.get(`/families/${fId}/transactions?skip=0&limit=${LIMIT}`).then(t => { if (famRef.current === fId) setTransactions(t.data); }).catch(() => { /**/ });
      }).catch(() => { /* bank unavailable — keep cached goals */ });
    }
  }, []);

  useEffect(() => {
    const webApp = (window as any).Telegram?.WebApp;
    if (!webApp || !webApp.initData) { setAuthError('Відкрийте застосунок через Telegram-бота.'); setLoading(false); return; }
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
        setFamilies((await api.get('/users/me/families')).data);
        await loadFamilyData(fId);
        setLoading(false);
      } catch (error: any) {
        const s = error?.response?.status;
        const detail = error?.response?.data?.detail;
        if (s === 401) setAuthError(detail && typeof detail === 'string' ? `Сесія не підтверджена: ${detail}` : 'Сесія не підтверджена. Закрийте та відкрийте застосунок ще раз.');
        else if (s === 404) setAuthError('Акаунт не знайдено. Натисніть /start у боті.');
        else setAuthError("Помилка з'єднання. Спробуйте пізніше.");
        setLoading(false);
      }
    })();
  }, [loadFamilyData]);

  const refreshStats = async () => {
    if (!familyId) return;
    try { setStats((await api.get(`/families/${familyId}/stats`)).data); } catch { /**/ }
    const f = familyId;
    anApi.budgets(f).then(b => { if (famRef.current === f) setBudgets(b); }).catch(() => { /**/ });
  };
  const refreshTransactions = async () => {
    if (!familyId) return;
    try {
      const r = await api.get(`/families/${familyId}/transactions?skip=0&limit=${LIMIT}`);
      setTransactions(r.data); setSkip(0); setHasMore(r.data.length >= LIMIT);
    } catch { /**/ }
  };

  const loadMoreTransactions = async () => {
    if (!familyId || loadingMore.current) return;
    loadingMore.current = true;
    const next = skip + LIMIT;
    try {
      const r = await api.get(`/families/${familyId}/transactions?skip=${next}&limit=${LIMIT}`);
      if (r.data.length < LIMIT) setHasMore(false);
      setTransactions(prev => { const ids = new Set(prev.map(t => t.id)); return [...prev, ...r.data.filter((t: Transaction) => !ids.has(t.id))]; });
      setSkip(next);
    } catch { toast('Помилка завантаження', 'err'); }
    loadingMore.current = false;
  };

  const sortTx = (list: Transaction[]) => [...list].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
  const onTxSaved = (tx: Transaction) => { setTransactions(prev => sortTx([tx, ...prev.filter(t => t.id !== tx.id)])); refreshStats(); };
  const onTxDeleted = (id: number) => { setTransactions(prev => prev.filter(t => t.id !== id)); refreshStats(); };

  // Після категоризації в Inbox лишаємось у ньому (наступна операція — одним дотиком), фон оновлюємо.
  const handleCategorized = async (tx: Transaction) => {
    setTransactions(prev => sortTx([tx, ...prev.filter(t => t.id !== tx.id)]));
    refreshStats();
  };

  const switchFamily = async (newFamilyId: number) => {
    setLoading(true);
    setPaymentsDraft(null);
    setMoreScreen(s => ({ screen: null, key: s.key + 1 }));
    try {
      await loadFamilyData(newFamilyId);
      setFamilyId(newFamilyId);
      setFamilies(prev => prev.map(f => ({ ...f, is_active: f.family_id === newFamilyId })));
      const active = (await api.get('/users/me/families')).data.find((f: FamilyMembership) => f.family_id === newFamilyId);
      if (active && me) setMe({ ...me, role: active.role, current_active_family_id: newFamilyId });
    } catch {
      // the server already switched the active family — never keep writing into the old one
      toast('Помилка завантаження сім\'ї', 'err');
      window.location.reload();
      return;
    }
    setLoading(false);
  };

  const handleMemberRoleChange = (userId: number, role: 'admin' | 'member') => {
    setFamilyUsers(prev => prev.map(u => u.id === userId ? { ...u, role } : u));
    if (userId === me?.id && me) setMe({ ...me, role });
  };

  const handleLeaveFamily = async () => {
    try {
      const remaining = (await api.get('/users/me/families')).data;
      if (remaining.length > 0) {
        const next = remaining[0];
        await api.patch('/users/me/active-family', { family_id: next.family_id });
        await switchFamily(next.family_id);
        setFamilies(remaining.map((f: FamilyMembership) => ({ ...f, is_active: f.family_id === next.family_id })));
      } else { setMe(null); setFamilyId(null); setFamilyUsers([]); }
    } catch { toast('Не вдалося перейти після виходу', 'err'); window.location.reload(); }
  };

  const saveNote = async () => {
    if (!familyId) return;
    try {
      if (notes.length > 0) await api.put(`/notes/${notes[0].id}`, { family_id: familyId, content: noteText });
      else if (noteText.trim()) setNotes([(await api.post('/notes', { family_id: familyId, content: noteText })).data]);
    } catch { /**/ }
  };
  const clearNote = () => {
    setNoteText('');
    if (notes.length > 0 && familyId) api.put(`/notes/${notes[0].id}`, { family_id: familyId, content: '' });
    haptic('success');
  };

  // Скарбничка: бекенд сам створює jar-транзакцію (готівка ↔ скарбничка). Раніше тут
  // додатково писалась «Витрата», і поповнення списувалось з готівки двічі.
  const onJarTopUp = (updated: Jar) => { setJars(prev => prev.map(j => j.id === updated.id ? updated : j)); refreshStats(); };

  const openMore = (screen: MoreScreen) => { setMoreScreen(s => ({ screen, key: s.key + 1 })); setActiveTab('more'); };
  const openJars = () => openMore('jars');
  const syncJars = async () => {
    if (!familyId) return;
    setJarsSyncing(true);
    try { setJars((await api.post(`/families/${familyId}/jars/sync`)).data); toast('Банки оновлено'); refreshTransactions(); refreshStats(); }
    catch { toast('Monobank не відповів, спробуйте за хвилину', 'err'); }
    setJarsSyncing(false);
  };
  const refreshUpcoming = () => { const f = familyId; if (f) payApi.upcoming(f, 10).then(u => { if (famRef.current === f) setUpcoming(u); }).catch(() => { /**/ }); };
  const setHousingAndUpcoming = (o: Overview) => { setHousing(o); refreshUpcoming(); };
  const openPayments = (draft: ObDraft | null = null) => { setPaymentsDraft(draft); openMore('payments'); };
  const accounts = ['Готівка', ...(bankBalances.find(b => b.user_id === me?.id)?.accounts.map(a => a.name) || [])];
  const housingOff = housing?.profile?.mode === 'off';
  // personal bottom bar: a section shows when the family uses it, unless this user hid it in «Ще» (or turned it on)
  const tabPrefs = me?.tab_prefs || {};
  const showTab = (t: 'housing' | 'auto', used: boolean) => tabPrefs[t] ?? used;
  const hideHousing = !showTab('housing', !housingOff);
  const hideAuto = !showTab('auto', !!auto && auto.vehicles.length > 0);
  const setTabPref = async (tab: 'housing' | 'auto', show: boolean) => {
    if (!me) return;
    setMe({ ...me, tab_prefs: { ...tabPrefs, [tab]: show } });
    try { const r = await api.put('/users/me/tabs', { tab, show }); setMe(m => m && { ...m, tab_prefs: r.data.tab_prefs }); }
    catch { toast('Не вдалося зберегти', 'err'); setMe(m => m && { ...m, tab_prefs: tabPrefs }); }
  };
  const refreshAuto = () => { const f = familyId; if (f) autoApi.overview(f).then(o => { if (famRef.current === f) setAuto(o); }).catch(() => { /**/ }); };

  if (authError) return <div className="screen-center"><div style={{ fontSize: 56 }}>🛑</div><h2 className="danger" style={{ margin: 0 }}>Доступ заборонено</h2><p className="muted">{authError}</p></div>;
  if (loading) return <div className="screen-center"><Spinner label="Завантаження…" /></div>;

  return (
    <div className={`app ${activeTab === 'transactions' ? 'app--fab' : ''}`}>
      <ToastHost />
      {activeTab === 'home' && (
        <div className="topbar">
          <Avatar name={tgUser?.first_name || 'User'} url={tgUser?.photo_url} size={38} />
          <div className="grow">
            <div className="topbar__title">Привіт, {tgUser?.first_name || 'друже'}!</div>
            <div className="topbar__sub">{familyName || 'Твоя фінансова панель'}</div>
          </div>
        </div>
      )}

      {activeTab === 'home' && (
        <HomePage stats={stats} transactions={transactions} categories={categories} bankBalances={bankBalances} jars={jars} housing={housing}
          auto={hideAuto ? null : auto} onAuto={() => { setActiveTab('auto'); refreshAuto(); }}
          upcoming={upcoming} budgets={budgets} onBudgets={() => setEditBudgets(true)} onEnvelope={setEnvelope} onUpcoming={u => { if (u && u.kind === 'housing') { setHousingAction({ pay: u.id }); setActiveTab('housing'); } else openPayments(); }}
          onOpenInbox={() => setIsInboxOpen(true)} onSeeAll={() => setActiveTab('transactions')}
          onAdd={t => setAddType(t || 'Витрати')} onView={setViewingTx}
          onHousing={() => setActiveTab('housing')} onReadings={() => { setHousingAction('readings'); setActiveTab('housing'); }}
          onJar={j => (j.mono_jar_id ? setHistoryJar(j) : setTopupJar(j))} onJars={openJars} />
      )}
      {activeTab === 'transactions' && (
        <TransactionsPage transactions={transactions} categories={categories} hasMore={hasMore}
          onLoadMore={loadMoreTransactions} onView={setViewingTx} onAdd={() => setAddType('Витрати')} />
      )}
      {activeTab === 'housing' && familyId && (
        <HousingPage familyId={familyId} overview={housing} setOverview={setHousingAndUpcoming} accounts={accounts}
          onFinanceChanged={() => { refreshTransactions(); refreshStats(); refreshUpcoming(); }}
          action={housingAction} onActionDone={() => setHousingAction(null)} />
      )}
      {activeTab === 'auto' && familyId && (
        <AutoPage familyId={familyId} overview={auto} setOverview={setAuto} accounts={accounts} familyUsers={familyUsers}
          onFinanceChanged={() => { refreshTransactions(); refreshStats(); }}
          action={autoAction} onActionDone={() => setAutoAction(null)} />
      )}
      {activeTab === 'analytics' && familyId && <AnalyticsPage familyId={familyId} categories={categories} onView={setViewingTx} onBudgetsChanged={setBudgets} />}
      {activeTab === 'more' && me && familyId && (
        <MorePage key={moreScreen.key} initialScreen={moreScreen.screen}
          me={{ id: me.id, name: me.name, role: me.role || 'member' }}
          families={families} familyId={familyId} familyName={familyName} inviteCode={inviteCode}
          familyUsers={familyUsers} hasMonoToken={me.has_mono_token}
          jars={jars} onJarTopUp={setTopupJar} onJarCreate={() => setIsJarModalOpen(true)} onJarsSync={bankBalances.length ? syncJars : undefined} jarsSyncing={jarsSyncing}
          noteText={noteText} setNoteText={setNoteText} onNoteBlur={saveNote} onNoteClear={clearNote}
          splitBy={splitBy} setSplitBy={setSplitBy}
          housingEnabled={!housingOff && !!housing?.profile}
          categories={categories} paymentsDraft={paymentsDraft} onPaymentsChanged={() => { refreshUpcoming(); refreshTransactions(); }}
          onHousingSettings={() => { setHousingAction('settings'); setActiveTab('housing'); }}
          autoSummary={auto?.vehicles.length ? auto.vehicles.map(v => `${v.icon} ${v.name}`).join(', ') : null} onAuto={() => setActiveTab('auto')}
          tabs={{ housing: !hideHousing, auto: !hideAuto }} onTab={setTabPref}
          onSwitchFamily={switchFamily} onInviteRegenerated={setInviteCode}
          onMemberRemoved={uid => setFamilyUsers(prev => prev.filter(u => u.id !== uid))}
          onMemberRoleChange={handleMemberRoleChange} onLeaveFamily={handleLeaveFamily}
          onTokenSaved={() => setMe({ ...me, has_mono_token: true })} copyToClipboard={copyToClipboard} />
      )}

      {activeTab === 'transactions' && (
        <button className="fab" aria-label="Додати операцію" onClick={() => { haptic('medium'); setAddType('Витрати'); }}>+</button>
      )}

      <TabBar activeTab={activeTab} onTab={t => { setActiveTab(t); if (t === 'auto') refreshAuto(); if (t === 'more') { setPaymentsDraft(null); setMoreScreen(s => ({ screen: null, key: s.key + 1 })); } }}
        hidden={[...(hideHousing && activeTab !== 'housing' ? ['housing' as Tab] : []), ...(hideAuto && activeTab !== 'auto' ? ['auto' as Tab] : [])]} />

      {isJarModalOpen && familyId && <CreateJarModal familyId={familyId} onClose={() => setIsJarModalOpen(false)} onCreated={j => setJars(prev => [...prev, j])} />}
      {envelope && familyId && budgets && <EnvelopeSheet familyId={familyId} env={envelope} categories={categories} daysLeft={budgets.days_left}
        onClose={() => setEnvelope(null)} onView={setViewingTx} onEdit={() => { setEnvelope(null); setEditBudgets(true); }} />}
      {editBudgets && familyId && <BudgetsSheet familyId={familyId} categories={categories} budgets={budgets} onClose={() => setEditBudgets(false)} onSaved={setBudgets} />}
      {historyJar && familyId && <JarHistoryModal jar={historyJar} familyId={familyId} onClose={() => setHistoryJar(null)} />}
      {topupJar && <TopUpJarModal jar={topupJar} onClose={() => setTopupJar(null)} onToppedUp={onJarTopUp} />}
      {isInboxOpen && familyId && <InboxModal familyId={familyId} categories={categories} onClose={() => setIsInboxOpen(false)} onCategorized={handleCategorized}
        onBulk={() => { refreshTransactions(); refreshStats(); refreshAuto(); }} />}
      {viewingTx && familyId && <TxDetailsSheet tx={viewingTx} categories={categories} familyId={familyId} onClose={() => setViewingTx(null)}
        onEdit={() => { setEditingTx(viewingTx); setViewingTx(null); }} onCopy={copyToClipboard}
        onLink={() => { setLinkTx(viewingTx); setViewingTx(null); }} />}
      {linkTx && familyId && <LinkSheet familyId={familyId} tx={linkTx} onClose={() => setLinkTx(null)}
        onChanged={() => { refreshTransactions(); refreshStats(); refreshUpcoming(); refreshAuto(); housingApi.overview(familyId).then(setHousing).catch(() => { /**/ }); }}
        onCreate={draft => { setLinkTx(null); openPayments(draft); }}
        onVehicle={vehicleId => { setAutoAction({ txId: linkTx.id, vehicleId }); setLinkTx(null); setActiveTab('auto'); }} />}
      {(addType || editingTx) && familyId && me && (
        <TxModal editingTx={editingTx} categories={categories} familyId={familyId} dbUserId={me.id} accounts={accounts}
          initialType={addType || 'Витрати'}
          onClose={() => { setAddType(null); setEditingTx(null); }} onSaved={onTxSaved} onDeleted={onTxDeleted} />
      )}
    </div>
  );
}
