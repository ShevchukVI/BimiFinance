import api from '../api';
import type { Bill, BillDraft, HousingNote, Outages, Overview, Payment, Reading, Stats, Template } from './types';

const base = (fid: number) => `/housing/families/${fid}`;

export const errText = (e: any, fallback = 'Помилка') => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
};

export const housingApi = {
  overview: (fid: number) => api.get<Overview>(`${base(fid)}/overview`).then(r => r.data),
  templates: () => api.get<Template[]>('/housing/templates').then(r => r.data),
  setup: (fid: number, body: object) => api.post<Overview>(`${base(fid)}/setup`, body).then(r => r.data),
  profile: (fid: number, body: object) => api.put(`${base(fid)}/profile`, body).then(r => r.data),

  createProvider: (fid: number, body: object) => api.post(`${base(fid)}/providers`, body).then(r => r.data),
  updateProvider: (fid: number, id: number, body: object) => api.put(`${base(fid)}/providers/${id}`, body).then(r => r.data),
  deleteProvider: (fid: number, id: number) => api.delete<{ archived: boolean }>(`${base(fid)}/providers/${id}`).then(r => r.data),

  createMeter: (fid: number, body: object) => api.post(`${base(fid)}/meters`, body).then(r => r.data),
  updateMeter: (fid: number, id: number, body: object) => api.put(`${base(fid)}/meters/${id}`, body).then(r => r.data),
  deleteMeter: (fid: number, id: number) => api.delete(`${base(fid)}/meters/${id}`).then(r => r.data),
  readings: (fid: number, meterId: number) => api.get<Reading[]>(`${base(fid)}/meters/${meterId}/readings`).then(r => r.data),
  addReadings: (fid: number, body: object) => api.post<{ overview: Overview }>(`${base(fid)}/readings`, body).then(r => r.data),
  deleteReading: (fid: number, id: number) => api.delete(`${base(fid)}/readings/${id}`).then(r => r.data),

  bills: (fid: number, providerId?: number) => api.get<Bill[]>(`${base(fid)}/bills${providerId ? `?provider_id=${providerId}` : ''}`).then(r => r.data),
  draft: (fid: number, providerId: number, period?: string) =>
    api.get<BillDraft>(`${base(fid)}/bills/draft?provider_id=${providerId}${period ? `&period=${period}` : ''}`).then(r => r.data),
  createBill: (fid: number, body: object) => api.post<Bill>(`${base(fid)}/bills`, body).then(r => r.data),
  updateBill: (fid: number, id: number, body: object) => api.put<Bill>(`${base(fid)}/bills/${id}`, body).then(r => r.data),
  deleteBill: (fid: number, id: number) => api.delete(`${base(fid)}/bills/${id}`).then(r => r.data),

  payments: (fid: number, providerId?: number) => api.get<Payment[]>(`${base(fid)}/payments${providerId ? `?provider_id=${providerId}` : ''}`).then(r => r.data),
  pay: (fid: number, body: object) => api.post<{ payment: Payment; overview: Overview }>(`${base(fid)}/payments`, body).then(r => r.data),
  deletePayment: (fid: number, id: number, withTx: boolean) => api.delete(`${base(fid)}/payments/${id}?delete_transaction=${withTx}`).then(r => r.data),

  notes: (fid: number) => api.get<HousingNote[]>(`${base(fid)}/notes`).then(r => r.data),
  addNote: (fid: number, body: object) => api.post<HousingNote>(`${base(fid)}/notes`, body).then(r => r.data),
  deleteNote: (fid: number, id: number) => api.delete(`${base(fid)}/notes/${id}`).then(r => r.data),
  heating: (fid: number, on: boolean) => api.post(`${base(fid)}/heating`, { on }).then(r => r.data),

  stats: (fid: number, months: number) => api.get<Stats>(`${base(fid)}/stats?months=${months}`).then(r => r.data),
  outages: (fid: number, days: number) => api.get<Outages>(`${base(fid)}/outages?days=${days}`).then(r => r.data),
  syncOutages: (fid: number) => api.post(`${base(fid)}/outages/sync`).then(r => r.data),
};
