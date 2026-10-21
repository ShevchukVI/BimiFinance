import { COLORS_AVATAR } from '../types';

export default function Avatar({ name, url, size = 40 }: { name: string; url?: string; size?: number }) {
  const style = { width: size, height: size, fontSize: size * 0.42 };
  if (url) return <img className="avatar" src={url} alt="" style={style} />;
  const initial = name ? name.charAt(0).toUpperCase() : '?';
  const bg = COLORS_AVATAR[name ? name.length % COLORS_AVATAR.length : 0];
  return <div className="avatar" style={{ ...style, background: bg }}>{initial}</div>;
}
