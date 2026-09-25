import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Mode dev: Vite di port 5173, proxy /api → FastAPI di 8000.
// Mode demo: `npm run build` lalu FastAPI menyajikan folder dist.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
});
