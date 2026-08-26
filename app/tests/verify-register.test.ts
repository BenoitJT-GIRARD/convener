import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  lookupCertificateState,
  isProjection,
  isValidIdentifierShape,
  IDENTIFIER_PATTERN,
  REGISTER_FILENAME,
  STATE_ISSUED,
  STATE_REVOKED,
} from '../src/verify/register';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

// tools/convener_ops/cli.py::certificates_public_data writes a *bare array* --
// see that function's own test,
// test_certificates_public_data_aggregates_every_events_register.
// projection_example used to be nested under a
// `{"certificates": [...]}` key, which read as the wire shape and was
// not; the fixture itself was corrected, so this is the real, bare-array
// shape directly. `{ certificates: [...] }` is still deliberately
// rejected below (isProjection's own "wrong shape" test), now spelled as
// an explicit literal rather than by reference to the fixture -- a
// fixture that has already been corrected can no longer demonstrate the
// shape it used to wrongly suggest.
const REAL_PROJECTION = cases.projection_example;
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

  it('rejects a nested {"certificates": [...]} envelope as a wire shape', () => {
    // The shape certificate-verification.json's own `projection_example`
    // once wrongly nested rows under -- kept here as an
    // explicit literal, not read from the fixture (which is now correct
    // and so can no longer demonstrate the shape it used to wrongly
    // suggest), as the cheapest guard against this reader accepting it.
    expect(isProjection({ certificates: REAL_PROJECTION })).toBe(false);
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

describe('IDENTIFIER_PATTERN / isValidIdentifierShape', () => {
  it('matches certificate._CERTIFICATE_ID_RE via the shared fixture (D-14)', () => {
    expect(IDENTIFIER_PATTERN.source).toBe(cases.identifier_pattern);
  });

  it('accepts a genuine, real identifier from the fixture', () => {
    expect(isValidIdentifierShape(cases.signed_example.identifier)).toBe(true);
  });

  it('accepts 32 lowercase hex characters, rejects 31 or 33', () => {
    expect(isValidIdentifierShape('a'.repeat(32))).toBe(true);
    expect(isValidIdentifierShape('a'.repeat(31))).toBe(false);
    expect(isValidIdentifierShape('a'.repeat(33))).toBe(false);
  });

  it('rejects uppercase hex -- _new_identifier only ever emits lowercase', () => {
    expect(isValidIdentifierShape('A'.repeat(32))).toBe(false);
  });

  it('rejects text that is not shaped like an identifier at all', () => {
    expect(isValidIdentifierShape('not-a-real-identifier')).toBe(false);
    expect(isValidIdentifierShape('')).toBe(false);
  });

  it('rejects an otherwise-valid identifier with something embedded after it', () => {
    expect(isValidIdentifierShape(`${cases.signed_example.identifier}\nextra`)).toBe(false);
  });
});

describe('lookupCertificateState -- fetches the whole projection, from the right URL', () => {
  it('requests exactly BASE/certificates.json, not merely a URL ending in that filename, carrying no identifier', async () => {
    // A suffix-only match here is exactly what
    // let register.ts's own URL directory drift with a green suite --
    // `${BASE}/data/${REGISTER_FILENAME}` still ends in
    // "/certificates.json". Exact equality against BASE, independently
    // recomputed rather than imported from register.ts, actually pins the
    // directory, not only the leaf filename.
    stubFetchOnce({ ok: true, json: async () => REAL_PROJECTION } as Response);
    await lookupCertificateState(ISSUED_ROW.identifier);
    expect(fetch).toHaveBeenCalledTimes(1);
    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    const base = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
    expect(url).toBe(`${base}/${REGISTER_FILENAME}`);
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
    stubFetchOnce({
      ok: true,
      json: async () => ({ certificates: REAL_PROJECTION }),
    } as Response);
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
