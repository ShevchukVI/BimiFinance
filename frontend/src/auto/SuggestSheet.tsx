import { useEffect, useState } from 'react';
import { toast } from '../toast';
import { day, money, qty } from '../format';
import { haptic } from '../tg';
import { Button, Card, Empty, Row, Sheet, Spinner } from '../ui';
import { errText } from '../housing/api';
import { autoApi } from './api';
import { FUELS, kindMeta, LogDraft, Suggestion } from './types';

export const draftSummary = (d: LogDraft) => [
  d.kind === 'fuel' ? [d.fuel ? FUELS[d.fuel].label : 'Пальне', d.liters ? `${qty(d.liters, 1)} ${d.fuel ? FUELS[d.fuel].unit : 'л'}` : null].filter(Boolean).join(' ') : kindMeta(d.kind).label,
  d.odometer ? `${qty(d.odometer, 0)} км` : null,
].filter(Boolean).join(' · ');

// Операції, схожі на авто, яких ще немає в журналі: категорія «Паливо»/«Авто…» або АЗС/мийка з банку.
export default function SuggestSheet({ familyId, onClose, onPick, onChanged }: {
  familyId: number; onClose: () => void; onPick: (s: Suggestion) => void; onChanged: () => void;
}) {
  const [items, setItems] = useState<Suggestion[] | null>(null);
  useEffect(() => { autoApi.suggestions(familyId).then(setItems).catch(e => { toast(errText(e), 'err'); setItems([]); }); }, [familyId]);

  const ignore = async (s: Suggestion) => {
    try { await autoApi.ignore(familyId, s.transaction.id); haptic('light'); setItems(xs => (xs || []).filter(x => x !== s)); onChanged(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <Sheet title="Схожі на авто" icon="🔗" onClose={onClose}>
      <div className="muted small" style={{ marginTop: -8 }}>Натисніть «+», щоб додати в журнал (літри й пробіг підставляться з коментаря), або «✕» — це не авто.</div>
      {items === null ? <Spinner /> : items.length === 0 ? <Empty icon="✨" title="Усе розібрано" /> : (
        <Card flush>
          {items.map(s => (
            <Row key={s.transaction.id} icon={kindMeta(s.draft.kind).icon} title={s.transaction.title}
              sub={[day(s.transaction.date), draftSummary(s.draft), s.transaction.account].filter(Boolean).join(' · ')}
              end={<div className="hstack" style={{ gap: 6 }}>
                <b className="tnum small">{money(s.transaction.amount, 'UAH', 0)}</b>
                <Button size="sm" variant="secondary" onClick={() => ignore(s)}>✕</Button>
                <Button size="sm" onClick={() => onPick(s)}>+</Button>
              </div>} />
          ))}
        </Card>
      )}
    </Sheet>
  );
}
