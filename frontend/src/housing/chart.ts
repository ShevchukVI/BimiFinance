// Chart helpers: SVG attributes can't reliably use CSS variables, so resolve them once.
export const cssVar = (name: string, fallback = '#8e8e93') => {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v && !v.startsWith('color-mix') ? v : fallback;
  } catch { return fallback; }
};

// Series palette tuned to read on both light and dark Telegram themes.
export const SERIES = ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16'];
export const HEAT = '#f97316';
