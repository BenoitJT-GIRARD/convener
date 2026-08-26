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

// The origin this worker answers CORS preflights for is
// the one address `config/instance.json` declares this project is
// published at -- the same declaration `tools/convener_ops/published.py`, the
// application's build and the showcase's build all read (D-14). A Worker
// cannot read any of it: it runs on Cloudflare with no repository in
// reach, so the deployed value lives in this package's own
// `wrangler.toml` and reaches `handle` as `env.ALLOWED_ORIGIN`. That is
// the honest arrangement, and it leaves exactly one thing for a test to
// hold: that the value shipped for deployment is the address the project
// is actually published at. TOML has no include and no reader here
// without a dependency this package does not have and the zero-cost
// constraint forbids adding, so the one line is matched out of it -- and
// a `wrangler.toml` that stopped declaring it fails loudly below rather
// than silently exercising this suite against a value nothing deploys.
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

const DISPATCH_URL = 'https://api.github.com/repos/example-instance/example-cockpit/dispatches';
const CONTENTS_URL = (id) =>
  `https://api.github.com/repos/example-instance/example-cockpit/contents/keys/events/${id}.pub`;

// A survey response is written to the queue branch
// through the Contents API instead of being dispatched. These mirror
// `src/index.js`'s own constants, which in turn mirror
// `tools/convener_ops/submission_queue.py`'s -- a branch name that disagreed
// across the three would be a queue nothing ever drains.
const QUEUE_BRANCH = 'submission-queue';
const QUEUE_ROOT =
  'https://api.github.com/repos/example-instance/example-cockpit/contents/queue/';
const QUEUE_PREFIX = `${QUEUE_ROOT}survey/`;
// The second kind the same queue carries. A branch of
// its own under the same directory, mirroring
// `submission_queue.REGISTRATION_KIND`.
const REGISTRATION_QUEUE_PREFIX = `${QUEUE_ROOT}registration/`;
const REF_URL =
  'https://api.github.com/repos/example-instance/example-cockpit/git/ref/heads/main';
const REFS_URL = 'https://api.github.com/repos/example-instance/example-cockpit/git/refs';

/** The path component of a queue write, i.e. what `queueEntryPath` built.
 *  `submission_queue.ENTRY_ID_RE` is the Python half of this shape; the
 *  two are pinned against each other by the entry-id test below. */
const QUEUE_ENTRY_RE = /^[0-9a-z]{1,16}-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.json$/;

// The survey switch is read through the same Contents
// API `CONTENTS_URL` above already exercises, just a different path in
// this repository -- not a second, deployed URL any more (that was
// SURVEY_STATUS_URL, removed along with wrangler.toml's own
// var of the same name; see that file's comment for why).
const SURVEY_STATUS_CONTENTS_URL =
  'https://api.github.com/repos/example-instance/example-cockpit/contents/public-data/survey-status.json';

// The registration lane cutoffs, read the same way from
// the same API. `tools/convener_ops/registration_routing.py` is what writes it
// and `deploy.yml` what commits it; this file only ever stands in for it.
const ROUTING_CONTENTS_URL =
  'https://api.github.com/repos/example-instance/example-cockpit/contents/public-data/registration-routing.json';

/** An ISO-8601 UTC instant `offsetMs` from now, spelled exactly the way
 *  `registration_routing.to_routing_data` spells one. */
function isoFromNow(offsetMs) {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** Base64-encodes the way `Buffer` does -- this test file's own stand-in
 *  for what GitHub's Contents API returns in a response's `content`
 *  field, mirroring `src/index.js::base64DecodeContentsApi`'s expectation
 *  that whitespace (GitHub line-wraps at 60 characters) is stripped
 *  before decoding, not that there is never any. */
function contentsApiBase64(text) {
  return Buffer.from(text, 'utf-8').toString('base64');
}

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
    // A second, independent limiter mock
    // by default, so a test that knows nothing about it
    // keeps passing unmodified.
    GLOBAL_RATE_LIMITER: makeRateLimiter(),
    ALLOWED_ORIGIN,
    ...overrides,
  };
}

/** Routes the mocked fetch by URL: the `.pub` existence check answers
 *  `known` (default true), the dispatch answers 204, and a GET to
 *  SURVEY_STATUS_CONTENTS_URL -- the Contents API, not a deployed URL --
 *  answers a Contents-API-shaped `{content: <base64>}` body encoding the
 *  array `surveyStatus` names (default: just EVENT_ID, so a survey test
 *  that never overrides this gets an enabled event for free), unless one
 *  of the three overrides below replaces some part of that response:
 *  `surveyStatusHttpStatus` replaces the HTTP status, `surveyStatusContent`
 *  replaces the base64 `content` field directly (to test malformed base64
 *  or base64 that decodes to non-JSON), or `surveyStatusRawBody` replaces
 *  the entire HTTP response body, bypassing the `{content: ...}` shape
 *  altogether (to test a response that is not valid JSON at all). The
 *  order these are checked in matters: a more specific override always
 *  wins over a less specific one. */
function stubFetch({
  known = true,
  dispatchStatus = 204,
  surveyStatus = [EVENT_ID],
  surveyStatusHttpStatus = 200,
  surveyStatusContent,
  surveyStatusRawBody,
  // `queueStatus` is what a queue write answers with
  // (201 is what the Contents API answers a created file with);
  // `queueStatusAfterBranch` is what the *retry* answers once the branch
  // has been created, so a test can make the first write fail with 404
  // and the second succeed. `refStatus` / `refSha` / `createRefStatus`
  // drive the one-time branch creation.
  queueStatus = 201,
  queueStatusAfterBranch,
  refStatus = 200,
  refSha = '0'.repeat(40),
  createRefStatus = 201,
  // `routing` is the object the routing file decodes to;
  // `undefined` (the default) makes the read answer 404, i.e. "nothing has
  // ever been published", which is the immediate lane -- so a test that
  // says nothing about lanes keeps dispatching, and does so
  // through the same code path a real unpublished file would take.
  // `routingHttpStatus`, `routingContent` and `routingRawBody` are the
  // same three escape hatches the survey-status stub already offers, in
  // the same order of precedence.
  routing,
  routingHttpStatus,
  routingContent,
  routingRawBody,
} = {}) {
  let queueWrites = 0;
  return vi.fn(async (url) => {
    const u = String(url);
    if (u.startsWith(QUEUE_ROOT)) {
      queueWrites += 1;
      const status =
        queueWrites > 1 && queueStatusAfterBranch !== undefined
          ? queueStatusAfterBranch
          : queueStatus;
      return new Response(null, { status });
    }
    if (u === REF_URL) {
      return new Response(JSON.stringify({ object: { sha: refSha } }), {
        status: refStatus,
      });
    }
    if (u === REFS_URL) {
      return new Response(null, { status: createRefStatus });
    }
    // Checked before the generic contents/ prefix below, which would
    // otherwise also match this URL.
    if (u === ROUTING_CONTENTS_URL) {
      if (routingRawBody !== undefined) {
        return new Response(routingRawBody, { status: routingHttpStatus ?? 200 });
      }
      if (routingContent !== undefined) {
        return new Response(JSON.stringify({ content: routingContent }), {
          status: routingHttpStatus ?? 200,
        });
      }
      if (routing === undefined) {
        return new Response(null, { status: routingHttpStatus ?? 404 });
      }
      return new Response(
        JSON.stringify({ content: contentsApiBase64(JSON.stringify(routing)) }),
        { status: routingHttpStatus ?? 200 },
      );
    }
    if (u === SURVEY_STATUS_CONTENTS_URL) {
      if (surveyStatusRawBody !== undefined) {
        return new Response(surveyStatusRawBody, { status: surveyStatusHttpStatus });
      }
      const content =
        surveyStatusContent !== undefined
          ? surveyStatusContent
          : contentsApiBase64(JSON.stringify(surveyStatus));
      return new Response(JSON.stringify({ content, encoding: 'base64' }), {
        status: surveyStatusHttpStatus,
      });
    }
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
    // Three, not two: the known-event check, the
    // lane read, and the dispatch. The lane read answers 404 here (nothing
    // published), which is the immediate lane -- see `stubFetch`'s own
    // `routing` option.
    expect(calls).toHaveLength(3);

    const [existsUrl, existsInit] = calls[0];
    expect(String(existsUrl)).toBe(CONTENTS_URL(EVENT_ID));
    expect(existsInit.headers.Authorization).toBe('Bearer ghp_test-token');
    expect(existsInit.headers['User-Agent']).toBe('convener-signup-relay');
    // No GitHub call is left to hang on this worker's own invocation
    // forever -- every one of them carries a timeout signal.
    expect(existsInit.signal).toBeInstanceOf(AbortSignal);

    const [routingUrl, routingInit] = calls[1];
    expect(String(routingUrl)).toBe(ROUTING_CONTENTS_URL);
    expect(routingInit.headers.Authorization).toBe('Bearer ghp_test-token');
    expect(routingInit.signal).toBeInstanceOf(AbortSignal);

    const [dispatchUrl, dispatchInit] = calls[2];
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

  // The module docstring's own claim --
  // "validatedEventId below makes no distinction between the two routes
  // at all" -- was enforced by nothing for a while: nothing ever sent
  // `/survey` a malformed envelope. The same table, run against both
  // routes, closes that gap for good; each malformed body is refused with
  // 400 on `/survey` exactly as it already was on `/`.
  describe.each([
    ['/', post],
    ['/survey', postSurvey],
  ])('the identical shape validation on route %s', (_route, postAt) => {
    it.each(mutations)('refuses a body that %s, with 400', async (_label, make) => {
      const res = await handle(postAt(make()), env());
      expect(res.status).toBe(400);
      expect(globalThis.fetch).not.toHaveBeenCalled();
    });
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

  // hasDuplicateKey, specifically, on /survey --
  // a mutant that skipped this guard on the newer
  // route alone survived all 60 tests before this case existed.
  it('refuses a body with a duplicated key on /survey too, not only on /', async () => {
    const dup = SURVEY_BODY.replace('"v":1,', '"v":1,"v":1,');
    expect(() => JSON.parse(dup)).not.toThrow();
    const res = await handle(postSurvey(dup), env());
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
    ['GLOBAL_RATE_LIMITER is not bound', { GLOBAL_RATE_LIMITER: undefined }],
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

describe('signup relay -- the global limiter', () => {
  it('refuses once the global limiter trips, with Retry-After, and never calls GitHub', async () => {
    const globalRateLimiter = makeRateLimiter(false);
    const kv = makeKv();
    const res = await handle(
      post(VALID_BODY),
      env({ GLOBAL_RATE_LIMITER: globalRateLimiter, SIGNUP_RELAY_KV: kv }),
    );
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBe('60');
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(kv.get).not.toHaveBeenCalled();
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('keys the global limiter by one fixed literal, never event_id', async () => {
    const globalRateLimiter = makeRateLimiter(true);
    await handle(post(VALID_BODY), env({ GLOBAL_RATE_LIMITER: globalRateLimiter }));
    expect(globalRateLimiter.limit).toHaveBeenCalledWith({ key: 'global' });
  });

  it('shares one global bucket across different event ids -- the gap this closes', async () => {
    // The whole point: unlike the per-event limiter, varying event_id
    // must not buy a fresh bucket. A limiter that answers false only once
    // it has seen the fixed 'global' key at least twice proves the same
    // key is reused across two structurally-different requests.
    let calls = 0;
    const globalRateLimiter = {
      limit: vi.fn(async ({ key }) => {
        if (key !== 'global') throw new Error(`unexpected key: ${key}`);
        calls += 1;
        return { success: calls <= 1 };
      }),
    };
    const firstBody = VALID_BODY;
    const secondBody = JSON.stringify({ event_id: 'mrg-999-fabricated', ...VALID_ENVELOPE });

    const first = await handle(post(firstBody), env({ GLOBAL_RATE_LIMITER: globalRateLimiter }));
    expect(first.status).toBe(204);

    globalThis.fetch = stubFetch({ known: false }); // mrg-999-fabricated does not exist
    const second = await handle(post(secondBody), env({ GLOBAL_RATE_LIMITER: globalRateLimiter }));
    expect(second.status).toBe(429);
    expect(globalRateLimiter.limit).toHaveBeenCalledTimes(2);
  });

  it('is checked before the per-event limiter -- an id-varying flood meets it first', async () => {
    const order = [];
    const globalRateLimiter = {
      limit: vi.fn(async () => {
        order.push('global');
        return { success: true };
      }),
    };
    const perEventRateLimiter = {
      limit: vi.fn(async () => {
        order.push('per-event');
        return { success: true };
      }),
    };
    await handle(
      post(VALID_BODY),
      env({ GLOBAL_RATE_LIMITER: globalRateLimiter, SIGNUP_RATE_LIMITER: perEventRateLimiter }),
    );
    expect(order).toEqual(['global', 'per-event']);
  });

  it('applies identically on /survey', async () => {
    const globalRateLimiter = makeRateLimiter(false);
    const res = await handle(postSurvey(SURVEY_BODY), env({ GLOBAL_RATE_LIMITER: globalRateLimiter }));
    expect(res.status).toBe(429);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('fails closed (502) when the global limiter itself cannot be reached, rather than skipping it', async () => {
    const globalRateLimiter = { limit: vi.fn(async () => { throw new Error('unavailable'); }) };
    const res = await handle(post(VALID_BODY), env({ GLOBAL_RATE_LIMITER: globalRateLimiter }));
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

describe('signup relay -- the /survey route', () => {
  it('accepts a well-shaped, known-event survey envelope, and queues it instead of dispatching', async () => {
    const kv = makeKv();
    const res = await handle(postSurvey(SURVEY_BODY), env({ SIGNUP_RELAY_KV: kv }));

    expect(res.status).toBe(204);

    // Three calls, not two, and not four: the known-event check, the
    // survey-status check (the Contents API, not a
    // deployed URL), and the queue write. The write replaced a
    // dispatch and spends exactly the same number of API
    // calls -- a queue that cost the relay more per submission
    // than the thing it replaced would be the wrong shape.
    const calls = globalThis.fetch.mock.calls;
    expect(calls).toHaveLength(3);
    expect(String(calls[1][0])).toBe(SURVEY_STATUS_CONTENTS_URL);
    // The same credential eventKeyExists already sends, not a
    // second, token-free read -- committing survey-status.json (rather
    // than serving it from a public URL) is what makes reading it require
    // one in the first place.
    expect(calls[1][1].headers.Authorization).toBe('Bearer ghp_test-token');

    // Nothing is dispatched any more: a survey response no longer starts a
    // run of its own, which is the whole point of the phase.
    expect(calls.map(([u]) => String(u))).not.toContain(DISPATCH_URL);

    const [queueUrl, queueInit] = calls[2];
    expect(String(queueUrl).startsWith(QUEUE_PREFIX)).toBe(true);
    expect(queueInit.method).toBe('PUT');
    expect(queueInit.headers.Authorization).toBe('Bearer ghp_test-token');
    const written = JSON.parse(queueInit.body);
    expect(written.branch).toBe(QUEUE_BRANCH);
    // Byte for byte what the browser encrypted: what the drain decrypts
    // has to be exactly what was submitted, never a re-serialisation.
    expect(atob(written.content)).toBe(SURVEY_BODY);
    // The precondition no test can enforce, written where somebody about
    // to break it might read it.
    expect(written.message).toContain('never open a pull request');

    // A distinct counter key from registration's own, so the two never
    // share -- or corrupt -- one budget.
    expect(kv.put).toHaveBeenCalledWith('count:survey:mrg-042', '1');

    // Exact, not a range -- the fixed-size
    // padding makes every stored-and-transmitted ciphertext the same
    // length regardless of content (8192 bytes of padded plaintext plus
    // the 16-byte GCM tag), so the fixture's own envelope is a fact this
    // suite can pin exactly rather than merely bound.
    expect(atob(SURVEY_ENVELOPE.ciphertext).length).toBe(8208);
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

  describe('the relay checks the survey switch itself, not only the page', () => {
    it('refuses with 404 when the event is not in survey-status.json', async () => {
      globalThis.fetch = stubFetch({ surveyStatus: [] });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(404);
      // Never dispatched -- the survey-status check runs before GitHub is
      // ever asked to create a repository_dispatch.
      const calls = globalThis.fetch.mock.calls;
      expect(calls.every(([url]) => url !== DISPATCH_URL)).toBe(true);
    });

    it('refuses with 404 when survey-status.json does not exist yet in this repository', async () => {
      // The edge case: before deploy.yml's "Commit survey status"
      // step has ever landed a commit, the file is simply absent -- a
      // clean 404 from the Contents API, not an error. Reads exactly like
      // "no event is open", the same as an empty array would.
      globalThis.fetch = stubFetch({ surveyStatusHttpStatus: 404 });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(404);
    });

    it("a different event's presence in survey-status.json does not enable this one", async () => {
      globalThis.fetch = stubFetch({ surveyStatus: ['mrg-999'] });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(404);
    });

    it('fails closed (502) when survey-status.json cannot be fetched at all (a non-200/404 status)', async () => {
      globalThis.fetch = stubFetch({ surveyStatusHttpStatus: 500 });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(502);
    });

    it('fails closed (502) when the Contents API response itself is not valid JSON', async () => {
      globalThis.fetch = stubFetch({ surveyStatusRawBody: 'not json at all' });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(502);
    });

    it('fails closed (502) when the content field is not valid base64', async () => {
      globalThis.fetch = stubFetch({ surveyStatusContent: '***not base64***' });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(502);
    });

    it('fails closed (502) when the decoded content is not valid JSON', async () => {
      globalThis.fetch = stubFetch({ surveyStatusContent: contentsApiBase64('not json either') });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(502);
    });

    it('fails closed (502) when the decoded content is valid JSON but not an array', async () => {
      globalThis.fetch = stubFetch({
        surveyStatusContent: contentsApiBase64(JSON.stringify({ 'mrg-042': true })),
      });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(502);
    });

    it('fails closed (502) when the fetch itself throws (a real network failure)', async () => {
      globalThis.fetch = vi.fn(async (url) => {
        const u = String(url);
        if (u === SURVEY_STATUS_CONTENTS_URL) {
          throw new TypeError('fetch failed');
        }
        if (u.startsWith('https://api.github.com/repos/example-instance/example-cockpit/contents/')) {
          return new Response(null, { status: 200 });
        }
        throw new Error(`unexpected fetch in test: ${u}`);
      });
      const res = await handle(postSurvey(SURVEY_BODY), env());
      expect(res.status).toBe(502);
    });

    it('is never checked on the bare registration route -- the Contents API is never asked for survey-status.json on /', async () => {
      const res = await handle(post(VALID_BODY), env());
      expect(res.status).toBe(204);
      const calls = globalThis.fetch.mock.calls;
      expect(calls.every(([url]) => String(url) !== SURVEY_STATUS_CONTENTS_URL)).toBe(true);
    });

    it('is checked only after the event is confirmed to exist, so an unknown event never reaches it', async () => {
      const fetchSpy = stubFetch({ known: false });
      globalThis.fetch = fetchSpy;
      await handle(postSurvey(SURVEY_BODY), env());
      const calls = fetchSpy.mock.calls;
      expect(calls.every(([url]) => String(url) !== SURVEY_STATUS_CONTENTS_URL)).toBe(true);
    });

    it('never depends on the published site at all', async () => {
      await handle(postSurvey(SURVEY_BODY), env());
      const calls = globalThis.fetch.mock.calls;
      // Built from the declaration rather than typed: the address this
      // worker must not reach for is whatever address this project is
      // published at, which is exactly what changes under a duplicate.
      const published = new URL(declaredOrigin()).host;
      expect(calls.every(([url]) => !String(url).includes(published))).toBe(true);
    });
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

describe('signup relay -- the submission queue', () => {
  it('names each entry so the drain can order it and never collide', async () => {
    await handle(postSurvey(SURVEY_BODY), env());
    const [queueUrl] = globalThis.fetch.mock.calls[2];
    const name = String(queueUrl).slice(QUEUE_PREFIX.length);
    // The shape `submission_queue.ENTRY_ID_RE` refuses anything else in:
    // a fixed-width base36 millisecond, then a uuid. Ordering the names as
    // strings and ordering the milliseconds as numbers have to be the same
    // thing, or a drain would apply two submissions out of order.
    expect(name).toMatch(QUEUE_ENTRY_RE);
  });

  it('gives two submissions two different names', async () => {
    await handle(postSurvey(SURVEY_BODY), env());
    const first = String(globalThis.fetch.mock.calls[2][0]);
    globalThis.fetch = stubFetch();
    await handle(postSurvey(SURVEY_BODY), env());
    const second = String(globalThis.fetch.mock.calls[2][0]);
    // Two submissions inside one millisecond are ordinary; the uuid is
    // what stops one overwriting the other, and the drain's own ledger
    // pruning rests on an entry name never coming back.
    expect(first).not.toBe(second);
  });

  it('creates the queue branch the one time it does not exist yet, and retries the write', async () => {
    globalThis.fetch = stubFetch({ queueStatus: 404, queueStatusAfterBranch: 201 });
    const res = await handle(postSurvey(SURVEY_BODY), env());

    expect(res.status).toBe(204);
    const urls = globalThis.fetch.mock.calls.map(([u]) => String(u));
    // Five calls, once in this repository's life: known-event,
    // survey-status, the write that found no branch, the two that create
    // it -- and then the retry.
    expect(urls).toContain(REF_URL);
    expect(urls).toContain(REFS_URL);
    expect(urls.filter((u) => u.startsWith(QUEUE_PREFIX))).toHaveLength(2);
    // Created from the default branch's own tip, with the sha the ref read
    // answered -- never a fabricated one.
    const createInit = globalThis.fetch.mock.calls.find(([u]) => String(u) === REFS_URL)[1];
    expect(JSON.parse(createInit.body)).toEqual({
      ref: `refs/heads/${QUEUE_BRANCH}`,
      sha: '0'.repeat(40),
    });
  });

  it('treats "the reference already exists" as the branch being there', async () => {
    // Two submissions racing to create the branch: the loser gets 422, and
    // that is a success for it too -- the branch it needed is there.
    globalThis.fetch = stubFetch({
      queueStatus: 404,
      queueStatusAfterBranch: 201,
      createRefStatus: 422,
    });
    const res = await handle(postSurvey(SURVEY_BODY), env());
    expect(res.status).toBe(204);
  });

  it('answers 502 when the queue write cannot be completed, and counts nothing', async () => {
    const kv = makeKv();
    globalThis.fetch = stubFetch({ queueStatus: 500 });
    const res = await handle(postSurvey(SURVEY_BODY), env({ SIGNUP_RELAY_KV: kv }));

    // The submitter learns at once that it did not work and can submit
    // again -- the queue only ever delays what was *accepted*.
    expect(res.status).toBe(502);
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('answers 502 rather than looping when the branch cannot be created either', async () => {
    globalThis.fetch = stubFetch({ queueStatus: 404, refStatus: 500 });
    const res = await handle(postSurvey(SURVEY_BODY), env());
    expect(res.status).toBe(502);
    // Exactly one write attempt: a second retry against a branch that is
    // still not there would hold the submitter's request open for nothing.
    const writes = globalThis.fetch.mock.calls.filter(([u]) =>
      String(u).startsWith(QUEUE_PREFIX),
    );
    expect(writes).toHaveLength(1);
  });

  it('answers 502 when the ref read answers something with no sha in it', async () => {
    globalThis.fetch = stubFetch({ queueStatus: 404, refSha: '' });
    const res = await handle(postSurvey(SURVEY_BODY), env());
    expect(res.status).toBe(502);
  });

  it('never writes a registration under the survey kind', async () => {
    // One queue, two directories: `submission_queue.read_entry` decides
    // what to do with an entry from the directory it is in, so a
    // registration filed under `queue/survey/` would be handed to the
    // survey drain and refused as ciphertext that will not read.
    globalThis.fetch = stubFetch({
      routing: { v: 1, queue_until: { [EVENT_ID]: isoFromNow(30 * 24 * 3600 * 1000) } },
    });
    await handle(post(VALID_BODY), env());
    const urls = globalThis.fetch.mock.calls.map(([u]) => String(u));
    expect(urls.filter((u) => u.startsWith(QUEUE_PREFIX))).toHaveLength(0);
    expect(urls.filter((u) => u.startsWith(REGISTRATION_QUEUE_PREFIX))).toHaveLength(1);
  });
});

// -------------------------------------------------------------------- //
// Which lane a registration takes
// -------------------------------------------------------------------- //

describe('signup relay -- the registration lane', () => {
  /** The routing file as `registration_routing.to_routing_data` writes it,
   *  with this event's cutoff `offsetMs` from now. */
  function routingFor(offsetMs, id = EVENT_ID) {
    return { v: 1, queue_until: { [id]: isoFromNow(offsetMs) } };
  }

  function urlsOf() {
    return globalThis.fetch.mock.calls.map(([u]) => String(u));
  }

  it('queues a registration whose event is still weeks away, and starts no run for it', async () => {
    globalThis.fetch = stubFetch({ routing: routingFor(30 * 24 * 3600 * 1000) });
    const res = await handle(post(VALID_BODY), env());

    expect(res.status).toBe(204);
    const urls = urlsOf();
    // The whole point: no dispatch, so no billed workflow run.
    expect(urls).not.toContain(DISPATCH_URL);

    const [queueUrl, queueInit] = globalThis.fetch.mock.calls.find(([u]) =>
      String(u).startsWith(REGISTRATION_QUEUE_PREFIX),
    );
    expect(queueInit.method).toBe('PUT');
    const written = JSON.parse(queueInit.body);
    expect(written.branch).toBe(QUEUE_BRANCH);
    // Byte-identical to what the browser encrypted: what the drain
    // decrypts has to be exactly what was received, never re-serialised.
    expect(Buffer.from(written.content, 'base64').toString('utf-8')).toBe(VALID_BODY);
    // The same entry-id shape `submission_queue.ENTRY_ID_RE` pins, so the
    // drain's total order over one day's arrivals is the order they
    // arrived in.
    expect(String(queueUrl).slice(REGISTRATION_QUEUE_PREFIX.length)).toMatch(
      QUEUE_ENTRY_RE,
    );
  });

  it('dispatches a registration whose event is hours away, exactly as it always did', async () => {
    globalThis.fetch = stubFetch({ routing: routingFor(-2 * 3600 * 1000) });
    const res = await handle(post(VALID_BODY), env());

    expect(res.status).toBe(204);
    const urls = urlsOf();
    expect(urls).toContain(DISPATCH_URL);
    expect(urls.filter((u) => u.startsWith(QUEUE_ROOT))).toHaveLength(0);
    const dispatchInit = globalThis.fetch.mock.calls.find(([u]) => String(u) === DISPATCH_URL)[1];
    expect(JSON.parse(dispatchInit.body).client_payload.body).toBe(VALID_BODY);
  });

  it('dispatches a registration arriving at exactly the cutoff, and queues the one a second earlier', async () => {
    // The boundary, driven on both sides rather than reasoned about. It is
    // closed on the immediate side deliberately: an off-by-one here has to
    // fall on the side that still delivers the room link.
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date('2026-09-01T00:00:00Z'));
      const cutoff = { v: 1, queue_until: { [EVENT_ID]: '2026-09-01T00:00:00Z' } };

      globalThis.fetch = stubFetch({ routing: cutoff });
      await handle(post(VALID_BODY), env());
      expect(urlsOf()).toContain(DISPATCH_URL);

      globalThis.fetch = stubFetch({
        routing: { v: 1, queue_until: { [EVENT_ID]: '2026-09-01T00:00:01Z' } },
      });
      await handle(post(VALID_BODY), env());
      expect(urlsOf()).not.toContain(DISPATCH_URL);
      expect(urlsOf().filter((u) => u.startsWith(REGISTRATION_QUEUE_PREFIX))).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it.each([
    ['no routing file has ever been published', { routingHttpStatus: 404 }],
    ['GitHub answered something other than 200', { routing: {}, routingHttpStatus: 403 }],
    ['the response body is not JSON at all', { routingRawBody: 'not json' }],
    ['the content field does not decode', { routingContent: '!!!not base64!!!' }],
    ['the content decodes to something that is not JSON', { routingContent: 'bm90IGpzb24=' }],
    ['the file carries a version this worker does not know', { routing: { v: 99, queue_until: {} } }],
    ['queue_until is not an object', { routing: { v: 1, queue_until: 'soon' } }],
    ['this event is not in the file', { routing: { v: 1, queue_until: { 'mrg-999': '2099-01-01T00:00:00Z' } } }],
    ['the instant will not parse', { routing: { v: 1, queue_until: { [EVENT_ID]: 'tomorrow' } } }],
  ])('dispatches immediately when %s', async (_why, options) => {
    // Every unreadable answer routes to the immediate lane, never the
    // queue. The cost of guessing wrong in this direction is one billed
    // run; the cost of guessing wrong in the other is a participant who
    // never receives the only message carrying their way into the room.
    globalThis.fetch = stubFetch(options);
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(204);
    expect(urlsOf()).toContain(DISPATCH_URL);
    expect(urlsOf().filter((u) => u.startsWith(QUEUE_ROOT))).toHaveLength(0);
  });

  it('dispatches immediately when the routing read fails outright', async () => {
    const inner = stubFetch({});
    globalThis.fetch = vi.fn(async (url, init) => {
      if (String(url) === ROUTING_CONTENTS_URL) throw new Error('network down');
      return inner(url, init);
    });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(204);
    expect(urlsOf()).toContain(DISPATCH_URL);
  });

  it('does not read a cutoff off Object.prototype for an event named after one of its keys', async () => {
    // `EVENT_ID_RE` accepts `constructor`, and `queue_until.constructor`
    // is a function on every plain object. Read with a bare subscript it
    // would reach Date.parse as something that is not a timestamp at all.
    const id = 'constructor';
    const body = JSON.stringify({ event_id: id, ...VALID_ENVELOPE });
    globalThis.fetch = stubFetch({ routing: { v: 1, queue_until: {} } });
    const res = await handle(post(body), env());
    expect(res.status).toBe(204);
    expect(urlsOf()).toContain(DISPATCH_URL);
  });

  it('answers 502 rather than losing a queued registration whose write did not land', async () => {
    globalThis.fetch = stubFetch({
      routing: routingFor(30 * 24 * 3600 * 1000),
      queueStatus: 500,
    });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(502);
    // Nothing is counted for a submission that did not land, and nothing
    // is dispatched either -- the submitter learns now and can retry.
    expect(urlsOf()).not.toContain(DISPATCH_URL);
  });

  it('creates the queue branch for the first registration ever queued, then writes again', async () => {
    globalThis.fetch = stubFetch({
      routing: routingFor(30 * 24 * 3600 * 1000),
      queueStatus: 404,
      queueStatusAfterBranch: 201,
    });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(204);
    const urls = urlsOf();
    expect(urls).toContain(REFS_URL);
    expect(urls.filter((u) => u.startsWith(REGISTRATION_QUEUE_PREFIX))).toHaveLength(2);
  });

  it('never reads the routing file for a refusal that has to stay immediate', async () => {
    // Unknown event, and the same holds for the abuse limits above it: a
    // refusal is decided before the lane is, so nothing a stranger sends
    // can be slowed down or sped up by this file's contents.
    globalThis.fetch = stubFetch({ known: false, routing: routingFor(3600 * 1000) });
    const res = await handle(post(VALID_BODY), env());
    expect(res.status).toBe(404);
    expect(urlsOf()).not.toContain(ROUTING_CONTENTS_URL);
  });

  it('leaves the survey route queuing whatever the routing file says', async () => {
    // Q-3: the delay rule is the registration's alone. A survey response
    // never reads this file at all.
    globalThis.fetch = stubFetch({ routing: routingFor(-2 * 3600 * 1000) });
    const res = await handle(postSurvey(SURVEY_BODY), env());
    expect(res.status).toBe(204);
    expect(urlsOf()).not.toContain(ROUTING_CONTENTS_URL);
    expect(urlsOf().filter((u) => u.startsWith(QUEUE_PREFIX))).toHaveLength(1);
  });

  it('counts a queued registration on the same counter a dispatched one uses', async () => {
    // The per-event ceiling must not become evadable by choosing a lane:
    // the counter key is the route's, not the lane's.
    const kv = makeKv({ 'count:mrg-042': '7' });
    globalThis.fetch = stubFetch({ routing: routingFor(30 * 24 * 3600 * 1000) });
    await handle(post(VALID_BODY), env({ SIGNUP_RELAY_KV: kv }));
    expect(kv.store.get('count:mrg-042')).toBe('8');
  });
});
