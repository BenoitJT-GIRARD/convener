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
 * It logs no request body and keeps nothing.
 */

const ROUTE = '/';
const DISPATCH_URL = 'https://api.github.com/repos/example-instance/example-cockpit/dispatches';

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

  // R-6: fail closed. An unconfigured secret refuses every request here,
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
  // exactly the bytes Tally sent.
  const body = await request.text();

  const expected = await signature(secret, body);
  if (!safeEqual(expected, given)) {
    return new Response('Unauthorized', { status: 401 });
  }

  const upstream = await fetch(DISPATCH_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CONVENER_DISPATCH_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
      // GitHub's REST API rejects a request with no User-Agent (403).
      'User-Agent': 'convener-form-relay',
    },
    // `body` must be a JSON *string*, never a nested object: the workflow
    // reads it as a bare ${{ github.event.client_payload.body }}
    // interpolation, which only renders raw JSON when the value is a
    // string (R-7). It is the exact bytes received, untouched.
    body: JSON.stringify({
      event_type: 'proposal-submitted',
      client_payload: { body, signature: given },
    }),
  });

  // A successful dispatch is 204 No Content, not 200 -- pass the upstream
  // status through rather than assuming one.
  return new Response(upstream.body, { status: upstream.status });
}

export default { fetch: handle };
