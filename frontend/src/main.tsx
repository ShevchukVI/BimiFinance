import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

// Ініціалізація Telegram Web App SDK (поки що просто ховаємо фон, щоб виглядало нативно)
if ((window as any).Telegram?.WebApp) {
  (window as any).Telegram.WebApp.ready();
  (window as any).Telegram.WebApp.expand();
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)