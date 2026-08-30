/**
 * The browser half of `tools/convener_ops/journey/signing.py::verify` -- read that
 * module's docstring before this one, especially "the wire format
 * transports what it signs" and "verify before you parse". This file has
 * to reproduce its *behaviour* exactly (not its bytes: nothing here ever
 * re-serialises anything -- see below), or a certificate that verifies on
 * one side and not the other silently breaks the one promise this
 * certificate design rests on.
 *
 * Why this never re-derives the signed bytes
 * --------------------------------------------
 * `signing.py`'s own docstring spends a long section explaining why its
 * first cut was wrong: a verifier that re-serialises the payload to check
 * a signature has to agree with the signer's exact byte-for-byte
 * formatting (`sort_keys`, separators, `\uXXXX` escaping) forever, in every
 * language that ever verifies a token -- and Python's `json.dumps` and
 * JavaScript's `JSON.stringify` provably disagree on the two kinds of
 * value this payload actually carries: a whole-number `duration_hours`
 * (`2.0` vs `2`) and an accented `name` (`É` vs the literal
 * character). The fix, on both sides, is to never re-derive: `signing.sign`
 * transports the *exact bytes it signed*, base64-encoded, inside the
 * token's `payload` field, and `verify` checks the signature against those
 * decoded bytes directly. This file follows the identical discipline:
 * `verify` below never calls `JSON.stringify` on anything it is trying to
 * authenticate. It base64-decodes `payload`, hands those raw bytes to
 * `crypto.subtle.verify`, and only `JSON.parse`s them *after* a key has
 * confirmed they are genuine.
 *
 * Verify before you parse
 * -------------------------
 * Two parses happen here, and they are not the same kind of parse, for the
 * same reason `signing.py` draws this line:
 *
 * - The **envelope** (`{"v":...,"payload":...,"signature":...}`) is
 *   necessarily parsed unauthenticated -- there is nothing to check a
 *   signature against until one has been read out of it.
 * - The **payload** -- what `payload` base64-decodes to -- is never
 *   `JSON.parse`d until some key in `publicPems` has confirmed the exact
 *   decoded bytes are what it signed. A hostile token can reach the first
 *   parse; it can never reach the second unless it is genuinely signed by
 *   one of our own keys.
 *
 * Two outcomes, one reason string apiece (mirroring `signing.MALFORMED` /
 * `signing.NO_MATCHING_KEY`)
 * ----------------------------------------------------------------------
 * `MALFORMED` and `NO_MATCHING_KEY` are pinned, byte-for-byte, against
 * `tools/tests/fixtures/certificate-verification.json`'s own `reasons`
 * object -- not retyped from `signing.py`'s docstring by hand, which is
 * exactly the kind of copy that could drift the moment either side edits
 * its own spelling and forgets the other (D-14). **`NO_MATCHING_KEY` is
 * not "forged" and must never be presented as one**: a well-formed token
 * no offered key confirms looks identical, from here, to a genuine
 * certificate signed under a key this page's embedded list does not (yet)
 * include -- see `signing.py`'s own "three outcomes" section. `VerifyPage`
 * shows one neutral "cannot confirm" appearance for both `MALFORMED` and
 * `NO_MATCHING_KEY` ("four answers, four
 * appearances", not five) -- but the two spellings themselves stay
 * distinct values all the way through this module, never collapsed into a
 * boolean, so a test can still tell them apart.
 *
 * RSASSA-PKCS1-v1_5 / SHA-256, and only that
 * ---------------------------------------------
 * The one fixed algorithm `signing.py` signs with -- no negotiation, no
 * `alg` field ever read from the token (see that module's own warning
 * about JWT's `"alg": "none"` history). `crypto.subtle.importKey` is
 * called with `['verify']` only: nothing imported here could ever decrypt
 * or sign anything, the same "smallest capability asked for" discipline
 * `signup/encrypt.ts` applies to its own `['encrypt']`-only import.
 */

/** Mirrors `signing.WIRE_VERSION`. */
const WIRE_VERSION = 1;

/** Mirrors `signing.MAX_TOKEN_BYTES` -- refuses a hostile input outright,
 *  cheaply, before any parsing touches it. A real token is a few hundred
 *  bytes; this is headroom, not a realistic ceiling. */
const MAX_TOKEN_BYTES = 8192;

/** `VerifyResult.reason` for a token that is not even shaped like a
 *  signing token, or one that a key genuinely confirmed and still could
 *  not be read as JSON (this system's own bug, never a forger's -- see
 *  `signing.py`'s docstring). Pinned against
 *  `certificate-verification.json`'s `reasons.malformed` in
 *  `app/tests/verify-crypto.test.ts`. */
export const MALFORMED = 'malformed';

/** `VerifyResult.reason` for a well-formed token that no offered key
 *  validates -- covers both a forged token and a genuine one signed under
 *  a key this list does not (yet) include. Never presented as "forged".
 *  Pinned against `certificate-verification.json`'s
 *  `reasons.no_matching_key`. */
export const NO_MATCHING_KEY = 'no_matching_key';

/**
 * The certificate payload's fields, exactly `signing.PAYLOAD_FIELDS`.
 * Loosely typed on purpose: `verify` (below), like `signing.verify`, never
 * re-checks that a genuinely-signed payload carries exactly this shape --
 * `sign` is the one place that is enforced, on the Python side, before a
 * token is ever produced (see `signing.py`'s "payload's shape" section).
 * `asCertificatePayload` in `format.ts` is where this file's *caller*
 * turns an unstructured, signature-confirmed object into something safe
 * to render.
 */
export interface CertificatePayload {
  readonly identifier?: unknown;
  readonly event?: unknown;
  readonly name?: unknown;
  readonly date?: unknown;
  readonly duration_hours?: unknown;
}

export type VerifyResult =
  | { readonly valid: true; readonly payload: CertificatePayload }
  | { readonly valid: false; readonly reason: typeof MALFORMED | typeof NO_MATCHING_KEY };

/** `atob`'s output is a binary string, one code unit per byte -- the same
 *  conversion `signup/encrypt.ts::pemToDer` performs on a PEM body. Kept
 *  as a private copy here rather than imported from that file: an event
 *  key (`encrypt.ts`) and a signing key are deliberately different key
 *  pairs used for different capabilities (`signing.py`'s own module
 *  docstring draws this line for its Python counterparts, `eventkeys.py`
 *  vs itself) -- sharing one PEM-decoding helper between the two files
 *  would be harmless today, but it is exactly the kind of shared plumbing
 *  that invites a future edit to reach for the wrong file's key by
 *  accident. Two small, independent copies keep each side legible on its
 *  own, the same trade `signing.py` makes deliberately over reusing
 *  `eventkeys.py`. */
function pemToDer(pem: string): Uint8Array<ArrayBuffer> {
  const body = pem
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line.length > 0 && !line.startsWith('-----'))
    .join('');
  const binary = atob(body);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** Whether `publicPem` confirms `signature` over `canonical` -- `false`
 *  for any reason at all (an unparsable PEM, a non-RSA key, a genuine
 *  mismatch), mirroring `signing.py::_verifies_with`'s blanket `except`:
 *  a verifier must never crash on a hostile or merely-unlucky input, it
 *  must only ever say yes or no. */
async function verifiesWith(
  publicPem: string,
  canonical: Uint8Array<ArrayBuffer>,
  signature: Uint8Array<ArrayBuffer>,
): Promise<boolean> {
  let key: CryptoKey;
  try {
    const der = pemToDer(publicPem);
    key = await crypto.subtle.importKey(
      'spki',
      der,
      { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
      false,
      ['verify'],
    );
  } catch {
    return false;
  }
  try {
    return await crypto.subtle.verify({ name: 'RSASSA-PKCS1-v1_5' }, key, signature, canonical);
  } catch {
    return false;
  }
}

/**
 * Verify `token` against every key in `publicPems`, in order -- the
 * browser-side mirror of `signing.py::verify`. Never throws, for any
 * input, including a hostile one: every failure path returns
 * `{ valid: false, reason: ... }` rather than rejecting, so a caller never
 * needs a `try`/`catch` around this to check a certificate.
 *
 * `publicPems == []` is not a special case in the code below -- the trial
 * loop simply never runs, falling straight to `NO_MATCHING_KEY` -- and it
 * is a real, expected input: a page built before any signing key has ever
 * been published (`instance/keys/signing/` starts empty, see that directory's own
 * README) must show the same honest "cannot confirm" outcome as any other
 * unmatched token, never an exception and never acceptance for want of
 * anything to check against.
 */
export async function verify(token: string, publicPems: readonly string[]): Promise<VerifyResult> {
  if (new TextEncoder().encode(token).length > MAX_TOKEN_BYTES) {
    return { valid: false, reason: MALFORMED };
  }

  let canonical: Uint8Array<ArrayBuffer>;
  let signature: Uint8Array<ArrayBuffer>;
  try {
    const parsed: unknown = JSON.parse(token);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { valid: false, reason: MALFORMED };
    }
    const envelope = parsed as Record<string, unknown>;
    if (envelope.v !== WIRE_VERSION) return { valid: false, reason: MALFORMED };
    if (typeof envelope.payload !== 'string' || typeof envelope.signature !== 'string') {
      return { valid: false, reason: MALFORMED };
    }
    canonical = base64ToBytes(envelope.payload);
    signature = base64ToBytes(envelope.signature);
  } catch {
    return { valid: false, reason: MALFORMED };
  }

  // Keys are tried in order (newest first, see instance/keys/signing/README.md),
  // stopping at the first match -- a sequential loop, not `Promise.all`,
  // which would try every key even after one already matched, for no
  // benefit: there are at most a handful of published signing keys ever.
  for (const publicPem of publicPems) {
    const matches = await verifiesWith(publicPem, canonical, signature);
    if (!matches) continue;
    // A key has just confirmed these are genuinely the signed bytes --
    // only now is it safe to read them. See this file's own top comment,
    // "verify before you parse": this ordering is the guarantee, not
    // merely the size cap above.
    try {
      const payload: unknown = JSON.parse(new TextDecoder().decode(canonical));
      if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
        return { valid: false, reason: MALFORMED };
      }
      return { valid: true, payload: payload as CertificatePayload };
    } catch {
      return { valid: false, reason: MALFORMED };
    }
  }
  return { valid: false, reason: NO_MATCHING_KEY };
}
