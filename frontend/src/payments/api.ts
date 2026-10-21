import api from '../api';
import type { Transaction } from '../types';

export type ObKind = 'installment' | 'loan' | 'subscription';
export type ObStatus = 'upcoming' | 'due_soon' | 'overdue' | 'finished' | 'charged' | 'missing' | 'stale';

export interface TxBrief { id: number; date: string; amount: number; title: string; account: string; }

export interface Obligation {
  id: number; kind: ObKind; name: string; icon: string; amount: number; currency: string; period: 'month' | 'year';
  due_day: number | null; first_due: string | null; payments_total: number | null; end_date: string | null;
  total_amount: number | null; paid_before: number; match_pattern: string; category_id: number | null;
  user_id: number | null; remind: boolean; is_active: boolean; note: string;
  state: {
    paid_count: number | null; payments_total: number | null; remaining_count: number | null; remaining_amount: number | null;
    next_due: string | null; last_date: string | null; last_amount: number | null; end: string | null; status: ObStatus;
    monthly: number; linked_count: number; expected?: string;
  };
  suggested: TxBrief[];
}

export interface ObList { items: Obligation[]; totals: { credits_monthly: number; subscriptions_monthly: number; remaining_total: number; suggested: number } }

export interface Upcoming { date: string; title: string; icon: string; amount: number; currency: string; kind: 'obligation' | 'housing'; id: number; status: string; sub: string; }

export interface LinkTarget { type: 'obligation' | 'provider'; id: number; name: string; icon: string; kind: string; hint?: string; match?: boolean; score?: number; progress?: string | null; }

export const payApi = {
  list: (fid: number, inactive = false) => api.get<ObList>(`/families/${fid}/obligations${inactive ? '?include_inactive=true' : ''}`).then(r => r.data),
  create: (fid: number, body: object) => api.post<Obligation>(`/families/${fid}/obligations`, body).then(r => r.data),
  update: (fid: number, id: number, body: object) => api.put<Obligation>(`/families/${fid}/obligations/${id}`, body).then(r => r.data),
  remove: (fid: number, id: number) => api.delete<{ archived: boolean }>(`/families/${fid}/obligations/${id}`).then(r => r.data),
  transactions: (fid: number, id: number) => api.get<Transaction[]>(`/families/${fid}/obligations/${id}/transactions`).then(r => r.data),
  linkSuggested: (fid: number, id: number) => api.post<{ linked: number }>(`/families/${fid}/obligations/${id}/link-suggested`).then(r => r.data),
  upcoming: (fid: number, days = 10) => api.get<Upcoming[]>(`/families/${fid}/upcoming?days=${days}`).then(r => r.data),
  link: (fid: number, txId: number) => api.get<{ current: LinkTarget | null; candidates: LinkTarget[] }>(`/families/${fid}/transactions/${txId}/link`).then(r => r.data),
  setLink: (fid: number, txId: number, type: string, id: number) =>
    api.post<{ current: LinkTarget; transaction: Transaction }>(`/families/${fid}/transactions/${txId}/link`, { type, id }).then(r => r.data),
  unlink: (fid: number, txId: number) => api.delete(`/families/${fid}/transactions/${txId}/link`).then(r => r.data),
  looseHousing: (fid: number) => api.get<{ providers: Record<string, TxBrief[]>; unassigned: TxBrief[] }>(`/families/${fid}/link-suggestions`).then(r => r.data),
};

export const KIND_LABEL: Record<ObKind, string> = { installment: 'Розстрочка', loan: 'Кредит', subscription: 'Підписка' };
