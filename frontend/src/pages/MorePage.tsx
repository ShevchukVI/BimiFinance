import { ReactNode, useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import { confirmAsync } from '../tg';
import Avatar from '../components/Avatar';
import { FamilyMembership, FamilyUser, Jar } from '../types';
import { Badge, Button, Card, Field, Row, Section, SubScreen } from '../ui';
import JarsPage from './JarsPage';
import NotesPage from './NotesPage';

type Screen = null | 'jars' | 'notes' | 'family' | 'mono';

export default function MorePage(props: {
  me: { id: number; name: string; role: string | null };
  families: FamilyMembership[]; familyId: number; familyName: string; inviteCode: string;
  familyUsers: FamilyUser[]; hasMonoToken: boolean;
  jars: Jar[]; onJarTopUp: (j: Jar) => void; onJarCreate: () => void;
  noteText: string; setNoteText: (s: string) => void; onNoteBlur: () => void; onNoteClear: () => void;
  splitBy: number; setSplitBy: (n: number) => void;
  housingEnabled: boolean; onHousingSettings: () => void;
  onSwitchFamily: (familyId: number) => void; onInviteRegenerated: (code: string) => void;
  onMemberRemoved: (userId: number) => void; onMemberRoleChange: (userId: number, role: 'admin' | 'member') => void;
  onLeaveFamily: () => void; onTokenSaved: () => void; copyToClipboard: (text: string) => void;
  initialScreen?: Screen;
}) {
  const [screen, setScreen] = useState<Screen>(props.initialScreen || null);
  const back = () => setScreen(null);

  if (screen === 'jars') return <div className="page"><SubScreen title="Цілі" onBack={back}>
    <JarsPage jars={props.jars} familyId={props.familyId} onTopUp={props.onJarTopUp} onCreate={props.onJarCreate} /></SubScreen></div>;
  if (screen === 'notes') return <div className="page"><SubScreen title="Чернетка" onBack={back}>
    <NotesPage noteText={props.noteText} setNoteText={props.setNoteText} onBlur={props.onNoteBlur} onClear={props.onNoteClear}
      splitBy={props.splitBy} setSplitBy={props.setSplitBy} /></SubScreen></div>;
  if (screen === 'family') return <div className="page"><SubScreen title="Сім'я" onBack={back}><FamilyScreen {...props} /></SubScreen></div>;
  if (screen === 'mono') return <div className="page"><SubScreen title="Monobank" onBack={back}><MonoScreen hasMonoToken={props.hasMonoToken} onTokenSaved={props.onTokenSaved} /></SubScreen></div>;

  const item = (icon: string, title: string, sub: ReactNode, onClick: () => void) => <Row icon={icon} title={title} sub={sub} chevron onClick={onClick} />;
  return (
    <div className="page">
      <h1 className="page-title">Ще</h1>
      <Card flush>
        {item('🎯', 'Цілі', props.jars.length ? `${props.jars.length} скарбнич${props.jars.length === 1 ? 'ка' : 'ки'}` : 'Відкладати на мрію', () => setScreen('jars'))}
        {item('📝', 'Чернетка', 'Швидкі підрахунки й нотатки', () => setScreen('notes'))}
        {item('🏡', 'Житло', props.housingEnabled ? 'Комуналка, оренда, лічильники' : 'Вимкнено — увімкнути', props.onHousingSettings)}
      </Card>
      <Card flush>
        {item('👨‍👩‍👧', "Сім'я", `${props.familyName} · ${props.familyUsers.length} учасн.`, () => setScreen('family'))}
        {item('💳', 'Monobank', props.hasMonoToken ? <span className="pos">Підключено</span> : 'Не підключено', () => setScreen('mono'))}
        <Row icon="📤" title="Експорт в Excel" sub="Скоро" />
      </Card>
    </div>
  );
}

function FamilyScreen({ me, families, familyId, familyName, inviteCode, familyUsers, onSwitchFamily, onInviteRegenerated,
  onMemberRemoved, onMemberRoleChange, onLeaveFamily, copyToClipboard }: Parameters<typeof MorePage>[0]) {
  // Роль беремо з backend payload учасників, а не лише з me.role.
  const isAdmin = (familyUsers.find(u => u.id === me.id)?.role ?? me.role ?? 'member') === 'admin';
  const [busyId, setBusyId] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);
  const link = `https://t.me/bimipal_bot?start=join_${inviteCode}`;

  const switchFamily = async (f: FamilyMembership) => {
    if (f.is_active) return;
    try {
      await api.patch('/users/me/active-family', { family_id: f.family_id });
      onSwitchFamily(f.family_id);
      toast(`Активна сім'я: ${f.name}`);
    } catch { toast('Не вдалося перемкнути сім\'ю', 'err'); }
  };
  const regenerate = async () => {
    if (!(await confirmAsync('Старий код перестане працювати. Згенерувати новий?'))) return;
    try { onInviteRegenerated((await api.post(`/families/${familyId}/regenerate-invite`)).data.invite_code); toast('Новий код згенеровано'); }
    catch { toast('Помилка генерації', 'err'); }
  };
  const changeRole = async (u: FamilyUser, role: 'admin' | 'member') => {
    setBusyId(u.id);
    try { await api.patch(`/families/${familyId}/members/${u.id}`, { role }); onMemberRoleChange(u.id, role); toast(role === 'admin' ? 'Призначено адміном' : 'Тепер учасник'); }
    catch (e: any) { toast(e?.response?.data?.detail || 'Помилка зміни ролі', 'err'); }
    setBusyId(null);
  };
  const kick = async (u: FamilyUser) => {
    if (!(await confirmAsync(`Видалити ${u.name} з сім'ї?`))) return;
    setBusyId(u.id);
    try { await api.delete(`/families/${familyId}/members/${u.id}`); onMemberRemoved(u.id); toast('Учасника видалено'); }
    catch (e: any) { toast(e?.response?.data?.detail || 'Помилка видалення', 'err'); }
    setBusyId(null);
  };
  const leave = async () => {
    if (!(await confirmAsync('Вийти з цієї сім\'ї? Цю дію неможливо скасувати.'))) return;
    setLeaving(true);
    try { await api.delete(`/families/${familyId}/leave`); onLeaveFamily(); toast('Ви вийшли з сім\'ї'); }
    catch (e: any) { toast(e?.response?.data?.detail || 'Не вдалося вийти', 'err'); }
    setLeaving(false);
  };

  return (
    <>
      <Card>
        <div className="spread"><b>{familyName}</b><Badge tone={isAdmin ? 'accent' : undefined}>{isAdmin ? '👑 Адмін' : 'Учасник'}</Badge></div>
        <div className="muted small" style={{ margin: '12px 0 6px' }}>Запрошення (натисніть, щоб скопіювати)</div>
        <button className="input tnum" style={{ textAlign: 'center', fontWeight: 700, color: 'var(--link)' }} onClick={() => copyToClipboard(link)}>{inviteCode} 📋</button>
        {isAdmin && <div style={{ marginTop: 8 }}><Button size="sm" variant="ghost" onClick={regenerate}>Згенерувати новий код</Button></div>}
      </Card>

      {families.length > 1 && (
        <Section title="Мої сім'ї">
          <Card flush>
            {families.map(f => <Row key={f.family_id} icon={f.is_active ? '✅' : '🏠'} title={f.name} sub={f.role === 'admin' ? 'Адмін' : 'Учасник'}
              end={f.is_active ? <Badge tone="ok">Активна</Badge> : undefined} onClick={f.is_active ? undefined : () => switchFamily(f)} />)}
          </Card>
        </Section>
      )}

      <Section title="Учасники">
        <Card flush>
          {familyUsers.map(u => (
            <div key={u.id} className="row" style={{ opacity: busyId === u.id ? 0.5 : 1 }}>
              <Avatar name={u.name} />
              <div className="row__body">
                <div className="row__title">{u.name}{u.id === me.id && <span className="muted small"> (ви)</span>}</div>
                <div className="row__sub">{u.role === 'admin' ? '👑 Адмін' : 'Учасник'}</div>
              </div>
              {isAdmin && u.id !== me.id && (
                <div className="hstack">
                  <Button size="sm" variant="secondary" onClick={() => changeRole(u, u.role === 'admin' ? 'member' : 'admin')}>{u.role === 'admin' ? 'Зняти адміна' : '👑'}</Button>
                  <Button size="sm" variant="danger" onClick={() => kick(u)}>✕</Button>
                </div>
              )}
            </div>
          ))}
        </Card>
      </Section>
      <Button variant="danger" onClick={leave} busy={leaving}>Вийти з сім'ї</Button>
    </>
  );
}

function MonoScreen({ hasMonoToken, onTokenSaved }: { hasMonoToken: boolean; onTokenSaved: () => void }) {
  const [token, setToken] = useState('');
  const [edit, setEdit] = useState(!hasMonoToken);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!token.trim()) return;
    setBusy(true);
    try { await api.put('/users/me/token', { mono_token: token.trim() }); setToken(''); setEdit(false); onTokenSaved(); toast('Токен збережено'); }
    catch { toast('Не вдалося зберегти токен', 'err'); }
    setBusy(false);
  };
  return (
    <Card>
      {!edit ? (
        <div className="stack-s center">
          <div className="pos bold" style={{ fontSize: 17 }}>✅ Автопілот підключено</div>
          <div className="muted small">Операції з картки автоматично з'являються в боті й у «Розібрати».</div>
          <Button variant="secondary" onClick={() => setEdit(true)}>Змінити токен</Button>
        </div>
      ) : (
        <div className="stack-s">
          <Field label="Токен з api.monobank.ua" hint="Токен шифрується і використовується лише для отримання операцій.">
            <input className="input" type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="Вставте токен" />
          </Field>
          <div className="btn-row">
            {hasMonoToken && <Button variant="secondary" onClick={() => setEdit(false)}>Скасувати</Button>}
            <Button onClick={save} busy={busy} disabled={!token.trim()}>Зберегти</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
