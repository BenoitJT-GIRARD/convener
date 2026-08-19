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

function post(body, tallySignature) {
  const headers = {};
  if (tallySignature !== undefined) headers['Tally-Signature'] = tallySignature;
  return new Request('https://relay.example/', { method: 'POST', headers, body });
}

function requestAt(path, method) {
  return new Request(`https://relay.example${path}`, { method });
}

function env(secret) {
  return { TALLY_WEBHOOK_SECRET: secret, CONVENER_DISPATCH_TOKEN: 'ghp_test-token' };
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
    expect(url).toBe('https://api.github.com/repos/example-instance/example-cockpit/dispatches');
    expect(init.method).toBe('POST');
    expect(init.headers['User-Agent']).toBeTruthy();
    expect(init.headers.Authorization).toBe('Bearer ghp_test-token');

    const sent = JSON.parse(init.body);
    expect(sent.event_type).toBe('proposal-submitted');
    // R-7: body must be a JSON string, never a nested object -- the
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

  it('refuses every request when the secret is not configured, even one with a signature that would otherwise verify', async () => {
    // R-6: fail closed. proposal.py::verify_signature is deliberately
    // tolerant with no secret configured -- safe there only because it sits
    // behind a repository_dispatch that already required an authenticated
    // token. This worker is the internet-facing boundary, so that
    // tolerance has no safe place here.
    const res = await handle(post(VALID_CASE.body, VALID_CASE.signature), env(''));
    expect(res.status).toBe(401);
    expect(globalThis.fetch).not.toHaveBeenCalled();
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
