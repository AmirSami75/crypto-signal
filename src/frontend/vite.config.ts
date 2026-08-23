import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Tailwind v4 is wired as a Vite plugin and configured entirely from src/styles.css. There is
// deliberately no tailwind.config.js and no postcss.config.js — v4 is CSS-first, and an empty
// JS config would only be a place for settings to silently diverge from the @theme block.

// The compose network resolves the API as `api`; a host-side `npm run dev` cannot. Overriding
// with VITE_API_PROXY=http://127.0.0.1:8000 makes the bare-metal workflow proxy correctly
// instead of failing every request with ENOTFOUND.
const apiTarget = process.env.VITE_API_PROXY ?? 'http://api:8080'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': apiTarget,
      '/health': apiTarget,
    },
  },
})
