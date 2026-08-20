import { afterEach, describe, expect, it, vi } from 'vitest';
import { encryptRegistration } from '../src/signup/encrypt';
import type { Registration } from '../src/signup/encrypt';
import cases from '../../tools/tests/fixtures/governance-cases.json';

// This suite exercises `crypto.subtle` directly and touches no network, so
// it does not need the global `fetch` stub `tests/setup.ts` installs --
// nothing here ever calls `fetch`.

const RSA_KEY_BYTES = 256; // 2048-bit RSA, matching eventkeys.RSA_KEY_BITS
const AES_KEY_BYTES = 32;
const GCM_NONCE_BYTES = 12;

const FIELDS: Registration = {
  first_name: 'Rosalind',
  surname: 'Franklin',
  email: 'rosalind@example.org',
  institution: 'Birkbeck College',
  membership_opt_in: true,
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

/** PEM-wraps DER at the conventional 64-column width, so tests exercise the
 *  same multi-line shape `keys/events/<id>.pub` actually has -- a single
 *  unwrapped base64 line would not catch a `pemToDer` that only strips the
 *  header and footer of a real, wrapped key. */
function toPem(der: ArrayBuffer, label: string): string {
  const b64 = bytesToBase64(new Uint8Array(der));
  const lines = b64.match(/.{1,64}/g) ?? [b64];
  return `-----BEGIN ${label}-----\n${lines.join('\n')}\n-----END ${label}-----\n`;
}

/** A fresh RSA-OAEP key pair, generated the same way `eventkeys.generate()`
 *  does (2048-bit, SHA-256), for a test to encrypt against and -- since
 *  `encryptRegistration` never exposes decryption -- to independently
 *  verify a round trip against, entirely through `crypto.subtle`. Never
 *  written to disk, never reused across tests. */
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

describe('encryptRegistration -- the wire format eventkeys.py documents', () => {
  it('produces exactly the four documented fields, sized the way the scheme requires', async () => {
    const { publicPem } = await generateEventKeyPair();

    const envelope = JSON.parse(await encryptRegistration(publicPem, FIELDS));

    expect(Object.keys(envelope).sort()).toEqual(['ciphertext', 'encrypted_key', 'iv', 'v']);
    expect(envelope.v).toBe(1);
    // Fixed by the RSA key size, not by what the registration contains --
    // a mutant that swaps the RSA step for something else changes this
    // length even though the JSON still parses and still has four fields.
    expect(base64ByteLength(envelope.encrypted_key)).toBe(RSA_KEY_BYTES);
    expect(base64ByteLength(envelope.iv)).toBe(GCM_NONCE_BYTES);
  });

  it('draws a fresh AES key and a fresh nonce on every call', async () => {
    const { publicPem } = await generateEventKeyPair();

    const first = JSON.parse(await encryptRegistration(publicPem, FIELDS));
    const second = JSON.parse(await encryptRegistration(publicPem, FIELDS));

    expect(first.iv).not.toBe(second.iv);
    expect(first.encrypted_key).not.toBe(second.encrypted_key);
    expect(first.ciphertext).not.toBe(second.ciphertext);
  });

  it('round-trips through the matching private half, entirely via crypto.subtle', async () => {
    const { publicPem, privateKey } = await generateEventKeyPair();

    const envelope = JSON.parse(await encryptRegistration(publicPem, FIELDS));
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

  it('handles an empty optional institution and a false opt-in without special-casing them', async () => {
    const { publicPem, privateKey } = await generateEventKeyPair();
    const fields: Registration = { ...FIELDS, institution: '', membership_opt_in: false };

    const envelope = JSON.parse(await encryptRegistration(publicPem, fields));
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

    await encryptRegistration(publicPem, FIELDS);

    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) {
      const usages = call[4] as string[];
      expect(usages).not.toContain('decrypt');
    }
  });

  it('a holder of only the public key cannot recover the AES key from the envelope', async () => {
    const { publicPem, publicKeyDer } = await generateEventKeyPair();
    const publicKeyOnly = await crypto.subtle.importKey(
      'spki',
      publicKeyDer,
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      false,
      ['encrypt'],
    );

    const envelope = JSON.parse(await encryptRegistration(publicPem, FIELDS));

    await expect(
      crypto.subtle.decrypt(
        { name: 'RSA-OAEP' },
        publicKeyOnly,
        base64ToBytes(envelope.encrypted_key),
      ),
    ).rejects.toThrow();
  });

  it('the envelope carries nothing a holder of only the public half could use: no extra field, no trace of the AES key or the plaintext', async () => {
    const { publicPem } = await generateEventKeyPair();
    const drawnAesKeys: Uint8Array[] = [];
    // `getRandomValues` fills its argument in place and returns that same
    // reference, so the spy below never needs the real call's return value
    // -- only its side effect -- which sidesteps the generic-vs-`BufferSource`
    // friction `.bind()` otherwise runs into here.
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

    const envelopeJson = await encryptRegistration(publicPem, FIELDS);
    const envelope = JSON.parse(envelopeJson);

    expect(drawnAesKeys.length).toBeGreaterThanOrEqual(1);
    const aesKey = drawnAesKeys[0];
    const aesKeyB64 = bytesToBase64(aesKey);
    const aesKeyHex = [...aesKey].map(b => b.toString(16).padStart(2, '0')).join('');

    // The wire format's entire vocabulary -- nothing else is on offer for a
    // holder of only the public half to read, decode or brute-force from.
    // A mutant that smuggles the AES key out as an extra field is caught
    // right here.
    expect(Object.keys(envelope).sort()).toEqual(['ciphertext', 'encrypted_key', 'iv', 'v']);
    // Neither the raw AES key nor the plaintext appears anywhere in the
    // envelope, encoded or not -- catches a mutant that hides the key
    // inside an existing field instead of adding a new one.
    expect(envelopeJson).not.toContain(aesKeyB64);
    expect(envelopeJson).not.toContain(aesKeyHex);
    expect(envelopeJson).not.toContain(FIELDS.surname);
    expect(envelopeJson).not.toContain(FIELDS.email);
  });
});

describe('encryptRegistration: malformed input is refused, not silently accepted', () => {
  it('rejects a PEM that is not a public key at all', async () => {
    await expect(
      encryptRegistration('not a pem', FIELDS),
    ).rejects.toThrow();
  });

  it('rejects a truncated public key PEM -- broken DER, not a label sniff', async () => {
    const { publicPem } = await generateEventKeyPair();
    // Still carries a well-formed PUBLIC KEY header and footer, so a
    // failure here comes from the DER content underneath, not from a
    // shortcut that only ever checks the header line. Drops exactly the
    // last body line before the footer.
    const truncated = publicPem.replace(/\n[^\n]+\n-----END/, '\n-----END');
    await expect(encryptRegistration(truncated, FIELDS)).rejects.toThrow();
  });
});

/**
 * D-14: the wire format is a rule written in two languages, so it is bound
 * by the fixture read from both sides, not by trusting the two suites to
 * agree. `tools/tests/fixtures/governance-cases.json::event_registration_encryption`
 * carries one fixed key pair and, for each case, an `envelope` that is the
 * literal output of the encryption below, captured once and pinned --
 * `tools/tests/test_eventkeys.py` decrypts that exact string with the real
 * `eventkeys.decrypt` and checks it recovers `fields`. This file cannot run
 * that half (there is no decrypt function here, on purpose -- see the
 * describe block above), so what it pins is that encrypting `fields` afresh
 * still produces the documented shape, and that the pinned `envelope` has
 * not rotted into something the scheme no longer recognises.
 */
describe('the shared encryption fixture (D-14) -- what this file must keep producing', () => {
  const fixture = cases.event_registration_encryption;

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
        await encryptRegistration(fixture.public_pem, fields as Registration),
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
