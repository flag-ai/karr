/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The build lands in dist/ and is copied into src/karr/web/static by the
// Dockerfile (see the README for the local copy step). The base is absolute:
// the service mounts /assets at the root and the history router has no
// basename, and a relative base would resolve to /agents/assets/... under a
// trailing slash and load index.html as the script.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
      '/ready': 'http://localhost:8080',
      '/metrics': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
