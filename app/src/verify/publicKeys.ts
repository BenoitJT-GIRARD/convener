/**
 * Every published certificate signing public key, newest first -- what
 * `verify()` (see verify.ts) checks a token's signature against.
 *
 * Same-origin, same mechanism as `SignupForm.tsx::fetchEventPublicKey`
 * -----------------------------------------------------------------------
 * `scripts/copy-signing-keys.mjs` publishes every `keys/signing/*.pub`
 * this repository has ever committed into `app/public/keys/signing/`
 * at build time -- the exact idiom `scripts/copy-event-keys.mjs` already
 * uses for `keys/events/`, adapted the way `keys/signing/README.md`'s own
 * "What task 13 needs from this directory" section asks for: one ordered
 * list, embedded at build time, not one file fetched per event id (a
 * verification page has no single event to key a fetch off of, and
 * `verify()` may need to try more than one key -- rotation must never
 * invalidate a certificate already signed).
 *
 * This module fetches `keys/signing/index.json` rather than truly
 * bundling the keys into this page's JS -- a same-origin static asset,
 * deployed alongside the app itself by the same build, never a request to
 * a live backend "for the payload": the file is the same for every
 * visitor regardless of which certificate they are checking, so it
 * carries nothing that could ever identify a lookup, and (unlike
 * `certificates.json`, see register.ts) it is small and effectively fixed
 * -- a handful of keys ever, appended to, never rewritten, growing far
 * slower than the register does. That is the "embedded" in ruling 1: not
 * literally zero bytes over the wire, but co-deployed with the page, no
 * dynamic backend behind it, and never varying with what is being
 * verified.
 */

const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

/** `scripts/copy-signing-keys.mjs`'s own manifest filename -- pinned
 *  together with this constant in
 *  `app/tests/copy-signing-keys.test.ts`. */
export const KEYS_INDEX_FILENAME = 'index.json';

function keysUrl(): string {
  return `${BASE}/keys/signing/${KEYS_INDEX_FILENAME}`;
}

/** Same reasoning as `register.ts::REGISTER_FETCH_TIMEOUT_MS` -- a hung
 *  fetch must resolve, not hang the page indefinitely. */
const KEYS_FETCH_TIMEOUT_MS = 15_000;

/**
 * Every published signing public key, newest first, or `[]` on any
 * failure to fetch or parse them -- never throws.
 *
 * `[]` is not a distinct failure state a caller has to handle specially:
 * `verify()` called with no keys at all deterministically returns
 * `NO_MATCHING_KEY` for every token (see verify.ts), exactly the same
 * "cannot confirm" outcome a genuinely-empty `keys/signing/` produces --
 * `keys/signing/README.md`'s own "What task 13 needs from this directory"
 * section names this as the current, real, normal state, not an error.
 * So a keys request that fails outright folds into the same honest
 * "not verifiable" appearance a page with zero published keys already
 * has to show, rather than inventing a second, distinct "the keys could
 * not be loaded" message nothing in this design asks for.
 */
export async function loadSigningPublicKeys(): Promise<string[]> {
  try {
    const response = await fetch(keysUrl(), {
      signal: AbortSignal.timeout(KEYS_FETCH_TIMEOUT_MS),
    });
    if (!response.ok) return [];
    const data: unknown = await response.json();
    if (!Array.isArray(data)) return [];
    return data.filter((entry): entry is string => typeof entry === 'string');
  } catch {
    return [];
  }
}
