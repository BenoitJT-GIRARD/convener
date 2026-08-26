/**
 * The bridge from Tally's webhook to a GitHub repository_dispatch.
 *
 * Tally signs a submission as base64(HMAC-SHA256(secret, rawBody)) in a
 * `Tally-Signature` header, over the raw JSON body and nothing else -- not
 * a wrapper, not a re-encoding. This worker checks that signature (the same
 * rule tools/convener_ops/proposal.py::verify_signature checks again, from a
 * shared fixture, once the payload reaches GitHub Actions) and, only if it
 * holds, forwards the raw body onward as a `proposal-submitted`
 * repository_dispatch.
 *
 * Unlike services/auth-proxy, this worker holds a GitHub token, so it
 * cannot be secret-free -- see README.md for why that makes it a separate
 * worker rather than another route on the existing one.
 *
 * It logs no request body and keeps nothing beyond the abuse-protection
 * counter README.md describes -- and a counter is a count, never the data
 * that produced it.
 *
 * 401 is reserved for a caller's own bad or missing Tally-Signature. Any
 * failure to complete the dispatch to GitHub -- an expired
 * CONVENER_DISPATCH_TOKEN, GitHub rejecting the call, GitHub being unreachable
 * -- reports 502 instead, on purpose: GitHub answers a bad token with 401
 * too, and if this worker passed that through unchanged, an expired
 * dispatch token and a forged submission would look identical in Tally's
 * webhook log, and an operator would go rotate the wrong secret.
 *
 * Bounds, at last
 * ---------------
 * This worker once had no body-size bound, no rate limiter and
 * no counter at all -- unlike services/signup-relay, which has all three
 * (README.md there, "Abuse protection"). A caller who already holds
 * TALLY_WEBHOOK_SECRET (a leak, an insider, a brute-forced weak secret)
 * could otherwise flood `.github/workflows/candidate-form.yml` with
 * `repository_dispatch` runs at no cost beyond signing each body, with
 * nothing here to slow it down. See README.md, "Abuse protection", for
 * why these three specific bounds and these specific numbers.
 */

const ROUTE = '/';
const DISPATCH_URL = 'https://api.github.com/repos/example-instance/example-cockpit/dispatches';
const USER_AGENT = 'convener-form-relay';

// A pre-parse guard on the whole request body, checked before it is even
// read: Tally's own payload wraps up to eleven fields (proposal.py::
// FORM_FIELDS), each carrying its question text and field metadata beside
// the answer, and a short abstract can run to a few paragraphs. 64 KiB is
// comfortably above any real submission's shape while remaining a firm,
// cheap-to-enforce ceiling far below "arbitrary" -- see README.md for the
// numbers this mirrors on services/signup-relay's own MAX_BODY_BYTES.
const MAX_BODY_BYTES = 65_536;

// The whole-lifetime cumulative ceiling on accepted submissions -- see
// README.md, "Abuse protection", for why this is a plain, ever-growing
// total rather than a per-window one the way services/signup-relay's own
// PER_EVENT_CEILING resets naturally per event id. An order of magnitude
// above any plausible number of real proposals this call-for-candidates
// form will ever receive over the project's life, the same "not a hard
// defence, a signal worth surfacing" reasoning services/signup-relay's own
// README.md gives for its own ceiling.
const PROPOSAL_CEILING = 2000;
const PROPOSAL_COUNTER_KEY = 'count:proposal';

// One shared burst limiter across the whole endpoint -- see README.md for
// why a single fixed key, not one derived from anything a caller sends: a
// key an attacker chooses is exactly the gap next door (services/signup-relay's
// limiter, keyed on the attacker-supplied event id, let a caller who
// varies that field evade it entirely). There is nothing on this form to
// vary a key by that would not repeat that mistake.
const RATE_LIMITER_KEY = 'proposal';

// GitHub's own dispatches endpoint has no documented timeout of its own --
// mirrors services/signup-relay's GITHUB_FETCH_TIMEOUT_MS so an
// unresponsive upstream cannot hold this worker's invocation open
// indefinitely.
const GITHUB_FETCH_TIMEOUT_MS = 5_000;

/**
 * Constant-time string comparison: walks the full length in every case,
 * rather than returning at the first mismatched character the way `===`
 * effectively does, so a wrong signature cannot be timed byte by byte.
 */
function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function signature(secret, body) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const digest = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  let binary = '';
  for (const byte of new Uint8Array(digest)) binary += String.fromCharCode(byte);
  return btoa(binary);
}

export async function handle(request, env) {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  const { pathname } = new URL(request.url);
  if (pathname !== ROUTE) {
    return new Response('Not Found', { status: 404 });
  }

  // Refuse an oversized body before it is even read into memory, when
  // the caller was honest enough to say how big it is -- the same
  // pre-parse guard services/signup-relay's own MAX_BODY_BYTES check uses.
  // The authoritative check is the real-byte-length check below; this only
  // saves the work of reading and hashing something that can never pass
  // it.
  const declaredLength = request.headers.get('content-length');
  if (declaredLength && Number(declaredLength) > MAX_BODY_BYTES) {
    return new Response('Bad Request', { status: 400 });
  }

  // Fail closed. An unconfigured secret refuses every request here,
  // the opposite of proposal.py::verify_signature's tolerance -- that
  // tolerance is safe only because it sits behind a repository_dispatch
  // that already required an authenticated token. This worker is the
  // internet-facing boundary, so tolerance has no safe place in it.
  const secret = env.TALLY_WEBHOOK_SECRET;
  if (!secret) {
    return new Response('Unauthorized', { status: 401 });
  }

  const given = request.headers.get('Tally-Signature');
  if (!given) {
    return new Response('Unauthorized', { status: 401 });
  }

  // Read raw, unparsed: what gets signed, compared and forwarded must stay
  // exactly the bytes Tally sent. Guarded: an aborted or malformed request
  // body throws here rather than resolving, and an uncaught throw would
  // escape as workerd's own generic error page -- outside the closed set
  // of statuses this worker promises.
  let body;
  try {
    body = await request.text();
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  // `body.length` is UTF-16 code units, not bytes -- the same
  // real-byte-length guard services/signup-relay's own index.js applies,
  // for the identical reason (a multi-byte-heavy body could pass a
  // byte-denominated MAX_BODY_BYTES compared against that count).
  if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) {
    return new Response('Bad Request', { status: 400 });
  }

  const expected = await signature(secret, body);
  if (!safeEqual(expected, given)) {
    return new Response('Unauthorized', { status: 401 });
  }

  // Failing closed, extended to the second secret and the two
  // abuse-protection bindings: a missing CONVENER_DISPATCH_TOKEN must not round-trip a
  // literal "undefined" Authorization header to GitHub, and a missing KV
  // or rate-limiter binding must refuse rather than silently skip the
  // check it exists for -- the same fail-closed discipline
  // services/signup-relay's own index.js applies to
  // SIGNUP_RELAY_KV/SIGNUP_RATE_LIMITER. Checked only once a valid
  // signature is already confirmed, so an unsigned flood never reaches --
  // or spends -- either binding.
  const token = env.CONVENER_DISPATCH_TOKEN;
  const kv = env.FORM_RELAY_KV;
  const rateLimiter = env.FORM_RATE_LIMITER;
  if (!token || !kv || !rateLimiter) {
    return new Response('Bad Gateway', { status: 502 });
  }

  // The burst limiter, checked before anything else touches GitHub or
  // the cumulative counter -- the same ordering services/signup-relay's
  // own index.js uses for its per-event limiter. One shared key across the
  // whole endpoint (RATE_LIMITER_KEY, a fixed literal -- see this worker's
  // own module comment and README.md for why the neighbouring mistake, a
  // caller-chosen key, is not repeated here): there is only one form, so
  // there is no legitimate reason to key this any finer, and any key
  // derived from caller-supplied data is exactly the gap that let
  // services/signup-relay's own limiter be evaded by varying it.
  let limited;
  try {
    limited = await rateLimiter.limit({ key: RATE_LIMITER_KEY });
  } catch {
    return new Response('Bad Gateway', { status: 502 });
  }
  if (!limited.success) {
    return new Response('Too Many Requests', { status: 429, headers: { 'Retry-After': '60' } });
  }

  // The cumulative ceiling, checked before the dispatch to GitHub --
  // cheaper to refuse here than to spend a GitHub API call on a request
  // that will be refused anyway. A KV read failure is treated as "no count
  // yet" rather than refusing the request, the same accepted trade-off
  // services/signup-relay's own README.md documents for its own counter.
  let count = 0;
  try {
    const stored = await kv.get(PROPOSAL_COUNTER_KEY);
    count = stored ? Number.parseInt(stored, 10) || 0 : 0;
  } catch {
    count = 0;
  }
  if (count >= PROPOSAL_CEILING) {
    return new Response('Too Many Requests', { status: 429, headers: { 'Retry-After': '60' } });
  }

  let upstream;
  try {
    upstream = await fetch(DISPATCH_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        // GitHub's REST API rejects a request with no User-Agent (403).
        'User-Agent': USER_AGENT,
      },
      // `body` must be a JSON *string*, never a nested object: the workflow
      // reads it as a bare ${{ github.event.client_payload.body }}
      // interpolation, which only renders raw JSON when the value is a
      // string. It is the exact bytes received, untouched.
      body: JSON.stringify({
        event_type: 'proposal-submitted',
        client_payload: { body, signature: given },
      }),
      signal: AbortSignal.timeout(GITHUB_FETCH_TIMEOUT_MS),
    });
  } catch {
    // A rejected fetch -- GitHub unreachable, DNS failure, a reset
    // connection -- is exactly as much "this worker could not complete
    // the dispatch" as a 401 or 500 answered by GitHub. Left uncaught,
    // this would escape as an uncaught exception, and workerd's generic
    // platform error page is not this worker's 502.
    return new Response('Bad Gateway', { status: 502 });
  }

  if (!upstream.ok) {
    // Never GitHub's status or body verbatim -- see the file-level comment
    // for why 401 must not leak through, and a caller with a valid
    // signature has no need to see GitHub's error detail either.
    return new Response('Bad Gateway', { status: 502 });
  }

  // Best-effort, after a confirmed dispatch -- a submission that
  // reached GitHub must not be un-sent because the counter could not be
  // written afterwards. Mirrors services/signup-relay's own
  // write-failure trace: a fixed message and no data that could identify
  // the submitter, never the body.
  try {
    await kv.put(PROPOSAL_COUNTER_KEY, String(count + 1));
  } catch {
    console.error('form-relay: failed to update the proposal counter');
  }

  // Fixed 204, not upstream.status: GitHub's dispatches endpoint is
  // documented to answer success with exactly 204, and returning the
  // literal upstream code here would let an unexpected 2xx (200, 202, ...)
  // leak through as-is -- a smaller version of the same "upstream detail
  // reaches the caller" problem the 502 branches above exist to avoid.
  // The caller only ever sees one of 204, 400, 401, 404, 405, 429 or 502
  // from this worker.
  return new Response(null, { status: 204 });
}

export default { fetch: handle };
