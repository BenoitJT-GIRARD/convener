/**
 * CORS relay for GitHub's OAuth device flow.
 *
 * GitHub's OAuth endpoints send no CORS headers, so a browser application
 * cannot call them directly. This worker forwards exactly two paths and adds
 * the headers. It holds no state, stores nothing, and logs no request body.
 */

const UPSTREAM = 'https://github.com';
const ALLOWED_PATHS = new Set(['/login/device/code', '/login/oauth/access_token']);

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
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
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
