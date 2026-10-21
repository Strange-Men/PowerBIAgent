import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // Local validation owns external output paths; CI keeps its default layout.
  cacheDir: process.env.PBIAGENT_VALIDATION_CACHE,
  build: { outDir: process.env.PBIAGENT_VALIDATION_OUTPUT },
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      // The BFF validates the browser origin before creating its login flow.
      '/auth': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    // Isolated threads avoid intermittent Windows child-process startup timeouts.
    // Keep the same test discovery and existing file scheduling contract.
    pool: 'threads',
    fileParallelism: false,
  },
})
