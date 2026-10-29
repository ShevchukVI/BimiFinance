export type Fuel = 'lpg' | 'petrol' | 'diesel' | 'electric';
export type LogKind = 'fuel' | 'service' | 'repair' | 'tires' | 'wash' | 'parking' | 'insurance' | 'fine' | 'other' | 'odometer';

export interface FuelStats {
  fills: number; liters: number; money: number; avg_per100: number | null; avg_km: number | null; estimated: number;
  last_per100: number | null; last_full_date: string | null; last_price: number | null; last_price_date: string | null;
  secondary: boolean; per_month_l: number | null; per_month_money: number | null; last_date: string;
}
export interface MonthPoint { month: string; fuel: number; maintenance: number; other: number; km: number | null; partial: boolean; }
export interface VehicleStats {
  odometer: number | null; odometer_date: string | null; fuels: Partial<Record<Fuel, FuelStats>>; months: MonthPoint[];
  month_spend: number; year_spend: number; total_spend: number; first_date: string | null; logs: number;
  km_tracked: number | null; km_per_month: number | null; cost_per_km: number | null; fuel_cost_per_km: number | null;
  prices?: { date: string; fuel: Fuel; price: number }[];
}
export interface Vehicle {
  id: number; name: string; icon: string; plate: string; fuel: Fuel; fuel2: Fuel | null; tank_l: number | null; tank2_l: number | null;
  start_odometer: number | null; match_pattern: string; user_id: number | null; driver_ids: number[]; is_active: boolean; note: string; stats: VehicleStats; documents?: VDoc[];
}
export type DocKind = 'osago' | 'kasko' | 'green_card' | 'other';
export interface VDoc {
  id: number; vehicle_id: number; kind: DocKind; icon: string; label: string; company: string; number: string;
  start_date: string | null; end_date: string | null; amount: number | null; url: string; note: string; log_id: number | null;
  has_file: boolean; file_name: string | null; days_left: number | null; status: 'active' | 'soon' | 'expired';
}
export const DOC_KINDS: { value: DocKind; icon: string; label: string; short: string }[] = [
  { value: 'osago', icon: '🛡️', label: 'Автоцивілка (ОСЦПВ)', short: 'Автоцивілка' },
  { value: 'kasko', icon: '💎', label: 'КАСКО', short: 'КАСКО' },
  { value: 'green_card', icon: '🌍', label: 'Зелена карта', short: 'Зелена карта' },
  { value: 'other', icon: '📄', label: 'Інший поліс', short: 'Інше' },
];
export interface TxBrief { id: number; date: string; amount: number; title: string; account: string; note: string; }
export interface VLog {
  id: number; vehicle_id: number; date: string; kind: LogKind; icon: string; label: string; odometer: number | null;
  fuel: Fuel | null; liters: number | null; price: number | null; full_tank: boolean; amount: number; title: string; note: string;
  source: string; place: string; transaction_id: number | null; transaction: TxBrief | null; km_since: number | null;
  segment: { km: number; per100: number; estimated: boolean } | null; user_name: string | null;
}
export interface LogDraft {
  vehicle_id: number | null; kind: LogKind; date: string; amount: number; odometer: number | null; fuel: Fuel | null;
  liters: number | null; price: number | null; full_tank: boolean; title: string; transaction_id: number | null; foreign_fuel?: boolean;
  place?: string | null; predicted?: ('fuel' | 'price' | 'liters')[]; odometer_hint?: number | null; confidence?: 'sure' | 'maybe' | null;
}
export interface Suggestion { transaction: TxBrief; draft: LogDraft; }
export interface AutoOverview { vehicles: Vehicle[]; suggested: number; suggested_sure: number; }
export interface PlaceHint { name: string; count: number; last_date: string; prices: Partial<Record<Fuel, number>>; kind: LogKind; }
export interface Hints {
  places: PlaceHint[]; last_fuel: Fuel; odometer_estimate: number | null;
  fuels: Partial<Record<Fuel, { last_price: number | null; liters: number | null; amount: number | null; full_share: number }>>;
}

export const FUELS: Record<Fuel, { label: string; unit: string; icon: string; color: string }> = {
  lpg: { label: 'Газ', unit: 'л', icon: '🔵', color: '#3b82f6' },
  petrol: { label: 'Бензин', unit: 'л', icon: '🟠', color: '#f59e0b' },
  diesel: { label: 'Дизель', unit: 'л', icon: '⚫', color: '#64748b' },
  electric: { label: 'Електро', unit: 'кВт·год', icon: '⚡', color: '#10b981' },
};

export const KINDS: { value: LogKind; icon: string; label: string }[] = [
  { value: 'fuel', icon: '⛽', label: 'Заправка' }, { value: 'service', icon: '🛢️', label: 'ТО' },
  { value: 'repair', icon: '🔧', label: 'Ремонт' }, { value: 'tires', icon: '🛞', label: 'Шини' },
  { value: 'wash', icon: '🧽', label: 'Мийка' }, { value: 'parking', icon: '🅿️', label: 'Парковка' },
  { value: 'insurance', icon: '📄', label: 'Страховка' }, { value: 'fine', icon: '👮', label: 'Штраф' },
  { value: 'other', icon: '📦', label: 'Інше' }, { value: 'odometer', icon: '📍', label: 'Пробіг' },
];
export const kindMeta = (k: LogKind) => KINDS.find(x => x.value === k) || KINDS[8];
export const vehicleFuels = (v: Vehicle): Fuel[] => [v.fuel, ...(v.fuel2 ? [v.fuel2] : [])];
