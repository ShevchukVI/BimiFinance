import { COLORS_AVATAR } from '../types';

export default function Avatar({ name, url }: { name: string; url?: string }) {
  if (url) return <img src={url} alt="avatar" style={{width: '40px', height: '40px', borderRadius: '50%', objectFit: 'cover'}}/>;
  const initial = name && name.length > 0 ? name.charAt(0).toUpperCase() : '?';
  const bgColor = COLORS_AVATAR[name ? name.length % COLORS_AVATAR.length : 0];
  return <div style={{width: '40px', height: '40px', borderRadius: '50%', backgroundColor: bgColor, color: '#fff', display: 'flex', justifyContent: 'center', alignItems: 'center', fontWeight: 'bold', fontSize: '18px'}}>{initial}</div>;
}
