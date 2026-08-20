import { describe, expect, it, vi, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { handle } from '../src/index.js';

// The shared fixture is the contract (decision D-14): the same hybrid
// wire format is written once in tools/convener_ops/eventkeys.py, once in
// app/src/signup/encrypt.ts, and pinned here as a real, correctly-shaped
// envelope -- rather than fabricated base64 this file would have to keep
// in sync with the RSA key size and GCM nonce length by hand.
const FIXTURE_PATH = fileURLToPath(
  new URL('../../../tools/tests/fixtures/governance-cases.json', import.meta.url),
);
const fixture = JSON.parse(readFileSync(FIXTURE_PATH, 'utf-8'));
const REGISTRATION_CASES = fixture.event_registration_encryption?.cases;

if (!REGISTRATION_CASES || REGISTRATION_CASES.length === 0) {
  throw new Error('event_registration_encryption fixture is empty');
}

const EVENT_ID = 'mrg-042';
const VALID_ENVELOPE = JSON.parse(REGISTRATION_CASES[0].envelope);
const VALID_BODY = JSON.stringify({ event_id: EVENT_ID, ...VALID_ENVELOPE });

const DISPATCH_URL = 'https://api.github.com/repos/example-instance/example-cockpit/dispatches';
const CONTENTS_URL = (id) =>
  `https://api.github.com/repos/example-instance/example-cockpit/contents/keys/events/${id}.pub`;

function post(body, headers = {}) {
  return new Request('https://relay.example/', { method: 'POST', headers, body });
}

function requestAt(path, method) {
  return new Request(`https://relay.example${path}`, { method });
}

function makeKv(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    store,
    get: vi.fn(async (key) => (store.has(key) ? store.get(key) : null)),
    put: vi.fn(async (key, value) => {
      store.set(key, value);
    }),
  };
}

function env(token = 'ghp_test-token', kv = makeKv()) {
  return { CONVENER_DISPATCH_TOKEN: token, SIGNUP_RELAY_KV: kv };
}

/** Routes the mocked fetch by URL: the existence check answers `known`
 *  (default true), the dispatch answers 204. */
function stubFetch({ known = true, dispatchStatus = 204 } = {}) {
  return vi.fn(async (url) => {
    const u = String(url);
    if (u.startsWith('https://api.github.com/repos/example-instance/example-cockpit/contents/')) {
      return new Response(null, { status: known ? 200 : 404 });
    }
    if (u === DISPATCH_URL) {
      return new Response(null, { status: dispatchStatus });
    }
    throw new Error(`unexpected fetch in test: ${u}`);
  });
}

beforeEach(() => {
  globalThis.fetch = stubFetch();
});

describe('signup relay -- routing', () => {
  it('refuses a method other than POST', async () => {
    const res = await handle(requestAt('/', 'GET'), env());
    expect(res.status).toBe(405);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('answers 404 on a path other than the one route', async () => {
    const res = await handle(requestAt('/unknown', 'POST'), env());
    expect(res.status).toBe(404);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('signup relay -- the happy path', () => {
  it('accepts a well-shaped, known-event envelope, dispatches it byte-identical, and counts it', async () => {
    const kv = makeKv();
    const res = await handle(post(VALID_BODY), env('ghp_test-token', kv));

    expect(res.status).toBe(204);

    const calls = globalThis.fetch.mock.calls;
    expect(calls).toHaveLength(2);

    const [existsUrl, existsInit] = calls[0];
    expect(String(existsUrl)).toBe(CONTENTS_URL(EVENT_ID));
    expect(existsInit.headers.Authorization).toBe('Bearer ghp_test-token');
    expect(existsInit.headers['User-Agent']).toBe('convener-signup-relay');

    const [dispatchUrl, dispatchInit] = calls[1];
    expect(dispatchUrl).toBe(DISPATCH_URL);
    expect(dispatchInit.headers['User-Agent']).toBe('convener-signup-relay');
    expect(dispatchInit.headers.Authorization).toBe('Bearer ghp_test-token');

    const sent = JSON.parse(dispatchInit.body);
    expect(sent.event_type).toBe('registration-submitted');
    // The dispatched field is a JSON string, never a nested object -- the
    // workflow that reads it interpolates it bare.
    expect(typeof sent.client_payload.body).toBe('string');
    // Byte-identical to what was received: never re-serialised.
    expect(sent.client_payload.body).toBe(VALID_BODY);

    // The per-event counter was written, once, to exactly one more than it
    // started at.
    expect(kv.put).toHaveBeenCalledWith('count:mrg-042', '1');
  });

  it('forwards every pinned registration case from the shared fixture', async () => {
    for (const c of REGISTRATION_CASES) {
      globalThis.fetch = stubFetch();
      const envelope = JSON.parse(c.envelope);
      const body = JSON.stringify({ event_id: EVENT_ID, ...envelope });
      const res = await handle(post(body), env());
      expect(res.status).toBe(204);
    }
  });
});

describe('signup relay -- shape validation (a shape check, not a content check)', () => {
  const mutations = [
    ['is not JSON at all', () => 'not json'],
    ['is a JSON array, not an object', () => JSON.stringify([1, 2, 3])],
    ['is missing event_id', () => {
      const { event_id, ...rest } = JSON.parse(VALID_BODY);
      void event_id;
      return JSON.stringify(rest);
    }],
    ['carries an extra, unexpected field', () => JSON.stringify({ ...JSON.parse(VALID_BODY), extra: 'x' })],
    ['has an event_id with a path separator', () => JSON.stringify({ ...JSON.parse(VALID_BODY), event_id: 'vw/042' })],
    ['has an event_id starting with a dot', () => JSON.stringify({ ...JSON.parse(VALID_BODY), event_id: '.mrg-042' })],
    ['has the wrong wire version', () => JSON.stringify({ ...JSON.parse(VALID_BODY), v: 2 })],
    ['has v as a string, not a number', () => JSON.stringify({ ...JSON.parse(VALID_BODY), v: '1' })],
    ['has encrypted_key that is not valid base64', () => JSON.stringify({ ...JSON.parse(VALID_BODY), encrypted_key: '***not base64***' })],
    ['has an encrypted_key one byte short of 256', () => {
      const b = JSON.parse(VALID_BODY);
      return JSON.stringify({ ...b, encrypted_key: btoa('x'.repeat(255)) });
    }],
    ['has an iv that is not 12 bytes', () => {
      const b = JSON.parse(VALID_BODY);
      return JSON.stringify({ ...b, iv: btoa('short') });
    }],
    ['has a ciphertext shorter than a bare GCM tag', () => {
      const b = JSON.parse(VALID_BODY);
      return JSON.stringify({ ...b, ciphertext: btoa('x'.repeat(15)) });
    }],
    ['has a ciphertext far past the plausible-length ceiling', () => {
      const b = JSON.parse(VALID_BODY);
      return JSON.stringify({ ...b, ciphertext: btoa('x'.repeat(20_000)) });
    }],
  ];

  it.each(mutations)('refuses a body that %s, with 400, and touches nothing else', async (_label, make) => {
    const kv = makeKv();
    const res = await handle(post(make()), env('ghp_test-token', kv));
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(kv.get).not.toHaveBeenCalled();
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('refuses a body declared oversized by Content-Length before reading it', async () => {
    const res = await handle(
      post(VALID_BODY, { 'content-length': String(10 * 1024 * 1024) }),
      env(),
    );
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('signup relay -- the event must be known', () => {
  it('refuses an unknown event id with 404, and never dispatches', async () => {
    globalThis.fetch = stubFetch({ known: false });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(404);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1); // the existence check only
  });

  it('reports 502, not 404, when the existence check itself cannot be completed', async () => {
    globalThis.fetch = vi.fn(async (url) => {
      const u = String(url);
      if (u.startsWith('https://api.github.com/repos/example-instance/example-cockpit/contents/')) {
        return new Response(null, { status: 403 }); // rate-limited, not "no such event"
      }
      throw new Error(`unexpected fetch in test: ${u}`);
    });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(502);
  });

  it('reports 502 when the existence check cannot even be attempted (a real network failure)', async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError('fetch failed');
    });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(502);
  });
});

describe('signup relay -- fail closed on a missing secret or store', () => {
  it.each([
    ['CONVENER_DISPATCH_TOKEN is unset', { CONVENER_DISPATCH_TOKEN: undefined, SIGNUP_RELAY_KV: makeKv() }],
    ['CONVENER_DISPATCH_TOKEN is an empty string', { CONVENER_DISPATCH_TOKEN: '', SIGNUP_RELAY_KV: makeKv() }],
    ['SIGNUP_RELAY_KV is not bound', { CONVENER_DISPATCH_TOKEN: 'ghp_test-token', SIGNUP_RELAY_KV: undefined }],
  ])('refuses every well-shaped request when %s, and never calls GitHub', async (_label, badEnv) => {
    const res = await handle(post(VALID_BODY), badEnv);
    expect(res.status).toBe(502);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('signup relay -- dispatch failure', () => {
  it('reports a failed dispatch as 502, without disclosing GitHub upstream detail', async () => {
    globalThis.fetch = stubFetch({ dispatchStatus: 401 });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(502);
  });

  it('reports 502 when the dispatch cannot even be attempted (a real network failure)', async () => {
    globalThis.fetch = vi.fn(async (url) => {
      const u = String(url);
      if (u.startsWith('https://api.github.com/repos/example-instance/example-cockpit/contents/')) {
        return new Response(null, { status: 200 });
      }
      throw new TypeError('fetch failed');
    });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(502);
  });

  it('does not count a failed dispatch toward the per-event ceiling', async () => {
    globalThis.fetch = stubFetch({ dispatchStatus: 500 });
    const kv = makeKv();
    await handle(post(VALID_BODY), env('ghp_test-token', kv));
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('normalises any 2xx from GitHub to a fixed 204, never the literal upstream code', async () => {
    globalThis.fetch = stubFetch({ dispatchStatus: 202 });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(204);
  });
});

describe('signup relay -- the per-event ceiling', () => {
  it('refuses once an event has reached the ceiling, without calling GitHub at all', async () => {
    const kv = makeKv({ 'count:mrg-042': '500' });
    const res = await handle(post(VALID_BODY), env('ghp_test-token', kv));
    expect(res.status).toBe(429);
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('still accepts the request one below the ceiling, and the count becomes the ceiling', async () => {
    const kv = makeKv({ 'count:mrg-042': '499' });
    const res = await handle(post(VALID_BODY), env('ghp_test-token', kv));
    expect(res.status).toBe(204);
    expect(kv.put).toHaveBeenCalledWith('count:mrg-042', '500');
  });

  it('keeps each event on its own counter -- a full event does not block a different one', async () => {
    const kv = makeKv({ 'count:mrg-042': '500' });
    const otherBody = JSON.stringify({ event_id: 'mrg-043', ...VALID_ENVELOPE });
    const res = await handle(post(otherBody), env('ghp_test-token', kv));
    expect(res.status).toBe(204);
  });

  it('treats a KV read failure as no count yet, rather than refusing the request', async () => {
    const kv = makeKv();
    kv.get = vi.fn(async () => {
      throw new Error('kv unavailable');
    });
    const res = await handle(post(VALID_BODY), env('ghp_test-token', kv));
    expect(res.status).toBe(204);
  });

  it('still answers 204 when the counter cannot be written after a successful dispatch', async () => {
    const kv = makeKv();
    kv.put = vi.fn(async () => {
      throw new Error('kv unavailable');
    });
    const res = await handle(post(VALID_BODY), env('ghp_test-token', kv));
    expect(res.status).toBe(204);
  });
});
