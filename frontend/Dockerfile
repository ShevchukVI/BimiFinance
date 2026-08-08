FROM node:20-alpine

WORKDIR /app

# Копіюємо файли конфігурації
COPY package.json package-lock.json* ./

# Встановлюємо залежності
RUN npm install

# Копіюємо весь інший код
COPY . .

# Відкриваємо порт, на якому працює Vite
EXPOSE 5173

# Запускаємо сервер розробки
CMD ["npm", "run", "dev"]