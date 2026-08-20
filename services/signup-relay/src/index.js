/**
 * The point of entry for a registration: `app/src/signup/SignupForm.tsx`
 * encrypts a participant's answers in the browser (`encrypt.ts`) and POSTs
 * the envelope here. This worker never sees plaintext -- it cannot, by
 * construction: the browser holds only the event's *public* half of an
 * RSA-2048 key pair (`tools/convener_ops/eventkeys.py`), which can encrypt but
 * not decrypt. What reaches this worker is `{event_id, v, encrypted_key,
 * iv, ciphertext}`, and every field but `event_id` is base64 ciphertext.
 * See README.md for what that does and does not let this worker verify.
 *
 * Unlike services/form-relay, there is no shared secret a caller signs
 * with -- a static page cannot hold one -- so this endpoint is open by
 * construction. README.md ("Abuse protection") records the choice made for
 * that and why. Unlike services/auth-proxy, this worker holds a GitHub
 * token (turning a submission into a repository_dispatch requires one), so
 * it cannot be secret-free either -- see README.md for why that puts it in
 * its own worker rather than a route on either of the other two.
 *
 * It logs no request body and keeps nothing beyond the per-event counter
 * README.md describes -- and that counter is a count, never the data that
 * produced it.
 */

const ROUTE = '/';
const REPO = 'example-instance/example-cockpit';
const DISPATCH_URL = `https://api.github.com/repos/${REPO}/dispatches`;
const USER_AGENT = 'convener-signup-relay';

//: Mirrors tools/convener_ops/eventkeys.py -- see that module's docstring for why
//: these are exactly these numbers, not approximations.
const WIRE_VERSION = 1;
const RSA_ENCRYPTED_KEY_BYTES = 256; // 2048-bit modulus / 8, RSA_KEY_BITS in eventkeys.py
const GCM_NONCE_BYTES = 12;
const MIN_CIPHERTEXT_BYTES = 16; // the GCM tag alone, an empty registration
// Comfortably above any real registration (five short fields) plus its
// GCM tag and JSON overhead, and far below anything worth reading into
// memory just to reject -- see README.md's "What 'shape' means here".
const MAX_CIPHERTEXT_BYTES = 16_384;
// A pre-parse guard on the whole request body, checked before it is even
// read: an id, four base64 fields at their bounds above, and JSON
// punctuation stay well under this. Exists so an oversized body is refused
// without first being pulled fully into memory.
const MAX_BODY_BYTES = 32_768;

//: Mirrors tools/convener_ops/commit_format._TOKEN (`[A-Za-z0-9][A-Za-z0-9._-]*`),
//: the same shape an event id already has to satisfy there -- imported by
//: reference, not copied byte for byte, because the two languages cannot
//: share one regex object. Length-capped at 64: no event id in this project
//: is remotely close to that, and the cap exists only so a pathological
//: input cannot inflate the GitHub API URL or the dispatch payload it
//: participates in.
const EVENT_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

// A per-event registration ceiling, needed regardless of whichever abuse
// protection is chosen (README.md): an event does not have ten thousand
// registrants, and a count that goes past this is worth surfacing as a
// signal even when it is not, on its own, a hard defence. 500 is
// generous -- an order of magnitude above any real seminar's attendance --
// while three orders of magnitude below "ten thousand".
const PER_EVENT_CEILING = 500;

const EXPECTED_FIELDS = ['ciphertext', 'encrypted_key', 'event_id', 'iv', 'v'];

/** Decodes standard-alphabet base64 to bytes, or `null` for anything that
 *  is not validly formed -- wrong alphabet, wrong padding, or a string
 *  `atob` itself refuses. Never throws. */
function base64Decode(value) {
  if (typeof value !== 'string' || value.length === 0) return null;
  if (value.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) return null;
  let binary;
  try {
    binary = atob(value);
  } catch {
    return null;
  }
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/**
 * The shape check the file-level comment promises, and nothing more: field
 * presence, exact field set (no stray extra key), plausible types and
 * lengths, and an event id shaped like one. It cannot and does not inspect
 * what `ciphertext` decrypts to -- there is no key here that could.
 *
 * Returns the validated `event_id` on success, `null` on any failure --
 * deliberately not which check failed, the same "one failure mode, no
 * oracle" reasoning `eventkeys.DecryptionError` documents for the job that
 * actually decrypts this later.
 */
function validatedEventId(parsed) {
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return null;

  const keys = Object.keys(parsed).sort();
  if (keys.length !== EXPECTED_FIELDS.length || !EXPECTED_FIELDS.every((k, i) => keys[i] === k)) {
    return null;
  }

  const { event_id: eventId, v, encrypted_key: encryptedKey, iv, ciphertext } = parsed;

  if (typeof eventId !== 'string' || !EVENT_ID_RE.test(eventId)) return null;
  if (v !== WIRE_VERSION) return null;

  const keyBytes = base64Decode(encryptedKey);
  if (!keyBytes || keyBytes.length !== RSA_ENCRYPTED_KEY_BYTES) return null;

  const ivBytes = base64Decode(iv);
  if (!ivBytes || ivBytes.length !== GCM_NONCE_BYTES) return null;

  const cipherBytes = base64Decode(ciphertext);
  if (!cipherBytes || cipherBytes.length < MIN_CIPHERTEXT_BYTES) return null;
  if (cipherBytes.length > MAX_CIPHERTEXT_BYTES) return null;

  return eventId;
}

/**
 * Whether `keys/events/<eventId>.pub` exists in the repository -- the
 * "identifiant d'événement connu" check the plan names alongside the field
 * checks above. Reuses `token`, the same GitHub credential the dispatch
 * below sends with: the "Contents: read & write" scope README.md documents
 * already covers a read. No second secret, no second account.
 *
 * Throws on anything other than a clean 200 or 404 -- a rate limit, a bad
 * token, GitHub unreachable -- so the caller reports that as this worker's
 * own failure (502) rather than confusing it with "no such event" (404).
 */
async function eventKeyExists(eventId, token) {
  const url = `https://api.github.com/repos/${REPO}/contents/keys/events/${encodeURIComponent(eventId)}.pub`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': USER_AGENT,
    },
  });
  if (res.status === 200) return true;
  if (res.status === 404) return false;
  throw new Error(`unexpected status checking event key: ${res.status}`);
}

function counterKey(eventId) {
  return `count:${eventId}`;
}

export async function handle(request, env) {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  const { pathname } = new URL(request.url);
  if (pathname !== ROUTE) {
    return new Response('Not Found', { status: 404 });
  }

  // Cheap, pre-parse guard: refuse an oversized body before it is even
  // read into memory, when the caller was honest enough to say how big it
  // is. The authoritative check is the per-field length check below --
  // this only saves the work of reading and parsing something that can
  // never pass it.
  const declaredLength = request.headers.get('content-length');
  if (declaredLength && Number(declaredLength) > MAX_BODY_BYTES) {
    return new Response('Bad Request', { status: 400 });
  }

  // Read raw: it contains ciphertext, and this worker cannot read it, that
  // is the point. It is parsed only far enough to check shape, then
  // forwarded byte-identical -- never re-serialised -- as
  // `client_payload.body`, the same pattern services/form-relay uses.
  const body = await request.text();
  if (body.length > MAX_BODY_BYTES) {
    return new Response('Bad Request', { status: 400 });
  }

  let parsed;
  try {
    parsed = JSON.parse(body);
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  const eventId = validatedEventId(parsed);
  if (!eventId) {
    return new Response('Bad Request', { status: 400 });
  }

  // Fail closed: this worker is the internet-facing boundary, so an
  // unconfigured secret or an unbound store refuses every request rather
  // than silently skipping the checks they exist for -- see README.md,
  // "Fail closed, not open", for why that is the opposite of how
  // tools/convener_ops/proposal.py treats its own absent secret, and correctly
  // so for each. Checked before anything below touches GitHub or the
  // counter, so neither is ever reached on a misconfigured deploy.
  const token = env.CONVENER_DISPATCH_TOKEN;
  const kv = env.SIGNUP_RELAY_KV;
  if (!token || !kv) {
    return new Response('Bad Gateway', { status: 502 });
  }

  // The per-event ceiling, checked before either GitHub call: cheaper to
  // refuse here than to spend a Contents-API read and a dispatch on a
  // request that will be refused anyway. A KV read failure is treated as
  // "no count yet" rather than refusing the request -- see README.md,
  // "Abuse protection", for why an approximate ceiling is the accepted
  // trade here, not a defect.
  let count = 0;
  try {
    const stored = await kv.get(counterKey(eventId));
    count = stored ? Number.parseInt(stored, 10) || 0 : 0;
  } catch {
    count = 0;
  }
  if (count >= PER_EVENT_CEILING) {
    return new Response('Too Many Requests', { status: 429 });
  }

  let known;
  try {
    known = await eventKeyExists(eventId, token);
  } catch {
    return new Response('Bad Gateway', { status: 502 });
  }
  if (!known) {
    return new Response('Not Found', { status: 404 });
  }

  let upstream;
  try {
    upstream = await fetch(DISPATCH_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
      },
      // `body` is the JSON *string* read above, never a nested object: the
      // workflow that handles this reads it as a bare
      // ${{ github.event.client_payload.body }} interpolation, which only
      // renders raw JSON when the value is a string.
      body: JSON.stringify({
        event_type: 'registration-submitted',
        client_payload: { body },
      }),
    });
  } catch {
    // A rejected fetch -- GitHub unreachable, DNS failure, a reset
    // connection -- is exactly as much "this worker could not complete the
    // dispatch" as a non-2xx answer below.
    return new Response('Bad Gateway', { status: 502 });
  }

  if (!upstream.ok) {
    // Never GitHub's status or body verbatim -- a caller with a
    // well-shaped, known-event envelope has no need to see GitHub's error
    // detail, and passing it through would blur this worker's own
    // taxonomy with GitHub's.
    return new Response('Bad Gateway', { status: 502 });
  }

  // Best-effort, after a confirmed dispatch: a registration that reached
  // GitHub must not be un-sent because the counter could not be written
  // afterwards. See README.md for why this counter is a signal and not a
  // gate that must never be wrong.
  try {
    await kv.put(counterKey(eventId), String(count + 1));
  } catch {
    // Nothing to do: the registration already succeeded.
  }

  // Fixed 204, not upstream.status -- see services/form-relay/src/index.js
  // for why an unexpected 2xx must not leak through as-is. The caller only
  // ever sees one of 204, 400, 404, 429 or 502 from this worker.
  return new Response(null, { status: 204 });
}

export default { fetch: handle };
