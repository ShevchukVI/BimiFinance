import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import api, { setAuthToken } from './api';

interface Transaction { id: number; amount: number; type: string; title: string; account: string; date: string; category_id: number; note: string; }
interface Category { id: number; name: string; icon: string; type: string; }
interface Stats { income: number; expense: number; balance: number; top_categories: { name: string; amount: number }[]; }
interface Note { id: number; content: string; }
interface Jar { id: number; name: string; balance: number; goal: number; }

const COLORS = ['#3498db', '#e74c3c', '#2ecc71', '#f1c40f', '#9b59b6', '#34495e', '#e67e22', '#1abc9c', '#f39c12', '#d35400'];

const Avatar = ({ name, url }: { name: string, url?: string }) => {
  if (url) return <img src={url} alt="avatar" style={{width: '40px', height: '40px', borderRadius: '50%', objectFit: 'cover'}}/>;
  const colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6'];
  const initial = name && name.length > 0 ? name.charAt(0).toUpperCase() : '?';
  const bgColor = colors[name ? name.length % colors.length : 0];
  return <div style={{width: '40px', height: '40px', borderRadius: '50%', backgroundColor: bgColor, color: '#fff', display: 'flex', justifyContent: 'center', alignItems: 'center', fontWeight: 'bold', fontSize: '18px'}}>{initial}</div>;
};

export default function App() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [jars, setJars] = useState<Jar[]>([]);

  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const [tgUser, setTgUser] = useState<any>(null);
  const [familyId, setFamilyId] = useState<number | null>(null);
  const [dbUserId, setDbUserId] = useState<number | null>(null);
  const [familyName, setFamilyName] = useState<string>('');
  const [inviteCode, setInviteCode] = useState<string>('');
  const [hasMonoToken, setHasMonoToken] = useState<boolean>(false);
  const [myRole, setMyRole] = useState<string>('member');
  const [familyUsers, setFamilyUsers] = useState<any[]>([]);

  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const LIMIT = 50;

  const [activeTab, setActiveTab] = useState<'transactions' | 'jars' | 'notes' | 'analytics' | 'settings'>('transactions');

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [viewingTx, setViewingTx] = useState<Transaction | null>(null);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);

  const [txType, setTxType] = useState<'Витрати' | 'Поповнення'>('Витрати');
  const [txAmount, setTxAmount] = useState('');
  const [txTitle, setTxTitle] = useState('');
  const [txDate, setTxDate] = useState('');
  const [txCategoryId, setTxCategoryId] = useState<number | null>(null);

  const [monoToken, setMonoToken] = useState('');
  const [showTokenInput, setShowTokenInput] = useState(false);

  const [currentNote, setCurrentNote] = useState<Note | null>(null);
  const [noteText, setNoteText] = useState('');
  const [splitBy, setSplitBy] = useState<number>(1);

  const [isJarModalOpen, setIsJarModalOpen] = useState(false);
  const [jarName, setJarName] = useState('');
  const [jarGoal, setJarGoal] = useState('');
  const [topupJarId, setTopupJarId] = useState<number | null>(null);
  const [jarTopupAmount, setJarTopupAmount] = useState('');

  useEffect(() => {
    const webApp = (window as any).Telegram?.WebApp;
    if (!webApp || !webApp.initData) {
      setAuthError("Відкрийте застосунок через Telegram-бота.");
      setLoading(false); return;
    }
    webApp.ready(); webApp.expand();
    setTgUser(webApp.initDataUnsafe?.user || null);

    const loadData = async () => {
      try {
        // 1. Аутентифікація: сервер валідує підписаний Telegram initData і видає JWT.
        const authRes = await api.post('/auth/token', { init_data: webApp.initData });
        setAuthToken(authRes.data.access_token);

        // 2. Ідентичність беремо з відповіді токена (це той самий UserOut, що й у /auth/me).
        const me = authRes.data.user;
        const fId: number = me.family_id;
        const uId: number = me.id;
        setFamilyId(fId); setDbUserId(uId);
        setHasMonoToken(!!me.has_mono_token);
        setMyRole(me.role || 'member');

        // 3. Тільки після успішної аутентифікації вантажимо дані сім'ї.
        const [txRes, catRes, statsRes, usersRes, famRes, notesRes, jarsRes] = await Promise.all([
          api.get(`/families/${fId}/transactions?skip=0&limit=${LIMIT}`),
          api.get(`/families/${fId}/categories`),
          api.get(`/families/${fId}/stats`),
          api.get(`/families/${fId}/users`),
          api.get(`/families`),
          api.get(`/families/${fId}/notes`),
          api.get(`/families/${fId}/jars`)
        ]);

        setTransactions(txRes.data);
        if (txRes.data.length < LIMIT) setHasMore(false);
        setCategories(catRes.data); setStats(statsRes.data);
        setFamilyUsers(usersRes.data.filter((u: any) => u.name && u.name.trim() !== ''));
        setJars(jarsRes.data);

        if (notesRes.data.length > 0) {
          setCurrentNote(notesRes.data[0]);
          setNoteText(notesRes.data[0].content);
        }

        // JWT-користувачу GET /families повертає ТІЛЬКИ його сім'ю (список із 1 елемента).
        const myFam = famRes.data[0];
        if (myFam) {
          setFamilyName(myFam.name); setInviteCode(myFam.invite_code);
        }
        setLoading(false);
      } catch (error: any) {
        const status = error?.response?.status;
        if (status === 401) setAuthError("Сесія не підтверджена. Відкрийте застосунок через Telegram-бота.");
        else if (status === 404) setAuthError("Акаунт не знайдено. Перезапустіть /start");
        else setAuthError("Помилка з'єднання. Спробуйте ще раз.");
        setLoading(false);
      }
    };
    loadData();
  }, []);

  const triggerHaptic = (style: 'light' | 'medium' | 'heavy' | 'success') => {
    const tg = (window as any).Telegram?.WebApp;
    if (tg?.HapticFeedback) {
      if (style === 'success') tg.HapticFeedback.notificationOccurred('success');
      else tg.HapticFeedback.impactOccurred(style);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    triggerHaptic('success');
    alert("Скопійовано!");
  };

  const loadMoreTransactions = async () => {
    if (!familyId) return;
    try {
      const nextSkip = skip + LIMIT;
      const res = await api.get(`/families/${familyId}/transactions?skip=${nextSkip}&limit=${LIMIT}`);
      if (res.data.length < LIMIT) setHasMore(false);
      setTransactions([...transactions, ...res.data]);
      setSkip(nextSkip);
    } catch (e) { console.error(e); }
  };

  const refreshStats = async () => {
    if (!familyId) return;
    const res = await api.get(`/families/${familyId}/stats`);
    setStats(res.data);
  };

  const openAddModal = () => {
    setTxType('Витрати'); setTxAmount(''); setTxTitle(''); setTxDate(new Date().toISOString().split('T')[0]);
    const expCat = categories.find(c => c.type === 'expense');
    setTxCategoryId(expCat ? expCat.id : null);
    setIsAddModalOpen(true);
  };

  const handleAdd = async () => {
    if (!txAmount || !txTitle || !txCategoryId || !familyId || !dbUserId) return alert("Заповніть всі поля!");
    try {
      const res = await api.post('/transactions', {
        family_id: familyId, user_id: dbUserId, category_id: txCategoryId,
        amount: parseFloat(txAmount.replace(',', '.')), type: txType,
        title: txTitle, account: "Готівка", date: txDate || new Date().toISOString().split('T')[0]
      });
      const newTxs = [res.data, ...transactions].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
      setTransactions(newTxs);
      await refreshStats();
      setIsAddModalOpen(false);
      triggerHaptic('success');
    } catch (e) { alert("Помилка."); }
  };

  const openEditFromView = () => {
    if (!viewingTx) return;
    setEditingTx(viewingTx);
    setTxType(viewingTx.type as 'Витрати' | 'Поповнення');
    setTxAmount(viewingTx.amount.toString());
    setTxTitle(viewingTx.title);
    setTxDate(viewingTx.date);
    setTxCategoryId(viewingTx.category_id);
    setViewingTx(null);
  };

  const handleUpdate = async () => {
    if (!editingTx || !txAmount || !txTitle || !txCategoryId) return alert("Заповніть всі поля!");
    try {
      const res = await api.put(`/transactions/${editingTx.id}`, {
        amount: parseFloat(txAmount.replace(',', '.')),
        type: txType, title: txTitle, category_id: txCategoryId, date: txDate
      });
      const newTxs = transactions.map(t => t.id === editingTx.id ? res.data : t).sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
      setTransactions(newTxs);
      await refreshStats();
      setEditingTx(null);
      triggerHaptic('success');
    } catch (e) { alert("Помилка."); }
  };

  const handleDelete = async () => {
    if (!editingTx) return;
    if (!window.confirm("Ви дійсно хочете видалити цю транзакцію?")) return;
    try {
      await api.delete(`/transactions/${editingTx.id}`);
      setTransactions(transactions.filter(t => t.id !== editingTx.id));
      await refreshStats();
      setEditingTx(null);
      triggerHaptic('success');
    } catch (e) { alert("Помилка."); }
  };

  const handleUpdateToken = async () => {
    if (!monoToken) return alert("Введіть токен!");
    try {
      await api.put('/users/me/token', { mono_token: monoToken });
      alert("✅ Токен успішно оновлено!");
      setMonoToken(''); setHasMonoToken(true); setShowTokenInput(false);
      triggerHaptic('success');
    } catch (error) { alert("❌ Помилка оновлення токена."); }
  };

  const regenerateInvite = async () => {
    if (!window.confirm("Старий код перестане працювати. Згенерувати новий?")) return;
    try {
      const res = await api.post(`/families/${familyId}/regenerate-invite`);
      setInviteCode(res.data.invite_code);
      triggerHaptic('success');
    } catch (e) { alert("Помилка."); }
  };

  const removeFamilyMember = async (userId: number, userName: string) => {
    if (!familyId) return;
    if (!window.confirm(`Видалити користувача ${userName} з сім'ї? Він втратить доступ до бюджету.`)) return;
    try {
      await api.delete(`/families/${familyId}/users/${userId}`);
      setFamilyUsers(familyUsers.filter(u => u.id !== userId));
      triggerHaptic('success');
    } catch (e) { alert("Помилка."); }
  };

  const saveNote = async () => {
    if (!familyId) return;
    try {
      if (currentNote) {
        await api.put(`/notes/${currentNote.id}`, { family_id: familyId, content: noteText });
      } else {
        const res = await api.post('/notes', { family_id: familyId, content: noteText });
        setCurrentNote(res.data);
      }
    } catch (e) { console.error(e); }
  };

  const clearNote = async () => {
    if (!window.confirm("Очистити чернетку?")) return;
    setNoteText('');
    if (currentNote && familyId) await api.put(`/notes/${currentNote.id}`, { family_id: familyId, content: '' });
    triggerHaptic('success');
  };

  const calculateNoteSum = () => {
    const regex = /(\d+([.,]\d{1,2})?)\s*(грн|uah|₴|\$|дол|eur|€)/gi;
    let total = 0; let match;
    while ((match = regex.exec(noteText)) !== null) {
      total += parseFloat(match[1].replace(',', '.'));
    }
    return total;
  };

  const handleCreateJar = async () => {
    if (!jarName || !jarGoal || !familyId) return alert("Заповніть назву і ціль!");
    try {
      const res = await api.post('/jars', { family_id: familyId, name: jarName, goal: parseFloat(jarGoal.replace(',', '.')) });
      setJars([...jars, res.data]);
      setIsJarModalOpen(false); setJarName(''); setJarGoal('');
      triggerHaptic('success');
    } catch (e) { alert("Помилка."); }
  };

  const handleTopUpJar = async () => {
    if (!jarTopupAmount || !topupJarId || !familyId || !dbUserId) return alert("Введіть суму!");
    try {
      const amt = parseFloat(jarTopupAmount.replace(',', '.'));
      const res = await api.post(`/jars/${topupJarId}/topup`, { amount: amt });
      setJars(jars.map(j => j.id === topupJarId ? res.data : j));

      const safeCatId = categories.find(c => c.name.includes("Інше") || c.name.includes("Накопичення"))?.id || 1;
      await api.post('/transactions', {
        family_id: familyId, user_id: dbUserId, category_id: safeCatId,
        amount: amt, type: "Витрати", title: `Поповнення банки: ${res.data.name}`, account: "Готівка", date: new Date().toISOString().split('T')[0]
      });
      await refreshStats();

      setTopupJarId(null); setJarTopupAmount('');
      triggerHaptic('success');
    } catch (e) { alert("Помилка."); }
  };

  const filteredCategories = categories.filter(c => c.type === (txType === 'Витрати' ? 'expense' : 'income'));
  const cleanStats = stats?.top_categories.map(c => ({ ...c, cleanName: c.name.replace(/^[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ0-9]+/, '').trim() || c.name })) || [];
  const totalSum = calculateNoteSum();

  if (authError) return <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100vh', backgroundColor: '#f5f7fa', padding: '20px', textAlign: 'center' }}><span style={{ fontSize: '60px', marginBottom: '20px' }}>🛑</span><h2 style={{ color: '#e74c3c' }}>Доступ заборонено</h2><p style={{ color: '#7f8c8d' }}>{authError}</p></div>;
  if (loading) return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', backgroundColor: '#f5f7fa' }}><h3 style={{ color: '#7f8c8d' }}>⏳ Завантаження...</h3></div>;

  return (
    <div style={{ fontFamily: 'sans-serif', backgroundColor: '#f5f7fa', minHeight: '100vh', paddingBottom: '80px', position: 'relative' }}>
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
        {activeTab === 'transactions' && (
          <>
            <h2 style={{ color: '#2c3e50', marginBottom: '15px', fontSize: '20px' }}>💸 Останні транзакції</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {transactions.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px 20px', backgroundColor: '#fff', borderRadius: '16px' }}><p style={{ color: '#7f8c8d' }}>Немає транзакцій.</p></div>
              ) : (
                transactions.map(tx => {
                  const cat = categories.find(c => c.id === tx.category_id);
                  const cleanCatName = cat ? cat.name.replace(/^[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ0-9]+/, '').trim() : 'Інше';
                  return (
                    <div key={tx.id} onClick={() => setViewingTx(tx)} style={{ backgroundColor: '#fff', padding: '16px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}>
                      <div style={{ overflow: 'hidden', paddingRight: '10px' }}>
                        <div style={{ fontWeight: 'bold', fontSize: '15px', color: '#2c3e50', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tx.title}</div>
                        <div style={{ fontSize: '12px', color: '#95a5a6', marginTop: '4px' }}>{cleanCatName} • {tx.account} • {tx.date}</div>
                      </div>
                      <div style={{ fontWeight: 'bold', fontSize: '16px', whiteSpace: 'nowrap', color: tx.type === 'Витрати' ? '#e74c3c' : '#27ae60' }}>{tx.type === 'Витрати' ? '-' : '+'}{tx.amount} ₴</div>
                    </div>
                  );
                })
              )}
              {hasMore && transactions.length > 0 && <button onClick={loadMoreTransactions} style={{ width: '100%', padding: '12px', marginTop: '10px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '14px' }}>⬇️ Завантажити ще</button>}
            </div>
          </>
        )}

        {activeTab === 'jars' && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <h2 style={{ color: '#2c3e50', margin: 0, fontSize: '20px' }}>🏦 Скарбнички</h2>
              <button onClick={() => setIsJarModalOpen(true)} style={{ border: 'none', background: 'transparent', color: '#3498db', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>+ Створити</button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              {jars.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px 20px', backgroundColor: '#fff', borderRadius: '16px' }}><p style={{ color: '#7f8c8d' }}>Немає цілей.</p></div>
              ) : (
                jars.map(jar => {
                  const pct = Math.min((jar.balance / jar.goal) * 100, 100);
                  return (
                    <div key={jar.id} style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                        <div style={{ fontWeight: 'bold', fontSize: '16px', color: '#2c3e50' }}>{jar.name}</div>
                        <div style={{ fontWeight: 'bold', fontSize: '14px', color: '#27ae60' }}>{jar.balance} / {jar.goal} ₴</div>
                      </div>
                      <div style={{ height: '8px', backgroundColor: '#ecf0f1', borderRadius: '4px', overflow: 'hidden', marginBottom: '15px' }}>
                        <div style={{ width: `${pct}%`, height: '100%', backgroundColor: '#2ecc71', borderRadius: '4px', transition: 'width 0.5s' }}></div>
                      </div>
                      <button onClick={() => setTopupJarId(jar.id)} style={{ width: '100%', padding: '10px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '10px', fontWeight: 'bold', fontSize: '14px' }}>📥 Поповнити</button>
                    </div>
                  );
                })
              )}
            </div>
          </>
        )}

        {activeTab === 'notes' && (
          <div style={{ display: 'flex', flexDirection: 'column', height: '65vh' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <h2 style={{ color: '#2c3e50', margin: 0, fontSize: '20px' }}>📝 Чернетка</h2>
              <button onClick={clearNote} style={{ border: 'none', background: 'transparent', color: '#e74c3c', fontWeight: 'bold', fontSize: '14px', cursor: 'pointer' }}>🗑 Очистити</button>
            </div>
            <p style={{ margin: '0 0 10px 0', color: '#7f8c8d', fontSize: '13px' }}>Додавайте <b>грн, uah, ₴, $, дол</b> біля суми, щоб вона порахувалась!</p>
            <textarea
              value={noteText} maxLength={2000} onChange={(e) => setNoteText(e.target.value)} onBlur={saveNote}
              placeholder={`Наприклад:\nМ'ясо 500 грн (вага 2 кг)\nПиво 350.50 ₴`}
              style={{ flex: 1, padding: '15px', borderRadius: '16px', border: 'none', backgroundColor: '#fff', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', fontSize: '15px', resize: 'none', outline: 'none' }}
            />
            <div style={{ marginTop: '15px', padding: '15px', backgroundColor: '#3498db', borderRadius: '16px', color: '#fff', boxShadow: '0 4px 15px rgba(52, 152, 219, 0.3)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: splitBy > 1 ? '10px' : '0' }}>
                <span style={{ fontSize: '16px', fontWeight: 'bold' }}>Сума (Авто):</span>
                <span style={{ fontSize: '24px', fontWeight: 'bold' }}>{totalSum.toLocaleString()} ₴</span>
              </div>
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.2)', paddingTop: '10px', marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '14px' }}>👤 Ділити на:</span>
                  <input type="number" min="1" max="50" value={splitBy} onChange={(e) => setSplitBy(Number(e.target.value))} style={{ width: '40px', padding: '5px', borderRadius: '6px', border: 'none', textAlign: 'center', fontWeight: 'bold', color: '#2c3e50' }} />
                </div>
                {splitBy > 1 && <span style={{ fontSize: '16px', fontWeight: 'bold' }}>По {(totalSum / splitBy).toFixed(2)} ₴</span>}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'analytics' && stats && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', display: 'flex', justifyContent: 'space-between' }}>
              <div><p style={{ margin: 0, color: '#7f8c8d', fontSize: '12px' }}>Дохід (Місяць)</p><h3 style={{ margin: '5px 0 0 0', color: '#27ae60' }}>+{stats.income.toLocaleString()} ₴</h3></div>
              <div><p style={{ margin: 0, color: '#7f8c8d', fontSize: '12px' }}>Витрати (Місяць)</p><h3 style={{ margin: '5px 0 0 0', color: '#e74c3c' }}>-{stats.expense.toLocaleString()} ₴</h3></div>
            </div>
            <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
              <h3 style={{ margin: '0 0 10px 0', color: '#2c3e50' }}>📊 Структура витрат</h3>
              {cleanStats.length > 0 ? (
                <>
                  <div style={{ width: '100%', height: '220px' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart><Pie data={cleanStats} dataKey="amount" nameKey="cleanName" cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={2}>{cleanStats.map((entry, index) => <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />)}</Pie><Tooltip formatter={(value: number) => `${value} ₴`} /></PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
                    {cleanStats.map((cat, index) => (
                        <div key={index} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '14px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><span style={{ display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%', backgroundColor: COLORS[index % COLORS.length] }}></span><span style={{ color: '#2c3e50' }}>{cat.cleanName}</span></div>
                          <span style={{ fontWeight: 'bold', color: '#7f8c8d' }}>{cat.amount.toLocaleString()} ₴</span>
                        </div>
                    ))}
                  </div>
                </>
              ) : <p style={{ textAlign: 'center', color: '#7f8c8d' }}>Немає витрат.</p>}
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
             <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
                <h3 style={{ margin: '0 0 10px 0', color: '#2c3e50' }}>🏠 Сім'я: {familyName}</h3>
                <p style={{ margin: '0 0 10px 0', color: '#7f8c8d', fontSize: '13px' }}>Код запрошення (натисніть, щоб скопіювати):</p>
                <div onClick={() => copyToClipboard(`https://t.me/bimipal_bot?start=join_${inviteCode}`)} style={{ backgroundColor: '#f1f2f6', padding: '12px', borderRadius: '8px', fontFamily: 'monospace', color: '#3498db', cursor: 'pointer', textAlign: 'center', fontWeight: 'bold' }}>
                  {inviteCode} 📋
                </div>
                {myRole === 'admin' && (
                  <button onClick={regenerateInvite} style={{ width: '100%', padding: '10px', marginTop: '10px', backgroundColor: 'transparent', color: '#e67e22', border: '1px solid #e67e22', borderRadius: '8px', fontWeight: 'bold', fontSize: '13px' }}>Згенерувати новий код</button>
                )}

                <h4 style={{ margin: '20px 0 10px 0', color: '#2c3e50' }}>Учасники:</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {familyUsers.map(u => (
                    <div key={u.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#f9f9f9', padding: '10px', borderRadius: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <Avatar name={u.name} />
                        <span style={{ color: '#2c3e50', fontWeight: '500' }}>{u.name} {u.id === dbUserId ? '(Ви)' : ''}</span>
                      </div>
                      {u.id !== dbUserId && myRole === 'admin' && (
                        <button onClick={() => removeFamilyMember(u.id, u.name)} style={{ border: 'none', background: 'transparent', color: '#e74c3c', fontSize: '18px', cursor: 'pointer' }}>✖</button>
                      )}
                    </div>
                  ))}
                </div>
             </div>

             <div style={{ backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
                <h3 style={{ margin: '0 0 10px 0', color: '#2c3e50' }}>💳 Monobank Автопілот</h3>
                {hasMonoToken && !showTokenInput ? (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
                    <div style={{ color: '#27ae60', fontWeight: 'bold', fontSize: '16px' }}>✅ Підключено</div>
                    <button onClick={() => setShowTokenInput(true)} style={{ width: '100%', padding: '10px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '10px', fontWeight: 'bold' }}>Змінити токен</button>
                  </div>
                ) : (
                  <>
                    <p style={{ margin: '0 0 15px 0', color: '#7f8c8d', fontSize: '13px' }}>Вставте токен з api.monobank.ua</p>
                    <input type="password" value={monoToken} onChange={(e) => setMonoToken(e.target.value)} placeholder="Введіть токен..." style={{ width: '100%', padding: '12px', borderRadius: '10px', border: '1px solid #dfe6e9', marginBottom: '10px', boxSizing: 'border-box' }} />
                    <div style={{ display: 'flex', gap: '10px' }}>
                      {hasMonoToken && <button onClick={() => setShowTokenInput(false)} style={{ flex: 1, padding: '12px', backgroundColor: '#ecf0f1', color: '#7f8c8d', border: 'none', borderRadius: '10px', fontWeight: 'bold' }}>Скасувати</button>}
                      <button onClick={handleUpdateToken} style={{ flex: 2, padding: '12px', backgroundColor: '#3498db', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: 'bold' }}>Зберегти</button>
                    </div>
                  </>
                )}
             </div>
          </div>
        )}
      </div>

      {(activeTab === 'transactions' || activeTab === 'jars') && (
        <div onClick={activeTab === 'transactions' ? openAddModal : () => setIsJarModalOpen(true)} style={{ position: 'fixed', bottom: '90px', right: '20px', width: '60px', height: '60px', backgroundColor: '#3498db', color: '#fff', borderRadius: '50%', display: 'flex', justifyContent: 'center', alignItems: 'center', fontSize: '32px', boxShadow: '0 4px 15px rgba(52, 152, 219, 0.4)', cursor: 'pointer', zIndex: 10 }}>+</div>
      )}

      <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: '70px', backgroundColor: '#fff', display: 'flex', justifyContent: 'space-around', alignItems: 'center', boxShadow: '0 -2px 10px rgba(0,0,0,0.05)', paddingBottom: 'env(safe-area-inset-bottom)', zIndex: 5 }}>
        <div onClick={() => setActiveTab('transactions')} style={{ textAlign: 'center', cursor: 'pointer', color: activeTab === 'transactions' ? '#3498db' : '#95a5a6', width: '20%' }}><div style={{ fontSize: '22px' }}>💸</div><div style={{ fontSize: '10px', fontWeight: activeTab === 'transactions' ? 'bold' : 'normal', marginTop: '4px' }}>Транзакції</div></div>
        <div onClick={() => setActiveTab('jars')} style={{ textAlign: 'center', cursor: 'pointer', color: activeTab === 'jars' ? '#3498db' : '#95a5a6', width: '20%' }}><div style={{ fontSize: '22px' }}>🏦</div><div style={{ fontSize: '10px', fontWeight: activeTab === 'jars' ? 'bold' : 'normal', marginTop: '4px' }}>Цілі</div></div>
        <div onClick={() => setActiveTab('notes')} style={{ textAlign: 'center', cursor: 'pointer', color: activeTab === 'notes' ? '#3498db' : '#95a5a6', width: '20%' }}><div style={{ fontSize: '22px' }}>📝</div><div style={{ fontSize: '10px', fontWeight: activeTab === 'notes' ? 'bold' : 'normal', marginTop: '4px' }}>Чернетка</div></div>
        <div onClick={() => setActiveTab('analytics')} style={{ textAlign: 'center', cursor: 'pointer', color: activeTab === 'analytics' ? '#3498db' : '#95a5a6', width: '20%' }}><div style={{ fontSize: '22px' }}>📊</div><div style={{ fontSize: '10px', fontWeight: activeTab === 'analytics' ? 'bold' : 'normal', marginTop: '4px' }}>Аналітика</div></div>
        <div onClick={() => setActiveTab('settings')} style={{ textAlign: 'center', cursor: 'pointer', color: activeTab === 'settings' ? '#3498db' : '#95a5a6', width: '20%' }}><div style={{ fontSize: '22px' }}>⚙️</div><div style={{ fontSize: '10px', fontWeight: activeTab === 'settings' ? 'bold' : 'normal', marginTop: '4px' }}>Меню</div></div>
      </div>

      {isJarModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 110, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
          <div style={{ backgroundColor: '#fff', borderTopLeftRadius: '24px', borderTopRightRadius: '24px', padding: '25px', paddingBottom: 'calc(25px + env(safe-area-inset-bottom))', animation: 'slideUp 0.3s ease-out' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#2c3e50' }}>Нова ціль</h3>
              <button onClick={() => setIsJarModalOpen(false)} style={{ border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6' }}>×</button>
            </div>
            <input type="text" placeholder="Назва (напр. Відпустка)" value={jarName} onChange={(e) => setJarName(e.target.value)} style={{ width: '100%', padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9', marginBottom: '15px', fontSize: '16px', boxSizing: 'border-box' }} />
            <input type="number" placeholder="Потрібна сума" value={jarGoal} onChange={(e) => setJarGoal(e.target.value)} style={{ width: '100%', padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9', marginBottom: '20px', fontSize: '16px', boxSizing: 'border-box' }} />
            <button onClick={handleCreateJar} style={{ width: '100%', padding: '15px', backgroundColor: '#3498db', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '16px' }}>Створити</button>
          </div>
        </div>
      )}

      {topupJarId && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 110, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
          <div style={{ backgroundColor: '#fff', borderTopLeftRadius: '24px', borderTopRightRadius: '24px', padding: '25px', paddingBottom: 'calc(25px + env(safe-area-inset-bottom))', animation: 'slideUp 0.3s ease-out' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#2c3e50' }}>Поповнити банку</h3>
              <button onClick={() => setTopupJarId(null)} style={{ border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6' }}>×</button>
            </div>
            <input type="number" placeholder="Сума поповнення" value={jarTopupAmount} onChange={(e) => setJarTopupAmount(e.target.value)} style={{ width: '100%', padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9', marginBottom: '20px', fontSize: '16px', boxSizing: 'border-box' }} />
            <button onClick={handleTopUpJar} style={{ width: '100%', padding: '15px', backgroundColor: '#2ecc71', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '16px' }}>Закинути гроші</button>
          </div>
        </div>
      )}

      {viewingTx && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 100, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
          <div style={{ backgroundColor: '#fff', borderTopLeftRadius: '24px', borderTopRightRadius: '24px', padding: '25px', paddingBottom: 'calc(25px + env(safe-area-inset-bottom))', animation: 'slideUp 0.3s ease-out' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#2c3e50' }}>Деталі транзакції</h3>
              <button onClick={() => setViewingTx(null)} style={{ border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6', cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <div style={{ fontSize: '32px', fontWeight: 'bold', color: viewingTx.type === 'Витрати' ? '#e74c3c' : '#27ae60' }}>{viewingTx.type === 'Витрати' ? '-' : '+'}{viewingTx.amount} ₴</div>
              <div style={{ color: '#7f8c8d', marginTop: '5px' }}>{categories.find(c => c.id === viewingTx.category_id)?.name.replace(/^[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ0-9]+/, '').trim() || 'Інше'}</div>
            </div>
            <div style={{ backgroundColor: '#f8f9fa', padding: '15px', borderRadius: '12px', marginBottom: '20px' }}>
              <p style={{ margin: '0 0 10px 0', color: '#2c3e50', fontSize: '15px', wordBreak: 'break-word' }}><b>Опис:</b> {viewingTx.title}</p>
              <p style={{ margin: '0 0 5px 0', color: '#7f8c8d', fontSize: '13px' }}><b>Рахунок:</b> {viewingTx.account}</p>
              <p style={{ margin: '0', color: '#7f8c8d', fontSize: '13px' }}><b>Дата:</b> {viewingTx.date}</p>
            </div>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button onClick={() => copyToClipboard(`${viewingTx.title} - ${viewingTx.amount}₴`)} style={{ flex: 1, padding: '15px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '15px' }}>📋 Копіювати</button>
              <button onClick={openEditFromView} style={{ flex: 1, padding: '15px', backgroundColor: '#3498db', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '15px' }}>✏️ Редагувати</button>
            </div>
          </div>
        </div>
      )}

      {(isAddModalOpen || editingTx) && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 110, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
          <div style={{ backgroundColor: '#fff', borderTopLeftRadius: '24px', borderTopRightRadius: '24px', padding: '25px', paddingBottom: 'calc(25px + env(safe-area-inset-bottom))', animation: 'slideUp 0.3s ease-out', maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, color: '#2c3e50' }}>{editingTx ? 'Редагування' : 'Нова транзакція'}</h3>
              <button onClick={() => { setIsAddModalOpen(false); setEditingTx(null); }} style={{ border: 'none', background: 'transparent', fontSize: '24px', color: '#95a5a6', cursor: 'pointer' }}>×</button>
            </div>

            <div style={{ display: 'flex', backgroundColor: '#f1f2f6', borderRadius: '12px', padding: '4px', marginBottom: '15px' }}>
              <div onClick={() => { setTxType('Витрати'); setTxCategoryId(categories.find(c => c.type === 'expense')?.id || null); }} style={{ flex: 1, textAlign: 'center', padding: '10px', borderRadius: '10px', cursor: 'pointer', backgroundColor: txType === 'Витрати' ? '#fff' : 'transparent', fontWeight: txType === 'Витрати' ? 'bold' : 'normal', color: txType === 'Витрати' ? '#e74c3c' : '#7f8c8d', boxShadow: txType === 'Витрати' ? '0 2px 5px rgba(0,0,0,0.05)' : 'none' }}>Витрата</div>
              <div onClick={() => { setTxType('Поповнення'); setTxCategoryId(categories.find(c => c.type === 'income')?.id || null); }} style={{ flex: 1, textAlign: 'center', padding: '10px', borderRadius: '10px', cursor: 'pointer', backgroundColor: txType === 'Поповнення' ? '#fff' : 'transparent', fontWeight: txType === 'Поповнення' ? 'bold' : 'normal', color: txType === 'Поповнення' ? '#27ae60' : '#7f8c8d', boxShadow: txType === 'Поповнення' ? '0 2px 5px rgba(0,0,0,0.05)' : 'none' }}>Дохід</div>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
              <input type="number" placeholder="Сума" value={txAmount} onChange={(e) => setTxAmount(e.target.value)} style={{ flex: 2, padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9', fontSize: '16px', boxSizing: 'border-box' }} />
              <input type="date" value={txDate} onChange={(e) => setTxDate(e.target.value)} style={{ flex: 1, padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9', fontSize: '16px', boxSizing: 'border-box', backgroundColor: '#fff' }} />
            </div>

            <input type="text" placeholder="Що купили?" value={txTitle} onChange={(e) => setTxTitle(e.target.value)} style={{ width: '100%', padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9', marginBottom: '15px', fontSize: '16px', boxSizing: 'border-box' }} />

            <select value={txCategoryId || ''} onChange={(e) => setTxCategoryId(Number(e.target.value))} style={{ width: '100%', padding: '15px', borderRadius: '12px', border: '1px solid #dfe6e9', marginBottom: '20px', fontSize: '16px', boxSizing: 'border-box', backgroundColor: '#fff' }}>
              <option value="" disabled>Оберіть категорію</option>
              {filteredCategories.map(cat => <option key={cat.id} value={cat.id}>{cat.name.replace(/^[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ0-9]+/, '').trim()}</option>)}
            </select>

            <button onClick={editingTx ? handleUpdate : handleAdd} style={{ width: '100%', padding: '15px', backgroundColor: '#3498db', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '16px', marginBottom: editingTx ? '10px' : '0', cursor: 'pointer' }}>Зберегти</button>
            {editingTx && <button onClick={handleDelete} style={{ width: '100%', padding: '15px', backgroundColor: '#fff', color: '#e74c3c', border: '1px solid #e74c3c', borderRadius: '12px', fontWeight: 'bold', fontSize: '16px', cursor: 'pointer' }}>Видалити транзакцію</button>}
          </div>
        </div>
      )}
      <style>{`@keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }`}</style>
    </div>
  );
}