/**
 * The browser half of the post-event survey's hybrid encryption -- the
 * sibling of `app/src/signup/encrypt.ts`, reproducing the exact same wire
 * format `tools/convener_ops/eventkeys.py` documents field by field, for the
 * exact same reason: this file has to agree with `tools/convener_ops/survey.py`
 * byte for byte, or every response this page sends becomes permanently
 * unreadable the moment the two implementations disagree.
 *
 * Why this file exists separately from `signup/encrypt.ts`, rather than a
 * shared helper both import
 * -----------------------------------------------------------------------
 * The crypto here is not new: RSA-OAEP wraps a throwaway AES-256-GCM key,
 * exactly as `signup/encrypt.ts`'s own module docstring explains at length
 * (read that docstring first -- it is not repeated here). What changes is
 * only the plaintext shape being encrypted. This project already keeps
 * `services/signup-relay` and `services/form-relay` as separate workers
 * that happen to share a dispatch pattern, rather than one worker with a
 * shared internal helper, on the reasoning that two independent trust
 * boundaries are worth the duplication (see that worker's own README,
 * "Why this is a third worker, not a route on either of the other two").
 * The survey page is the same trade at the browser layer: this form is the
 * intake for a different, optional, event-gated flow (spec S:6, "Facultatif,
 * activable par evenement"), and a shared crypto helper both pages import
 * would couple a change meant for one page's field shape to a review of the
 * other's, for no gain -- neither page holds a decrypt capability either
 * side of that helper could leak.
 *
 * The wire format
 * ----------------
 * Identical to `signup/encrypt.ts`'s own, because it is the same envelope
 * `services/signup-relay` validates on every route it answers (`README.md`,
 * "What 'shape' means here"):
 *
 *     {"v":1,"encrypted_key":"<base64>","iv":"<base64>","ciphertext":"<base64>"}
 *
 * What this file deliberately does not do
 * -----------------------------------------
 * There is no decrypt function here, for the identical reason
 * `signup/encrypt.ts` has none: a static survey page holds only the
 * published public half of an event's key, which cannot decrypt anything
 * by construction.
 */

/**
 * A participant's answers to the three fixed questions, and nothing else --
 * see `tools/convener_ops/survey.py`'s module docstring for why these three and
 * no others. `overall_rating` is a whole number 1-5; `recommend` is a plain
 * yes/no; `feedback` is free text, `''` when a participant chooses to leave
 * it blank -- the same "absence means blank string" idiom
 * `signup/encrypt.ts`'s own `Registration.institution` already uses,
 * because declining to write anything is a complete answer, not an
 * unfinished one.
 */
export interface SurveyResponse {
  overall_rating: number;
  recommend: boolean;
  feedback: string;
}

interface Envelope {
  v: number;
  encrypted_key: string;
  iv: string;
  ciphertext: string;
}

/** Mirrors `eventkeys.WIRE_VERSION` -- identical to `signup/encrypt.ts`'s
 *  own constant of the same name; both must always agree with the one
 *  Python source of truth, not with each other directly. */
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
 *  `keys/events/<id>.pub` is PEM. Identical to `signup/encrypt.ts::pemToDer`
 *  -- not imported from it, for the reason the module docstring gives for
 *  this file's own independence. */
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
 * encryption -- see `signup/encrypt.ts::importEventPublicKey`'s own
 * docstring for why `keyUsages: ['encrypt']` alone matters, and why
 * validating a fetched PEM by attempting this import is the correct check,
 * not a substring sniff on the header line.
 */
export async function importEventPublicKey(publicKeyPem: string): Promise<CryptoKey> {
  const der = pemToDer(publicKeyPem);
  return crypto.subtle.importKey('spki', der, { name: 'RSA-OAEP', hash: 'SHA-256' }, false, [
    'encrypt',
  ]);
}

/**
 * Hybrid-encrypts `fields` for the holder of the private half matching
 * `publicKeyPem` -- the browser-side mirror of
 * `tools/convener_ops/eventkeys.py::encrypt`, called here on a `SurveyResponse`
 * rather than a `Registration`. See the module docstring for the wire
 * format this produces.
 */
export async function encryptSurveyResponse(
  publicKeyPem: string,
  fields: SurveyResponse,
): Promise<string> {
  const publicKey = await importEventPublicKey(publicKeyPem);

  const aesKeyBytes = crypto.getRandomValues(new Uint8Array(AES_KEY_BYTES));
  const iv = crypto.getRandomValues(new Uint8Array(GCM_NONCE_BYTES));

  const encryptedKey = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, publicKey, aesKeyBytes);

  // Imported for encryption only, like the RSA key above -- and unlike it,
  // this key never leaves this function in any form.
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
