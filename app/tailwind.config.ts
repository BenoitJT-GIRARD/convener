import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: 'var(--paper)',
        'paper-soft': 'var(--paper-soft)',
        surface: 'var(--surface)',
        'surface-mute': 'var(--surface-mute)',
        ink: {
          DEFAULT: 'var(--ink)',
          muted: 'var(--ink-muted)',
          faint: 'var(--ink-faint)',
        },
        field: {
          DEFAULT: 'var(--field)',
          text: 'var(--field-text)',
          tint: 'var(--field-tint)',
        },
        dominant: {
          DEFAULT: 'var(--dominant)',
          hover: 'var(--dominant-hover)',
          tint: 'var(--dominant-tint)',
        },
        border: { DEFAULT: 'var(--border)', strong: 'var(--border-strong)' },
        danger: 'var(--danger)',
        info: 'var(--info)',
      },
      fontFamily: {
        serif: ['"Archivo"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        sans: ['"Archivo"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        display: ['"Archivo"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      maxWidth: { content: '1180px' },
    },
  },
  plugins: [],
} satisfies Config;
