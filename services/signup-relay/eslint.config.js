// The globals this relay's own source uses, and nothing else: the shape
// and the rules are `../eslint.config.base.mjs`.
//
// The longest of the three lists, because this relay reads a request
// body and writes an encrypted queue entry: `crypto.randomUUID` names
// each entry, `atob`/`btoa` and the two coders move it between text and
// bytes, `ReadableStream` is the body itself, and `AbortSignal` bounds
// the call to GitHub.
import { relayConfig } from '../eslint.config.base.mjs';

export default [
  relayConfig({
    ReadableStream: 'readonly',
    atob: 'readonly',
    btoa: 'readonly',
    crypto: 'readonly',
    AbortSignal: 'readonly',
    TextEncoder: 'readonly',
    TextDecoder: 'readonly',
  }),
  {
    // `Buffer` is a Node global, and the tests run under Node -- but the
    // Worker runtime this service actually deploys to has no `Buffer` at
    // all. Granting it above would let `src/` reference it and still lint
    // clean, failing only once deployed. Scoped here instead.
    //
    // `performance` is here for the opposite reason: the Worker runtime
    // does have it, but only one test reaches for it -- the one that
    // measures what the duplicate-key scan costs on a hostile body -- and
    // `src/` has no business timing itself. Granted where it is used.
    files: ['test/**'],
    languageOptions: {
      globals: {
        Buffer: 'readonly',
        performance: 'readonly',
      },
    },
  },
];
