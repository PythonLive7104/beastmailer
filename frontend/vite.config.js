import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Pinned off Vite's default 5173: other projects on this machine use it.
  // strictPort so a clash fails loudly instead of silently hopping to another
  // port, which would leave the API base URL pointing at the wrong origin.
  server: {
    port: 5290,
    strictPort: true,
  },
})
