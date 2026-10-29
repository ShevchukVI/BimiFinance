import { useState } from 'react';
import { toast } from '../toast';
import { confirmAsync, haptic } from '../tg';
import type { FamilyUser } from '../types';
import { Button, Chips, Field, Sheet } from '../ui';
import { errText } from '../housing/api';
import { autoApi } from './api';
import { Fuel, FUELS, Vehicle } from './types';

const ICONS = ['🚗', '🚙', '🛻', '🚐', '🏎️', '🏍️', '🛵'];
const FUEL_OPTS = (Object.keys(FUELS) as Fuel[]).map(f => ({ value: f, label: FUELS[f].label }));

// Нове авто / налаштування авто. Друге паливо — для ГБО (газ + бензин).
export default function VehicleForm({ familyId, vehicle, familyUsers, onClose, onSaved }: {
  familyId: number; vehicle?: Vehicle; familyUsers: FamilyUser[]; onClose: () => void; onSaved: (v: Vehicle | null) => void;
}) {
  const [name, setName] = useState(vehicle?.name || '');
  const [icon, setIcon] = useState(vehicle?.icon || '🚗');
  const [plate, setPlate] = useState(vehicle?.plate || '');
  const [fuel, setFuel] = useState<Fuel>(vehicle?.fuel || 'petrol');
  const [fuel2, setFuel2] = useState<Fuel | 'none'>(vehicle?.fuel2 || 'none');
  const [odo, setOdo] = useState(vehicle?.start_odometer ? String(vehicle.start_odometer) : '');
  const [drivers, setDrivers] = useState<number[]>(vehicle?.driver_ids || []);
  const toggleDriver = (id: number) => setDrivers(d => d.includes(id) ? d.filter(x => x !== id) : [...d, id]);
  const [pattern, setPattern] = useState(vehicle?.match_pattern ?? '');
  const [note, setNote] = useState(vehicle?.note || '');
  const [busy, setBusy] = useState(false);
  const valid = name.trim().length > 0;

  const save = async () => {
    if (!valid) return;
    setBusy(true);
    const body: Record<string, unknown> = {
      name: name.trim(), icon, plate: plate.trim().toUpperCase(), fuel, fuel2: fuel2 === 'none' || fuel2 === fuel ? null : fuel2,
      start_odometer: Number(odo.replace(/\D/g, '')) || null, driver_ids: drivers, note: note.trim(),
    };
    if (vehicle) body.match_pattern = pattern.trim();
    try {
      const v = vehicle ? await autoApi.updateVehicle(familyId, vehicle.id, body) : await autoApi.createVehicle(familyId, body);
      haptic('success');
      toast(vehicle ? 'Збережено' : `${v.icon} ${v.name} додано`);
      onSaved(v);
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const archive = async () => {
    if (!vehicle || !(await confirmAsync(`Прибрати «${vehicle.name}»? Журнал залишиться в архіві, операції — в «Історії».`))) return;
    try { const r = await autoApi.removeVehicle(familyId, vehicle.id); toast(r.archived ? 'Перенесено в архів' : 'Видалено'); onSaved(null); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <Sheet title={vehicle ? vehicle.name : 'Нове авто'} icon={icon} onClose={onClose} confirmClose
      footer={<>
        <Button onClick={save} disabled={!valid} busy={busy}>{vehicle ? 'Зберегти' : 'Додати авто'}</Button>
        {vehicle && <Button variant="danger" onClick={archive}>Прибрати авто</Button>}
      </>}>
      <Chips value={icon} onChange={setIcon} options={ICONS.map(i => ({ value: i, label: <span style={{ fontSize: 20 }}>{i}</span> }))} />
      <div className="grid2">
        <Field label="Назва"><input className="input" placeholder="Skoda Octavia" value={name} autoFocus={!vehicle} onChange={e => setName(e.target.value)} /></Field>
        <Field label="Номер"><input className="input" placeholder="необов'язково" value={plate} onChange={e => setPlate(e.target.value)} /></Field>
      </div>
      <Field label="Основне паливо"><Chips small value={fuel} onChange={setFuel} options={FUEL_OPTS} /></Field>
      <Field label="Друге паливо" hint="Для ГБО: основне — газ, друге — бензин. Витрата рахується окремо для кожного.">
        <Chips small value={fuel2} onChange={setFuel2} options={[{ value: 'none' as const, label: 'Немає' }, ...FUEL_OPTS.filter(o => o.value !== fuel)]} />
      </Field>
      <Field label="Пробіг зараз" hint="Можна пропустити — візьметься з першої заправки з пробігом.">
        <input className="input tnum" inputMode="numeric" placeholder="км" value={odo} onChange={e => setOdo(e.target.value.replace(/[^\d ]/g, ''))} />
      </Field>
      {familyUsers.length > 1 && (
        <Field label="Хто їздить" hint="Можна кількох. Якщо в сім'ї кілька авто, заправки водія потраплятимуть у його авто.">
          <Chips small value={null} multi={drivers} onChange={toggleDriver} options={familyUsers.map(u => ({ value: u.id, label: u.name }))} />
        </Field>
      )}
      {vehicle && (
        <Field label="АЗС і мийки в банку" hint="Слова з опису операцій Monobank через «|». Такі витрати від 200 ₴ з'являться в «Схожих».">
          <input className="input" value={pattern} onChange={e => setPattern(e.target.value)} />
        </Field>
      )}
      <Field label="Примітка"><input className="input" placeholder="VIN, страховка до…, необов'язково" value={note} onChange={e => setNote(e.target.value)} /></Field>
    </Sheet>
  );
}
