// Types of the /housing API (see backend app/api/housing.py).
export type HousingMode = 'rent' | 'mortgage' | 'own' | 'off';
export type Billing = 'metered' | 'fixed' | 'manual';

export interface HousingProfile {
  mode: HousingMode; title: string; area_m2: number | null; heating: string;
  svitlobot_channel: string | null; readings_day: number; reminders_enabled: boolean;
}

export interface RentHistoryItem { month: string; due: string; paid_on: string | null; days_late: number | null; status: 'paid' | 'overdue' | 'upcoming'; }

export interface ProviderBalance {
  debt: number; accrued_since: number; to_pay_now: number; next_bill_forecast: number | null;
  estimated: boolean; basis: string; next_due: string | null;
  last_bill: { id: number; period: string; to_pay: number; accrued: number } | null;
  last_payment: { date: string; amount: number } | null;
  paid_until?: string | null; next_charge?: { month: string; due: string; amount: number } | null;
  history?: RentHistoryItem[]; punctuality?: { months: number; late: number; max_days_late: number };
}

export interface Provider {
  id: number; name: string; service: string; icon: string; billing: Billing; fixed_amount: number | null;
  due_day: number | null; account_number: string; pay_url: string; start_date: string | null;
  opening_balance: number; note: string; is_active: boolean; sort_order: number;
}

export interface ProviderOverview extends Provider {
  balance: ProviderBalance; meter_ids: number[]; bills_count: number; warnings: number;
}

export interface MeterSummary {
  id: number; name: string; utility_type: string; unit: string; zone: string | null; provider_id: number | null;
  tariff: number | null; is_active: boolean; last_value: number | null; last_date: string | null;
  days_since_reading: number | null; daily_rate: number | null;
  since_billed_volume: number | null; since_billed_date: string | null; since_billed_cost: number | null;
  month_to_date: number | null; month_forecast: number | null; month_forecast_cost: number | null;
  last_year_month: number | null; heating_on: boolean;
}

export interface HousingAlert { level: 'warn' | 'info'; kind: 'readings' | 'pay' | 'bill'; text: string; provider_id?: number; }

export interface PowerSummary {
  channel: string; state: 'on' | 'off' | null; since: string | null; month_off_hours: number; month_outages: number;
  synced_at: string | null;
}

export interface Overview {
  today: string; profile: HousingProfile | null;
  totals: { to_pay_now: number; debt: number; accrued_since: number; next_month_forecast: number };
  providers: ProviderOverview[]; meters: MeterSummary[]; alerts: HousingAlert[];
  heating: { on: boolean; since: string | null; note_id: number | null };
  power: PowerSummary | null;
}

export interface BillFlag { level: 'warn' | 'info'; code: string; text: string; diff: number | null; }

export interface BillLine {
  id?: number; meter_id: number | null; label: string; prev_value: number | null; curr_value: number | null;
  volume: number | null; tariff: number | null; amount: number | null; estimated?: boolean;
}

export interface Bill {
  id: number; provider_id: number; period: string; issued_on: string | null; opening_balance: number; paid: number;
  accrued: number; adjustment: number; to_pay: number; consumption: number | null; note: string;
  lines: BillLine[]; flags: BillFlag[];
}

export interface BillDraft {
  provider_id: number; period: string; issued_on: string; opening_balance: number; paid: number; accrued: number;
  adjustment: number; to_pay: number; lines: BillLine[]; existing_id: number | null;
}

export interface Payment { id: number; provider_id: number; date: string; amount: number; note: string; user_name: string | null; transaction_id: number | null; }

export interface Reading { id: number; date: string; value: number; note: string; source: string; rate: number | null; }

export interface HousingNote { id: number; date: string; end_date: string | null; kind: string; text: string; provider_id: number | null; }

export interface Template { key: string; title: string; icon: string; service: string; meters: number; }

export interface StatsPoint { month: string; volume: number | null; cost: number | null; source: string | null; heating: boolean; partial: boolean; per_powered_hour?: number; }
export interface Stats {
  months: string[];
  meters: { meter_id: number; name: string; unit: string; utility_type: string; provider_id: number | null; points: StatsPoint[] }[];
  providers: { provider_id: number; name: string; icon: string; service: string; points: { month: string; accrued: number | null; paid: number; estimated: boolean }[] }[];
  power: { month: string; off_hours: number | null; outages: number | null; hours: number }[];
  insights: string[];
}

export interface Outages { channel: string | null; items: { id: number; started_at: string; ended_at: string | null; minutes: number }[]; daily: { date: string; off_hours: number }[]; }

export const SERVICE_LABELS: Record<string, string> = {
  electricity: 'Світло', gas: 'Газ', gas_delivery: 'Доставка газу', water: 'Вода', heating: 'Опалення',
  maintenance: 'Утримання будинку', waste: 'Вивіз сміття', internet: 'Інтернет', rent: 'Оренда', mortgage: 'Іпотека', other: 'Інше',
};

export const isFixedService = (s: string) => s === 'rent' || s === 'mortgage';
