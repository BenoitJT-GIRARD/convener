import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/app/',
  build: { outDir: 'dist' },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./tests/setup.ts'] },
});
