import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadSigningPublicKeys, KEYS_INDEX_FILENAME } from '../src/verify/publicKeys';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

function stubFetch(response: Partial<Response> | (() => Response | Promise<Response>)) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => (typeof response === 'function' ? response() : (response as Response))),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('loadSigningPublicKeys -- requests the published index, same-origin', () => {
  it('fetches exactly BASE/keys/signing/index.json, not merely a URL ending in that filename (Important 2)', async () => {
    // A regex suffix match alone would still pass if `keysUrl()` grew an
    // extra path segment (e.g. BASE/signing-keys/index.json still ends in
    // "index.json") -- exact equality against BASE, independently
    // recomputed here rather than imported from publicKeys.ts, is what
    // actually pins the directory, not only the leaf filename.
    stubFetch({ ok: true, json: async () => [cases.signed_example.public_pem] } as Response);
    await loadSigningPublicKeys();
    expect(fetch).toHaveBeenCalledTimes(1);
    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    const base = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
    expect(url).toBe(`${base}/keys/signing/${KEYS_INDEX_FILENAME}`);
  });

  it('returns the published keys in the order the manifest lists them', async () => {
    const pems = [cases.signed_example.public_pem, cases.integer_duration_example.public_pem];
    stubFetch({ ok: true, json: async () => pems } as Response);
    expect(await loadSigningPublicKeys()).toEqual(pems);
  });
});

describe('loadSigningPublicKeys -- any failure to fetch or parse must be distinguishable from a successfully-read, genuinely empty manifest (Important 1b)', () => {
  it('a 404 response resolves to null, not []', async () => {
    stubFetch({ ok: false, status: 404 } as Response);
    expect(await loadSigningPublicKeys()).toBeNull();
  });

  it('a network error resolves to null, not []', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('offline');
      }),
    );
    expect(await loadSigningPublicKeys()).toBeNull();
  });

  it('malformed JSON resolves to null, not []', async () => {
    stubFetch({
      ok: true,
      json: async () => {
        throw new SyntaxError('Unexpected token');
      },
    } as unknown as Response);
    expect(await loadSigningPublicKeys()).toBeNull();
  });

  it('valid JSON that is not an array resolves to null, not [] -- an unparsable manifest is not the same claim as "we publish zero keys"', async () => {
    stubFetch({ ok: true, json: async () => ({ keys: [] }) } as Response);
    expect(await loadSigningPublicKeys()).toBeNull();
  });
});

describe('loadSigningPublicKeys -- a manifest that was read successfully, even an empty one, is [] -- never null', () => {
  it('a well-formed, genuinely empty manifest', async () => {
    stubFetch({ ok: true, json: async () => [] } as Response);
    expect(await loadSigningPublicKeys()).toEqual([]);
  });

  it('an array containing a non-string entry, filtered rather than rejected wholesale', async () => {
    stubFetch({ ok: true, json: async () => [cases.signed_example.public_pem, 42, null] } as Response);
    expect(await loadSigningPublicKeys()).toEqual([cases.signed_example.public_pem]);
  });
});
