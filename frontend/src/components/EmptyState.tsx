import { ReactNode } from 'react';

// Уніфікований empty state з українським CTA.
export default function EmptyState({
  emoji, title, subtitle, actionLabel, onAction,
}: {
  emoji: string;
  title: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div style={{ textAlign: 'center', padding: '44px 24px', backgroundColor: '#fff', borderRadius: '16px' }}>
      <div style={{ fontSize: '48px', marginBottom: '14px' }}>{emoji}</div>
      <p style={{ color: '#2c3e50', fontWeight: 'bold', fontSize: '16px', margin: '0 0 6px 0' }}>{title}</p>
      {subtitle && <p style={{ color: '#7f8c8d', fontSize: '13px', margin: '0 auto 18px auto', maxWidth: '260px', lineHeight: '1.5' }}>{subtitle}</p>}
      {actionLabel && onAction && (
        <button onClick={onAction} style={{ padding: '13px 26px', backgroundColor: '#3498db', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 'bold', fontSize: '15px', cursor: 'pointer' }}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
