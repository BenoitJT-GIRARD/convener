import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/example-showcase/app/',
  build: { outDir: 'dist' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      // Pure logic only. UI components are covered by behaviour, not by a
      // percentage — a threshold there buys assertions nobody reads.
      include: ['src/state/**', 'src/data/**', 'src/github/**', 'src/auth/**'],
      exclude: ['src/data/demo.ts'],
      thresholds: { lines: 90, functions: 90, branches: 85, statements: 90 },
    },
  },
});
