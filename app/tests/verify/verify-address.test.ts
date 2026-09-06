import { describe, expect, it } from 'vitest';
import { normaliseIdentifier, parsePrintedAddress } from '../../src/verify/address';
import cases from '../../../tools/tests/fixtures/certificate-verification.json';

/**
 * What a certificate has printed on it, read back.
 *
 * `app/tests/islands/verify-island-mount.test.tsx` already holds `parseVerificationFragment`
 * against the shared fixture, because that is the shape a *link* arrives
 * in and it is the island's own bootstrap that reads it. This file holds
 * the other half: what somebody types or pastes into `VerifyPage`'s
 * hand-entry form, which is the same two values arriving without a
 * browser having parsed a URL first.
 *
 * Pinned against `tools/tests/fixtures/certificate-verification.json`
 * rather than a hand-typed address (D-14): the only address worth reading
 * back is the one `certificate.verification_url` actually writes, and the
 * fixture is where both sides of the language border read it from.
 */

const SIGNED = cases.signed_example;

describe('normaliseIdentifier', () => {
  it('folds away what a copy off a printed page adds, and nothing else', () => {
    expect(normaliseIdentifier(` ${SIGNED.identifier.toUpperCase()} `)).toBe(SIGNED.identifier);
    // A line break is what a PDF viewer puts in the middle of a
    // thirty-two character run when the column is narrow.
    const halved = `${SIGNED.identifier.slice(0, 16)}\n${SIGNED.identifier.slice(16)}`;
    expect(normaliseIdentifier(halved)).toBe(SIGNED.identifier);
  });

  it('changes nothing about an identifier already in the shape it is printed in', () => {
    expect(normaliseIdentifier(SIGNED.identifier)).toBe(SIGNED.identifier);
  });
});

describe('parsePrintedAddress', () => {
  it('reads both values out of the whole address a certificate prints', () => {
    const printed = `https://example.invalid/a-series/${SIGNED.verification_url_path}`;

    expect(parsePrintedAddress(printed)).toEqual({
      identifier: SIGNED.identifier,
      token: SIGNED.token,
    });
  });

  it('reads them out of an address whose host is one that no longer answers', () => {
    // The reason this function exists. A certificate carries the address
    // it was issued under, printed and encoded as a QR; a renamed
    // organisation or a moved repository leaves that address resolving to
    // nothing, and what is printed is still every value needed to check
    // it here.
    const stale = `https://an-organisation-that-moved.invalid/gone/${SIGNED.verification_url_path}`;

    expect(parsePrintedAddress(stale).token).toBe(SIGNED.token);
  });

  it('reads a bare fragment, which is what a link copied out of an address bar leaves', () => {
    const fragment = SIGNED.verification_url_path.slice(
      SIGNED.verification_url_path.indexOf('#'),
    );

    expect(parsePrintedAddress(fragment)).toEqual({
      identifier: SIGNED.identifier,
      token: SIGNED.token,
    });
  });

  it('reads a query a mail client has flattened the fragment out of', () => {
    expect(
      parsePrintedAddress(`https://example.invalid/verify/?token=${encodeURIComponent('abc')}`),
    ).toEqual({ identifier: undefined, token: 'abc' });
  });

  it('reads a bare identifier as one', () => {
    expect(parsePrintedAddress(` ${SIGNED.identifier.toUpperCase()} `)).toEqual({
      identifier: SIGNED.identifier,
    });
  });

  it('reads nothing out of text that is neither, rather than inventing one', () => {
    // Never a half-answer: a caller that got `{}` says so to whoever
    // typed it, and `VerifyPage`'s form is where that sentence lives.
    expect(parsePrintedAddress('')).toEqual({});
    expect(parsePrintedAddress('   ')).toEqual({});
    expect(parsePrintedAddress('the certificate I was sent last week')).toEqual({});
    expect(parsePrintedAddress(SIGNED.identifier.slice(0, 30))).toEqual({});
  });
});
