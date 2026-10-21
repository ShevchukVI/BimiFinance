import { useState } from 'react';
import { toast } from '../toast';
import { dmy, hm } from '../format';
import { haptic } from '../tg';
import { Button, Card, Chips, Field, Row, Section, Segmented, Sheet, Switch } from '../ui';
import { errText, housingApi } from './api';
import type { HousingMode, Overview } from './types';
import { providerStatus } from './HousingPage';

const HEATING = [
  { value: 'electric', label: '⚡ Електро' }, { value: 'gas', label: '🔥 Газ' }, { value: 'central', label: '♨️ Центральне' },
  { value: 'other', label: 'Інше' }, { value: 'none', label: 'Немає' },
];

export default function SettingsSheet({ familyId, overview, onClose, onChanged, onEditProvider, onAddProvider }: {
  familyId: number; overview: Overview; onClose: () => void; onChanged: () => void;
  onEditProvider: (id: number) => void; onAddProvider: () => void;
}) {
  const pr = overview.profile!;
  const [mode, setMode] = useState<HousingMode>(pr.mode);
  const [title, setTitle] = useState(pr.title);
  const [area, setArea] = useState(pr.area_m2 ? String(pr.area_m2) : '');
  const [heating, setHeating] = useState(pr.heating);
  const [readingsDay, setReadingsDay] = useState(String(pr.readings_day || 1));
  const [reminders, setReminders] = useState(pr.reminders_enabled);
  const [channel, setChannel] = useState(pr.svitlobot_channel || '');
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      await housingApi.profile(familyId, {
        mode, title: title.trim(), area_m2: parseFloat(area.replace(',', '.')) || null, heating,
        readings_day: Math.min(Math.max(Number(readingsDay) || 1, 1), 28), reminders_enabled: reminders, svitlobot_channel: channel.trim() || null,
      });
      haptic('success');
      toast(mode === 'off' ? 'Вкладку «Житло» вимкнено' : 'Збережено');
      onChanged();
      onClose();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  const sync = async () => {
    setSyncing(true);
    try {
      if (channel.trim() !== (pr.svitlobot_channel || '')) await housingApi.profile(familyId, { svitlobot_channel: channel.trim() || null });
      const r = await housingApi.syncOutages(familyId);
      toast(r.skipped ? 'Щойно оновлено' : `Оновлено: ${r.events} подій`);
      onChanged();
    } catch (e) { toast(errText(e, 'Не вдалося отримати дані світлобота'), 'err'); }
    setSyncing(false);
  };

  return (
    <Sheet title="Налаштування житла" icon="⚙️" onClose={onClose} footer={<Button onClick={save} busy={busy}>Зберегти</Button>}>
      <Field label="Житло">
        <Segmented value={mode} onChange={setMode} options={[{ value: 'rent', label: 'Оренда' }, { value: 'mortgage', label: 'Іпотека' }, { value: 'own', label: 'Власне' }, { value: 'off', label: 'Вимк.' }]} />
      </Field>
      <div className="grid2">
        <Field label="Назва"><input className="input" placeholder="Квартира" value={title} onChange={e => setTitle(e.target.value)} /></Field>
        <Field label="Площа, м²"><input className="input tnum" inputMode="decimal" value={area} onChange={e => setArea(e.target.value)} /></Field>
      </div>
      <Field label="Опалення"><Chips small value={heating} onChange={setHeating} options={HEATING} /></Field>

      <Section title="Послуги" action="+ Додати" onAction={onAddProvider}>
        <Card flush>
          {overview.providers.map(p => <Row key={p.id} icon={p.icon} title={p.name} sub={providerStatus(p).sub} chevron onClick={() => onEditProvider(p.id)} />)}
        </Card>
      </Section>

      <Section title="Нагадування">
        <Card>
          <div className="spread">
            <div><div className="bold">Нагадувати в боті</div><div className="muted small">Показники, оплати, оренда</div></div>
            <Switch on={reminders} onChange={setReminders} label="Нагадування" />
          </div>
          {reminders && (
            <div className="spread" style={{ marginTop: 12 }}>
              <span className="small">Показники знімаємо</span>
              <span className="hstack small"><input className="input tnum" style={{ width: 64, height: 38 }} inputMode="numeric" value={readingsDay}
                onChange={e => setReadingsDay(e.target.value.replace(/\D/g, '').slice(0, 2))} /> числа</span>
            </div>
          )}
        </Card>
      </Section>

      <Section title="Світло (світлобот)">
        <Card>
          <div className="stack-s">
            <Field hint="Публічний Telegram-канал вашого світлобота — історія відключень підтягується автоматично">
              <input className="input" placeholder="t.me/svitlobot_…" value={channel} onChange={e => setChannel(e.target.value)} />
            </Field>
            {overview.power?.synced_at && <div className="muted xsmall">Оновлено {dmy(overview.power.synced_at)} {hm(overview.power.synced_at)}</div>}
            <Button variant="secondary" size="sm" onClick={sync} busy={syncing} disabled={!channel.trim()}>Оновити історію відключень</Button>
          </div>
        </Card>
      </Section>
    </Sheet>
  );
}
