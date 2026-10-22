import api from '../api';
import type { Transaction } from '../types';

export interface CatRow { category_id: number | null; name: string; amount: number; prev: number; avg3: number; budget: number | null; share: number; pending: boolean; }
export interface MonthAnalytics {
  month: string; is_current: boolean; days_elapsed: number; days_in_month: number;
  income: number; expense: number; balance: number; prev: { income: number; expense: number };
  avg3_expense: number; forecast_expense: number | null; other_currencies: Record<string, { income: number; expense: number }>;
  categories: CatRow[]; daily: { date: string; expense: number }[]; by_user: { name: string; expense: number }[];
  top_merchants: { title: string; amount: number; count: number }[];
  trend: { month: string; income: number; expense: number }[]; budget_total: number | null; insights: string[];
}
export type BudgetStatus = 'ok' | 'warn' | 'over';
export interface BudgetRow { category_id: number; name: string; amount: number; spent: number; remaining: number; pct: number; forecast: number; status: BudgetStatus; per_day_left: number | null; }
export interface Budgets { month: string; days_left: number; items: BudgetRow[]; totals: { amount: number; spent: number; forecast: number } }
export interface Suggestion { category_id: number; name: string; avg3: number; suggested: number; current: number | null; }

export const anApi = {
  month: (fid: number, month?: string) => api.get<MonthAnalytics>(`/families/${fid}/analytics${month ? `?month=${month.slice(0, 7)}` : ''}`).then(r => r.data),
  budgets: (fid: number, month?: string) => api.get<Budgets>(`/families/${fid}/budgets${month ? `?month=${month.slice(0, 7)}` : ''}`).then(r => r.data),
  suggest: (fid: number) => api.get<Suggestion[]>(`/families/${fid}/budgets/suggest`).then(r => r.data),
  saveBulk: (fid: number, items: { category_id: number; amount: number | null }[]) => api.post<Budgets>(`/families/${fid}/budgets/bulk`, { items }).then(r => r.data),
  categoryTx: (fid: number, month: string, categoryId: number | null) =>
    api.get<Transaction[]>(`/families/${fid}/transactions?month=${month.slice(0, 7)}&type=Витрати&limit=500${categoryId !== null ? `&category_id=${categoryId}` : ''}`).then(r => r.data),
};
