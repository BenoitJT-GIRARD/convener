import { afterEach, describe, expect, it, vi } from 'vitest';
import { encryptSurveyResponse } from '../src/survey/encrypt';
import type { SurveyResponse } from '../src/survey/encrypt';
import cases from '../../tools/tests/fixtures/governance-cases.json';

// This suite exercises `crypto.subtle` directly and touches no network, so
// it does not need the global `fetch` stub `tests/setup.ts` installs --
// the same reasoning `signup-encrypt.test.ts` gives for its own suite.

const RSA_KEY_BYTES = 256; // 2048-bit RSA, matching eventkeys.RSA_KEY_BITS
const AES_KEY_BYTES = 32;
const GCM_NONCE_BYTES = 12;

const FIELDS: SurveyResponse = {
  overall_rating: 5,
  recommend: true,
  feedback: 'Loved the live Q&A.',
};

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function base64ByteLength(b64: string): number {
  return atob(b64).length;
}

const PLAINTEXT_PAD_BYTES = 8192;

/** The test's own inverse of `padPlaintext` (not exported from `encrypt.ts`
 *  on purpose -- see that module's docstring, "What this file deliberately
 *  does not do"): everything up to the first `0x00` byte, mirroring
 *  `survey.py::_unpad`'s identical reasoning about JSON's grammar
 *  forbidding a literal NUL in valid output. */
function unpadPlaintext(bytes: Uint8Array): Uint8Array {
  const end = bytes.indexOf(0);
  return end === -1 ? bytes : bytes.slice(0, end);
}

function toPem(der: ArrayBuffer, label: string): string {
  const b64 = bytesToBase64(new Uint8Array(der));
  const lines = b64.match(/.{1,64}/g) ?? [b64];
  return `-----BEGIN ${label}-----\n${lines.join('\n')}\n-----END ${label}-----\n`;
}

async function generateEventKeyPair(): Promise<{
  publicPem: string;
  publicKeyDer: ArrayBuffer;
  privateKey: CryptoKey;
}> {
  const { publicKey, privateKey } = await crypto.subtle.generateKey(
    {
      name: 'RSA-OAEP',
      modulusLength: RSA_KEY_BYTES * 8,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: 'SHA-256',
    },
    true,
    ['encrypt', 'decrypt'],
  );
  const publicKeyDer = await crypto.subtle.exportKey('spki', publicKey);
  return { publicPem: toPem(publicKeyDer, 'PUBLIC KEY'), publicKeyDer, privateKey };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('encryptSurveyResponse -- the wire format eventkeys.py documents', () => {
  it('produces exactly the four documented fields, sized the way the scheme requires', async () => {
    const { publicPem } = await generateEventKeyPair();

    const envelope = JSON.parse(await encryptSurveyResponse(publicPem, FIELDS));

    expect(Object.keys(envelope).sort()).toEqual(['ciphertext', 'encrypted_key', 'iv', 'v']);
    expect(envelope.v).toBe(1);
    expect(base64ByteLength(envelope.encrypted_key)).toBe(RSA_KEY_BYTES);
    expect(base64ByteLength(envelope.iv)).toBe(GCM_NONCE_BYTES);
  });

  it('draws a fresh AES key and a fresh nonce on every call', async () => {
    const { publicPem } = await generateEventKeyPair();

    const drawnAesKeys: Uint8Array[] = [];
    const realGetRandomValues = crypto.getRandomValues.bind(crypto) as (
      array: ArrayBufferView,
    ) => void;
    vi.spyOn(crypto, 'getRandomValues').mockImplementation(
      ((array: ArrayBufferView | null) => {
        if (array) realGetRandomValues(array);
        if (array instanceof Uint8Array && array.length === AES_KEY_BYTES) {
          drawnAesKeys.push(new Uint8Array(array));
        }
        return array;
      }) as typeof crypto.getRandomValues,
    );

    const first = JSON.parse(await encryptSurveyResponse(publicPem, FIELDS));
    const second = JSON.parse(await encryptSurveyResponse(publicPem, FIELDS));

    expect(first.iv).not.toBe(second.iv);
    expect(first.encrypted_key).not.toBe(second.encrypted_key);
    expect(first.ciphertext).not.toBe(second.ciphertext);

    expect(drawnAesKeys).toHaveLength(2);
    expect(drawnAesKeys[0]).not.toEqual(drawnAesKeys[1]);
  });

  it('round-trips through the matching private half, entirely via crypto.subtle', async () => {
    const { publicPem, privateKey } = await generateEventKeyPair();

    const envelope = JSON.parse(await encryptSurveyResponse(publicPem, FIELDS));
    const aesKeyBytes = await crypto.subtle.decrypt(
      { name: 'RSA-OAEP' },
      privateKey,
      base64ToBytes(envelope.encrypted_key),
    );
    const aesKey = await crypto.subtle.importKey('raw', aesKeyBytes, { name: 'AES-GCM' }, false, [
      'decrypt',
    ]);
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: base64ToBytes(envelope.iv) },
      aesKey,
      base64ToBytes(envelope.ciphertext),
    );

    expect(new Uint8Array(plaintext).length).toBe(PLAINTEXT_PAD_BYTES);
    const unpadded = unpadPlaintext(new Uint8Array(plaintext));
    expect(JSON.parse(new TextDecoder().decode(unpadded))).toEqual(FIELDS);
  });

  it('handles a false recommend and blank feedback without special-casing them', async () => {
    const { publicPem, privateKey } = await generateEventKeyPair();
    const fields: SurveyResponse = { overall_rating: 2, recommend: false, feedback: '' };

    const envelope = JSON.parse(await encryptSurveyResponse(publicPem, fields));
    const aesKeyBytes = await crypto.subtle.decrypt(
      { name: 'RSA-OAEP' },
      privateKey,
      base64ToBytes(envelope.encrypted_key),
    );
    const aesKey = await crypto.subtle.importKey('raw', aesKeyBytes, { name: 'AES-GCM' }, false, [
      'decrypt',
    ]);
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: base64ToBytes(envelope.iv) },
      aesKey,
      base64ToBytes(envelope.ciphertext),
    );
    const unpadded = unpadPlaintext(new Uint8Array(plaintext));
    expect(JSON.parse(new TextDecoder().decode(unpadded))).toEqual(fields);
  });

  it('the ciphertext length is the same regardless of how much feedback was written', async () => {
    // Measured before this fix: an empty `feedback` produced a
    // 92-character base64 ciphertext and a 2000-character one produced
    // 2756 -- the exact quasi-identifier the review named. Padding every
    // plaintext to PLAINTEXT_PAD_BYTES before AES-GCM removes it: the
    // ciphertext length is now a function of the pad target alone.
    const { publicPem } = await generateEventKeyPair();
    const short = { overall_rating: 1, recommend: false, feedback: '' };
    const long = { overall_rating: 5, recommend: true, feedback: 'x'.repeat(2000) };

    const shortEnvelope = JSON.parse(await encryptSurveyResponse(publicPem, short));
    const longEnvelope = JSON.parse(await encryptSurveyResponse(publicPem, long));

    expect(base64ByteLength(shortEnvelope.ciphertext)).toBe(
      base64ByteLength(longEnvelope.ciphertext),
    );
    // Sanity: the shared length is exactly the padded plaintext plus the
    // 16-byte GCM tag, not merely "the same as each other" by coincidence.
    expect(base64ByteLength(shortEnvelope.ciphertext)).toBe(PLAINTEXT_PAD_BYTES + 16);
  });

  it('rejects an answer too long to pad, rather than silently truncating it', async () => {
    const { publicPem } = await generateEventKeyPair();
    // Comfortably past PLAINTEXT_PAD_BYTES once JSON-encoded -- the shape
    // `to_survey_response`'s own length cap should already refuse well
    // before this, but padPlaintext must not silently truncate if it were
    // ever reached anyway.
    const tooLong = { overall_rating: 1, recommend: true, feedback: 'x'.repeat(9000) };
    await expect(encryptSurveyResponse(publicPem, tooLong)).rejects.toThrow();
  });

  it('a 2000-character non-Latin answer round-trips, JSON.stringify and ensure_ascii=False agreeing byte for byte', async () => {
    // The browser side of that fix: `JSON.stringify` here always
    // left non-ASCII as itself (at most 4 UTF-8 bytes/char), so this side
    // never needed a code change -- this test exists to prove the claim,
    // not to fix anything here. 2000 CJK characters (3 bytes each) is
    // comfortably under PLAINTEXT_PAD_BYTES, same as the Python-side
    // equivalent (test_every_script_at_the_character_cap_still_fits_the_
    // pad_target).
    const { publicPem, privateKey } = await generateEventKeyPair();
    const fields: SurveyResponse = {
      overall_rating: 4,
      recommend: true,
      feedback: '你'.repeat(2000),
    };

    const envelope = JSON.parse(await encryptSurveyResponse(publicPem, fields));
    const aesKeyBytes = await crypto.subtle.decrypt(
      { name: 'RSA-OAEP' },
      privateKey,
      base64ToBytes(envelope.encrypted_key),
    );
    const aesKey = await crypto.subtle.importKey('raw', aesKeyBytes, { name: 'AES-GCM' }, false, [
      'decrypt',
    ]);
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: base64ToBytes(envelope.iv) },
      aesKey,
      base64ToBytes(envelope.ciphertext),
    );
    expect(new Uint8Array(plaintext).length).toBe(PLAINTEXT_PAD_BYTES);
    const unpadded = unpadPlaintext(new Uint8Array(plaintext));
    expect(JSON.parse(new TextDecoder().decode(unpadded))).toEqual(fields);
  });

  it('an over-long non-Latin answer is refused cleanly, the same as an over-long ASCII one', async () => {
    const { publicPem } = await generateEventKeyPair();
    // 2100 emoji (an astral character, 4 UTF-8 bytes each) = 8400 bytes
    // alone, already past PLAINTEXT_PAD_BYTES before the JSON envelope
    // around it -- what to_survey_response's own byte-bound check exists
    // to catch server-side if this ever got past the character cap; here,
    // padPlaintext itself must still throw a clean Error rather than
    // truncate or hang, the identical contract the ASCII case above pins.
    const tooLong = { overall_rating: 1, recommend: true, feedback: '\u{1F600}'.repeat(2100) };
    await expect(encryptSurveyResponse(publicPem, tooLong)).rejects.toThrow();
  });
});

describe('the pad target: bound by the shared fixture, not only by this file\'s own literal', () => {
  it("pins this file's own PLAINTEXT_PAD_BYTES to governance-cases.json::event_survey_response_encryption.pad_bytes", () => {
    // Before this test, changing survey.py::_PLAINTEXT_PAD_BYTES left
    // this whole suite green: every assertion here compared against this
    // file's own separately-hardcoded PLAINTEXT_PAD_BYTES, which by
    // definition always agrees with itself. The fixture's own pad_bytes
    // is an independent literal, written once when its cross-language case
    // was captured, that a real disagreement now fails
    // against.
    expect(PLAINTEXT_PAD_BYTES).toBe(cases.event_survey_response_encryption.pad_bytes);
  });
});

describe('cannot decrypt what it just encrypted -- the page only ever holds the published half', () => {
  it('imports the public key for encryption only -- decrypt is never even requested', async () => {
    const { publicPem } = await generateEventKeyPair();
    const calls: unknown[][] = [];
    const realImportKey = crypto.subtle.importKey.bind(crypto.subtle);
    vi.spyOn(crypto.subtle, 'importKey').mockImplementation(
      (...args: Parameters<typeof crypto.subtle.importKey>) => {
        calls.push(args);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        return (realImportKey as any)(...args);
      },
    );

    await encryptSurveyResponse(publicPem, FIELDS);

    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) {
      const usages = call[4] as string[];
      expect(usages).not.toContain('decrypt');
    }
  });

  it('the envelope carries nothing a holder of only the public half could use: no extra field, no trace of the AES key or the feedback text', async () => {
    const { publicPem } = await generateEventKeyPair();
    const drawnAesKeys: Uint8Array[] = [];
    const realGetRandomValues = crypto.getRandomValues.bind(crypto) as (
      array: ArrayBufferView,
    ) => void;
    vi.spyOn(crypto, 'getRandomValues').mockImplementation(
      ((array: ArrayBufferView | null) => {
        if (array) realGetRandomValues(array);
        if (array instanceof Uint8Array && array.length === AES_KEY_BYTES) {
          drawnAesKeys.push(new Uint8Array(array));
        }
        return array;
      }) as typeof crypto.getRandomValues,
    );

    const envelopeJson = await encryptSurveyResponse(publicPem, FIELDS);
    const envelope = JSON.parse(envelopeJson);

    expect(drawnAesKeys.length).toBeGreaterThanOrEqual(1);
    const aesKey = drawnAesKeys[0];
    const aesKeyB64 = bytesToBase64(aesKey);
    const aesKeyHex = [...aesKey].map(b => b.toString(16).padStart(2, '0')).join('');

    expect(Object.keys(envelope).sort()).toEqual(['ciphertext', 'encrypted_key', 'iv', 'v']);
    expect(envelopeJson).not.toContain(aesKeyB64);
    expect(envelopeJson).not.toContain(aesKeyHex);
    expect(envelopeJson).not.toContain(FIELDS.feedback);
  });

  it('touches no console method and writes nothing to storage -- there is no sink for the plaintext to leak into', async () => {
    const { publicPem } = await generateEventKeyPair();
    const consoleSpies = (['log', 'warn', 'error', 'debug', 'info'] as const).map(m =>
      vi.spyOn(console, m).mockImplementation(() => {}),
    );
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem');

    await encryptSurveyResponse(publicPem, FIELDS);

    for (const spy of consoleSpies) expect(spy).not.toHaveBeenCalled();
    expect(storageSpy).not.toHaveBeenCalled();
  });
});

describe('encryptSurveyResponse: malformed input is refused, not silently accepted', () => {
  it('rejects a PEM that is not a public key at all', async () => {
    await expect(encryptSurveyResponse('not a pem', FIELDS)).rejects.toThrow();
  });

  it('rejects a truncated public key PEM -- broken DER, not a label sniff', async () => {
    const { publicPem } = await generateEventKeyPair();
    const truncated = publicPem.replace(/\n[^\n]+\n-----END/, '\n-----END');
    await expect(encryptSurveyResponse(truncated, FIELDS)).rejects.toThrow();
  });
});

/**
 * D-14: `tools/tests/fixtures/governance-cases.json::event_survey_response_encryption`
 * carries one fixed key pair (reused from `event_registration_encryption`
 * -- the crypto is identical, only the plaintext shape differs) and, for
 * each case, an `envelope` that is the literal output of the encryption
 * below, captured once and pinned. `tools/tests/test_survey.py` decrypts
 * that exact string with the real `eventkeys.decrypt` and
 * `to_survey_response`, and checks it recovers `fields`.
 */
describe('the shared encryption fixture (D-14) -- what this file must keep producing', () => {
  const fixture = cases.event_survey_response_encryption;

  function byteLength(b64: string): number {
    return atob(b64).length;
  }

  it('is not empty -- an emptied block here would silently drop the only proof the two languages still agree', () => {
    expect(fixture.cases.length).toBeGreaterThan(0);
  });

  it.each(fixture.cases)(
    '$name: encrypts to the documented wire shape under the fixture key',
    async ({ fields }) => {
      const envelope = JSON.parse(
        await encryptSurveyResponse(fixture.public_pem, fields as SurveyResponse),
      );
      expect(Object.keys(envelope).sort()).toEqual(['ciphertext', 'encrypted_key', 'iv', 'v']);
      expect(envelope.v).toBe(1);
      expect(byteLength(envelope.encrypted_key)).toBe(RSA_KEY_BYTES);
      expect(byteLength(envelope.iv)).toBe(GCM_NONCE_BYTES);
    },
  );

  it.each(fixture.cases)(
    '$name: the envelope pinned for Python to decrypt still has the documented shape',
    ({ envelope }) => {
      const parsed = JSON.parse(envelope);
      expect(Object.keys(parsed).sort()).toEqual(['ciphertext', 'encrypted_key', 'iv', 'v']);
      expect(parsed.v).toBe(1);
      expect(byteLength(parsed.encrypted_key)).toBe(RSA_KEY_BYTES);
      expect(byteLength(parsed.iv)).toBe(GCM_NONCE_BYTES);
    },
  );
});
