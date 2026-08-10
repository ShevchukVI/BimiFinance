export interface Transaction { id: number; amount: number; type: string; title: string; account: string; date: string; category_id: number; note: string; user_name?: string | null; }
export interface Category { id: number; name: string; icon: string; type: string; }
export interface CashUserBalance { user_id: number; user_name: string; balance: number; }
export interface Stats { income: number; expense: number; balance: number; top_categories: { name: string; amount: number }[]; pending_count: number; balances: Record<string, number>; cash_by_user?: CashUserBalance[]; }
export interface Note { id: number; content: string; }
export interface Jar { id: number; name: string; balance: number; goal: number; }
export interface FamilyMembership { family_id: number; name: string; role: string; is_active: boolean; }
export interface FamilyUser { id: number; tg_id: number | null; name: string; has_mono_token: boolean; role: string | null; }
export interface BankAccountBalance { name: string; balance: number; currency: string; }
export interface BankUserBalances { user_id: number; user_name: string; provider: string; accounts: BankAccountBalance[]; }
export interface Me { id: number; tg_id: number | null; name: string; has_mono_token: boolean; current_active_family_id: number | null; family_id: number | null; role: string | null; }

export const COLORS = ['#3498db', '#e74c3c', '#2ecc71', '#f1c40f', '#9b59b6', '#34495e', '#e67e22', '#1abc9c', '#f39c12', '#d35400'];

export type Tab = 'home' | 'transactions' | 'jars' | 'notes' | 'analytics' | 'settings';

export const COLORS_AVATAR = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6'];

export const cleanCatName = (name?: string) =>
  (name || '').replace(/^[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐ0-9]+/, '').trim() || 'Інше';

export const fmt = (n: number) => `${n.toLocaleString('uk-UA')} ₴`;
