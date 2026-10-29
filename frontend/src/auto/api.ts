import api from '../api';
import type { AutoOverview, Hints, LogDraft, Suggestion, TxBrief, Vehicle, VehicleStats, VLog } from './types';

const fam = (fid: number) => `/families/${fid}`;

export const autoApi = {
  overview: (fid: number, inactive = false) => api.get<AutoOverview>(`${fam(fid)}/auto${inactive ? '?include_inactive=true' : ''}`).then(r => r.data),
  createVehicle: (fid: number, body: object) => api.post<Vehicle>(`${fam(fid)}/vehicles`, body).then(r => r.data),
  updateVehicle: (fid: number, id: number, body: object) => api.put<Vehicle>(`${fam(fid)}/vehicles/${id}`, body).then(r => r.data),
  removeVehicle: (fid: number, id: number) => api.delete<{ archived: boolean }>(`${fam(fid)}/vehicles/${id}`).then(r => r.data),
  stats: (fid: number, id: number, months: number) => api.get<VehicleStats>(`${fam(fid)}/vehicles/${id}/stats?months=${months}`).then(r => r.data),
  logs: (fid: number, id: number) => api.get<VLog[]>(`${fam(fid)}/vehicles/${id}/logs`).then(r => r.data),
  addLog: (fid: number, body: object) => api.post<VLog>(`${fam(fid)}/vehicle-logs`, body).then(r => r.data),
  updateLog: (fid: number, id: number, body: object) => api.put<VLog>(`${fam(fid)}/vehicle-logs/${id}`, body).then(r => r.data),
  deleteLog: (fid: number, id: number, withTx: boolean) => api.delete(`${fam(fid)}/vehicle-logs/${id}?delete_transaction=${withTx}`).then(r => r.data),
  suggestions: (fid: number) => api.get<Suggestion[]>(`${fam(fid)}/auto/suggestions`).then(r => r.data),
  draft: (fid: number, txId: number, vehicleId?: number) =>
    api.get<{ transaction: TxBrief; draft: LogDraft }>(`${fam(fid)}/auto/draft?tx_id=${txId}${vehicleId ? `&vehicle_id=${vehicleId}` : ''}`).then(r => r.data),
  accept: (fid: number, txIds: number[]) => api.post<{ added: number }>(`${fam(fid)}/auto/suggestions/accept`, { transaction_ids: txIds }).then(r => r.data),
  hints: (fid: number, id: number) => api.get<Hints>(`${fam(fid)}/vehicles/${id}/hints`).then(r => r.data),
  ignore: (fid: number, txId: number) => api.post(`${fam(fid)}/auto/ignore`, { transaction_id: txId }).then(r => r.data),
  importHistory: (fid: number, id: number) => api.post<{ linked: number; skipped: TxBrief[] }>(`${fam(fid)}/vehicles/${id}/import`).then(r => r.data),
};
