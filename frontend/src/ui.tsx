// UI kit: every screen is built from these, styles live in styles/theme.css.
import { ReactNode, useEffect, useRef } from 'react';
import { confirmAsync, haptic, pushBack } from './tg';

type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

export function Button({ children, variant = 'primary', size, onClick, disabled, busy, type = 'button', className = '' }: {
  children: ReactNode; variant?: BtnVariant; size?: 'sm'; onClick?: () => void; disabled?: boolean; busy?: boolean;
  type?: 'button' | 'submit'; className?: string;
}) {
  return (
    <button type={type} className={`btn btn--${variant} ${size ? `btn--${size}` : ''} ${className}`}
      disabled={disabled || busy} onClick={() => { haptic('light'); onClick?.(); }}>
      {busy ? <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} /> : children}
    </button>
  );
}

export function IconButton({ children, onClick, label }: { children: ReactNode; onClick: () => void; label: string }) {
  return <button className="btn btn--icon" aria-label={label} onClick={() => { haptic('light'); onClick(); }}>{children}</button>;
}

export function Card({ children, flush, onClick, className = '' }: { children: ReactNode; flush?: boolean; onClick?: () => void; className?: string }) {
  return (
    <div className={`card ${flush ? 'card--flush' : ''} ${onClick ? 'card--tap' : ''} ${className}`} onClick={onClick}>
      {children}
    </div>
  );
}

export function Section({ title, action, onAction, children }: { title: string; action?: string; onAction?: () => void; children: ReactNode }) {
  return (
    <div className="stack-s">
      <div className="section-head">
        <span className="section-title">{title}</span>
        {action && onAction && <button className="link" onClick={onAction}>{action}</button>}
      </div>
      {children}
    </div>
  );
}

export function Row({ icon, iconAccent, title, sub, end, onClick, chevron, compact }: {
  icon?: ReactNode; iconAccent?: boolean; title: ReactNode; sub?: ReactNode; end?: ReactNode;
  onClick?: () => void; chevron?: boolean; compact?: boolean;
}) {
  const Tag: any = onClick ? 'button' : 'div';
  return (
    <Tag className={`row ${onClick ? 'row--tap' : ''} ${compact ? 'row--compact' : ''}`} onClick={onClick ? () => { haptic('select'); onClick(); } : undefined}>
      {icon !== undefined && <div className={`row__icon ${iconAccent ? 'row__icon--accent' : ''}`}>{icon}</div>}
      <div className="row__body">
        <div className="row__title">{title}</div>
        {sub && <div className="row__sub">{sub}</div>}
      </div>
      {end !== undefined && <div className="row__end">{end}</div>}
      {chevron && <div className="row__chev">›</div>}
    </Tag>
  );
}

export function Chips<T extends string | number>({ options, value, onChange, scroll, small }: {
  options: { value: T; label: ReactNode }[]; value: T | null; onChange: (v: T) => void; scroll?: boolean; small?: boolean;
}) {
  return (
    <div className={`chips ${scroll ? 'chips--scroll' : ''}`}>
      {options.map(o => (
        <button key={String(o.value)} className={`chip ${small ? 'chip--sm' : ''} ${o.value === value ? 'chip--on' : ''}`}
          onClick={() => { haptic('select'); onChange(o.value); }}>{o.label}</button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange }: {
  options: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div className="seg" role="tablist">
      {options.map(o => (
        <button key={o.value} role="tab" aria-selected={o.value === value}
          className={`seg__btn ${o.value === value ? 'seg__btn--on' : ''}`}
          onClick={() => { haptic('select'); onChange(o.value); }}>{o.label}</button>
      ))}
    </div>
  );
}

export function Field({ label, hint, error, children }: { label?: ReactNode; hint?: ReactNode; error?: ReactNode; children: ReactNode }) {
  return (
    <div className="field">
      {label && <span className="field__label">{label}</span>}
      {children}
      {error ? <span className="field__error">{error}</span> : hint ? <span className="field__hint">{hint}</span> : null}
    </div>
  );
}

export function Switch({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return <button className={`switch ${on ? 'switch--on' : ''}`} role="switch" aria-checked={on} aria-label={label}
    onClick={() => { haptic('select'); onChange(!on); }} />;
}

export function Badge({ children, tone }: { children: ReactNode; tone?: 'ok' | 'warn' | 'danger' | 'accent' }) {
  return <span className={`badge ${tone ? `badge--${tone}` : ''}`}>{children}</span>;
}

export function Banner({ icon, children, tone, onClick }: { icon?: ReactNode; children: ReactNode; tone?: 'warn'; onClick?: () => void }) {
  const Tag: any = onClick ? 'button' : 'div';
  return (
    <Tag className={`banner ${tone ? `banner--${tone}` : ''}`} onClick={onClick}>
      {icon && <span className="banner__icon">{icon}</span>}
      <span className="banner__body">{children}</span>
      {onClick && <span className="muted">›</span>}
    </Tag>
  );
}

export function Progress({ value, tone, mark }: { value: number; tone?: 'warn' | 'danger'; mark?: number }) {
  const bg = tone === 'danger' ? 'var(--danger)' : tone === 'warn' ? 'var(--warn)' : undefined;
  return (
    <div className="progress" style={{ position: 'relative' }}>
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: bg }} />
      {mark !== undefined && mark > 0 && mark < 100 && <span style={{ position: 'absolute', top: -2, bottom: -2, left: `${mark}%`, width: 2, borderRadius: 1, background: 'var(--hint)' }} />}
    </div>
  );
}

export function Tile({ label, value, tone }: { label: ReactNode; value: ReactNode; tone?: 'pos' | 'danger' | 'warn' }) {
  return (
    <div className="tile">
      <div className="tile__label">{label}</div>
      <div className={`tile__value ${tone || ''}`}>{value}</div>
    </div>
  );
}

export function KV({ k, v }: { k: ReactNode; v: ReactNode }) {
  return <div className="kv"><span className="kv__k">{k}</span><span className="kv__v">{v}</span></div>;
}

export function Empty({ icon, title, text, action, onAction }: { icon: string; title: string; text?: string; action?: string; onAction?: () => void }) {
  return (
    <div className="card empty">
      <div className="empty__icon">{icon}</div>
      <div className="empty__title">{title}</div>
      {text && <div className="empty__text">{text}</div>}
      {action && onAction && <Button size="sm" onClick={onAction}>{action}</Button>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <div className="center" style={{ padding: 24 }}><div className="spinner" style={{ margin: '0 auto' }} />{label && <div className="muted small" style={{ marginTop: 8 }}>{label}</div>}</div>;
}

/** Bottom sheet: backdrop tap, Escape and Telegram «Назад» close it. */
export function Sheet({ title, icon, onClose, children, footer, card, confirmClose }: {
  title: ReactNode; icon?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; card?: boolean;
  confirmClose?: boolean; // form sheet: ask before dropping typed data (backdrop / ✕ / «Назад»)
}) {
  const dirty = useRef(false);
  const guardRef = useRef(confirmClose);
  guardRef.current = confirmClose;
  const requestClose = async () => {
    if (guardRef.current && dirty.current && !(await confirmAsync('Закрити без збереження?'))) return;
    onClose();
  };
  const closeRef = useRef(requestClose);
  closeRef.current = requestClose;
  useEffect(() => {
    const pop = pushBack(() => closeRef.current());
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { pop(); window.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, []);
  return (
    <div className="sheet-backdrop" onClick={e => { if (e.target === e.currentTarget) requestClose(); }}>
      <div className={`sheet ${card ? 'sheet--card' : ''}`} role="dialog" aria-modal="true" onInput={() => { dirty.current = true; }}>
        <div className="sheet__grip" />
        <div className="sheet__head">
          {icon && <span style={{ fontSize: 22 }}>{icon}</span>}
          <div className="sheet__title">{title}</div>
          <button className="sheet__close" aria-label="Закрити" onClick={requestClose}>✕</button>
        </div>
        <div className="stack">{children}</div>
        {footer && <div className="stack-s" style={{ marginTop: 16 }}>{footer}</div>}
      </div>
    </div>
  );
}

/** Sub-screen with its own back handling (used inside «Ще»). */
export function SubScreen({ title, onBack, children, action }: { title: string; onBack: () => void; children: ReactNode; action?: ReactNode }) {
  const backRef = useRef(onBack);
  backRef.current = onBack;
  useEffect(() => pushBack(() => backRef.current()), []);
  return (
    <div className="stack">
      <div className="spread">
        <div className="hstack">
          <IconButton label="Назад" onClick={onBack}>‹</IconButton>
          <span className="topbar__title">{title}</span>
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}
