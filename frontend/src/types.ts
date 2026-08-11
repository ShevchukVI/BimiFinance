export interface Transaction { id: number; amount: number; type: string; title: string; account: string; date: string; category_id: number; note: string; user_name?: string | null; currency?: string; jar_id?: number | null; }
export interface Category { id: number; name: string; icon: string; type: string; }
export interface CashUserBalance { user_id: number; user_name: string; balance: number; currency?: string; }
export interface Stats { income: number; expense: number; balance: number; top_categories: { name: string; amount: number }[]; pending_count: number; balances: Record<string, number>; cash_by_user?: CashUserBalance[]; by_currency?: Record<string, { income: number; expense: number }>; cash_by_currency?: { currency: string; balance: number }[]; }
export interface Note { id: number; content: string; }
export interface Jar { id: number; name: string; balance: number; goal: number; currency?: string; }
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

export const CURRENCY_SYMBOLS: Record<string, string> = { UAH: '₴', USD: '$', EUR: '€' };

export const curSym = (currency?: string | null) => CURRENCY_SYMBOLS[currency || 'UAH'] || currency || '₴';

const _num = (n: number | string | null | undefined): number => {
  const v = typeof n === 'number' ? n : parseFloat(String(n));
  return Number.isFinite(v) ? v : 0;
};

export const fmt = (n: number | string | null | undefined) => `${_num(n).toLocaleString('uk-UA')} ₴`;

export const fmtCur = (n: number | string | null | undefined, currency?: string | null) => {
  const sym = curSym(currency);
  return `${_num(n).toLocaleString('uk-UA')} ${sym}`;
};

export const CURRENCIES = ['UAH', 'USD', 'EUR'];

// Жорсткий порядок валют: UAH завжди перша, потім USD, EUR, далі решта (за назвою).
const CURRENCY_RANK: Record<string, number> = { UAH: 0, USD: 1, EUR: 2 };
export const sortCurrencies = (currencies: string[]) =>
  [...currencies].sort((a, b) => (CURRENCY_RANK[a] ?? 99) - (CURRENCY_RANK[b] ?? 99) || a.localeCompare(b));
