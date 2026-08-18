// Minimal flat config, deliberately free of any plugin dependency: this
// package's failure locks everyone out, so its quality gate should not
// depend on anything beyond eslint itself (invoked via npx, same pattern
// quality.yml already uses for cspell).
export default [
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        fetch: 'readonly',
        Request: 'readonly',
        Response: 'readonly',
        URL: 'readonly',
        console: 'readonly',
        globalThis: 'writable',
      },
    },
    rules: {
      'no-unused-vars': 'error',
      'no-undef': 'error',
      eqeqeq: 'error',
    },
  },
];
