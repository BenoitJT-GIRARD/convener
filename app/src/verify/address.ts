/**
 * What a certificate has printed on it, read back into the two values
 * this page verifies from.
 *
 * `tools/convener_ops/journey/delivery.py::render_certificate` prints
 * two of them, and this module is the reader for both: the identifier on
 * its own (`<dt>Identifier</dt>`, 32 lowercase hexadecimal characters)
 * and the whole verification address
 * (`certificate.verification_url`, `<host><prefix>verify/#/<identifier>?token=<token>`),
 * which is also what that certificate's QR encodes.
 *
 * Why this is a module of its own
 * ------------------------------------
 * `parseVerificationFragment` was `islands/verify/main.tsx`'s, where the
 * island reads `location.hash`. It is imported here by `VerifyPage`'s
 * hand-entry form as well, and `main.tsx` is not importable from a
 * component: importing it runs its bootstrap, which mounts an island onto
 * whatever `#verify-app` the importing document happens to have. So the
 * parsing moved beside the other pure verification modules and `main.tsx`
 * re-exports it, which keeps one definition and every existing import
 * path.
 *
 * Nothing here reaches the network, and nothing here decides anything: a
 * function in this file only ever describes what a string said, never
 * what it means. `register.ts::isValidIdentifierShape` is what decides
 * whether an identifier is one of ours, and `verify.ts` is what decides
 * whether a token is genuine.
 */
import { IDENTIFIER_PATTERN } from './register';

function safeDecodeURIComponent(value: string): string {
  // A hand-edited or truncated fragment can carry a lone `%` that is not
  // the start of a real percent-encoding -- `decodeURIComponent` throws
  // `URIError` on that rather than returning best-effort text. Falling
  // back to the raw segment keeps this a parsing step, never a page
  // crash: whatever comes out still reaches `VerifyPage`, which already
  // has to handle an identifier that is not shaped like one of ours
  // (`InvalidIdentifierShape`) or a token whose signature does not verify
  // (`NotVerifiable`) -- garbled input is exactly the same shape of
  // "cannot confirm this" either way.
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/**
 * Pulls `identifier` and `token` out of a URL fragment, the same shape
 * `certificate.verification_url` builds: `#/<identifier>?token=<token>`.
 * Takes the fragment as a plain string -- `location.hash` when called from
 * `main.tsx`'s own bootstrap -- rather than reading `window.location`
 * itself, so a test can exercise every shape of input directly, with no
 * `window.location` stubbing at all.
 *
 * Both `#` and the leading `/` are optional on the way in: a caller may
 * pass `location.hash` verbatim (which always includes the `#` once a
 * fragment exists) or an already-stripped fragment. An identifier segment
 * is decoded but never validated here -- `VerifyPage` -> `register.ts`'s
 * own `isValidIdentifierShape` is where a malformed identifier is turned
 * into an honest "not a certificate identifier" answer, not this function,
 * which only ever describes what the URL said, never what it means.
 */
export function parseVerificationFragment(hash: string): { identifier?: string; token?: string } {
  const withoutHash = hash.startsWith('#') ? hash.slice(1) : hash;
  const withoutSlash = withoutHash.startsWith('/') ? withoutHash.slice(1) : withoutHash;
  const [rawIdentifier = '', query = ''] = withoutSlash.split('?');
  const identifier = rawIdentifier ? safeDecodeURIComponent(rawIdentifier) : undefined;
  const token = new URLSearchParams(query).get('token') ?? undefined;
  return { identifier, token };
}

/**
 * Whitespace out, capitals down.
 *
 * `certificate._new_identifier` produces `secrets.token_hex(16)` and
 * nothing else, so every real identifier is lowercase and
 * `IDENTIFIER_PATTERN` is lowercase-only. Hexadecimal is the same value
 * either case, and somebody reading one off a printed page types what
 * they see or pastes what a PDF viewer gives them -- which can arrive
 * capitalised, or broken across a line. Folding both changes no
 * identifier into a different one and refuses nothing real.
 */
export function normaliseIdentifier(text: string): string {
  return text.replace(/\s+/g, '').toLowerCase();
}

/**
 * One field of hand-entered text, read as whichever of the two printed
 * things it is.
 *
 * A URL carries no whitespace, so every space and line break is a copy's
 * own artefact and goes first. Then, in order:
 *
 * - anything with a `#` in it is a verification address, and everything
 *   from the `#` is the fragment `parseVerificationFragment` already
 *   reads -- this is the case that matters, because it is how a
 *   certificate issued under an address that no longer resolves is still
 *   checked here;
 * - anything carrying `token=` without a `#` is a query somebody's mail
 *   client or PDF viewer has mangled the fragment out of, read the same
 *   way rather than refused;
 * - anything shaped like an identifier is one.
 *
 * Anything else returns neither, and the caller says so to whoever typed
 * it. This function never reports an error of its own: it describes, and
 * the form decides.
 */
export function parsePrintedAddress(text: string): { identifier?: string; token?: string } {
  const compact = text.replace(/\s+/g, '');
  if (!compact) return {};
  const hash = compact.indexOf('#');
  if (hash >= 0) return parseVerificationFragment(compact.slice(hash));
  const query = compact.indexOf('token=');
  if (query >= 0) return parseVerificationFragment(`/?${compact.slice(query)}`);
  const identifier = normaliseIdentifier(compact);
  return IDENTIFIER_PATTERN.test(identifier) ? { identifier } : {};
}
