import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'coverage']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // Deliberately-unused parameters kept for interface/signature reasons
      // (e.g. `_token` in fetchContent, reserved for future authenticated
      // requests) are exempted via the conventional leading-underscore
      // pattern instead of being deleted or silenced file-wide.
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      // AuthContext/DataContext intentionally export their `useAuth`/`useData`
      // hook next to the provider component — idiomatic React context usage.
      // This rule only concerns hot-module-reload, so we allow these two
      // named exports rather than disabling the rule or splitting the files.
      'react-refresh/only-export-components': [
        'error',
        { allowExportNames: ['useAuth', 'useData'] },
      ],
    },
  },
])
