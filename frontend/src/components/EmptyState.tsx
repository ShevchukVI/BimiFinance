import { Empty } from '../ui';

// Back-compat wrapper over the UI kit empty state.
export default function EmptyState({ emoji, title, subtitle, actionLabel, onAction }: {
  emoji: string; title: string; subtitle?: string; actionLabel?: string; onAction?: () => void;
}) {
  return <Empty icon={emoji} title={title} text={subtitle} action={actionLabel} onAction={onAction} />;
}
