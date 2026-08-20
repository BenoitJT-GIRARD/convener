import { describe, expect, it } from 'vitest';
import { verify, MALFORMED, NO_MATCHING_KEY } from '../src/verify/verify';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

// This suite exercises `crypto.subtle` directly and touches no network, so
// it does not need the global `fetch` stub `tests/setup.ts` installs --
// nothing here ever calls `fetch`.

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function toPem(der: ArrayBuffer, label: string): string {
  const b64 = bytesToBase64(new Uint8Array(der));
  const lines = b64.match(/.{1,64}/g) ?? [b64];
  return `-----BEGIN ${label}-----\n${lines.join('\n')}\n-----END ${label}-----\n`;
}

/** A fresh RSA-PKCS1v15/SHA-256 signing key pair -- for the two "signed by
 *  one of our own keys but the decoded payload still will not parse"
 *  cases the fixture cannot supply (`tools/convener_ops/signing.py::sign`
 *  refuses to produce one; see verify.ts's own docstring, "verify before
 *  you parse", for why this outcome is this system's own bug, never a
 *  forger's, and only reachable by a key that genuinely signed it).
 *  Never written to disk, never reused across tests. */
async function generateSigningKeyPair(): Promise<{ publicPem: string; privateKey: CryptoKey }> {
  const { publicKey, privateKey } = await crypto.subtle.generateKey(
    { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
    true,
    ['sign', 'verify'],
  );
  const der = await crypto.subtle.exportKey('spki', publicKey);
  return { publicPem: toPem(der, 'PUBLIC KEY'), privateKey };
}

async function signRawBytes(privateKey: CryptoKey, bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const signature = await crypto.subtle.sign({ name: 'RSASSA-PKCS1-v1_5' }, privateKey, bytes);
  return JSON.stringify({
    v: 1,
    payload: bytesToBase64(bytes),
    signature: bytesToBase64(new Uint8Array(signature)),
  });
}

describe('verify -- the two reason spellings, pinned to the shared fixture', () => {
  // D-14: a rule written in two languages is bound by a shared fixture read
  // from both sides. If either side's literal string ever drifted --
  // including by having the two constants below swapped -- this is what
  // would catch it (mutation test 4).
  it('MALFORMED matches signing.MALFORMED', () => {
    expect(MALFORMED).toBe(cases.reasons.malformed);
  });
  it('NO_MATCHING_KEY matches signing.NO_MATCHING_KEY', () => {
    expect(NO_MATCHING_KEY).toBe(cases.reasons.no_matching_key);
  });
});

describe('verify -- the fixture\'s real signed token', () => {
  it('accepts a genuine token against the key that signed it', async () => {
    const result = await verify(cases.signed_example.token, [cases.signed_example.public_pem]);
    expect(result.valid).toBe(true);
    if (!result.valid) throw new Error('unreachable');
    expect(result.payload).toEqual(cases.signed_example.payload_decoded);
  });

  it('finds the right key regardless of its position in the list (rotation tolerance)', async () => {
    const result = await verify(cases.signed_example.token, [
      cases.integer_duration_example.public_pem,
      cases.signed_example.public_pem,
    ]);
    expect(result.valid).toBe(true);
    if (!result.valid) throw new Error('unreachable');
    expect(result.payload.identifier).toBe(cases.signed_example.identifier);
  });

  it('reports no_matching_key, never an exception, against an empty key list', async () => {
    const result = await verify(cases.signed_example.token, []);
    expect(result).toEqual({ valid: false, reason: NO_MATCHING_KEY });
  });

  it('carries an exact whole-number duration_hours through as a number, not a rounded string', async () => {
    // Minor 10 (task 12, fix round 1): duration_hours: 2.0, the case a
    // naive re-serialisation would round-trip differently between Python
    // and JS. verify() never re-serialises anything -- see its own
    // docstring -- so this must survive untouched.
    const result = await verify(cases.integer_duration_example.token, [
      cases.integer_duration_example.public_pem,
    ]);
    expect(result.valid).toBe(true);
    if (!result.valid) throw new Error('unreachable');
    expect(result.payload).toEqual(cases.integer_duration_example.payload_decoded);
    expect(result.payload.duration_hours).toBe(2);
  });
});

describe('verify -- the fixture\'s negative cases (verification_rejects)', () => {
  it.each(cases.verification_rejects)('$name -> $reason', async ({ token, valid, reason }) => {
    const result = await verify(token, [cases.signed_example.public_pem]);
    expect(result.valid).toBe(valid);
    if (!result.valid) expect(result.reason).toBe(reason);
  });

  it('a token signed by a key entirely absent from the list also reports no_matching_key', async () => {
    // Same token the fixture pins as "signed by a different key" (which is
    // itself absent from the list passed here), checked against a *third*
    // key that never touched it at all -- the ordinary "wrong certificate
    // presented to this page" case, not merely the fixture's own curated
    // adversarial examples.
    const flippedByteCase = cases.verification_rejects.find(c => c.name === 'one byte flipped in the signature');
    if (!flippedByteCase) throw new Error('fixture case not found');
    const result = await verify(flippedByteCase.token, [cases.integer_duration_example.public_pem]);
    expect(result).toEqual({ valid: false, reason: NO_MATCHING_KEY });
  });
});

describe('verify -- malformed input the fixture does not enumerate', () => {
  const KEYS = [cases.signed_example.public_pem];

  it('rejects a token that is not JSON at all', async () => {
    expect(await verify('this is not json', KEYS)).toEqual({ valid: false, reason: MALFORMED });
  });

  it('rejects valid JSON that is not an object (an array)', async () => {
    expect(await verify('[1,2,3]', KEYS)).toEqual({ valid: false, reason: MALFORMED });
  });

  it('rejects an envelope missing "v"', async () => {
    const token = JSON.stringify({ payload: 'AA==', signature: 'AA==' });
    expect(await verify(token, KEYS)).toEqual({ valid: false, reason: MALFORMED });
  });

  it('rejects an unsupported wire version', async () => {
    const token = JSON.stringify({ v: 2, payload: 'AA==', signature: 'AA==' });
    expect(await verify(token, KEYS)).toEqual({ valid: false, reason: MALFORMED });
  });

  it('rejects a payload field that is not a string', async () => {
    const token = JSON.stringify({ v: 1, payload: 12345, signature: 'AA==' });
    expect(await verify(token, KEYS)).toEqual({ valid: false, reason: MALFORMED });
  });

  it('rejects a signature field that is not a string', async () => {
    const token = JSON.stringify({ v: 1, payload: 'AA==', signature: 12345 });
    expect(await verify(token, KEYS)).toEqual({ valid: false, reason: MALFORMED });
  });

  it('rejects payload text that will not base64-decode', async () => {
    const token = JSON.stringify({ v: 1, payload: 'not base64 at all!!', signature: 'AA==' });
    expect(await verify(token, KEYS)).toEqual({ valid: false, reason: MALFORMED });
  });

  it('rejects a token far larger than any real one -- cheaply, before parsing it', async () => {
    const token = 'a'.repeat(9000);
    expect(await verify(token, KEYS)).toEqual({ valid: false, reason: MALFORMED });
  });
});

describe('verify -- a corrupt or unparsable key in the list must not stop the rest from being tried (Minor 2)', () => {
  // signing-keys-files.mjs:61 copies whatever .pub text it finds under
  // keys/signing/ with no validation at all, so a truncated or corrupted
  // key file is a reachable input in production. verifiesWith's two
  // blanket catches (an unparsable PEM at crypto.subtle.importKey, and
  // crypto.subtle.verify itself throwing) are the module's only
  // uncovered lines -- and the rotation guarantee
  // keys/signing/README.md rests on depends on one bad key never
  // stopping the loop before it reaches a good one.
  it('an unparsable PEM ahead of the genuine key still lets the genuine key verify', async () => {
    const result = await verify(cases.signed_example.token, [
      'not a PEM at all',
      cases.signed_example.public_pem,
    ]);
    expect(result.valid).toBe(true);
    if (!result.valid) throw new Error('unreachable');
    expect(result.payload).toEqual(cases.signed_example.payload_decoded);
  });

  it('a well-formed but non-matching key ahead of a corrupt one still tries every key (no_matching_key, not a crash)', async () => {
    const result = await verify(cases.signed_example.token, [
      cases.integer_duration_example.public_pem,
      'also not a PEM, and also not the signing key',
    ]);
    expect(result).toEqual({ valid: false, reason: NO_MATCHING_KEY });
  });

  it('a corrupt key ahead of a non-matching one still reaches the end of the list, never throwing', async () => {
    await expect(
      verify(cases.signed_example.token, ['garbage', '-----BEGIN PUBLIC KEY-----\nnot valid base64 either\n-----END PUBLIC KEY-----\n']),
    ).resolves.toEqual({ valid: false, reason: NO_MATCHING_KEY });
  });
});

describe('verify -- signed by one of our own keys, but the payload still will not parse', () => {
  // signing.py's own docstring: this shape is this system's own bug, never
  // a forger's -- reachable only once a key has already confirmed the
  // bytes, which is exactly why the fixture (whose every token was
  // produced by `signing.sign`, which refuses to produce this shape) has
  // no example of it. Built here with an independent key pair instead.
  it('reports malformed for signed bytes that are not JSON at all', async () => {
    const { publicPem, privateKey } = await generateSigningKeyPair();
    const token = await signRawBytes(privateKey, new TextEncoder().encode('not-json-at-all'));
    expect(await verify(token, [publicPem])).toEqual({ valid: false, reason: MALFORMED });
  });

  it('reports malformed for signed bytes that are valid JSON but not an object', async () => {
    const { publicPem, privateKey } = await generateSigningKeyPair();
    const token = await signRawBytes(privateKey, new TextEncoder().encode('[1,2,3]'));
    expect(await verify(token, [publicPem])).toEqual({ valid: false, reason: MALFORMED });
  });
});
