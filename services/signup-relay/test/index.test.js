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

const SURVEY_CASES = fixture.event_survey_response_encryption?.cases;
if (!SURVEY_CASES || SURVEY_CASES.length === 0) {
  throw new Error('event_survey_response_encryption fixture is empty');
}

const EVENT_ID = 'mrg-042';
const VALID_ENVELOPE = JSON.parse(REGISTRATION_CASES[0].envelope);
const VALID_BODY = JSON.stringify({ event_id: EVENT_ID, ...VALID_ENVELOPE });
const SURVEY_ENVELOPE = JSON.parse(SURVEY_CASES[0].envelope);
const SURVEY_BODY = JSON.stringify({ event_id: EVENT_ID, ...SURVEY_ENVELOPE });

// Mirrors services/signup-relay/wrangler.toml's ALLOWED_ORIGIN, which in
// turn mirrors services/auth-proxy/wrangler.toml's -- the app's origin,
// not its full URL (Origin never carries a path).
const ALLOWED_ORIGIN = 'https://example-instance.github.io';

const DISPATCH_URL = 'https://api.github.com/repos/example-instance/example-cockpit/dispatches';
const CONTENTS_URL = (id) =>
  `https://api.github.com/repos/example-instance/example-cockpit/contents/keys/events/${id}.pub`;

function post(body, headers = {}) {
  return new Request('https://relay.example/', {
    method: 'POST',
    headers: { Origin: ALLOWED_ORIGIN, ...headers },
    body,
  });
}

/** Same as `post`, against `/survey` instead of the bare registration
 *  route. */
function postSurvey(body, headers = {}) {
  return new Request('https://relay.example/survey', {
    method: 'POST',
    headers: { Origin: ALLOWED_ORIGIN, ...headers },
    body,
  });
}

function requestAt(path, method, headers = {}) {
  return new Request(`https://relay.example${path}`, {
    method,
    headers: { Origin: ALLOWED_ORIGIN, ...headers },
  });
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

function makeRateLimiter(success = true) {
  return { limit: vi.fn(async () => ({ success })) };
}

function env(overrides = {}) {
  return {
    CONVENER_DISPATCH_TOKEN: 'ghp_test-token',
    SIGNUP_RELAY_KV: makeKv(),
    SIGNUP_RATE_LIMITER: makeRateLimiter(),
    ALLOWED_ORIGIN,
    ...overrides,
  };
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

describe('signup relay -- CORS and the browser boundary', () => {
  it('answers an OPTIONS preflight from the allowed origin with 204 and every CORS header a browser needs', async () => {
    const res = await handle(requestAt('/', 'OPTIONS'), env());
    expect(res.status).toBe(204);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe(ALLOWED_ORIGIN);
    expect(res.headers.get('Access-Control-Allow-Methods')).toBe('POST, OPTIONS');
    expect(res.headers.get('Access-Control-Allow-Headers')).toBe('Content-Type, Accept');
    expect(res.headers.get('Vary')).toBe('Origin');
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('carries CORS headers on a real success response, not only the preflight', async () => {
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(204);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe(ALLOWED_ORIGIN);
  });

  it('carries CORS headers on an error response too -- a fetch() cannot read a response with none', async () => {
    const res = await handle(post('not json'), env());
    expect(res.status).toBe(400);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe(ALLOWED_ORIGIN);
  });

  it('refuses a request from any other origin with a bare 403 -- no CORS headers, nothing touched', async () => {
    const res = await handle(post(VALID_BODY, { Origin: 'https://evil.example' }), env());
    expect(res.status).toBe(403);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBeNull();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a request with no Origin header at all', async () => {
    const res = await handle(
      new Request('https://relay.example/', { method: 'POST', body: VALID_BODY }),
      env(),
    );
    expect(res.status).toBe(403);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses every request when ALLOWED_ORIGIN is not configured, even from what would otherwise be the right origin', async () => {
    const res = await handle(post(VALID_BODY), env({ ALLOWED_ORIGIN: undefined }));
    expect(res.status).toBe(403);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('signup relay -- routing', () => {
  it('refuses a method other than POST or OPTIONS', async () => {
    const res = await handle(requestAt('/', 'GET'), env());
    expect(res.status).toBe(405);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('answers 404 on a path other than the two known routes', async () => {
    const res = await handle(requestAt('/unknown', 'POST'), env());
    expect(res.status).toBe(404);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('signup relay -- the happy path', () => {
  it('accepts a well-shaped, known-event envelope, dispatches it byte-identical, and counts it', async () => {
    const kv = makeKv();
    const res = await handle(post(VALID_BODY), env({ SIGNUP_RELAY_KV: kv }));

    expect(res.status).toBe(204);

    const calls = globalThis.fetch.mock.calls;
    expect(calls).toHaveLength(2);

    const [existsUrl, existsInit] = calls[0];
    expect(String(existsUrl)).toBe(CONTENTS_URL(EVENT_ID));
    expect(existsInit.headers.Authorization).toBe('Bearer ghp_test-token');
    expect(existsInit.headers['User-Agent']).toBe('convener-signup-relay');
    // Neither GitHub call is left to hang on this worker's own invocation
    // forever -- both carry a timeout signal.
    expect(existsInit.signal).toBeInstanceOf(AbortSignal);

    const [dispatchUrl, dispatchInit] = calls[1];
    expect(dispatchUrl).toBe(DISPATCH_URL);
    expect(dispatchInit.headers['User-Agent']).toBe('convener-signup-relay');
    expect(dispatchInit.headers.Authorization).toBe('Bearer ghp_test-token');
    expect(dispatchInit.signal).toBeInstanceOf(AbortSignal);

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
    const rateLimiter = makeRateLimiter();
    const res = await handle(post(make()), env({ SIGNUP_RELAY_KV: kv, SIGNUP_RATE_LIMITER: rateLimiter }));
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(kv.get).not.toHaveBeenCalled();
    expect(kv.put).not.toHaveBeenCalled();
    expect(rateLimiter.limit).not.toHaveBeenCalled();
  });

  it('refuses a body declared oversized by Content-Length before reading it', async () => {
    const res = await handle(
      post(VALID_BODY, { 'content-length': String(10 * 1024 * 1024) }),
      env(),
    );
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a body whose real byte length exceeds the budget even when its UTF-16 length does not', async () => {
    // Every field this worker accepts is ASCII by construction (event_id's
    // token charset, base64 for the rest, and `v` a bare number), so a
    // shape-valid envelope can never itself hit this path -- this pins the
    // resource guard's own precision (MAX_BODY_BYTES is a byte budget, and
    // must be measured in bytes, not UTF-16 code units), not an acceptance
    // bug. A repeated 3-byte character keeps `.length` (UTF-16 units) at a
    // third of the true UTF-8 byte count, comfortably under the budget
    // while the real byte count is comfortably over it.
    const oversized = '€'.repeat(11_000); // length 11,000; byte length 33,000
    const res = await handle(post(oversized), env());
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a request whose body cannot even be read (an aborted or broken stream)', async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.error(new Error('stream broken'));
      },
    });
    const request = new Request('https://relay.example/', {
      method: 'POST',
      headers: { Origin: ALLOWED_ORIGIN },
      body: stream,
      duplex: 'half',
    });
    const res = await handle(request, env());
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a body with a duplicated event_id key, even though JSON.parse would silently resolve one', async () => {
    // JSON.parse keeps only the last "event_id", so Object.keys(parsed)
    // shows exactly the expected five keys -- the exact-set check alone
    // cannot see this. The forwarded raw body still carries both.
    const dup =
      `{"event_id":"${EVENT_ID}","event_id":"mrg-999",` +
      `"v":${VALID_ENVELOPE.v},"encrypted_key":"${VALID_ENVELOPE.encrypted_key}",` +
      `"iv":"${VALID_ENVELOPE.iv}","ciphertext":"${VALID_ENVELOPE.ciphertext}"}`;
    // Sanity check on the test's own premise: this really is valid JSON
    // that a naive parsed-object-only check would accept.
    expect(() => JSON.parse(dup)).not.toThrow();
    const res = await handle(post(dup), env());
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a body with a duplicated key anywhere, not only event_id', async () => {
    const dup = VALID_BODY.replace('"v":1,', '"v":1,"v":1,');
    expect(() => JSON.parse(dup)).not.toThrow();
    const res = await handle(post(dup), env());
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
    ['CONVENER_DISPATCH_TOKEN is unset', { CONVENER_DISPATCH_TOKEN: undefined }],
    ['CONVENER_DISPATCH_TOKEN is an empty string', { CONVENER_DISPATCH_TOKEN: '' }],
    ['SIGNUP_RELAY_KV is not bound', { SIGNUP_RELAY_KV: undefined }],
    ['SIGNUP_RATE_LIMITER is not bound', { SIGNUP_RATE_LIMITER: undefined }],
  ])('refuses every well-shaped request when %s, and never calls GitHub', async (_label, override) => {
    const res = await handle(post(VALID_BODY), env(override));
    expect(res.status).toBe(502);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('signup relay -- the burst limiter', () => {
  it('refuses once the per-event burst limiter trips, with Retry-After, and never calls GitHub', async () => {
    const rateLimiter = makeRateLimiter(false);
    const kv = makeKv();
    const res = await handle(post(VALID_BODY), env({ SIGNUP_RATE_LIMITER: rateLimiter, SIGNUP_RELAY_KV: kv }));
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBe('60');
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(kv.get).not.toHaveBeenCalled();
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('keys the limiter by event id', async () => {
    const rateLimiter = makeRateLimiter(true);
    await handle(post(VALID_BODY), env({ SIGNUP_RATE_LIMITER: rateLimiter }));
    expect(rateLimiter.limit).toHaveBeenCalledWith({ key: EVENT_ID });
  });

  it('fails closed (502) when the limiter itself cannot be reached, rather than skipping it', async () => {
    const rateLimiter = { limit: vi.fn(async () => { throw new Error('unavailable'); }) };
    const res = await handle(post(VALID_BODY), env({ SIGNUP_RATE_LIMITER: rateLimiter }));
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
    await handle(post(VALID_BODY), env({ SIGNUP_RELAY_KV: kv }));
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('normalises any 2xx from GitHub to a fixed 204, never the literal upstream code', async () => {
    globalThis.fetch = stubFetch({ dispatchStatus: 202 });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(204);
  });
});

describe('signup relay -- the per-event cumulative ceiling', () => {
  it('refuses once an event has reached the ceiling, with Retry-After, without calling GitHub at all', async () => {
    const kv = makeKv({ 'count:mrg-042': '500' });
    const res = await handle(post(VALID_BODY), env({ SIGNUP_RELAY_KV: kv }));
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBe('60');
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('still accepts the request one below the ceiling, and the count becomes the ceiling', async () => {
    const kv = makeKv({ 'count:mrg-042': '499' });
    const res = await handle(post(VALID_BODY), env({ SIGNUP_RELAY_KV: kv }));
    expect(res.status).toBe(204);
    expect(kv.put).toHaveBeenCalledWith('count:mrg-042', '500');
  });

  it('keeps each event on its own counter -- a full event does not block a different one, and writes that event\'s own key', async () => {
    const kv = makeKv({ 'count:mrg-042': '500' });
    const otherBody = JSON.stringify({ event_id: 'mrg-043', ...VALID_ENVELOPE });
    const res = await handle(post(otherBody), env({ SIGNUP_RELAY_KV: kv }));
    expect(res.status).toBe(204);
    // Not just "some" write succeeded -- the write landed on mrg-043's own
    // key, not mrg-042's (which would silently push the full event further
    // over its ceiling instead of tracking the new one).
    expect(kv.put).toHaveBeenCalledWith('count:mrg-043', '1');
    expect(kv.put).not.toHaveBeenCalledWith('count:mrg-042', expect.anything());
  });

  it('treats a KV read failure as no count yet, rather than refusing the request', async () => {
    const kv = makeKv();
    kv.get = vi.fn(async () => {
      throw new Error('kv unavailable');
    });
    const res = await handle(post(VALID_BODY), env({ SIGNUP_RELAY_KV: kv }));
    expect(res.status).toBe(204);
  });

  it('still answers 204 when the counter cannot be written after a successful dispatch, and traces the failure', async () => {
    const kv = makeKv();
    kv.put = vi.fn(async () => {
      throw new Error('kv unavailable');
    });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const res = await handle(post(VALID_BODY), env({ SIGNUP_RELAY_KV: kv }));
      expect(res.status).toBe(204);
      // A write failure is no longer discarded without a trace -- but the
      // trace names only the event id (already public) and a fixed
      // message, never the body.
      expect(errorSpy).toHaveBeenCalledTimes(1);
      const [logged] = errorSpy.mock.calls[0];
      expect(logged).toContain(EVENT_ID);
      expect(logged).not.toContain(VALID_BODY);
    } finally {
      errorSpy.mockRestore();
    }
  });
});

describe('signup relay -- the /survey route (task 16, spec S:6)', () => {
  it('accepts a well-shaped, known-event survey envelope, and dispatches it as survey-response-submitted', async () => {
    const kv = makeKv();
    const res = await handle(postSurvey(SURVEY_BODY), env({ SIGNUP_RELAY_KV: kv }));

    expect(res.status).toBe(204);

    const calls = globalThis.fetch.mock.calls;
    expect(calls).toHaveLength(2);
    const [, dispatchInit] = calls[1];
    const sent = JSON.parse(dispatchInit.body);
    expect(sent.event_type).toBe('survey-response-submitted');
    expect(sent.client_payload.body).toBe(SURVEY_BODY);

    // A distinct counter key from registration's own, so the two never
    // share -- or corrupt -- one budget.
    expect(kv.put).toHaveBeenCalledWith('count:survey:mrg-042', '1');
  });

  it('forwards every pinned survey case from the shared fixture', async () => {
    for (const c of SURVEY_CASES) {
      globalThis.fetch = stubFetch();
      const envelope = JSON.parse(c.envelope);
      const body = JSON.stringify({ event_id: EVENT_ID, ...envelope });
      const res = await handle(postSurvey(body), env());
      expect(res.status).toBe(204);
    }
  });

  it('applies the identical shape validation as the registration route -- a malformed envelope is refused with 400', async () => {
    const res = await handle(postSurvey('not json'), env());
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('answers the OPTIONS preflight on /survey the same as on /', async () => {
    const res = await handle(
      new Request('https://relay.example/survey', {
        method: 'OPTIONS',
        headers: { Origin: ALLOWED_ORIGIN },
      }),
      env(),
    );
    expect(res.status).toBe(204);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe(ALLOWED_ORIGIN);
  });

  it('refuses an unknown event id on /survey with 404, the same as on /', async () => {
    globalThis.fetch = stubFetch({ known: false });
    const res = await handle(postSurvey(SURVEY_BODY), env());
    expect(res.status).toBe(404);
  });

  describe('the survey path fails closed exactly like the registration path', () => {
    it.each([
      ['CONVENER_DISPATCH_TOKEN is unset', { CONVENER_DISPATCH_TOKEN: undefined }],
      ['SIGNUP_RELAY_KV is not bound', { SIGNUP_RELAY_KV: undefined }],
      ['SIGNUP_RATE_LIMITER is not bound', { SIGNUP_RATE_LIMITER: undefined }],
    ])('refuses every well-shaped /survey request when %s, and never calls GitHub', async (_label, override) => {
      const res = await handle(postSurvey(SURVEY_BODY), env(override));
      expect(res.status).toBe(502);
      expect(globalThis.fetch).not.toHaveBeenCalled();
    });
  });

  describe('the survey path has its own abuse ceiling -- not a bypass of the registration one', () => {
    it('keys the burst limiter separately from the registration route, for the same event', async () => {
      const rateLimiter = makeRateLimiter(true);
      await handle(postSurvey(SURVEY_BODY), env({ SIGNUP_RATE_LIMITER: rateLimiter }));
      expect(rateLimiter.limit).toHaveBeenCalledWith({ key: 'survey:mrg-042' });
    });

    it('refuses once the survey burst limiter trips, with Retry-After, and never calls GitHub', async () => {
      const rateLimiter = makeRateLimiter(false);
      const res = await handle(postSurvey(SURVEY_BODY), env({ SIGNUP_RATE_LIMITER: rateLimiter }));
      expect(res.status).toBe(429);
      expect(res.headers.get('Retry-After')).toBe('60');
      expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it('refuses once the survey cumulative ceiling is reached, on its own counter key, without touching the registration counter', async () => {
      const kv = makeKv({ 'count:survey:mrg-042': '500' });
      const res = await handle(postSurvey(SURVEY_BODY), env({ SIGNUP_RELAY_KV: kv }));
      expect(res.status).toBe(429);
      expect(globalThis.fetch).not.toHaveBeenCalled();
      expect(kv.put).not.toHaveBeenCalled();
    });

    it('a survey at its ceiling does not block a registration for the same event, and vice versa', async () => {
      // The registration counter is already at the ceiling; the survey
      // counter for the same event is untouched. A registration must still
      // be refused (its own ceiling) while a survey response for the same
      // event must still be accepted (a fresh counter under a different key).
      const kv = makeKv({ 'count:mrg-042': '500' });
      const registrationRes = await handle(post(VALID_BODY), env({ SIGNUP_RELAY_KV: kv }));
      expect(registrationRes.status).toBe(429);

      const surveyRes = await handle(postSurvey(SURVEY_BODY), env({ SIGNUP_RELAY_KV: kv }));
      expect(surveyRes.status).toBe(204);
      expect(kv.put).toHaveBeenCalledWith('count:survey:mrg-042', '1');
    });

    it('a registration burst limiter trip does not block a survey response for the same event', async () => {
      // A rate limiter whose .limit() answers false only when keyed exactly
      // as the bare event id (registration's own key) -- a survey response,
      // keyed 'survey:<id>', must sail through untouched.
      const rateLimiter = {
        limit: vi.fn(async ({ key }) => ({ success: key !== EVENT_ID })),
      };
      const registrationRes = await handle(post(VALID_BODY), env({ SIGNUP_RATE_LIMITER: rateLimiter }));
      expect(registrationRes.status).toBe(429);

      const surveyRes = await handle(postSurvey(SURVEY_BODY), env({ SIGNUP_RATE_LIMITER: rateLimiter }));
      expect(surveyRes.status).toBe(204);
    });
  });
});
