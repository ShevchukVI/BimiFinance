// Shared formatting (uk-UA): money, dates, months.
import { curSym } from './types';

const num = (n: unknown): number => {
  const v = typeof n === 'number' ? n : parseFloat(String(n));
  return Number.isFinite(v) ? v : 0;
};

/** 1 045,44 ₴ — up to 2 decimals, no trailing zeros. */
export const money = (n: unknown, currency = 'UAH', digits = 2) =>
  `${num(n).toLocaleString('uk-UA', { maximumFractionDigits: digits })} ${curSym(currency)}`;

/** ≈ 698 ₴ — rounded estimate. */
export const approx = (n: unknown, currency = 'UAH') => `≈ ${money(Math.round(num(n)), currency, 0)}`;

export const signed = (n: unknown, currency = 'UAH') => {
  const v = num(n);
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${money(Math.abs(v), currency)}`;
};

export const qty = (n: unknown, digits = 2) => num(n).toLocaleString('uk-UA', { maximumFractionDigits: digits });

export const parseNum = (s: string): number => parseFloat(String(s).replace(/\s/g, '').replace(',', '.'));

const toDate = (iso: string) => new Date(iso.length <= 10 ? `${iso}T12:00:00` : iso);

/** 4 жовт. */
export const day = (iso?: string | null) =>
  iso ? toDate(iso).toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' }) : '—';

/** 04.10.2026 */
export const dmy = (iso?: string | null) =>
  iso ? toDate(iso).toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';

/** 21:13 (local) */
export const hm = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' }) : '—';

const MONTHS = ['Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень', 'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень'];
const MONTHS_SHORT = ['січ', 'лют', 'бер', 'кві', 'тра', 'чер', 'лип', 'сер', 'вер', 'жов', 'лис', 'гру'];
const MONTHS_GEN = ['січні', 'лютому', 'березні', 'квітні', 'травні', 'червні', 'липні', 'серпні', 'вересні', 'жовтні', 'листопаді', 'грудні'];

export const monthName = (iso: string) => MONTHS[Number(iso.slice(5, 7)) - 1] || iso;
export const monthShort = (iso: string) => MONTHS_SHORT[Number(iso.slice(5, 7)) - 1] || iso;
/** «у жовтні» */
export const inMonth = (iso: string) => MONTHS_GEN[Number(iso.slice(5, 7)) - 1] || iso;
export const monthYear = (iso: string) => `${monthName(iso)} ${iso.slice(0, 4)}`;

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

export const addMonthsIso = (iso: string, n: number) => {
  const y = Number(iso.slice(0, 4)), m = Number(iso.slice(5, 7)) - 1 + n;
  const d = new Date(y, m, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
};

/** «Сьогодні», «Вчора», «15 жовтня», «15 жовтня 2025» — list date headers. */
export const dateHeader = (iso: string) => {
  const t = todayIso();
  if (iso === t) return 'Сьогодні';
  const y = new Date(); y.setDate(y.getDate() - 1);
  const yIso = `${y.getFullYear()}-${String(y.getMonth() + 1).padStart(2, '0')}-${String(y.getDate()).padStart(2, '0')}`;
  if (iso === yIso) return 'Вчора';
  const opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long' };
  if (iso.slice(0, 4) !== t.slice(0, 4)) opts.year = 'numeric';
  return toDate(iso).toLocaleDateString('uk-UA', opts);
};

export const plural = (n: number, one: string, few: string, many: string) => {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b === 1) return one;
  if (b >= 2 && b <= 4) return few;
  return many;
};

export const hoursText = (h: number) => {
  const total = Math.round(h * 60);
  const hh = Math.floor(total / 60), mm = total % 60;
  return hh ? `${hh} год${mm ? ` ${mm} хв` : ''}` : `${mm} хв`;
};
