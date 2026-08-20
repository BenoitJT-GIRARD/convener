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
 * that and why -- a per-event burst limiter plus a per-event cumulative
 * ceiling, both with their own storage bindings. Unlike services/auth-proxy,
 * this worker holds a GitHub token (turning a submission into a
 * repository_dispatch requires one), so it cannot be secret-free either --
 * see README.md for why that puts it in its own worker rather than a route
 * on either of the other two.
 *
 * It answers cross-origin requests -- the form is served from a different
 * origin than this worker -- following the same pattern
 * `services/auth-proxy/src/index.js` already uses: an `ALLOWED_ORIGIN`
 * check, a preflight answer, and CORS headers on every response, error or
 * not, so a caller can actually read what this worker sends back.
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

// A per-event *cumulative* registration ceiling, needed regardless of
// whichever burst protection sits in front of it (README.md): an event
// does not have ten thousand registrants, and a count that goes past this
// is worth surfacing as a signal even where it is not, on its own, a hard
// defence. 500 is generous -- an order of magnitude above any real
// seminar's attendance -- while three orders of magnitude below "ten
// thousand". This is a *total*, unbounded in time; SIGNUP_RATE_LIMITER
// below is what bounds *velocity*, and the two are complementary, not
// redundant -- see README.md, "Abuse protection".
const PER_EVENT_CEILING = 500;

// GitHub's own dispatches/contents API has no documented timeout of its
// own, so an unresponsive upstream would otherwise hold this worker's
// invocation open until the *caller's* timeout -- SUBMIT_TIMEOUT_MS in
// app/src/signup/SignupForm.tsx -- fires instead. Both outbound GitHub
// calls carry this, well inside that 15-second client budget even if both
// were to time out in sequence.
const GITHUB_FETCH_TIMEOUT_MS = 5_000;

const EXPECTED_FIELDS = ['ciphertext', 'encrypted_key', 'event_id', 'iv', 'v'];

/** The CORS headers on every response once `ALLOWED_ORIGIN` is known to
 *  match -- mirrors `services/auth-proxy/src/index.js` exactly, including
 *  attaching them to *error* responses (a caller's `fetch` cannot read a
 *  204, or a 4xx/502 body, without `Access-Control-Allow-Origin` on that
 *  specific response, not only on success). */
function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

/** `new Response`, always carrying the CORS headers -- one call site so no
 *  branch below this line can forget them and produce a response a real
 *  browser silently discards. */
function respond(status, env, body = null, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: { ...corsHeaders(env.ALLOWED_ORIGIN), ...extraHeaders },
  });
}

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
 * True if `rawBody` -- already confirmed to be valid JSON describing a flat
 * object -- spells the same key twice. `JSON.parse` silently keeps only the
 * *last* occurrence of a duplicate key, so `Object.keys` on the *parsed*
 * result can never see this: two `"event_id"` entries collapse to the one
 * key this worker validates, while `client_payload.body` still forwards
 * both, byte for byte, to whatever parses it next -- which may not resolve
 * the same collision the same way `JSON.parse` did here.
 *
 * Sound rather than approximate, because every field this worker accepts
 * is a string or a number, never a nested object or array (enforced
 * elsewhere): with no legal `{...}` inside any value, an unescaped
 * `"name":` sequence anywhere in the raw text can only be an actual
 * top-level key. Inside a JSON string, an unescaped `"` always terminates
 * the string, so the same literal, unescaped sequence could never appear as
 * content instead.
 */
function hasDuplicateKey(rawBody) {
  const seen = new Set();
  const keyPattern = /"((?:[^"\\]|\\.)*)"\s*:/g;
  let match;
  while ((match = keyPattern.exec(rawBody)) !== null) {
    if (seen.has(match[1])) return true;
    seen.add(match[1]);
  }
  return false;
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
 * token, GitHub unreachable, a timeout -- so the caller reports that as
 * this worker's own failure (502) rather than confusing it with "no such
 * event" (404).
 */
async function eventKeyExists(eventId, token) {
  const url = `https://api.github.com/repos/${REPO}/contents/keys/events/${encodeURIComponent(eventId)}.pub`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': USER_AGENT,
    },
    signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
  });
  if (res.status === 200) return true;
  if (res.status === 404) return false;
  throw new Error(`unexpected status checking event key: ${res.status}`);
}

function counterKey(eventId) {
  return `count:${eventId}`;
}

export async function handle(request, env) {
  // CORS, first: the in-repo pattern services/auth-proxy/src/index.js
  // uses, copied rather than reinvented. A mismatched or absent Origin
  // gets a bare 403 with no CORS headers at all -- exactly like that
  // worker -- because a real browser sending the wrong Origin would not be
  // able to read a CORS-headed response as this worker's own origin
  // either, and a non-browser caller has no CORS to satisfy in the first
  // place. An unset ALLOWED_ORIGIN var behaves the same way: `origin` can
  // never literally equal `undefined`, so every request is refused, the
  // same fail-closed direction as the checks further down.
  const origin = request.headers.get('Origin');
  if (origin !== env.ALLOWED_ORIGIN) {
    return new Response('Forbidden', { status: 403 });
  }

  if (request.method !== 'OPTIONS' && request.method !== 'POST') {
    return respond(405, env, 'Method Not Allowed');
  }

  const { pathname } = new URL(request.url);
  if (pathname !== ROUTE) {
    return respond(404, env, 'Not Found');
  }

  if (request.method === 'OPTIONS') {
    // The preflight a browser sends before the real POST, because
    // `content-type: application/json` is not a CORS-safelisted value
    // (SignupForm.tsx's own submit call sets it). No body, 204, and the
    // same CORS headers every other response carries.
    return respond(204, env);
  }

  // Cheap, pre-parse guard: refuse an oversized body before it is even
  // read into memory, when the caller was honest enough to say how big it
  // is. The authoritative check is the per-field length check below --
  // this only saves the work of reading and parsing something that can
  // never pass it.
  const declaredLength = request.headers.get('content-length');
  if (declaredLength && Number(declaredLength) > MAX_BODY_BYTES) {
    return respond(400, env, 'Bad Request');
  }

  // Read raw: it contains ciphertext, and this worker cannot read it, that
  // is the point. It is parsed only far enough to check shape, then
  // forwarded byte-identical -- never re-serialised -- as
  // `client_payload.body`, the same pattern services/form-relay uses.
  // Guarded: an aborted or malformed request body throws here rather than
  // resolving, and an uncaught throw would escape as workerd's own generic
  // error page -- outside the closed set of statuses this worker promises.
  let body;
  try {
    body = await request.text();
  } catch {
    return respond(400, env, 'Bad Request');
  }

  // `body.length` is UTF-16 code units, not bytes -- a multi-byte-heavy
  // body could pass a byte-denominated MAX_BODY_BYTES compared against
  // that count. `TextEncoder` gives the real encoded byte length, the same
  // unit `MAX_BODY_BYTES` and the Content-Length check above are in.
  if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) {
    return respond(400, env, 'Bad Request');
  }

  let parsed;
  try {
    parsed = JSON.parse(body);
  } catch {
    return respond(400, env, 'Bad Request');
  }

  // Checked on the *raw text*, not the parsed object: see hasDuplicateKey's
  // own docstring for why a duplicate key is invisible to any check that
  // only looks at `parsed`.
  if (hasDuplicateKey(body)) {
    return respond(400, env, 'Bad Request');
  }

  const eventId = validatedEventId(parsed);
  if (!eventId) {
    return respond(400, env, 'Bad Request');
  }

  // Fail closed: this worker is the internet-facing boundary, so an
  // unconfigured secret or an unbound store refuses every request rather
  // than silently skipping the checks they exist for -- see README.md,
  // "Fail closed, not open", for why that is the opposite of how
  // tools/convener_ops/proposal.py treats its own absent secret, and correctly
  // so for each. Checked before anything below touches GitHub or either
  // counter, so none of them is ever reached on a misconfigured deploy.
  const token = env.CONVENER_DISPATCH_TOKEN;
  const kv = env.SIGNUP_RELAY_KV;
  const rateLimiter = env.SIGNUP_RATE_LIMITER;
  if (!token || !kv || !rateLimiter) {
    return respond(502, env, 'Bad Gateway');
  }

  // The burst limiter, checked before anything else touches GitHub or the
  // cumulative counter: purpose-built for exactly this (unlike
  // SIGNUP_RELAY_KV, a general store repurposed as a counter), keyed per
  // event so one flooded event cannot exhaust another's budget. Cloudflare
  // documents this binding as "permissive, eventually consistent, and
  // intentionally designed to not be used as an accurate accounting
  // system" -- quoted, not paraphrased, in README.md -- so a thrown
  // `.limit()` call is treated the same as any other fail-closed check
  // here: refused, not silently skipped.
  let limited;
  try {
    limited = await rateLimiter.limit({ key: eventId });
  } catch {
    return respond(502, env, 'Bad Gateway');
  }
  if (!limited.success) {
    return respond(429, env, 'Too Many Requests', { 'Retry-After': '60' });
  }

  // The cumulative ceiling, checked before either GitHub call: cheaper to
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
    return respond(429, env, 'Too Many Requests', { 'Retry-After': '60' });
  }

  let known;
  try {
    known = await eventKeyExists(eventId, token);
  } catch {
    return respond(502, env, 'Bad Gateway');
  }
  if (!known) {
    return respond(404, env, 'Not Found');
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
      signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
    });
  } catch {
    // A rejected fetch -- GitHub unreachable, DNS failure, a reset
    // connection, this worker's own timeout -- is exactly as much "this
    // worker could not complete the dispatch" as a non-2xx answer below.
    return respond(502, env, 'Bad Gateway');
  }

  if (!upstream.ok) {
    // Never GitHub's status or body verbatim -- a caller with a
    // well-shaped, known-event envelope has no need to see GitHub's error
    // detail, and passing it through would blur this worker's own
    // taxonomy with GitHub's.
    return respond(502, env, 'Bad Gateway');
  }

  // Best-effort, after a confirmed dispatch: a registration that reached
  // GitHub must not be un-sent because the counter could not be written
  // afterwards -- see README.md for why this counter is a signal and not a
  // gate that must never be wrong. But a failure here is still worth a
  // trace: unlike a KV *read* failure above (indistinguishable from "no
  // registrations yet", and harmless to treat as one), a *write* failure
  // means a real, accepted registration will never be counted, which is
  // exactly the state a signal exists to surface, not hide. `console.error`
  // carries only the event id -- already public, the same identifier every
  // dispatch and every workflow run already names -- and a fixed message;
  // never the body.
  try {
    await kv.put(counterKey(eventId), String(count + 1));
  } catch {
    console.error(`signup-relay: failed to update the registration counter for event ${eventId}`);
  }

  // Fixed 204, not upstream.status -- see services/form-relay/src/index.js
  // for why an unexpected 2xx must not leak through as-is. The caller only
  // ever sees one of 204, 400, 403, 404, 405, 429 or 502 from this worker.
  return respond(204, env);
}

export default { fetch: handle };
