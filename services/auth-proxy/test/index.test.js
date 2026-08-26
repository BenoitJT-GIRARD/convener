import { describe, expect, it, vi, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { handle } from '../src/index.js';

// The origin this worker answers CORS preflights for
// is the one address `config/instance.json` declares this project is
// published at. A Worker can read none of that -- it runs on Cloudflare
// with no repository in reach -- so the deployed value lives in this
// package's own `wrangler.toml` and reaches `handle` as
// `env.ALLOWED_ORIGIN`; what a test can hold is that the value shipped
// for deployment is the address the project is actually published at.
// See `services/signup-relay/test/index.test.js`'s own copy of this
// block for the reasoning in full, including why the one TOML line is
// matched rather than parsed.
// Read inside the one test that needs it, never while this module loads.
// `config/instance.json` is a path
// `config/boundary.yml` hands to the instance, and a derived repository
// is entitled not to have it: a read at module scope would have taken
// this whole suite down at import -- every test in it, including the
// dozens that exercise the worker and touch no declaration at all -- with
// a stack trace instead of a sentence. Inside the test, exactly one
// assertion goes red, and it is the one that is actually about the
// declaration.
function declaredOrigin() {
  return new URL(
    JSON.parse(
      readFileSync(new URL('../../../config/instance.json', import.meta.url), 'utf-8'),
    ).published_url,
  ).origin;
}

const WRANGLER = readFileSync(new URL('../wrangler.toml', import.meta.url), 'utf-8');
const DEPLOYED_ORIGIN_MATCH = /^ALLOWED_ORIGIN\s*=\s*"([^"]+)"/m.exec(WRANGLER);
if (!DEPLOYED_ORIGIN_MATCH) {
  throw new Error(
    'wrangler.toml no longer declares ALLOWED_ORIGIN -- this worker would ' +
      'deploy answering CORS preflights for nothing at all',
  );
}
const ALLOWED_ORIGIN = DEPLOYED_ORIGIN_MATCH[1];

describe('the deployed origin is the address this project is published at', () => {
  it('matches config/instance.json', () => {
    expect(ALLOWED_ORIGIN).toBe(declaredOrigin());
  });
});

const env = { ALLOWED_ORIGIN };

function post(path, body = {}, origin = env.ALLOWED_ORIGIN) {
  return new Request(`https://relay.example${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Origin: origin },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  globalThis.fetch = vi.fn(async () =>
    new Response(JSON.stringify({ device_code: 'abc', user_code: 'WDJB-MJHT' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
});

describe('auth proxy', () => {
  it('forwards the device-code request and adds CORS headers', async () => {
    const res = await handle(post('/login/device/code', { client_id: 'Iv1.x' }), env);
    expect(res.status).toBe(200);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe(env.ALLOWED_ORIGIN);
    expect(await res.json()).toMatchObject({ user_code: 'WDJB-MJHT' });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'https://github.com/login/device/code',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('answers preflight without calling GitHub', async () => {
    const req = new Request('https://relay.example/login/device/code', {
      method: 'OPTIONS',
      headers: { Origin: env.ALLOWED_ORIGIN },
    });
    const res = await handle(req, env);
    expect(res.status).toBe(204);
    expect(res.headers.get('Access-Control-Allow-Methods')).toContain('POST');
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses an unknown origin', async () => {
    const res = await handle(post('/login/device/code', {}, 'https://evil.example'), env);
    expect(res.status).toBe(403);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a path that is not an OAuth endpoint', async () => {
    const res = await handle(post('/user/repos'), env);
    expect(res.status).toBe(404);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a method other than POST', async () => {
    const req = new Request('https://relay.example/login/device/code', {
      method: 'GET',
      headers: { Origin: env.ALLOWED_ORIGIN },
    });
    expect((await handle(req, env)).status).toBe(405);
  });

  it('passes the upstream status through on failure', async () => {
    globalThis.fetch = vi.fn(async () => new Response('nope', { status: 422 }));
    const res = await handle(post('/login/oauth/access_token', {}), env);
    expect(res.status).toBe(422);
  });

  it('sources Access-Control-Allow-Origin from config, not from the request, at every write site', async () => {
    // env.ALLOWED_ORIGIN is a getter so we can count how many times the code
    // reads *configuration* to build the header. The old implementation
    // (`corsHeaders(origin)`, where `origin` is the closed-over request
    // header) reads env.ALLOWED_ORIGIN exactly once — for the initial gate
    // comparison — and then reuses the request-derived variable for every
    // header it writes. The fixed implementation (`corsHeaders(env.ALLOWED_ORIGIN)`)
    // reads it again at each write site. A single successful POST touches the
    // gate once and the response header once, so the fixed code must read at
    // least twice; the old code would read exactly once and this assertion
    // would fail against it.
    let reads = 0;
    const trackedEnv = {
      get ALLOWED_ORIGIN() {
        reads += 1;
        return ALLOWED_ORIGIN;
      },
    };
    const res = await handle(
      post('/login/device/code', { client_id: 'Iv1.x' }, ALLOWED_ORIGIN),
      trackedEnv,
    );
    expect(res.status).toBe(200);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe(ALLOWED_ORIGIN);
    expect(reads).toBeGreaterThanOrEqual(2);
  });

  it('refuses an origin that differs from config only by case or a trailing slash', async () => {
    // The host upper-cased, not the whole URL: a scheme is case-insensitive
    // by RFC 3986 and upper-casing it too would test a second thing. Built
    // from the configured origin by string surgery rather than through
    // `new URL`, whose host setter lower-cases what it is given -- and
    // built rather than typed, so this case follows the declared address
    // like every other one in this file.
    const { protocol, host } = new URL(ALLOWED_ORIGIN);
    const upper = await handle(
      post('/login/device/code', {}, `${protocol}//${host.toUpperCase()}`),
      env,
    );
    expect(upper.status).toBe(403);
    expect(upper.headers.get('Access-Control-Allow-Origin')).toBeNull();

    const trailingSlash = await handle(post('/login/device/code', {}, `${env.ALLOWED_ORIGIN}/`), env);
    expect(trailingSlash.status).toBe(403);
    expect(trailingSlash.headers.get('Access-Control-Allow-Origin')).toBeNull();

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a preflight for a path that is not an OAuth endpoint', async () => {
    const req = new Request('https://relay.example/user/repos', {
      method: 'OPTIONS',
      headers: { Origin: env.ALLOWED_ORIGIN },
    });
    const res = await handle(req, env);
    expect(res.status).toBe(404);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
