import { useState } from 'react';
import { Stats, Transaction, Category, BankUserBalances, Jar, sortCurrencies } from '../types';
import type { Overview } from '../housing/types';
import type { Upcoming } from '../payments/api';
import type { Budgets, BudgetRow } from '../analytics/api';
import type { AutoOverview } from '../auto/types';
import { catIcon } from '../components/TransactionCard';
import { approx, day, money, monthName, plural, qty, todayIso } from '../format';
import { Badge, Banner, Card, Empty, Progress, Row, Section } from '../ui';
import { TxList } from '../components/TransactionCard';

const n = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);

export default function HomePage({
  stats, transactions, categories, bankBalances, jars, housing, auto, upcoming, budgets,
  onAuto, onAnalytics, onMono, hasBank, smartSure, onOpenInbox, onUpcoming, onBudgets, onEnvelope, onSeeAll, onAdd, onView, onHousing, onReadings, onJar, onJars,
}: {
  stats: Stats | null; transactions: Transaction[]; categories: Category[]; bankBalances: BankUserBalances[];
  jars: Jar[]; housing: Overview | null; auto: AutoOverview | null; onAuto: () => void; upcoming: Upcoming[]; budgets: Budgets | null;
  onOpenInbox: () => void; onUpcoming: (u: Upcoming | null) => void; onBudgets: () => void; onEnvelope: (b: BudgetRow) => void; onSeeAll: () => void; onAdd: (type?: 'Витрати' | 'Поповнення') => void;
  onView: (tx: Transaction) => void; onHousing: () => void; onReadings: () => void; onJar: (j: Jar) => void; onJars: () => void;
  onAnalytics: () => void; onMono: () => void; hasBank: boolean; smartSure: number;
}) {
  const [allEnv, setAllEnv] = useState(false);
  const pending = stats?.pending_count || 0;
  const byCurrency = stats?.by_currency || {};
  const curs = sortCurrencies(Object.keys(byCurrency));
  const main = curs[0] || 'UAH';
  const m = byCurrency[main] ? { income: n(byCurrency[main].income), expense: n(byCurrency[main].expense) }
    : { income: n(stats?.income), expense: n(stats?.expense) };
  const housingOn = !!housing?.profile && housing.profile.mode !== 'off';
  const hasMeters = housingOn && (housing?.meters.length || 0) > 0;

  // Готівка: (user, currency) → групуємо по користувачу
  const cash = new Map<number, { name: string; byCur: Record<string, number> }>();
  for (const u of stats?.cash_by_user || []) {
    const e = cash.get(u.user_id) || { name: u.user_name, byCur: {} };
    const c = u.currency || 'UAH';
    e.byCur[c] = n(e.byCur[c]) + n(u.balance);
    cash.set(u.user_id, e);
  }
  const fmtCurs = (byCur: Record<string, number>) => sortCurrencies(Object.keys(byCur)).map(c => money(byCur[c], c)).join(' · ');

  // «Гроші» як у банку: картки (власні кошти окремо від кредитного ліміту), готівка, відкладене
  const cards = bankBalances.flatMap(u => u.accounts.map(a => ({ ...a, user: u.user_name, cur: a.currency || 'UAH' })));
  const own: Record<string, number> = {};
  const add = (c: string, v: number) => { own[c] = n(own[c]) + n(v); };
  cards.forEach(a => add(a.cur, a.balance));
  cash.forEach(u => Object.entries(u.byCur).forEach(([c, v]) => add(c, v)));
  const ownCurs = sortCurrencies(Object.keys(own));
  const limit = cards.filter(a => a.cur === 'UAH').reduce((t, a) => t + n(a.credit_limit), 0);
  const creditLeft = cards.filter(a => a.cur === 'UAH' && n(a.credit_limit) > 0).reduce((t, a) => t + Math.min(n(a.credit_limit), Math.max(0, n(a.available))), 0);
  const creditUsed = limit - creditLeft;
  const saved = jars.filter(j => (j.currency || 'UAH') === 'UAH').reduce((t, j) => t + n(j.balance), 0);
  const people = new Set([...cards.map(a => a.user), ...[...cash.values()].map(u => u.name)]).size;

  const actions = [
    { icon: '➖', label: 'Витрата', onClick: () => onAdd('Витрати') },
    { icon: '➕', label: 'Дохід', onClick: () => onAdd('Поповнення') },
    { icon: '🧹', label: 'Розібрати', onClick: onOpenInbox, badge: pending },
    hasMeters ? { icon: '📸', label: 'Показники', onClick: onReadings } : { icon: '🎯', label: 'Цілі', onClick: onJars },
  ];

  return (
    <div className="page">
      <Card className="hero">
        <div className="hero__label">{people > 1 ? 'Гроші сім\'ї' : 'Мої гроші'}</div>
        <div className={`hero__value tnum ${n(own.UAH) < 0 ? 'danger' : ''}`}>{money(n(own.UAH), 'UAH', 0)}</div>
        <div className="hero__sub">
          {ownCurs.filter(c => c !== 'UAH').map(c => <span key={c}>+ {money(own[c], c, 0)}</span>)}
          {limit > 0 && <span>кредитний ліміт {money(creditLeft, 'UAH', 0)}{creditUsed > 1 ? ` з ${money(limit, 'UAH', 0)}` : ''}</span>}
        </div>
        <div className="money-list">
          {cards.map((a, i) => (
            <div key={`c${i}`} className="money-row">
              <span className="money-row__icon">💳</span>
              <span className="money-row__body">
                <span className="money-row__title">{a.name}{a.last4 ? <span className="muted"> ··{a.last4}</span> : null}</span>
                <span className="money-row__sub">{[people > 1 ? a.user : null, n(a.credit_limit) > 0 ? (a.balance < 0 ? `кредит ${money(-a.balance, a.cur, 0)}` : `+ ліміт ${money(a.credit_limit, a.cur, 0)}`) : null].filter(Boolean).join(' · ')}</span>
              </span>
              <b className={`tnum ${a.balance < 0 ? 'danger' : ''}`}>{money(a.balance, a.cur, 0)}</b>
            </div>
          ))}
          {[...cash.entries()].map(([uid, u]) => (
            <div key={`h${uid}`} className="money-row">
              <span className="money-row__icon">💵</span>
              <span className="money-row__body"><span className="money-row__title">Готівка</span>{people > 1 && <span className="money-row__sub">{u.name}</span>}</span>
              <b className="tnum">{fmtCurs(u.byCur)}</b>
            </div>
          ))}
          {jars.length > 0 && (
            <button className="money-row" onClick={onJars}>
              <span className="money-row__icon">🎯</span>
              <span className="money-row__body"><span className="money-row__title">Відкладено</span><span className="money-row__sub">{jars.length} {jars.length === 1 ? 'ціль' : 'цілі'} · не входить у суму вище</span></span>
              <b className="tnum">{money(saved, 'UAH', 0)}</b>
            </button>
          )}
          {stats?.work && (
            <div className="money-row">
              <span className="money-row__icon">💼</span>
              <span className="money-row__body"><span className="money-row__title">{stats.work.payer} винне</span><span className="money-row__sub">{stats.work.owed < 0 ? `їхній запас у вас ${money(-stats.work.owed, 'UAH', 0)}` : 'хостинги й послуги · поза сумою'}</span></span>
              <b className="tnum">{money(Math.max(0, stats.work.owed), 'UAH', 0)}</b>
            </div>
          )}
          {!hasBank && (
            <button className="money-row" onClick={onMono}>
              <span className="money-row__icon">🏦</span>
              <span className="money-row__body"><span className="money-row__title link">Підключити Monobank</span><span className="money-row__sub">Баланс карток і операції — самі</span></span>
            </button>
          )}
        </div>
        <div className="actions" style={{ marginTop: 14 }}>
          {actions.map(a => (
            <button key={a.label} className="action" onClick={a.onClick}>
              <span className="action__icon">{a.icon}{!!a.badge && <span className="action__badge">{a.badge > 99 ? '99+' : a.badge}</span>}</span>
              {a.label}
            </button>
          ))}
        </div>
      </Card>

      <button className="month-card" onClick={onAnalytics}>
        <div className="spread"><span className="muted small">{monthName(todayIso())}</span><span className="muted small">Аналітика ›</span></div>
        <div className="month-card__grid">
          <div><div className="muted xsmall">Витрати</div><b className="tnum">{money(m.expense, main, 0)}</b></div>
          <div><div className="muted xsmall">Дохід</div><b className="tnum pos">+{money(m.income, main, 0)}</b></div>
          <div><div className="muted xsmall">Різниця</div><b className={`tnum ${m.income - m.expense < 0 ? 'danger' : ''}`}>{money(m.income - m.expense, main, 0)}</b></div>
        </div>
        {curs.filter(c => c !== main).map(c => (
          <div key={c} className="muted xsmall" style={{ marginTop: 4 }}>{c}: +{money(byCurrency[c].income, c)} · −{money(byCurrency[c].expense, c)}</div>
        ))}
      </button>

      {pending > 0 && (
        <Banner icon={smartSure ? '✨' : '🧹'} tone={smartSure ? undefined : 'warn'} onClick={onOpenInbox}>
          <b>{pending} {plural(pending, 'операція', 'операції', 'операцій')} без категорії</b>
          <div className="muted small">{smartSure ? `${smartSure} Bimi розкладе одним дотиком — так ви вже робили` : 'Розкладіть за хвилину — так аналітика буде точною'}</div>
        </Banner>
      )}

      {upcoming.length > 0 && (
        <Section title="Найближчі платежі" action="Усі" onAction={() => onUpcoming(null)}>
          <Card flush>
            {upcoming.slice(0, 5).map(u => {
              const days = Math.round((new Date(`${u.date}T12:00:00`).getTime() - new Date(`${todayIso()}T12:00:00`).getTime()) / 86400000);
              const when = days < 0 ? <Badge tone="danger">прострочено</Badge> : days === 0 ? <Badge tone="warn">сьогодні</Badge> : days === 1 ? <Badge tone="warn">завтра</Badge> : null;
              return <Row key={`${u.kind}${u.id}${u.date}`} icon={u.icon} title={u.title} sub={<>{day(u.date)} · {u.sub}</>}
                end={<span className="stack-s" style={{ gap: 2, alignItems: 'flex-end' }}><b>{money(u.amount, u.currency, 0)}</b>{when}</span>} onClick={() => onUpcoming(u)} />;
            })}
          </Card>
        </Section>
      )}

      {budgets && budgets.items.length > 0 && (() => {
        const dim = budgets.days_left + new Date().getDate() || 30;
        const mark = ((dim - budgets.days_left) / dim) * 100;
        const rank = (b: BudgetRow) => (b.status === 'over' ? 2 : b.status === 'warn' ? 1 : 0) * 1000 + b.pct;
        const items = [...budgets.items].sort((x, y) => rank(y) - rank(x));
        const shown = allEnv ? items : items.slice(0, 4);
        const t = budgets.totals;
        const over = items.filter(b => b.status === 'over').length;
        return (
          <Section title={`Конверти · ще ${budgets.days_left} ${plural(budgets.days_left, 'день', 'дні', 'днів')}`} action="Налаштувати" onAction={onBudgets}>
            <Card flush>
              <div className="env-sum">
                <div className="spread">
                  <span className="muted small">Лишилось на місяць</span>
                  <span className="muted small tnum">з {money(t.amount, 'UAH', 0)}</span>
                </div>
                <div className={`env-sum__value tnum ${t.amount - t.spent < 0 ? 'danger' : ''}`}>{money(t.amount - t.spent, 'UAH', 0)}</div>
                <Progress value={t.amount ? (t.spent / t.amount) * 100 : 0} tone={t.spent > t.amount ? 'danger' : t.forecast > t.amount ? 'warn' : undefined} mark={mark} />
                <div className="muted xsmall" style={{ marginTop: 6 }}>
                  {[over ? `${over} ${plural(over, 'конверт перевищено', 'конверти перевищено', 'конвертів перевищено')}` : 'усі в межах',
                    t.forecast > t.amount ? `прогноз ${money(t.forecast, 'UAH', 0)}` : null].filter(Boolean).join(' · ')}
                </div>
              </div>
              {shown.map(b => {
                const cat = categories.find(c => c.id === b.category_id);
                const isOver = b.status === 'over';
                return (
                  <Row key={b.category_id} icon={catIcon(cat)} title={b.name.replace(/^\S+\s/, '')} onClick={() => onEnvelope(b)}
                    sub={<div className="env-row__bar"><Progress value={b.pct} tone={isOver ? 'danger' : b.status === 'warn' ? 'warn' : undefined} mark={mark} /></div>}
                    end={<div className="end-stack">
                      <b className={`tnum ${isOver ? 'danger' : ''}`}>{isOver ? '−' : ''}{money(Math.abs(b.remaining), 'UAH', 0)}</b>
                      <span className="muted xsmall tnum">{isOver ? 'перевищено' : b.per_day_left ? `${money(b.per_day_left, 'UAH', 0)}/день` : `з ${money(b.amount, 'UAH', 0)}`}</span>
                    </div>} />
                );
              })}
              {items.length > 4 && (
                <button className="row-more" onClick={() => setAllEnv(x => !x)}>{allEnv ? 'Згорнути' : `Усі ${items.length} конвертів`}</button>
              )}
            </Card>
          </Section>
        );
      })()}

      {housingOn && housing && (
        <Section title="Житло" action="Відкрити" onAction={onHousing}>
          <Card flush>
            <Row icon="🏡" iconAccent title={housing.totals.to_pay_now > 1 ? `До сплати ${approx(housing.totals.to_pay_now)}` : 'Все сплачено'}
              sub={housing.alerts[0]?.text || (housing.power ? (housing.power.state === 'off' ? '🔴 Немає світла' : '🟢 Світло є') : 'Комуналка, оренда, лічильники')}
              chevron onClick={onHousing} />
          </Card>
        </Section>
      )}

      {auto && auto.vehicles.length > 0 && (() => {
        const v = auto.vehicles[0];
        const main = v.stats.fuels[v.fuel];
        const fresh = auto.suggested_sure;
        const doc = (v.documents || []).find(d => d.status !== 'active');
        return (
          <Section title="Авто" action="Відкрити" onAction={onAuto}>
            <Card flush>
              {doc && <Row icon={doc.icon} iconAccent title={doc.status === 'expired' ? `${doc.label} закінчилась` : `${doc.label}: ще ${doc.days_left} ${plural(doc.days_left || 0, 'день', 'дні', 'днів')}`}
                sub={<span className={doc.status === 'expired' ? 'danger' : 'warn'}>{doc.status === 'expired' ? 'Оформіть новий поліс' : `до ${day(doc.end_date)} — час продовжити`}</span>} chevron onClick={onAuto} />}
              <Row icon={fresh ? '⛽' : v.icon} iconAccent
                title={fresh ? `${fresh} ${plural(fresh, 'нова заправка', 'нові заправки', 'нових заправок')} з банку` : v.name}
                sub={fresh ? 'Додати в журнал одним дотиком' : [v.stats.odometer ? `${qty(v.stats.odometer, 0)} км` : null,
                  main?.avg_per100 ? `${main.avg_per100.toFixed(1).replace('.', ',')} л/100` : null,
                  `${money(v.stats.month_spend, 'UAH', 0)} цього місяця`].filter(Boolean).join(' · ')}
                chevron onClick={onAuto} />
            </Card>
          </Section>
        );
      })()}

      {jars.length > 0 && (
        <Section title="Цілі" action="Усі" onAction={onJars}>
          <div className="chips--scroll" style={{ display: 'flex', gap: 8 }}>
            {jars.map(j => (
              <Card key={j.id} onClick={() => onJar(j)} className={jars.length === 1 ? 'grow' : ''}>
                <div style={{ width: jars.length === 1 ? 'auto' : 150 }} className="stack-s">
                  <div className="bold ellipsis">{j.mono_jar_id ? '🏦' : '🎯'} {j.name}</div>
                  <div className="small tnum">{money(j.balance, j.currency, 0)} <span className="muted">/ {money(j.goal, j.currency, 0)}</span></div>
                  <Progress value={j.goal ? (j.balance / j.goal) * 100 : 0} />
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      <Section title="Останні операції" action="Усі" onAction={onSeeAll}>
        {transactions.length === 0
          ? <Empty icon="💸" title="Тут з'являться ваші операції" text="Додайте першу витрату або напишіть боту «150 таксі»." action="Додати" onAction={() => onAdd()} />
          : <TxList transactions={transactions.slice(0, 6)} categories={categories} onView={onView} />}
      </Section>
    </div>
  );
}
