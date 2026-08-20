/**
 * The one thing this page ever asks the register for: an identifier's
 * current state -- never the payload, never a name, and (see below) never
 * even the identifier itself, over the network.
 *
 * What is fetched, and why the whole file rather than one row
 * -----------------------------------------------------------------------
 * `scripts/copy-certificates.mjs` publishes `certificate.public_register`'s
 * own output -- `tools/convener_ops/cli.py::certificates_public_data` writes it
 * as **a bare JSON array** of `{"identifier", "state"}` objects, e.g.
 * `[{"identifier":"...","state":"issued"}, ...]`, confirmed against that
 * function's own `test_certificates_public_data_aggregates_every_events_register`
 * -- not the `{"certificates": [...]}` shape
 * `certificate-verification.json`'s `projection_example` key might suggest
 * at a glance. That key name only labels *a property inside the fixture
 * file*, holding the same two worked rows either way; it is not a claim
 * about the wire shape. `isProjection` below is written, and tested,
 * against the real shape `cli.py` puts on disk, and a body shaped like
 * `{"certificates": [...]}` is deliberately one of this file's own "wrong
 * shape" test cases -- not treated as a friendlier alternative to accept.
 *
 * This function fetches that whole file for every lookup, rather than
 * asking for one identifier's row -- deliberately the more expensive
 * request, for a privacy reason no amount of caching would buy back: a
 * request naming `?id=<identifier>` (or a path segment) would put *which
 * certificate a visitor is checking* into this page's one outbound
 * request, and from there into whatever access log the static host that
 * serves it happens to keep -- IP address, timestamp, and the one
 * identifier a certificate holder was just asked to keep to themselves.
 * The whole-file request is identical for every visitor checking every
 * certificate, indistinguishable from simply loading the page again nearer
 * the top -- there is nothing in it to correlate a request with a person.
 * The register is small (identifier and state, nothing else, one row per
 * certificate ever issued) and static-hosted, so this trade costs nothing
 * that matters and buys back the one property ruling 6 asks for: the
 * request this page makes carries no identifier at all.
 *
 * Signature first, register second (ruling 2)
 * -----------------------------------------------
 * `VerifyPage` only ever calls this once a token's signature has already
 * verified -- a malformed or unmatched token never reaches this module at
 * all, because there is no state worth asking about for a certificate
 * that has not been confirmed genuine. That ordering is enforced by the
 * caller, not by anything in this file, which is why it is worth saying
 * here too: this module answers "is this identifier currently issued or
 * revoked", never "is this a real certificate" -- those are different
 * questions, and confusing them is exactly the mistake ruling 2 warns
 * against.
 */

const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

/** `scripts/copy-certificates.mjs`'s own destination filename -- pinned
 *  together with this constant in `app/tests/copy-certificates.test.ts`,
 *  so the file that script writes and the URL this module fetches can
 *  never silently drift apart from each other. */
export const REGISTER_FILENAME = 'certificates.json';

function registerUrl(): string {
  return `${BASE}/${REGISTER_FILENAME}`;
}

/** A hung fetch has no other end -- the same reasoning
 *  `SignupForm.tsx::KEY_FETCH_TIMEOUT_MS` gives for its own key fetch,
 *  applied here so a flaky connection resolves to "state unknown" rather
 *  than leaving a visitor looking at "Checking…" forever. */
const REGISTER_FETCH_TIMEOUT_MS = 15_000;

export const STATE_ISSUED = 'issued';
export const STATE_REVOKED = 'revoked';

/**
 * What the register says about one identifier -- four outcomes, not two,
 * because "not recorded" and "we could not read the register" are
 * different facts a caller must never conflate (ruling 2 and ruling 5):
 *
 * - `issued` / `revoked` -- the register was read successfully and this
 *   identifier is in it.
 * - `not_found` -- the register was read successfully and this
 *   identifier is simply not in it. A positive, decisive fact: the
 *   token-less flow (`VerifyPage`) shows this as "not recorded", plainly
 *   distinct from "we do not know".
 * - `unavailable` -- the register could not be fetched, could not be
 *   parsed, or was not shaped like a projection at all. Covers a 404, a
 *   network error, a timeout, malformed JSON and a body that is valid
 *   JSON but the wrong shape -- every one of these must land here, never
 *   on `not_found` and never on anything that reads as "invalid".
 */
export type LookupResult =
  | { readonly status: typeof STATE_ISSUED }
  | { readonly status: typeof STATE_REVOKED }
  | { readonly status: 'not_found' }
  | { readonly status: 'unavailable' };

interface ProjectionRow {
  readonly identifier: string;
  readonly state: string;
}

function isProjectionRow(value: unknown): value is ProjectionRow {
  if (typeof value !== 'object' || value === null) return false;
  const row = value as Record<string, unknown>;
  return typeof row.identifier === 'string' && typeof row.state === 'string';
}

/** The real, on-disk shape: a bare array. See this file's own top comment
 *  for why `{"certificates": [...]}` is deliberately rejected here, not
 *  accepted as an alternative. */
export function isProjection(value: unknown): value is ProjectionRow[] {
  return Array.isArray(value) && value.every(isProjectionRow);
}

/**
 * Fetches the whole public register and reports what it says about
 * `identifier`. Never throws: every failure -- a non-2xx response, a
 * network error, a timeout, a body that will not `JSON.parse`, or one
 * that parses but is not shaped like a projection -- resolves to
 * `{ status: 'unavailable' }`, the single outcome `VerifyPage` renders as
 * "we cannot confirm the state right now", never as "invalid".
 */
export async function lookupCertificateState(identifier: string): Promise<LookupResult> {
  let response: Response;
  try {
    response = await fetch(registerUrl(), {
      signal: AbortSignal.timeout(REGISTER_FETCH_TIMEOUT_MS),
    });
  } catch {
    return { status: 'unavailable' };
  }
  if (!response.ok) return { status: 'unavailable' };

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    return { status: 'unavailable' };
  }
  if (!isProjection(data)) return { status: 'unavailable' };

  const row = data.find(entry => entry.identifier === identifier);
  if (!row) return { status: 'not_found' };
  if (row.state === STATE_ISSUED) return { status: STATE_ISSUED };
  if (row.state === STATE_REVOKED) return { status: STATE_REVOKED };
  // A state spelling neither `issue` nor `revoke` has ever written --
  // never invented a meaning for it, folded into the same honest
  // "cannot confirm" outcome as any other unreadable register.
  return { status: 'unavailable' };
}
