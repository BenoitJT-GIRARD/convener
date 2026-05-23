import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: 'var(--paper)',
        surface: 'var(--surface)',
        ink: { DEFAULT: 'var(--ink)', muted: 'var(--ink-muted)' },
        primary: { DEFAULT: 'var(--primary)', hover: 'var(--primary-hover)' },
        accent: 'var(--accent)',
        border: 'var(--border)',
        danger: 'var(--danger)',
        info: 'var(--info)',
      },
      fontFamily: {
        serif: ['"Archivo"', 'system-ui', 'sans-serif'],
        sans: ['"Archivo"', 'system-ui', 'sans-serif'],
        display: ['"Archivo"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      maxWidth: { content: '1280px' },
    },
  },
  plugins: [],
} satisfies Config;
