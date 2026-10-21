import { Stats, Transaction, Category, BankUserBalances, Jar, sortCurrencies } from '../types';
import type { Overview } from '../housing/types';
import type { Upcoming } from '../payments/api';
import { approx, day, inMonth, money, todayIso } from '../format';
import { Badge, Banner, Card, Empty, Progress, Row, Section } from '../ui';
import { TxList } from '../components/TransactionCard';

const n = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);

export default function HomePage({
  stats, transactions, categories, bankBalances, jars, housing, upcoming,
  onOpenInbox, onUpcoming, onSeeAll, onAdd, onView, onHousing, onReadings, onJar, onJars,
}: {
  stats: Stats | null; transactions: Transaction[]; categories: Category[]; bankBalances: BankUserBalances[];
  jars: Jar[]; housing: Overview | null; upcoming: Upcoming[];
  onOpenInbox: () => void; onUpcoming: (u: Upcoming | null) => void; onSeeAll: () => void; onAdd: (type?: 'Витрати' | 'Поповнення') => void;
  onView: (tx: Transaction) => void; onHousing: () => void; onReadings: () => void; onJar: (j: Jar) => void; onJars: () => void;
}) {
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

  const actions = [
    { icon: '➖', label: 'Витрата', onClick: () => onAdd('Витрати') },
    { icon: '➕', label: 'Дохід', onClick: () => onAdd('Поповнення') },
    { icon: '🧹', label: 'Розібрати', onClick: onOpenInbox, badge: pending },
    hasMeters ? { icon: '📸', label: 'Показники', onClick: onReadings } : { icon: '🎯', label: 'Цілі', onClick: onJars },
  ];

  return (
    <div className="page">
      <Card className="hero">
        <div className="hero__label">Витрати у {inMonth(todayIso())}</div>
        <div className="hero__value tnum">{money(m.expense, main, 0)}</div>
        <div className="hero__sub">
          <span className="pos">+{money(m.income, main, 0)} дохід</span>
          <span>залишок {money(m.income - m.expense, main, 0)}</span>
        </div>
        {curs.filter(c => c !== main).map(c => (
          <div key={c} className="muted small" style={{ marginTop: 4 }}>
            {c}: <span className="pos">+{money(byCurrency[c].income, c)}</span> · −{money(byCurrency[c].expense, c)}
          </div>
        ))}
        <div className="actions" style={{ marginTop: 16 }}>
          {actions.map(a => (
            <button key={a.label} className="action" onClick={a.onClick}>
              <span className="action__icon">{a.icon}{!!a.badge && <span className="action__badge">{a.badge > 99 ? '99+' : a.badge}</span>}</span>
              {a.label}
            </button>
          ))}
        </div>
      </Card>

      {pending > 0 && (
        <Banner icon="🧹" tone="warn" onClick={onOpenInbox}>
          <b>{pending} операцій без категорії</b><div className="muted small">Розкладіть за хвилину — так аналітика буде точною</div>
        </Banner>
      )}

      {(cash.size > 0 || bankBalances.length > 0) && (
        <Section title="Рахунки">
          <Card flush>
            {[...cash.entries()].map(([uid, u]) => (
              <Row key={`c${uid}`} icon="💵" title="Готівка" sub={u.name} end={<b>{fmtCurs(u.byCur)}</b>} />
            ))}
            {bankBalances.flatMap(u => u.accounts.map((a, i) => (
              <Row key={`b${u.user_id}-${i}`} icon="💳" title={a.name} sub={u.user_name}
                end={<b className={a.balance < 0 ? 'danger' : ''}>{money(a.balance, a.currency || 'UAH')}</b>} />
            )))}
          </Card>
        </Section>
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

      {housingOn && housing && (
        <Section title="Житло" action="Відкрити" onAction={onHousing}>
          <Card flush>
            <Row icon="🏡" iconAccent title={housing.totals.to_pay_now > 1 ? `До сплати ${approx(housing.totals.to_pay_now)}` : 'Все сплачено'}
              sub={housing.alerts[0]?.text || (housing.power ? (housing.power.state === 'off' ? '🔴 Немає світла' : '🟢 Світло є') : 'Комуналка, оренда, лічильники')}
              chevron onClick={onHousing} />
          </Card>
        </Section>
      )}

      {jars.length > 0 && (
        <Section title="Цілі" action="Усі" onAction={onJars}>
          <div className="chips--scroll" style={{ display: 'flex', gap: 8 }}>
            {jars.map(j => (
              <Card key={j.id} onClick={() => onJar(j)} className="" >
                <div style={{ width: 150 }} className="stack-s">
                  <div className="bold ellipsis">🎯 {j.name}</div>
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
