import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  lookupCertificateState,
  isProjection,
  REGISTER_FILENAME,
  STATE_ISSUED,
  STATE_REVOKED,
} from '../src/verify/register';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

// tools/convener_ops/cli.py::certificates_public_data writes a *bare array* --
// see that function's own test,
// test_certificates_public_data_aggregates_every_events_register -- not
// the `{"certificates": [...]}` shape the fixture's own `projection_example`
// property name might suggest at a glance. This suite's "valid" fixtures
// reshape the fixture's two worked rows into that real, bare-array shape;
// `{"certificates": [...]}` itself is deliberately one of the "wrong shape"
// cases below, not a friendlier alternative this code accepts.
const REAL_PROJECTION = cases.projection_example.certificates;
const ISSUED_ROW = REAL_PROJECTION.find(row => row.state === STATE_ISSUED);
const REVOKED_ROW = REAL_PROJECTION.find(row => row.state === STATE_REVOKED);
if (!ISSUED_ROW || !REVOKED_ROW) throw new Error('fixture missing an issued or revoked row');

function stubFetchOnce(response: Partial<Response> | (() => Response | Promise<Response>)) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => (typeof response === 'function' ? response() : (response as Response))),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('isProjection', () => {
  it('accepts the real, bare-array shape', () => {
    expect(isProjection(REAL_PROJECTION)).toBe(true);
  });

  it('rejects the fixture-file\'s own nested key name as a wire shape', () => {
    // Precisely the shape a reader might expect from
    // certificate-verification.json's `projection_example` property --
    // and precisely what tools/convener_ops/cli.py never actually writes.
    expect(isProjection(cases.projection_example)).toBe(false);
  });

  it('rejects a row missing "state"', () => {
    expect(isProjection([{ identifier: 'abc' }])).toBe(false);
  });

  it('rejects a non-array', () => {
    expect(isProjection('hello')).toBe(false);
    expect(isProjection(null)).toBe(false);
    expect(isProjection(42)).toBe(false);
  });

  it('accepts an empty register', () => {
    expect(isProjection([])).toBe(true);
  });
});

describe('lookupCertificateState -- fetches the whole projection, from the right URL', () => {
  it('requests certificates.json, same-origin, carrying no identifier in the URL', async () => {
    stubFetchOnce({ ok: true, json: async () => REAL_PROJECTION } as Response);
    await lookupCertificateState(ISSUED_ROW.identifier);
    expect(fetch).toHaveBeenCalledTimes(1);
    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    expect(url).toMatch(new RegExp(`/${REGISTER_FILENAME}$`));
    expect(url).not.toContain(ISSUED_ROW.identifier);
  });
});

describe('lookupCertificateState -- what the register says', () => {
  it('reports issued for a row currently issued', async () => {
    stubFetchOnce({ ok: true, json: async () => REAL_PROJECTION } as Response);
    expect(await lookupCertificateState(ISSUED_ROW.identifier)).toEqual({ status: STATE_ISSUED });
  });

  it('reports revoked for a row currently revoked', async () => {
    stubFetchOnce({ ok: true, json: async () => REAL_PROJECTION } as Response);
    expect(await lookupCertificateState(REVOKED_ROW.identifier)).toEqual({ status: STATE_REVOKED });
  });

  it('reports not_found for an identifier the register was read successfully but does not mention', async () => {
    stubFetchOnce({ ok: true, json: async () => REAL_PROJECTION } as Response);
    expect(await lookupCertificateState('no-such-identifier')).toEqual({ status: 'not_found' });
  });
});

describe('lookupCertificateState -- an unreadable register must say "unavailable", never "invalid" (mutation 2)', () => {
  it('a 404 response', async () => {
    stubFetchOnce({ ok: false, status: 404 } as Response);
    expect(await lookupCertificateState(ISSUED_ROW.identifier)).toEqual({ status: 'unavailable' });
  });

  it('a network error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('offline');
      }),
    );
    expect(await lookupCertificateState(ISSUED_ROW.identifier)).toEqual({ status: 'unavailable' });
  });

  it('malformed JSON', async () => {
    stubFetchOnce({
      ok: true,
      json: async () => {
        throw new SyntaxError('Unexpected token');
      },
    } as unknown as Response);
    expect(await lookupCertificateState(ISSUED_ROW.identifier)).toEqual({ status: 'unavailable' });
  });

  it('valid JSON, wrong shape (an object instead of an array)', async () => {
    stubFetchOnce({ ok: true, json: async () => cases.projection_example } as Response);
    expect(await lookupCertificateState(ISSUED_ROW.identifier)).toEqual({ status: 'unavailable' });
  });

  it('valid JSON, an array of the wrong row shape', async () => {
    stubFetchOnce({ ok: true, json: async () => [{ identifier: 'abc' }] } as Response);
    expect(await lookupCertificateState('abc')).toEqual({ status: 'unavailable' });
  });

  it('a row whose state is neither of the two spellings this register ever writes', async () => {
    stubFetchOnce({
      ok: true,
      json: async () => [{ identifier: 'abc', state: 'pending' }],
    } as Response);
    expect(await lookupCertificateState('abc')).toEqual({ status: 'unavailable' });
  });
});
