import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // vendor chunks change rarely → cached by Telegram WebView between releases
      output: { manualChunks: { react: ['react', 'react-dom'], charts: ['recharts'] } },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true, // Дозволяє всі хости (безпечно, бо ми за Cloudflare тунелем)
  }
})
