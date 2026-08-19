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
  {
    // P2-9: `new Date().toISOString().slice(0, 10)` is a *UTC* calendar day, and
    // this series runs on Europe/Paris time -- late in the evening the two are
    // different days, and several call sites persist the value (`opened_on`,
    // `joined_on`, `decided_on`, every working-day deadline) rather than merely
    // comparing it. `parisToday()` in src/state/derived.ts is the only way the
    // app asks what day it is; `parisDayOf(instant)` covers an instant other
    // than now. Scoped to src/: the test suite builds fixed dates this way on
    // purpose. The one legitimate use in src/ (formatting a fixed UTC epoch, in
    // src/state/working-days.ts) carries an explaining disable comment.
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "CallExpression[callee.object.callee.property.name='toISOString'][callee.property.name='slice']",
          message:
            'A UTC calendar day, not a Paris one (P2-9). Use parisToday() from ' +
            'src/state/derived.ts, or parisDayOf(instant) for an instant other than now.',
        },
        {
          // A `Subject` is a commit subject that `state/decisions.ts`
          // assembled, and a commit subject is permanent, unrewritable and
          // mailed to every watcher. The brand is what makes one built
          // anywhere else fail to compile whatever spelling it is written in
          // -- concatenated, split across chunks, hidden in a helper module
          // of its own -- and a cast is the one way past a brand, so the cast
          // is refused here. `decisions.ts`, where the brand is applied, is
          // the exception below. The source walk in
          // `app/tests/decisions.test.ts` is the third net, over the text
          // rather than the types.
          selector:
            "TSAsExpression > TSTypeReference > Identifier[name=/^(Subject|Identifier|ItemKey|FieldKey)$/]",
          message:
            'A commit subject is permanent and unrewritable: build it with ' +
            'formatDecision() or dataEdit() in src/state/decisions.ts rather ' +
            'than casting a string to Subject, Identifier, ItemKey or FieldKey.',
        },
      ],
    },
  },
  {
    // Where the brand is applied, and the only place a cast to `Subject` is
    // one. The P2-9 selector is restated because a flat-config block
    // replaces a rule's options rather than adding to them.
    files: ['src/state/decisions.ts'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "CallExpression[callee.object.callee.property.name='toISOString'][callee.property.name='slice']",
          message:
            'A UTC calendar day, not a Paris one (P2-9). Use parisToday() from ' +
            'src/state/derived.ts, or parisDayOf(instant) for an instant other than now.',
        },
      ],
    },
  },
  {
    // The tests may build a fixed calendar day any way they like -- that is
    // why P2-9 is scoped to `src/` -- but a subject cast into existence here
    // would be a subject the app could be given.
    files: ['tests/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          // A `Subject` is a commit subject that `state/decisions.ts`
          // assembled, and a commit subject is permanent, unrewritable and
          // mailed to every watcher. The brand is what makes one built
          // anywhere else fail to compile whatever spelling it is written in
          // -- concatenated, split across chunks, hidden in a helper module
          // of its own -- and a cast is the one way past a brand, so the cast
          // is refused here. `decisions.ts`, where the brand is applied, is
          // the exception below. The source walk in
          // `app/tests/decisions.test.ts` is the third net, over the text
          // rather than the types.
          selector: "TSAsExpression > TSTypeReference > Identifier[name='Subject']",
          message:
            'A commit subject is permanent and unrewritable: build it with ' +
            'formatDecision() or dataEdit() in src/state/decisions.ts rather ' +
            'than casting a string to Subject.',
        },
      ],
    },
  },
])
