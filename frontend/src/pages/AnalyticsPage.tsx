import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, Cell, ComposedChart, Line, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { toast } from '../toast';
import { COLORS, Category, Transaction, cleanCatName } from '../types';
import { addMonthsIso, inMonth, money, monthName, monthShort, monthYear, plural, todayIso } from '../format';
import { Banner, Button, Card, Empty, IconButton, Progress, Row, Section, Spinner } from '../ui';
import { errText } from '../housing/api';
import { cssVar } from '../housing/chart';
import { catIcon } from '../components/TransactionCard';
import { anApi, BudgetRow, Budgets, CatRow, MonthAnalytics } from '../analytics/api';
import BudgetsSheet from '../analytics/BudgetsSheet';
import CategorySheet from '../analytics/CategorySheet';

const pctDelta = (cur: number, base: number) => (base ? Math.round((cur / base - 1) * 100) : null);
const tone = (b?: BudgetRow) => (b?.status === 'over' ? 'danger' : b?.status === 'warn' ? 'warn' : undefined);

export default function AnalyticsPage({ familyId, categories, onView, onBudgetsChanged }: {
  familyId: number; categories: Category[]; onView: (t: Transaction) => void; onBudgetsChanged?: (b: Budgets) => void;
}) {
  const thisMonth = todayIso().slice(0, 7) + '-01';
  const [month, setMonth] = useState(thisMonth);
  const [data, setData] = useState<MonthAnalytics | null>(null);
  const [budgets, setBudgets] = useState<Budgets | null>(null);
  const [editBudgets, setEditBudgets] = useState(false);
  const [openCat, setOpenCat] = useState<CatRow | null>(null);
  const [allCats, setAllCats] = useState(false);

  useEffect(() => {
    let alive = true;
    setData(null);
    Promise.all([anApi.month(familyId, month), anApi.budgets(familyId, month)])
      .then(([a, b]) => { if (alive) { setData(a); setBudgets(b); } })
      .catch(e => toast(errText(e, 'Не вдалося завантажити аналітику'), 'err'));
    return () => { alive = false; };
  }, [familyId, month]);

  const budgetBy = useMemo(() => new Map((budgets?.items || []).map(b => [b.category_id, b])), [budgets]);
  const catBy = useMemo(() => new Map(categories.map(c => [c.id, c])), [categories]);
  const hint = cssVar('--hint');
  const accent = cssVar('--accent', '#3b82f6');
  const timeMark = data && data.is_current ? (data.days_elapsed / data.days_in_month) * 100 : undefined;

  const nav = (
    <div className="spread">
      <IconButton label="Попередній місяць" onClick={() => setMonth(addMonthsIso(month, -1))}>‹</IconButton>
      <div className="center"><div className="bold" style={{ fontSize: 17 }}>{monthYear(month)}</div>
        {month !== thisMonth && <button className="link small" onClick={() => setMonth(thisMonth)}>до поточного</button>}</div>
      {month < thisMonth ? <IconButton label="Наступний місяць" onClick={() => setMonth(addMonthsIso(month, 1))}>›</IconButton> : <span style={{ width: 36 }} />}
    </div>
  );

  if (!data) return <div className="page"><h1 className="page-title">Аналітика</h1>{nav}<Spinner /></div>;

  const dExp = pctDelta(data.expense, data.prev.expense);
  const cats = data.categories.filter(c => c.amount > 0 || c.budget);
  const shown = allCats ? cats : cats.slice(0, 8);
  const pie = cats.filter(c => c.amount > 0).slice(0, 8);
  const trend = data.trend.map(t => ({ ...t, label: monthShort(t.month), sel: t.month === month }));
  let run = 0;
  const daily = Array.from({ length: data.days_in_month }, (_, i) => {
    const d = `${month.slice(0, 8)}${String(i + 1).padStart(2, '0')}`;
    const v = data.daily.find(x => x.date === d)?.expense || 0;
    run += v;
    return { day: i + 1, v, cum: i < (data.is_current ? data.days_elapsed : data.days_in_month) ? Math.round(run) : null };
  });

  return (
    <div className="page">
      <h1 className="page-title">Аналітика</h1>
      {nav}

      <Card className="hero">
        <div className="hero__label">Витрати {month === thisMonth ? `у ${inMonth(month)}` : `за ${monthName(month).toLowerCase()}`}</div>
        <div className="hero__value tnum">{money(data.expense, 'UAH', 0)}</div>
        <div className="hero__sub">
          {dExp !== null && <span className={dExp > 0 ? 'danger' : 'pos'}>{dExp > 0 ? '↑' : '↓'} {Math.abs(dExp)}% до {monthShort(addMonthsIso(month, -1))}</span>}
          {data.forecast_expense && <span>прогноз ≈ {money(data.forecast_expense, 'UAH', 0)}</span>}
          {data.avg3_expense > 0 && <span>звично ≈ {money(data.avg3_expense, 'UAH', 0)}</span>}
        </div>
        <div className="grid2" style={{ marginTop: 14 }}>
          <div className="tile"><div className="tile__label">Дохід</div><div className="tile__value pos">+{money(data.income, 'UAH', 0)}</div></div>
          <div className="tile"><div className="tile__label">Залишок</div><div className={`tile__value ${data.balance < 0 ? 'danger' : ''}`}>{money(data.balance, 'UAH', 0)}</div></div>
        </div>
        {Object.entries(data.other_currencies).map(([cur, v]) => (
          <div key={cur} className="muted small" style={{ marginTop: 6 }}>{cur}: <span className="pos">+{money(v.income, cur)}</span> · −{money(v.expense, cur)}</div>
        ))}
      </Card>

      {data.insights.length > 0 && (
        <Card>
          <div className="muted small" style={{ marginBottom: 6 }}>💡 Варто знати</div>
          <ul className="insights">{data.insights.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </Card>
      )}

      <Section title="12 місяців">
        <Card>
          <div style={{ height: 170 }}>
            <ResponsiveContainer>
              <BarChart data={trend} margin={{ top: 6, right: 0, left: -10, bottom: 0 }} onClick={(e: any) => { const m = e?.activePayload?.[0]?.payload?.month; if (m && m <= thisMonth) setMonth(m); }}>
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} interval={0} />
                <YAxis tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={44} tickFormatter={(v: number) => (v >= 1000 ? `${Math.round(v / 1000)}к` : String(v))} />
                <Tooltip cursor={{ fill: 'transparent' }} formatter={(v: any, n: any) => [money(v, 'UAH', 0), n === 'income' ? 'Дохід' : 'Витрати']} labelFormatter={() => ''} />
                <Bar isAnimationActive={false} dataKey="income" radius={[3, 3, 0, 0]}>{trend.map((t, i) => <Cell key={i} fill="#22a356" fillOpacity={t.sel ? 1 : 0.45} />)}</Bar>
                <Bar isAnimationActive={false} dataKey="expense" radius={[3, 3, 0, 0]}>{trend.map((t, i) => <Cell key={i} fill={accent} fillOpacity={t.sel ? 1 : 0.45} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-legend"><span><i className="dot" style={{ background: '#22a356' }} />дохід</span><span><i className="dot" style={{ background: accent }} />витрати</span><span>торкніться місяця, щоб відкрити</span></div>
        </Card>
      </Section>

      <Section title={data.budget_total ? 'Витрати наростаючим підсумком' : 'Витрати по днях'}>
        <Card>
          <div style={{ height: 160 }}>
            <ResponsiveContainer>
              <ComposedChart data={daily} margin={{ top: 6, right: 0, left: -10, bottom: 0 }}>
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} interval={4} />
                <YAxis tick={{ fontSize: 10, fill: hint }} axisLine={false} tickLine={false} width={44} tickFormatter={(v: number) => (v >= 1000 ? `${Math.round(v / 1000)}к` : String(v))} />
                <Tooltip formatter={(v: any, n: any) => [money(v, 'UAH', 0), n === 'cum' ? 'З початку місяця' : 'За день']} labelFormatter={(d: any) => `${d} число`} />
                <Bar isAnimationActive={false} dataKey="v" fill={accent} fillOpacity={0.35} radius={[2, 2, 0, 0]} />
                <Line isAnimationActive={false} dataKey="cum" stroke={accent} strokeWidth={2} dot={false} connectNulls={false} />
                {data.budget_total ? <ReferenceLine y={data.budget_total} stroke="#d9822b" strokeDasharray="4 4" /> : null}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          {data.budget_total ? <div className="chart-legend"><span><i className="dot" style={{ background: '#d9822b' }} />сума бюджетів {money(data.budget_total, 'UAH', 0)}</span></div> : null}
        </Card>
      </Section>

      <Section title="Бюджети" action={budgets?.items.length ? 'Змінити' : undefined} onAction={() => setEditBudgets(true)}>
        {!budgets?.items.length ? (
          <Card>
            <div className="stack-s center">
              <div className="bold">Задайте ліміти на категорії</div>
              <div className="muted small">Побачите, скільки лишилось до кінця місяця, а бот попередить на 80%.</div>
              <Button size="sm" onClick={() => setEditBudgets(true)}>🎯 Налаштувати бюджети</Button>
            </div>
          </Card>
        ) : (
          <Card>
            <div className="stack">
              <div className="spread small"><span className="muted">Усього {money(budgets.totals.spent, 'UAH', 0)} з {money(budgets.totals.amount, 'UAH', 0)}</span>
                {data.is_current && <span className="muted">лишилось {budgets.days_left} дн.</span>}</div>
              {budgets.items.map(b => (
                <div key={b.category_id} className="stack-s" role="button" tabIndex={0} style={{ gap: 4, cursor: 'pointer' }}
                  onClick={() => { const r = data.categories.find(c => c.category_id === b.category_id); if (r) setOpenCat(r); }}>
                  <div className="spread small">
                    <span className="ellipsis"><b>{b.name}</b></span>
                    <span className="tnum"><b className={b.status === 'over' ? 'danger' : b.status === 'warn' ? 'warn' : ''}>{money(b.spent, 'UAH', 0)}</b> <span className="muted">/ {money(b.amount, 'UAH', 0)}</span></span>
                  </div>
                  <Progress value={b.pct} tone={tone(b)} mark={timeMark} />
                  <div className="muted xsmall">
                    {b.status === 'over' ? `перевищено на ${money(-b.remaining, 'UAH', 0)}`
                      : `лишилось ${money(b.remaining, 'UAH', 0)}${b.per_day_left && data.is_current ? ` · ≈ ${money(b.per_day_left, 'UAH', 0)}/день` : ''}`}
                    {data.is_current && b.status !== 'over' && b.forecast > b.amount ? ` · прогноз ${money(b.forecast, 'UAH', 0)}` : ''}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </Section>

      <Section title="Категорії">
        {cats.length === 0 ? <Empty icon="🧾" title="Витрат за цей місяць немає" /> : (
          <Card flush>
            {pie.length > 1 && (
              <div style={{ position: 'relative', height: 180, marginTop: 8 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie isAnimationActive={false} data={pie} dataKey="amount" nameKey="name" innerRadius={55} outerRadius={80} paddingAngle={2} stroke="none"
                      onClick={(p: any) => setOpenCat(p?.payload || null)}>
                      {pie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
                  <div className="center"><div className="muted xsmall">Усього</div><div className="bold tnum">{money(data.expense, 'UAH', 0)}</div></div>
                </div>
              </div>
            )}
            {shown.map((c, i) => {
              const b = budgetBy.get(c.category_id ?? -1);
              const d = pctDelta(c.amount, c.avg3);
              const color = i < 8 && pie.includes(c) ? COLORS[pie.indexOf(c) % COLORS.length] : undefined;
              return (
                <Row key={`${c.category_id}`} icon={c.category_id ? catIcon(catBy.get(c.category_id)) : '❓'}
                  title={<span className="hstack">{color && <span className="dot" style={{ background: color }} />}{cleanCatName(c.name)}</span>}
                  sub={<>{c.share}%{d !== null && Math.abs(d) >= 10 ? <span className={d > 0 ? 'danger' : 'pos'}> · {d > 0 ? '↑' : '↓'}{Math.abs(d)}% до звичного</span> : null}
                    {b ? <span className={b.status !== 'ok' ? 'warn' : ''}> · бюджет {Math.round(b.pct)}%</span> : null}</>}
                  end={<b className="tnum">{money(c.amount, 'UAH', 0)}</b>} onClick={() => setOpenCat(c)} />
              );
            })}
            {cats.length > 8 && <Row compact title={<span className="link">{allCats ? 'Згорнути' : `Усі категорії (${cats.length})`}</span>} onClick={() => setAllCats(v => !v)} />}
          </Card>
        )}
      </Section>

      {(data.by_user.length > 1 || data.top_merchants.length > 0) && (
        <>
          {data.by_user.length > 1 && (() => {
            const total = data.by_user.reduce((t, u) => t + u.expense, 0) || 1;
            return (
              <Section title="Хто витрачав">
                <Card flush>
                  {data.by_user.map(u => <Row key={u.name} compact icon="👤" title={u.name} sub={<Progress value={u.expense / total * 100} />}
                    end={<div className="end-stack"><b className="tnum">{money(u.expense, 'UAH', 0)}</b><span className="muted xsmall">{Math.round(u.expense / total * 100)}%</span></div>} />)}
                </Card>
              </Section>
            );
          })()}
          {data.top_merchants.length > 0 && (
            <Section title="Де найбільше">
              <Card flush>
                {data.top_merchants.map(m => <Row key={m.title} compact title={m.title} sub={`${m.count} ${plural(m.count, 'операція', 'операції', 'операцій')}`} end={<span className="tnum">{money(m.amount, 'UAH', 0)}</span>} />)}
              </Card>
            </Section>
          )}
        </>
      )}

      {editBudgets && <BudgetsSheet familyId={familyId} categories={categories} budgets={budgets} onClose={() => setEditBudgets(false)}
        onSaved={b => { onBudgetsChanged?.(b); anApi.month(familyId, month).then(setData).catch(() => { /**/ }); if (month === thisMonth) setBudgets(b); else anApi.budgets(familyId, month).then(setBudgets); }} />}
      {openCat && <CategorySheet familyId={familyId} month={month} row={openCat} budget={openCat.category_id ? budgetBy.get(openCat.category_id) : undefined}
        categories={categories} onClose={() => setOpenCat(null)} onView={onView} />}
    </div>
  );
}
