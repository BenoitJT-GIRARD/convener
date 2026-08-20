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
      // `signup/encrypt.ts` is the one file in `signup/` named here, not the
      // whole directory: it is pure crypto the phase 4 promise rests on, and
      // `SignupForm.tsx` is UI like every other screen.
      include: [
        'src/state/**',
        'src/data/**',
        'src/github/**',
        'src/auth/**',
        'src/signup/encrypt.ts',
      ],
      exclude: ['src/data/demo.ts'],
      thresholds: { lines: 90, functions: 90, branches: 85, statements: 90 },
    },
  },
});
