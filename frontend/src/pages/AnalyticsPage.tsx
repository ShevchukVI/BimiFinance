import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { Stats, COLORS, cleanCatName, sortCurrencies } from '../types';
import { inMonth, money, todayIso } from '../format';
import { Card, Empty, Progress, Section } from '../ui';

export default function AnalyticsPage({ stats }: { stats: Stats | null }) {
  if (!stats) return <div className="page"><Empty icon="📊" title="Немає даних для аналітики" /></div>;
  const byCurrency = stats.by_currency || {};
  const curs = sortCurrencies(Object.keys(byCurrency));
  const main = curs[0] || 'UAH';
  const cats = stats.top_categories.map(c => ({ ...c, label: cleanCatName(c.name), icon: (c.name.match(/^\S+/) || [''])[0] }));
  const total = cats.reduce((s, c) => s + c.amount, 0);

  return (
    <div className="page">
      <h1 className="page-title">Аналітика</h1>
      <div className="grid2">
        <Card><div className="muted small">Дохід у {inMonth(todayIso())}</div><div className="bold pos tnum" style={{ fontSize: 20 }}>+{money(stats.income, main, 0)}</div></Card>
        <Card><div className="muted small">Витрати у {inMonth(todayIso())}</div><div className="bold tnum" style={{ fontSize: 20 }}>−{money(stats.expense, main, 0)}</div></Card>
      </div>
      {curs.filter(c => c !== main).map(c => (
        <Card key={c}><div className="spread small"><span className="muted">{c}</span>
          <span><span className="pos">+{money(byCurrency[c].income, c)}</span> · −{money(byCurrency[c].expense, c)}</span></div></Card>
      ))}
      <Section title={`Структура витрат (${main})`}>
        {cats.length === 0 ? <Empty icon="🧾" title="Витрат цього місяця ще немає" /> : (
          <Card>
            <div style={{ position: 'relative', width: '100%', height: 200 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie isAnimationActive={false} data={cats} dataKey="amount" nameKey="label" innerRadius={62} outerRadius={88} paddingAngle={2} stroke="none">
                    {cats.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
                <div className="center"><div className="muted xsmall">Усього</div><div className="bold tnum">{money(total, main, 0)}</div></div>
              </div>
            </div>
            <div className="stack-s" style={{ marginTop: 8 }}>
              {cats.map((c, i) => (
                <div key={c.name} className="stack-s" style={{ gap: 4 }}>
                  <div className="spread small">
                    <span className="hstack"><span className="dot" style={{ background: COLORS[i % COLORS.length] }} />{c.label}</span>
                    <span className="tnum"><b>{money(c.amount, main, 0)}</b> <span className="muted">{total ? Math.round((c.amount / total) * 100) : 0}%</span></span>
                  </div>
                  <Progress value={total ? (c.amount / total) * 100 : 0} />
                </div>
              ))}
            </div>
          </Card>
        )}
      </Section>
    </div>
  );
}
