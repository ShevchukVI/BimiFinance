import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/theme.css'

// Telegram WebApp: native look — follow the user's theme, match header/background colors.
const tg = (window as any).Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  if (tg.themeParams && Object.keys(tg.themeParams).length) document.documentElement.setAttribute('data-tg', '1');
  try {
    if (tg.isVersionAtLeast?.('6.1')) {
      tg.setHeaderColor('secondary_bg_color');
      tg.setBackgroundColor('secondary_bg_color');
    }
    if (tg.isVersionAtLeast?.('7.7')) tg.disableVerticalSwipes?.();
  } catch { /* old clients */ }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
