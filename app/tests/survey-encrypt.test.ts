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

    expect(JSON.parse(new TextDecoder().decode(plaintext))).toEqual(FIELDS);
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
    expect(JSON.parse(new TextDecoder().decode(plaintext))).toEqual(fields);
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
