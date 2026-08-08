export interface Transaction { id: number; amount: number; type: string; title: string; account: string; date: string; category_id: number; note: string; }
export interface Category { id: number; name: string; icon: string; type: string; }
export interface Stats { income: number; expense: number; balance: number; top_categories: { name: string; amount: number }[]; }
export interface Note { id: number; content: string; }
export interface Jar { id: number; name: string; balance: number; goal: number; }

export const COLORS = ['#3498db', '#e74c3c', '#2ecc71', '#f1c40f', '#9b59b6', '#34495e', '#e67e22', '#1abc9c', '#f39c12', '#d35400'];

export type Tab = 'transactions' | 'jars' | 'notes' | 'analytics' | 'settings';

export const COLORS_AVATAR = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6'];
