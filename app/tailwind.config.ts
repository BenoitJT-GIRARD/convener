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
        primary: {
          DEFAULT: 'var(--primary)',
          hover: 'var(--primary-hover)',
          soft: 'var(--primary-soft)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          soft: 'var(--accent-soft)',
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
