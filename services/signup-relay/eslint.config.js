// Minimal flat config, deliberately free of any plugin dependency: this
// package's failure locks out the public registration form, so its quality
// gate should not depend on anything beyond eslint itself (invoked via npx,
// same pattern quality.yml already uses for cspell). Mirrors
// services/form-relay/eslint.config.js and services/auth-proxy/eslint.config.js.
export default [
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        fetch: 'readonly',
        Request: 'readonly',
        Response: 'readonly',
        ReadableStream: 'readonly',
        URL: 'readonly',
        atob: 'readonly',
        btoa: 'readonly',
        // `crypto.randomUUID` names each queue entry.
        // A Worker global, and a Node one since 19 -- granted the
        // same way services/form-relay's own config already grants it
        // for its HMAC.
        crypto: 'readonly',
        console: 'readonly',
        globalThis: 'writable',
        AbortSignal: 'readonly',
        TextEncoder: 'readonly',
        TextDecoder: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': 'error',
      'no-undef': 'error',
      eqeqeq: 'error',
    },
  },
  {
    // `Buffer` is a Node global, and the tests run under Node -- but the
    // Worker runtime this service actually deploys to has no `Buffer` at
    // all. Granting it in the block above would let `src/` reference it and
    // still lint clean, failing only once deployed. Scoped here instead.
    files: ['test/**'],
    languageOptions: {
      globals: {
        Buffer: 'readonly',
      },
    },
  },
];
