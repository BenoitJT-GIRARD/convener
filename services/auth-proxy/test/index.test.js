import { describe, expect, it, vi, beforeEach } from 'vitest';
import { handle } from '../src/index.js';

const env = { ALLOWED_ORIGIN: 'https://example-instance.github.io' };

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
});
