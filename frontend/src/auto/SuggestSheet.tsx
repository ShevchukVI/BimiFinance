import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { day, money, plural, qty } from '../format';
import { haptic } from '../tg';
import { Button, Card, Empty, Row, Section, Sheet, Spinner } from '../ui';
import { errText } from '../housing/api';
import { autoApi } from './api';
import { FUELS, kindMeta, LogDraft, Suggestion } from './types';

export const draftSummary = (d: LogDraft) => {
  const est = (f: 'fuel' | 'price' | 'liters') => d.predicted?.includes(f) ? '≈' : '';
  return [
    d.kind === 'fuel'
      ? [d.fuel ? FUELS[d.fuel].label : 'Пальне', d.liters ? `${est('liters')}${qty(d.liters, 1)} ${d.fuel ? FUELS[d.fuel].unit : 'л'}` : null].filter(Boolean).join(' ')
      : kindMeta(d.kind).label,
    d.place || null,
    d.odometer ? `${qty(d.odometer, 0)} км` : null,
  ].filter(Boolean).join(' · ');
};

// Операції, схожі на авто, яких ще немає в журналі. Впевненість — з історії: на «AZS 4» заправки по ~1000 ₴,
// а кава там до 100 ₴; чого немає в коментарі (паливо, ціна, літри, АЗС) — передбачено з попередніх заправок.
export default function SuggestSheet({ familyId, onClose, onPick, onChanged }: {
  familyId: number; onClose: () => void; onPick: (s: Suggestion) => void; onChanged: () => void;
}) {
  const [items, setItems] = useState<Suggestion[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { autoApi.suggestions(familyId).then(setItems).catch(e => { toast(errText(e), 'err'); setItems([]); }); }, [familyId]);

  const drop = (ids: number[]) => setItems(xs => (xs || []).filter(x => !ids.includes(x.transaction.id)));
  const ignore = async (s: Suggestion) => {
    try { await autoApi.ignore(familyId, s.transaction.id); haptic('light'); drop([s.transaction.id]); onChanged(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const sure = (items || []).filter(s => s.draft.confidence === 'sure' && !s.draft.foreign_fuel && s.draft.vehicle_id);
  const rest = (items || []).filter(s => !sure.includes(s));
  const acceptAll = async () => {
    setBusy(true);
    try {
      const ids = sure.map(s => s.transaction.id);
      const r = await autoApi.accept(familyId, ids);
      haptic('success');
      toast(`Додано ${r.added} ${plural(r.added, 'запис', 'записи', 'записів')}`);
      drop(ids); onChanged();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  const row = (s: Suggestion) => (
    <Row key={s.transaction.id} icon={kindMeta(s.draft.kind).icon} title={s.transaction.title}
      sub={<>
        <div>{s.draft.foreign_fuel ? `${draftSummary(s.draft)} — інше авто?` : draftSummary({ ...s.draft, place: s.draft.place === s.transaction.title ? null : s.draft.place })}</div>
        <div>{[day(s.transaction.date), s.transaction.account].join(' · ')}</div>
      </>}
      end={<div className="hstack" style={{ gap: 6 }}>
        <b className="tnum small">{money(s.transaction.amount, 'UAH', 0)}</b>
        <Button size="sm" variant="secondary" onClick={() => ignore(s)}>✕</Button>
        <Button size="sm" onClick={() => onPick(s)}>+</Button>
      </div>} />
  );

  return (
    <Sheet title="Схожі на авто" icon="🔗" onClose={onClose}>
      {items === null ? <Spinner /> : items.length === 0 ? <Empty icon="✨" title="Усе розібрано" text="Нові заправки з банку з'являться тут самі." /> : (
        <>
          {sure.length > 0 && (
            <Section title="Майже напевно">
              <Card flush>{sure.map(row)}</Card>
              <Button onClick={acceptAll} busy={busy}>{sure.length > 1 ? `Додати всі ${sure.length} в журнал` : 'Додати в журнал'}</Button>
              <div className="muted xsmall">≈ — літри оцінено за ціною попередньої заправки на цій АЗС; уточнити можна в записі.</div>
            </Section>
          )}
          {rest.length > 0 && (
            <Section title={sure.length ? 'Перевірте' : 'Схожі операції'}>
              <Card flush>{rest.map(row)}</Card>
              <div className="muted xsmall">«+» — відкрити й додати, «✕» — не авто: Bimi запам'ятає, які суми тут не заправки.</div>
            </Section>
          )}
        </>
      )}
    </Sheet>
  );
}
