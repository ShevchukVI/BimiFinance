import axios from 'axios';

// Клієнт для звернення до FastAPI (BimiFinance).
const api = axios.create({
  baseURL: 'https://bimif.vshevchuk.pp.ua', // Працюючий бекенд
  headers: {
    'Content-Type': 'application/json',
  },
});

// JWT тримаємо тільки в пам'яті (не в localStorage), щоб не зберігати токен на диску.
let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

// Автоматично підставляємо Authorization: Bearer <token> у кожен запит.
api.interceptors.request.use((config) => {
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`;
  }
  return config;
});

export default api;
