// The globals this relay's own source uses, and nothing else: the shape
// and the rules are `../eslint.config.base.mjs`.
//
// `crypto` and `TextEncoder` are the HMAC over a submission; `btoa`
// encodes the file it commits; `AbortSignal` bounds the call to GitHub.
import { relayConfig } from '../eslint.config.base.mjs';

export default [
  relayConfig({
    crypto: 'readonly',
    TextEncoder: 'readonly',
    btoa: 'readonly',
    AbortSignal: 'readonly',
  }),
];
