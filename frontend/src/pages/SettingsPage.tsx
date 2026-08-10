import { useState } from 'react';
import api from '../api';
import { toast } from '../toast';
import Avatar from '../components/Avatar';
import { FamilyMembership, FamilyUser } from '../types';

const cardStyle: React.CSSProperties = { backgroundColor: '#fff', padding: '20px', borderRadius: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' };

export default function SettingsPage({
  me, families, familyId, familyName, inviteCode, familyUsers, hasMonoToken,
  onSwitchFamily, onInviteRegenerated, onMemberRemoved, onTokenSaved, copyToClipboard,
}: {
  me: { id: number; name: string; role: string | null };
  families: FamilyMembership[];
  familyId: number;
  familyName: string;
  inviteCode: string;
  familyUsers: FamilyUser[];
  hasMonoToken: boolean;
  onSwitchFamily: (familyId: number) => void;
  onInviteRegenerated: (code: string) => void;
  onMemberRemoved: (userId: number) => void;
  onTokenSaved: () => void;
  copyToClipboard: (text: string) => void;
}) {
  const isAdmin = me.role === 'admin';
  const [monoToken, setMonoToken] = useState('');
  const [showTokenInput, setShowTokenInput] = useState(false);
  const [switching, setSwitching] = useState<number | null>(null);

  const switchFamily = async (f: FamilyMembership) => {
    if (f.is_active || switching) return;
    setSwitching(f.family_id);
    try {
      await api.patch('/users/me/active-family', { family_id: f.family_id });
      onSwitchFamily(f.family_id);
      toast(`✅ Активна сім'я: ${f.name}`);
    } catch {
      toast('Не вдалося перемкнути сім\'ю', 'err');
    }
    setSwitching(null);
  };

  const regenerateInvite = async () => {
    if (!window.confirm('Старий код перестане працювати. Згенерувати новий?')) return;
    try {
      const r = await api.post(`/families/${familyId}/regenerate-invite`);
      onInviteRegenerated(r.data.invite_code);
      toast('✅ Новий код згенеровано');
    } catch {
      toast('Помилка генерації', 'err');
    }
  };

  const removeMember = async (u: FamilyUser) => {
    if (!window.confirm(`Видалити ${u.name} з сім'ї?`)) return;
    try {
      await api.delete(`/families/${familyId}/users/${u.id}`);
      onMemberRemoved(u.id);
      toast('🗑 Учасника видалено');
    } catch {
      toast('Помилка видалення', 'err');
    }
  };

  const saveToken = async () => {
    if (!monoToken.trim()) return;
    try {
      await api.put('/users/me/token', { mono_token: monoToken.trim() });
      setMonoToken('');
      setShowTokenInput(false);
      onTokenSaved();
      toast('✅ Токен збережено');
    } catch {
      toast('Не вдалося зберегти токен', 'err');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 4px 0', color: '#2c3e50' }}>🏠 Сім'я: {familyName}</h3>
        <p style={{ margin: '0 0 12px 0', color: '#7f8c8d', fontSize: '13px' }}>
          Ваша роль: <b>{isAdmin ? '👑 Адмін' : 'Учасник'}</b>
        </p>

        {families.length > 1 && (
          <>
            <p style={{ margin: '0 0 8px 0', color: '#7f8c8d', fontSize: '13px' }}>Мої сім'ї:</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '15px' }}>
              {families.map(f => (
                <div key={f.family_id} onClick={() => switchFamily(f)}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', borderRadius: '10px', cursor: f.is_active ? 'default' : 'pointer', backgroundColor: f.is_active ? '#ebf5fb' : '#f8f9fa', border: f.is_active ? '1px solid #3498db' : '1px solid transparent', opacity: switching === f.family_id ? 0.5 : 1 }}>
                  <span style={{ color: '#2c3e50', fontWeight: f.is_active ? 'bold' : 'normal' }}>{f.name}</span>
                  <span style={{ fontSize: '12px', color: '#7f8c8d' }}>{f.role === 'admin' ? '👑' : ''} {f.is_active ? '✅ Активна' : 'Перемкнути'}</span>
                </div>
              ))}
            </div>
          </>
        )}

        <p style={{ margin: '0 0 10px 0', color: '#7f8c8d', fontSize: '13px' }}>Код запрошення (натисни, щоб скопіювати):</p>
        <div onClick={() => copyToClipboard(`https://t.me/bimipal_bot?start=join_${inviteCode}`)} style={{ backgroundColor: '#f1f2f6', padding: '12px', borderRadius: '8px', fontFamily: 'monospace', color: '#3498db', cursor: 'pointer', textAlign: 'center', fontWeight: 'bold' }}>{inviteCode} 📋</div>
        {isAdmin && <button onClick={regenerateInvite} style={{ width: '100%', padding: '10px', marginTop: '10px', backgroundColor: 'transparent', color: '#e67e22', border: '1px solid #e67e22', borderRadius: '8px', fontWeight: 'bold', fontSize: '13px', cursor: 'pointer' }}>Згенерувати новий код</button>}

        <h4 style={{ margin: '20px 0 10px 0', color: '#2c3e50' }}>Учасники ({familyUsers.length}):</h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {familyUsers.map(u => (
            <div key={u.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#f9f9f9', padding: '10px', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Avatar name={u.name} />
                <span style={{ color: '#2c3e50', fontWeight: '500' }}>
                  {u.role === 'admin' ? '👑 ' : ''}{u.name} {u.id === me.id ? '(Ви)' : ''}
                </span>
              </div>
              {u.id !== me.id && isAdmin && <button onClick={() => removeMember(u)} style={{ border: 'none', background: 'transparent', color: '#e74c3c', fontSize: '18px', cursor: 'pointer' }}>✖</button>}
            </div>
          ))}
        </div>
      </div>

      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 10px 0', color: '#2c3e50' }}>📤 Експорт даних</h3>
        <p style={{ margin: '0 0 15px 0', color: '#7f8c8d', fontSize: '13px' }}>
          Вивантаж свої транзакції у файл для зручного аналізу.
        </p>
        <button
          onClick={() => toast("Функція з'явиться в наступних оновленнях")}
          style={{ width: '100%', padding: '14px', backgroundColor: '#27ae60', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '15px', cursor: 'pointer' }}
        >📊 Експорт в Excel (Скоро)</button>
      </div>

      <div style={cardStyle}>
        <h3 style={{ margin: '0 0 10px 0', color: '#2c3e50' }}>💳 Monobank Автопілот</h3>
        {hasMonoToken && !showTokenInput ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
            <div style={{ color: '#27ae60', fontWeight: 'bold', fontSize: '16px' }}>✅ Підключено</div>
            <p style={{ margin: 0, color: '#7f8c8d', fontSize: '12px', textAlign: 'center' }}>Операції по картці автоматично з'являються у боті</p>
            <button onClick={() => setShowTokenInput(true)} style={{ width: '100%', padding: '10px', backgroundColor: '#ecf0f1', color: '#34495e', border: 'none', borderRadius: '10px', fontWeight: 'bold', cursor: 'pointer' }}>Змінити токен</button>
          </div>
        ) : (
          <>
            <p style={{ margin: '0 0 15px 0', color: '#7f8c8d', fontSize: '13px' }}>Вставте токен з api.monobank.ua</p>
            <input type="password" value={monoToken} onChange={e => setMonoToken(e.target.value)} placeholder="Введіть токен..." style={{ width: '100%', padding: '12px', borderRadius: '10px', border: '1px solid #dfe6e9', marginBottom: '10px', boxSizing: 'border-box' }} />
            <div style={{ display: 'flex', gap: '10px' }}>
              {hasMonoToken && <button onClick={() => setShowTokenInput(false)} style={{ flex: 1, padding: '12px', backgroundColor: '#ecf0f1', color: '#7f8c8d', border: 'none', borderRadius: '10px', fontWeight: 'bold', cursor: 'pointer' }}>Скасувати</button>}
              <button onClick={saveToken} style={{ flex: 2, padding: '12px', backgroundColor: '#3498db', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: 'bold', cursor: 'pointer' }}>Зберегти</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
