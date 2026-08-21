/**
 * The browser half of the hybrid encryption scheme `tools/convener_ops/eventkeys.py`
 * documents field by field -- read that module's docstring before this one.
 * This file has to reproduce its wire format exactly, or every registration
 * this page sends becomes permanently unreadable the moment the two
 * implementations disagree (`tools/tests/fixtures/governance-cases.json`,
 * decision D-14, is what keeps them from drifting apart unnoticed).
 *
 * Why RSA-OAEP + AES-GCM, not RSA-OAEP alone
 * -------------------------------------------
 * `crypto.subtle` only ever encrypts one short RSA-OAEP block -- 190 bytes
 * at most, for the 2048-bit key `eventkeys.generate()` produces. Today's
 * registration fits with room to spare, but relying on that headroom is
 * exactly how a field added two years from now would silently break
 * encryption for whoever adds it. So this never puts the registration
 * itself through RSA: it draws a throwaway AES-256-GCM key, encrypts the
 * registration with *that*, and RSA-OAEP-encrypts only the 32-byte AES key.
 * Ordinary hybrid construction, not a shortcut worth removing later.
 *
 * The wire format
 * ----------------
 * One compact JSON object, matching `eventkeys.py`'s field by field:
 *
 *     {"v":1,"encrypted_key":"<base64>","iv":"<base64>","ciphertext":"<base64>"}
 *
 * - `v` -- format version, `1`. `eventkeys.decrypt` rejects anything else.
 * - `encrypted_key` -- the 32-byte AES-256 key, RSA-OAEP-encrypted (SHA-256
 *   hash and MGF1, no label) under the event's public key. Always 256 bytes
 *   once base64-decoded, for the 2048-bit RSA key `eventkeys.generate()`
 *   produces -- a fixed size regardless of what the registration contains,
 *   which is what a wire-format test can pin without caring about payload
 *   length.
 * - `iv` -- the AES-GCM nonce: 12 random bytes, one fresh draw every call.
 *   Nothing here ever reuses one.
 * - `ciphertext` -- the AES-256-GCM output with its 16-byte authentication
 *   tag appended, exactly what `crypto.subtle.encrypt` already returns for
 *   AES-GCM -- there is no separate tag field to keep in sync between the
 *   two languages.
 *
 * Every base64 field is the standard alphabet, written here with `btoa`
 * over raw bytes -- the same alphabet Python's `base64.b64encode` uses.
 *
 * PEM in, DER in: the one gap eventkeys.py leaves for this file to close
 * -----------------------------------------------------------------------
 * `keys/events/<id>.pub` is PEM (`-----BEGIN PUBLIC KEY----- ... -----END
 * PUBLIC KEY-----`), but `crypto.subtle.importKey("spki", ...)` refuses PEM
 * outright -- it wants only the DER bytes the PEM wraps. `pemToDer` strips
 * the header and footer lines and `atob`s what is left, before the key is
 * ever imported. Skipping this step is not a smaller failure, it is the
 * form failing to load a key it is holding in front of it.
 *
 * What this file deliberately does not do
 * -----------------------------------------
 * There is no decrypt function here, and there must never be one: a static
 * registration page holds only the published public half (see
 * `SignupForm.tsx`), which cannot decrypt anything by construction -- that
 * is the property the whole design in the phase 4 spec (S:4, "Protection
 * des données") rests on. `app/tests/signup-encrypt.test.ts` asserts this
 * directly, not just by this file's shape.
 */

/**
 * What a participant supplies, and nothing else (spec S:3): first name,
 * surname, email address; institution is optional, `''` when not given --
 * the same "absent means blank string" idiom `Speaker` uses in
 * `data/types.ts`, not an omitted key. `membership_opt_in` is G-18's
 * announce-list checkbox. Nothing here defaults it to `true`: the only
 * place that decides its starting value is `SignupForm`'s own state, kept
 * unticked, because a serialisation default is exactly the kind of place a
 * silently-opted-in participant would come from.
 */
export interface Registration {
  first_name: string;
  surname: string;
  email: string;
  institution: string;
  membership_opt_in: boolean;
}

interface Envelope {
  v: number;
  encrypted_key: string;
  iv: string;
  ciphertext: string;
}

/** Mirrors `eventkeys.WIRE_VERSION`. */
const WIRE_VERSION = 1;
/** Mirrors `eventkeys.AES_KEY_BYTES`. */
const AES_KEY_BYTES = 32;
/** Mirrors `eventkeys.GCM_NONCE_BYTES`. */
const GCM_NONCE_BYTES = 12;

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

/** See the module docstring: `importKey("spki", ...)` wants DER, and
 *  `keys/events/<id>.pub` is PEM. Built with `new Uint8Array(n)` rather
 *  than `Uint8Array.from`, whose return type is not specific enough about
 *  its backing buffer for `crypto.subtle.importKey`'s `BufferSource`
 *  parameter to accept directly. */
function pemToDer(pem: string): Uint8Array<ArrayBuffer> {
  const body = pem
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line.length > 0 && !line.startsWith('-----'))
    .join('');
  const binary = atob(body);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/**
 * Imports the event's published public half for encryption, and *only*
 * encryption: `keyUsages` names `['encrypt']` alone, so nothing downstream
 * of this call could be handed a key WebCrypto itself would let decrypt --
 * the capability was never asked for, not merely unused.
 *
 * Exported so `SignupForm` can use it as the validity check on a fetched
 * PEM, rather than a substring sniff on the header line: a truncated body
 * or a non-RSA key (an EC public key carries the identical
 * `BEGIN PUBLIC KEY` label) both fail `importKey` with the exact algorithm
 * and format this module actually needs, so a sniff-based check would have
 * let either through to fail later, mid-submission, with a message that
 * blames encryption for what was really an unusable key.
 */
export async function importEventPublicKey(publicKeyPem: string): Promise<CryptoKey> {
  const der = pemToDer(publicKeyPem);
  return crypto.subtle.importKey('spki', der, { name: 'RSA-OAEP', hash: 'SHA-256' }, false, [
    'encrypt',
  ]);
}

/**
 * Hybrid-encrypts `fields` for the holder of the private half matching
 * `publicKeyPem` -- the browser-side mirror of `eventkeys.py::encrypt`.
 * See the module docstring for the wire format this produces.
 */
export async function encryptRegistration(
  publicKeyPem: string,
  fields: Registration,
): Promise<string> {
  const publicKey = await importEventPublicKey(publicKeyPem);

  const aesKeyBytes = crypto.getRandomValues(new Uint8Array(AES_KEY_BYTES));
  const iv = crypto.getRandomValues(new Uint8Array(GCM_NONCE_BYTES));

  const encryptedKey = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, publicKey, aesKeyBytes);

  // Imported for encryption only, like the RSA key above -- and unlike it,
  // this key never leaves this function in any form: only its RSA-OAEP
  // encryption (`encryptedKey`, above) and its use to seal `ciphertext`,
  // below, are ever produced.
  const aesKey = await crypto.subtle.importKey('raw', aesKeyBytes, { name: 'AES-GCM' }, false, [
    'encrypt',
  ]);
  const plaintext = new TextEncoder().encode(JSON.stringify(fields));
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aesKey, plaintext);

  const envelope: Envelope = {
    v: WIRE_VERSION,
    encrypted_key: bytesToBase64(new Uint8Array(encryptedKey)),
    iv: bytesToBase64(iv),
    ciphertext: bytesToBase64(new Uint8Array(ciphertext)),
  };
  return JSON.stringify(envelope);
}
