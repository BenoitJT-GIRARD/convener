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
  it('fetches keys/signing/index.json', async () => {
    stubFetch({ ok: true, json: async () => [cases.signed_example.public_pem] } as Response);
    await loadSigningPublicKeys();
    expect(fetch).toHaveBeenCalledTimes(1);
    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    expect(url).toMatch(new RegExp(`/keys/signing/${KEYS_INDEX_FILENAME}$`));
  });

  it('returns the published keys in the order the manifest lists them', async () => {
    const pems = [cases.signed_example.public_pem, cases.integer_duration_example.public_pem];
    stubFetch({ ok: true, json: async () => pems } as Response);
    expect(await loadSigningPublicKeys()).toEqual(pems);
  });
});

describe('loadSigningPublicKeys -- any failure folds into "no keys", never an exception', () => {
  it('a 404 response', async () => {
    stubFetch({ ok: false, status: 404 } as Response);
    expect(await loadSigningPublicKeys()).toEqual([]);
  });

  it('a network error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('offline');
      }),
    );
    expect(await loadSigningPublicKeys()).toEqual([]);
  });

  it('malformed JSON', async () => {
    stubFetch({
      ok: true,
      json: async () => {
        throw new SyntaxError('Unexpected token');
      },
    } as unknown as Response);
    expect(await loadSigningPublicKeys()).toEqual([]);
  });

  it('valid JSON that is not an array', async () => {
    stubFetch({ ok: true, json: async () => ({ keys: [] }) } as Response);
    expect(await loadSigningPublicKeys()).toEqual([]);
  });

  it('an array containing a non-string entry, filtered rather than rejected wholesale', async () => {
    stubFetch({ ok: true, json: async () => [cases.signed_example.public_pem, 42, null] } as Response);
    expect(await loadSigningPublicKeys()).toEqual([cases.signed_example.public_pem]);
  });
});
