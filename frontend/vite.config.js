import { defineConfig } from 'vite';
export default defineConfig({
  server: { port: 5173, proxy: {
    '/api': { target: process.env.FLASK_API_URL || 'http://127.0.0.1:3000', changeOrigin: true },
  } },
});
