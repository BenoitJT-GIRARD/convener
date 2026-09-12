/**
 * CORS relay for GitHub's OAuth device flow.
 *
 * GitHub's OAuth endpoints send no CORS headers, so a browser application
 * cannot call them directly. This worker forwards exactly two paths and adds
 * the headers. It holds no state, stores nothing, and logs no request body.
 */

const UPSTREAM = 'https://github.com';
const ALLOWED_PATHS = new Set(['/login/device/code', '/login/oauth/access_token']);

// Named rather than left to the runtime's default, for the reason
// services/form-relay states beside its own: GitHub answers 403 to a
// request whose User-Agent it does not like, before the call is evaluated.
// Measured there against api.github.com; unmeasured here, because these two
// OAuth paths accept the default today. They are also the whole of the
// device flow, so the day that changes every Board member is locked out at
// once, and the header costs a line.
const USER_AGENT = 'convener-auth-proxy';

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

export async function handle(request, env) {
  const origin = request.headers.get('Origin');
  if (origin !== env.ALLOWED_ORIGIN) {
    return new Response('Forbidden', { status: 403 });
  }

  if (request.method !== 'OPTIONS' && request.method !== 'POST') {
    return new Response('Method Not Allowed', {
      status: 405,
      headers: corsHeaders(env.ALLOWED_ORIGIN),
    });
  }

  const { pathname } = new URL(request.url);
  if (!ALLOWED_PATHS.has(pathname)) {
    return new Response('Not Found', { status: 404, headers: corsHeaders(env.ALLOWED_ORIGIN) });
  }

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders(env.ALLOWED_ORIGIN) });
  }

  const upstream = await fetch(`${UPSTREAM}${pathname}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'User-Agent': USER_AGENT,
    },
    body: await request.text(),
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      ...corsHeaders(env.ALLOWED_ORIGIN),
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
    },
  });
}

export default { fetch: handle };
