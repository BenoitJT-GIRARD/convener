import { describe, expect, it, vi, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { handle } from '../src/index.js';

// The shared fixture is the contract (decision D-14): the same
// webhook-signature rule is written once in tools/convener_ops/proposal.py and
// once here, and this file reads the very fixture
// tools/tests/test_proposal.py reads, so the two cannot silently drift.
const FIXTURE_PATH = fileURLToPath(
  new URL('../../../tools/tests/fixtures/governance-cases.json', import.meta.url),
);
const fixture = JSON.parse(readFileSync(FIXTURE_PATH, 'utf-8'));
const WEBHOOK_SIGNATURE_CASES = fixture.webhook_signature_cases;

// A parametrize over an emptied fixture list would silently collect zero
// tests and still pass -- this project has a history of vacuously passing
// tests (see tools/tests/test_proposal.py's own guard), so this makes that
// impossible here too.
if (!WEBHOOK_SIGNATURE_CASES || WEBHOOK_SIGNATURE_CASES.length === 0) {
  throw new Error('webhook_signature_cases fixture is empty');
}

const VALID_CASE = WEBHOOK_SIGNATURE_CASES.find((c) => c.valid);
const INVALID_CASE = WEBHOOK_SIGNATURE_CASES.find((c) => !c.valid);
if (!VALID_CASE || !INVALID_CASE) {
  throw new Error('fixture must hold at least one valid case and one invalid case');
}

// The repository this worker dispatches into is not this package's to
// know. It is what `instance/config.json` declares as
// `identity.repository`, and it reaches `handle` as `env.REPOSITORY` --
// passed to `wrangler deploy --var` by
// `.github/workflows/deploy-form-relay.yml`, which reads the declaration
// through the reader that owns it. `src/index.js` names no repository at
// all; `wrangler.toml`'s own header argues why, and
// `tools/tests/test_published.py` is where the two are held together, on
// the side that has the declaration in reach.
//
// So this suite states a repository of its own instead of reading one,
// and that is the point: every test below is about what the worker does
// with whatever repository it was deployed for, and none of them is about
// which repository this instance happens to use. Manifestly synthetic,
// and no owner anybody is asked to register.
const REPOSITORY = 'a-fixture-owner/a-fixture-repository';
const DISPATCH_URL = `https://api.github.com/repos/${REPOSITORY}/dispatches`;

function post(body, tallySignature, headers = {}) {
  const allHeaders = { ...headers };
  if (tallySignature !== undefined) allHeaders['Tally-Signature'] = tallySignature;
  return new Request('https://relay.example/', { method: 'POST', headers: allHeaders, body });
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

function makeRateLimiter(success = true) {
  return { limit: vi.fn(async () => ({ success })) };
}

// FORM_RELAY_KV and FORM_RATE_LIMITER join
// TALLY_WEBHOOK_SECRET and CONVENER_DISPATCH_TOKEN here -- a working mock of
// both by default, so a test that knows
// nothing about either keeps passing unmodified; `overrides` is how a
// new test replaces one on its own.
function env(secret, token = 'ghp_test-token', overrides = {}) {
  return {
    TALLY_WEBHOOK_SECRET: secret,
    CONVENER_DISPATCH_TOKEN: token,
    FORM_RELAY_KV: makeKv(),
    FORM_RATE_LIMITER: makeRateLimiter(),
    REPOSITORY,
    ...overrides,
  };
}

beforeEach(() => {
  globalThis.fetch = vi.fn(async () => new Response(null, { status: 204 }));
});

describe('form relay', () => {
  it('forwards a validly signed submission with a byte-identical body', async () => {
    const res = await handle(post(VALID_CASE.body, VALID_CASE.signature), env(VALID_CASE.secret));

    // A successful dispatch is 204 No Content, not 200.
    expect(res.status).toBe(204);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    const [url, init] = globalThis.fetch.mock.calls[0];
    expect(url).toBe(DISPATCH_URL);
    expect(init.method).toBe('POST');
    // This exact value matters: GitHub 403s a request with a wrong or
    // absent User-Agent.
    expect(init.headers['User-Agent']).toBe('convener-form-relay');
    expect(init.headers.Accept).toBe('application/vnd.github+json');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(init.headers.Authorization).toBe('Bearer ghp_test-token');
    // Neither GitHub call in this suite is left to hang on this worker's
    // own invocation forever (mirroring services/signup-relay's own
    // GITHUB_FETCH_TIMEOUT_MS).
    expect(init.signal).toBeInstanceOf(AbortSignal);

    const sent = JSON.parse(init.body);
    expect(sent.event_type).toBe('proposal-submitted');
    // Body must be a JSON string, never a nested object -- the
    // workflow reads it as a bare ${{ github.event.client_payload.body }}.
    expect(typeof sent.client_payload.body).toBe('string');
    expect(sent.client_payload.body).toBe(VALID_CASE.body);
    expect(sent.client_payload.signature).toBe(VALID_CASE.signature);
  });

  it('refuses a wrong signature with 401, and never calls GitHub', async () => {
    const res = await handle(post(INVALID_CASE.body, INVALID_CASE.signature), env(INVALID_CASE.secret));
    expect(res.status).toBe(401);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a missing signature with 401, and never calls GitHub', async () => {
    const res = await handle(post(VALID_CASE.body), env(VALID_CASE.secret));
    expect(res.status).toBe(401);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it.each([
    ['an empty string', ''],
    ['unset (an undefined binding, as it is when a Wrangler secret was never put)', undefined],
  ])(
    'refuses every request when TALLY_WEBHOOK_SECRET is %s, even one with a signature that would otherwise verify',
    async (_label, secret) => {
      // Fail closed. proposal.py::verify_signature is deliberately
      // tolerant with no secret configured -- safe there only because it
      // sits behind a repository_dispatch that already required an
      // authenticated token. This worker is the internet-facing boundary,
      // so that tolerance has no safe place here. Production absence of a
      // Wrangler secret surfaces as `undefined`, not `''`, so both must
      // refuse alike.
      const res = await handle(post(VALID_CASE.body, VALID_CASE.signature), env(secret));
      expect(res.status).toBe(401);
      expect(globalThis.fetch).not.toHaveBeenCalled();
    },
  );

  it('refuses to dispatch, without calling GitHub, when CONVENER_DISPATCH_TOKEN is not configured', async () => {
    // Same fail-closed reasoning, extended to the second secret: sending
    // "Bearer undefined" to GitHub is not an option, so this is refused
    // locally -- 502, not 401, since it is this worker's own
    // misconfiguration and not a bad Tally-Signature.
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      { TALLY_WEBHOOK_SECRET: VALID_CASE.secret },
    );
    expect(res.status).toBe(502);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('reports a failed dispatch as 502, without disclosing GitHub upstream detail to the caller', async () => {
    // A bad or expired CONVENER_DISPATCH_TOKEN gets a 401 from GitHub. Passed
    // through unchanged, that 401 would be indistinguishable from this
    // worker's own 401 for a bad Tally-Signature -- so any non-2xx from
    // GitHub is reported as 502 instead, and the caller never sees
    // GitHub's response body.
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ message: 'Bad credentials' }), { status: 401 }),
    );
    const res = await handle(post(VALID_CASE.body, VALID_CASE.signature), env(VALID_CASE.secret));
    expect(res.status).toBe(502);
    const text = await res.text();
    expect(text).not.toContain('Bad credentials');
  });

  it('reports 502 when the dispatch to GitHub cannot even be attempted (a real network failure)', async () => {
    // fetch rejects, rather than resolving to a Response, on a genuine
    // network failure -- GitHub unreachable, DNS failure, a reset
    // connection. Left uncaught, this would escape as an unhandled
    // exception instead of the 502 the file-level comment promises.
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError('fetch failed');
    });
    const res = await handle(post(VALID_CASE.body, VALID_CASE.signature), env(VALID_CASE.secret));
    expect(res.status).toBe(502);
    const text = await res.text();
    expect(text).not.toContain('fetch failed');
  });

  it('normalises any 2xx from GitHub to a fixed 204, never the literal upstream code', async () => {
    // GitHub's dispatches endpoint is documented to answer success with
    // exactly 204. Passing upstream.status straight through would let an
    // unexpected 2xx leak to the caller as-is -- the caller must only
    // ever see one of this worker's response codes.
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 200 }));
    const res = await handle(post(VALID_CASE.body, VALID_CASE.signature), env(VALID_CASE.secret));
    expect(res.status).toBe(204);
  });

  it('refuses a method other than POST', async () => {
    const res = await handle(requestAt('/', 'GET'), env(VALID_CASE.secret));
    expect(res.status).toBe(405);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('answers 404 on a path other than the one route', async () => {
    const res = await handle(requestAt('/unknown', 'POST'), env(VALID_CASE.secret));
    expect(res.status).toBe(404);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it.each(WEBHOOK_SIGNATURE_CASES.map((c) => [c.name, c]))('shared fixture: %s', async (_name, c) => {
    const res = await handle(post(c.body, c.signature), env(c.secret));
    expect(res.status).toBe(c.valid ? 204 : 401);
    if (!c.valid) {
      expect(globalThis.fetch).not.toHaveBeenCalled();
    }
  });
});

// ====================================================================== //
// The body-size bound, the burst limiter and the cumulative counter --
// none of the three existed at first.
// ====================================================================== //

describe('form relay -- the body-size bound', () => {
  it('refuses a body declared oversized by Content-Length before reading or verifying it', async () => {
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature, { 'content-length': String(200 * 1024) }),
      env(VALID_CASE.secret),
    );
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a body whose real byte length exceeds the budget even when Content-Length is absent', async () => {
    // 70,000 bytes of ASCII, comfortably past MAX_BODY_BYTES (65,536) --
    // never valid JSON, so this also proves the size check runs before
    // any attempt to sign or parse it.
    const oversized = 'x'.repeat(70_000);
    const res = await handle(post(oversized, 'irrelevant-signature'), env(VALID_CASE.secret));
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('refuses a body whose real byte length exceeds the budget even when its UTF-16 length does not', async () => {
    // A repeated 3-byte character keeps `.length` (UTF-16 units) a third
    // of the true UTF-8 byte count, comfortably under the budget while
    // the real byte count is comfortably over it -- the same distinction
    // services/signup-relay's own test file pins for MAX_BODY_BYTES there.
    const oversized = '€'.repeat(30_000); // length 30,000; byte length 90,000
    const res = await handle(post(oversized, 'irrelevant-signature'), env(VALID_CASE.secret));
    expect(res.status).toBe(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('still accepts a validly signed body comfortably under the size budget', async () => {
    const res = await handle(post(VALID_CASE.body, VALID_CASE.signature), env(VALID_CASE.secret));
    expect(res.status).toBe(204);
  });
});

describe('form relay -- the burst limiter', () => {
  it('refuses once the burst limiter trips, with Retry-After, and never calls GitHub', async () => {
    const rateLimiter = makeRateLimiter(false);
    const kv = makeKv();
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { FORM_RATE_LIMITER: rateLimiter, FORM_RELAY_KV: kv }),
    );
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBe('60');
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(kv.get).not.toHaveBeenCalled();
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('keys the limiter by a fixed literal, never anything the caller sent -- the gap next door', async () => {
    const rateLimiter = makeRateLimiter(true);
    await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { FORM_RATE_LIMITER: rateLimiter }),
    );
    expect(rateLimiter.limit).toHaveBeenCalledWith({ key: 'proposal' });
  });

  it('is checked only after a valid signature -- an unsigned flood never spends this budget', async () => {
    const rateLimiter = makeRateLimiter(true);
    const res = await handle(
      post(INVALID_CASE.body, INVALID_CASE.signature),
      env(INVALID_CASE.secret, 'ghp_test-token', { FORM_RATE_LIMITER: rateLimiter }),
    );
    expect(res.status).toBe(401);
    expect(rateLimiter.limit).not.toHaveBeenCalled();
  });

  it('fails closed (502) when the limiter itself cannot be reached, rather than skipping it', async () => {
    const rateLimiter = { limit: vi.fn(async () => { throw new Error('unavailable'); }) };
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { FORM_RATE_LIMITER: rateLimiter }),
    );
    expect(res.status).toBe(502);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('form relay -- the cumulative ceiling', () => {
  it('refuses once the ceiling is reached, with Retry-After, without calling GitHub at all', async () => {
    const kv = makeKv({ 'count:proposal': '2000' });
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { FORM_RELAY_KV: kv }),
    );
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBe('60');
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('still accepts the request one below the ceiling, and the count becomes the ceiling', async () => {
    const kv = makeKv({ 'count:proposal': '1999' });
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { FORM_RELAY_KV: kv }),
    );
    expect(res.status).toBe(204);
    expect(kv.put).toHaveBeenCalledWith('count:proposal', '2000');
  });

  it('counts a fresh worker (no stored count yet) as zero, not a refusal', async () => {
    const kv = makeKv();
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { FORM_RELAY_KV: kv }),
    );
    expect(res.status).toBe(204);
    expect(kv.put).toHaveBeenCalledWith('count:proposal', '1');
  });

  it('treats a KV read failure as no count yet, rather than refusing the request', async () => {
    const kv = makeKv();
    kv.get = vi.fn(async () => {
      throw new Error('kv unavailable');
    });
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { FORM_RELAY_KV: kv }),
    );
    expect(res.status).toBe(204);
  });

  it('does not count a failed dispatch toward the ceiling', async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 500 }));
    const kv = makeKv();
    await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { FORM_RELAY_KV: kv }),
    );
    expect(kv.put).not.toHaveBeenCalled();
  });

  it('still answers 204 when the counter cannot be written after a successful dispatch, and traces the failure', async () => {
    const kv = makeKv();
    kv.put = vi.fn(async () => {
      throw new Error('kv unavailable');
    });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const res = await handle(
        post(VALID_CASE.body, VALID_CASE.signature),
        env(VALID_CASE.secret, 'ghp_test-token', { FORM_RELAY_KV: kv }),
      );
      expect(res.status).toBe(204);
      expect(errorSpy).toHaveBeenCalledTimes(1);
      const [logged] = errorSpy.mock.calls[0];
      // Never the body: the trace names only a fixed message, nothing
      // that could identify who submitted it.
      expect(logged).not.toContain(VALID_CASE.body);
    } finally {
      errorSpy.mockRestore();
    }
  });
});

describe('form relay -- the repository it dispatches into', () => {
  // A second, different repository. The assertion is that the worker
  // dispatched into *this* one, so a call that went to the repository
  // stated at the top of this file would be a failure and not a
  // coincidence.
  const ELSEWHERE = 'another-fixture-owner/another-fixture-repository';

  it('dispatches into whatever repository the deploy gave it, and no other', async () => {
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { REPOSITORY: ELSEWHERE }),
    );
    expect(res.status).toBe(204);
    const [url] = globalThis.fetch.mock.calls[0];
    expect(url).toBe(`https://api.github.com/repos/${ELSEWHERE}/dispatches`);
  });

  it('refuses a validly signed submission when REPOSITORY is unset, and never calls GitHub', async () => {
    // In the fail-closed set for a reason the secrets and bindings around
    // it are not: unset, this one is *present and wrong*. The dispatch
    // would carry the word `undefined` where the repository belongs,
    // GitHub would answer 404, and the caller would get this worker's own
    // 502 -- the same answer an expired CONVENER_DISPATCH_TOKEN gives, so
    // an operator reading Tally's webhook log would rotate a token that
    // was never wrong.
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', { REPOSITORY: undefined }),
    );
    expect(res.status).toBe(502);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe('form relay -- fail closed on a missing abuse-protection binding', () => {
  it.each([
    ['FORM_RELAY_KV is not bound', { FORM_RELAY_KV: undefined }],
    ['FORM_RATE_LIMITER is not bound', { FORM_RATE_LIMITER: undefined }],
  ])('refuses every validly signed request when %s, and never calls GitHub', async (_label, overrides) => {
    const res = await handle(
      post(VALID_CASE.body, VALID_CASE.signature),
      env(VALID_CASE.secret, 'ghp_test-token', overrides),
    );
    expect(res.status).toBe(502);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
