import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SignupForm } from '../src/signup/SignupForm';
import { App } from '../src/App';
import cases from '../../tools/tests/fixtures/governance-cases.json';

// The fixture (D-14) carries a real RSA-2048 key pair generated once for
// cross-language tests: `public_pem` here, `private_pem` used below to
// decrypt what the form actually sent, and by the sibling Python test
// (`tools/tests/test_eventkeys.py`) to decrypt what `encrypt.ts` itself
// produces. Using the same key here as the crypto suite's own fixture --
// rather than a second, unrelated one hardcoded in this file -- is what
// makes decrypting the captured wire body possible at all.
const FIXTURE = cases.event_registration_encryption;
const VALID_PEM = FIXTURE.public_pem;

const RSA_KEY_BITS = 2048;

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

function toPem(der: ArrayBuffer, label: string): string {
  const b64 = bytesToBase64(new Uint8Array(der));
  const lines = b64.match(/.{1,64}/g) ?? [b64];
  return `-----BEGIN ${label}-----\n${lines.join('\n')}\n-----END ${label}-----\n`;
}

async function importPrivateKeyPem(pem: string): Promise<CryptoKey> {
  return crypto.subtle.importKey('pkcs8', pemToDer(pem), { name: 'RSA-OAEP', hash: 'SHA-256' }, false, [
    'decrypt',
  ]);
}

/**
 * The test's own, deliberately separate implementation of what
 * `eventkeys.py::decrypt` does -- `encrypt.ts` exposes no decrypt function,
 * on purpose (see `signup-encrypt.test.ts`), so proving what actually left
 * the browser means redoing the other half here, not calling into the
 * component under test. `envelope` may carry extra keys (`event_id`); only
 * the four wire fields are read.
 */
async function decryptEnvelopeFields(
  privateKey: CryptoKey,
  envelope: { encrypted_key: string; iv: string; ciphertext: string },
): Promise<unknown> {
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
  return JSON.parse(new TextDecoder().decode(plaintext));
}

/** A second, independent event key pair -- for the cross-event test, which
 *  needs two events with two different keys to prove a registration is
 *  never encrypted under the wrong one. */
async function generateEventKeyPair(): Promise<{ publicPem: string; privateKey: CryptoKey }> {
  const { publicKey, privateKey } = await crypto.subtle.generateKey(
    {
      name: 'RSA-OAEP',
      modulusLength: RSA_KEY_BITS,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: 'SHA-256',
    },
    true,
    ['encrypt', 'decrypt'],
  );
  const der = await crypto.subtle.exportKey('spki', publicKey);
  return { publicPem: toPem(der, 'PUBLIC KEY'), privateKey };
}

function renderSignup(eventId = 'mrg-042') {
  return render(
    <MemoryRouter initialEntries={[`/signup/${eventId}`]}>
      <Routes>
        <Route path="/signup/:eventId" element={<SignupForm />} />
      </Routes>
    </MemoryRouter>,
  );
}

function stubKeyFetchOk() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
        return { ok: true, text: async () => VALID_PEM } as Response;
      }
      throw new Error(`unexpected fetch in test: ${url}`);
    }),
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('SignupForm -- the notice', () => {
  it('shows the data-protection notice before any field, not after', async () => {
    stubKeyFetchOk();
    renderSignup();

    await screen.findByLabelText(/first name/i);

    const text = document.body.textContent ?? '';
    const noticeAt = text.indexOf('Before you register');
    const firstFieldAt = text.indexOf('First name');
    expect(noticeAt).toBeGreaterThanOrEqual(0);
    expect(firstFieldAt).toBeGreaterThan(noticeAt);
  });

  it('shows the notice even while the key is still loading or unavailable', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 }) as Response));
    renderSignup();
    expect(screen.getByText('Before you register')).toBeInTheDocument();
  });

  it('states browser-side encryption, the 90-day retention and key destruction, and a real contact address -- not just its own heading', async () => {
    // A test asserting only that the heading precedes the first field label
    // would still pass if every sentence underneath it were gutted -- and
    // those sentences are the legal substance of requirement 1, not the
    // heading.
    stubKeyFetchOk();
    renderSignup();
    await screen.findByLabelText(/first name/i);

    const text = document.body.textContent ?? '';
    expect(text).toMatch(/encrypts this information before it is sent/i);
    expect(text).toMatch(/90 days/);
    expect(text).toMatch(/destroying the key/i);
    expect(text).toContain('reading-group@example.test');
  });
});

describe('SignupForm -- what it collects, and nothing else', () => {
  it('collects first name, surname, email, an optional institution, and an unticked opt-in', async () => {
    stubKeyFetchOk();
    renderSignup();

    const firstName = await screen.findByLabelText(/first name/i);
    const surname = screen.getByLabelText(/surname/i);
    const email = screen.getByLabelText(/email address/i);
    const institution = screen.getByLabelText(/institution/i);
    const optIn = screen.getByRole('checkbox');

    expect(firstName).toBeRequired();
    expect(surname).toBeRequired();
    expect(email).toBeRequired();
    expect(institution).not.toBeRequired();

    // G-18: unticked by default. Nothing loads it as `true`.
    expect(optIn).not.toBeChecked();
  });

  it('fetches the event public key from the event-scoped, same-origin path', async () => {
    stubKeyFetchOk();

    renderSignup('mrg-042');
    await screen.findByLabelText(/first name/i);

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toMatch(/\/keys\/events\/mrg-042\.pub$/);
  });
});

describe('SignupForm -- the public key cannot be fetched', () => {
  it('refuses to send, says so, and never asks for anything to send in the clear', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 }) as Response));
    renderSignup();

    await screen.findByText(/registration is not available right now/i);

    // The refusal replaces the form entirely -- there is nothing here that
    // could be filled in and sent unencrypted as a fallback.
    expect(screen.queryByLabelText(/first name/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /register/i })).not.toBeInTheDocument();
    // Only the one attempt to fetch the key -- nothing was ever sent.
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('also refuses when the key file fetch throws outright (offline, DNS failure, ...)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network down');
      }),
    );
    renderSignup();

    await screen.findByText(/registration is not available right now/i);
    expect(screen.queryByLabelText(/first name/i)).not.toBeInTheDocument();
  });

  it('also refuses when the fetched body is not actually a public key', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, text: async () => '404: not found' }) as Response),
    );
    renderSignup();

    await screen.findByText(/registration is not available right now/i);
    expect(screen.queryByLabelText(/first name/i)).not.toBeInTheDocument();
  });

  it('refuses a PEM that is truncated but still carries a valid header and footer, before anyone can type into it', async () => {
    // A `BEGIN PUBLIC KEY` substring sniff would have let this through: the
    // label is intact, only the DER body underneath is broken. Left
    // unvalidated, the participant would fill in the whole form and only
    // learn it never worked at submit, with a message that can never be
    // fixed by retrying.
    const truncated = VALID_PEM.replace(/\n[^\n]+\n-----END/, '\n-----END');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => truncated } as Response;
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );
    renderSignup();

    await screen.findByText(/registration is not available right now/i);
    expect(screen.queryByLabelText(/first name/i)).not.toBeInTheDocument();
  });

  it('refuses a real, well-formed, but non-RSA public key -- an EC key carries the identical BEGIN PUBLIC KEY label', async () => {
    const { publicKey } = await crypto.subtle.generateKey(
      { name: 'ECDSA', namedCurve: 'P-256' },
      true,
      ['sign', 'verify'],
    );
    const der = await crypto.subtle.exportKey('spki', publicKey);
    const ecPem = toPem(der, 'PUBLIC KEY');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => ecPem } as Response;
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );
    renderSignup();

    await screen.findByText(/registration is not available right now/i);
    expect(screen.queryByLabelText(/first name/i)).not.toBeInTheDocument();
  });
});

describe('SignupForm -- a hung key fetch eventually refuses too', () => {
  it('times out and refuses rather than showing "Checking…" forever', async () => {
    vi.useFakeTimers();
    try {
      // Never resolves on its own -- the only way out is the component's
      // own timeout aborting it, exactly like a stalled connection would
      // leave a real `fetch` pending indefinitely.
      vi.stubGlobal(
        'fetch',
        vi.fn((_url: string, opts?: RequestInit) => {
          return new Promise<Response>((_resolve, reject) => {
            opts?.signal?.addEventListener('abort', () => {
              reject(new DOMException('The operation was aborted.', 'AbortError'));
            });
          });
        }),
      );

      renderSignup();
      expect(screen.getByText(/checking that registration is available/i)).toBeInTheDocument();

      // Mirrors SignupForm's own KEY_FETCH_TIMEOUT_MS.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(15_000);
      });

      expect(screen.getByText(/registration is not available right now/i)).toBeInTheDocument();
      expect(screen.queryByText(/checking that registration is available/i)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('SignupForm -- sending', () => {
  async function fillForm() {
    fireEvent.change(await screen.findByLabelText(/first name/i), {
      target: { value: 'Ada' },
    });
    fireEvent.change(screen.getByLabelText(/surname/i), { target: { value: 'Lovelace' } });
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'ada@example.org' },
    });
    fireEvent.change(screen.getByLabelText(/institution/i), {
      target: { value: 'Analytical Engines Institute' },
    });
  }

  it('when the relay is configured, sends only the encrypted envelope -- and it decrypts to exactly what was typed', async () => {
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example/');
    const consoleSpies = (['log', 'warn', 'error', 'debug', 'info'] as const).map(m =>
      vi.spyOn(console, m).mockImplementation(() => {}),
    );
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem');
    const calls: { url: string; body: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, opts?: RequestInit) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        if (String(url) === 'https://signup-relay.example/') {
          calls.push({ url: String(url), body: String(opts?.body ?? '') });
          return { ok: true } as Response;
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );

    renderSignup('mrg-042');
    await fillForm();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /register/i }));

    await screen.findByText(/registration sent/i);

    expect(calls).toHaveLength(1);
    const sent = JSON.parse(calls[0].body);
    expect(sent.event_id).toBe('mrg-042');
    expect(Object.keys(sent).sort()).toEqual([
      'ciphertext',
      'encrypted_key',
      'event_id',
      'iv',
      'v',
    ]);

    // The decisive check, not a substring probe: decrypt the exact body
    // that left the browser with the fixture's real private key and
    // compare the whole recovered object. A mutation hard-coding
    // `membership_opt_in: true`, swapping `first_name`/`surname`, or
    // dropping a `.trim()` all fail this -- none of them are visible to a
    // `not.toContain` check on base64 text, which also has a real chance of
    // matching short names by coincidence.
    const privateKey = await importPrivateKeyPem(FIXTURE.private_pem);
    const recovered = await decryptEnvelopeFields(privateKey, sent);
    expect(recovered).toEqual({
      first_name: 'Ada',
      surname: 'Lovelace',
      email: 'ada@example.org',
      institution: 'Analytical Engines Institute',
      membership_opt_in: true,
    });

    // Nothing about this flow writes anywhere it does not have to: no
    // console message and no storage write could carry the plaintext where
    // this suite would not see it.
    for (const spy of consoleSpies) expect(spy).not.toHaveBeenCalled();
    expect(storageSpy).not.toHaveBeenCalled();
  });

  it('sends the announce-list opt-in as exactly what was left unticked -- not a hard-coded value', async () => {
    // Deliberately the mirror of the test above: that one ticks the
    // checkbox, so a mutation hard-coding `membership_opt_in: true` would
    // coincidentally match its expectation and slip through. Leaving the
    // box unticked here, and decrypting to confirm `false` actually
    // travelled, is what closes that gap -- the reviewer's exact mutant
    // only failed the cross-event test below for this same reason.
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example/');
    const calls: { body: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, opts?: RequestInit) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        if (String(url) === 'https://signup-relay.example/') {
          calls.push({ body: String(opts?.body ?? '') });
          return { ok: true } as Response;
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );

    renderSignup('mrg-042');
    await fillForm();
    // The checkbox is left exactly as it defaults: unticked.
    fireEvent.click(screen.getByRole('button', { name: /register/i }));
    await screen.findByText(/registration sent/i);

    const sent = JSON.parse(calls[0].body);
    const privateKey = await importPrivateKeyPem(FIXTURE.private_pem);
    const recovered = await decryptEnvelopeFields(privateKey, sent);
    expect(recovered).toEqual({
      first_name: 'Ada',
      surname: 'Lovelace',
      email: 'ada@example.org',
      institution: 'Analytical Engines Institute',
      membership_opt_in: false,
    });
  });

  it('when the relay is not configured, says registration is not open yet and sends nothing', async () => {
    stubKeyFetchOk();
    renderSignup('mrg-042');
    await fillForm();
    fireEvent.click(screen.getByRole('button', { name: /register/i }));

    await screen.findByText(/registration is not open for this event yet/i);
    // The key fetch, and nothing else: encryption may have happened
    // in-memory, but no request carrying it was ever made.
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('reports a relay error without pretending the registration was sent, and keeps what was typed', async () => {
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example/');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        return { ok: false, status: 502 } as Response;
      }),
    );

    renderSignup('mrg-042');
    await fillForm();
    fireEvent.click(screen.getByRole('button', { name: /register/i }));

    await screen.findByText(/could not be sent/i);
    expect(screen.queryByText(/registration sent/i)).not.toBeInTheDocument();
    // An error must not force retyping: only a successful send clears the
    // fields (see SignupForm.tsx's `submit`).
    expect(screen.getByLabelText(/first name/i)).toHaveValue('Ada');
    expect(screen.getByLabelText(/surname/i)).toHaveValue('Lovelace');
    expect(screen.getByLabelText(/email address/i)).toHaveValue('ada@example.org');
  });
});

describe('SignupForm -- reachable with no eventId at all', () => {
  it('treats a route with no eventId as an unavailable key rather than crashing', async () => {
    render(
      <MemoryRouter initialEntries={['/signup/']}>
        <Routes>
          <Route path="/signup/:eventId?" element={<SignupForm />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText(/registration is not available right now/i);
  });
});

// Sanity check that this component alone -- with no AuthProvider and no
// DataProvider in the tree at all -- is the proof that it needs neither: a
// screen requiring one would fail to render, not silently omit it. This
// proves the component's own requirements, not the production route: see
// the `App`-level block below for that.
describe('SignupForm -- needs no organiser account', () => {
  it('renders without AuthProvider or DataProvider in the tree', async () => {
    stubKeyFetchOk();
    renderSignup();
    await screen.findByLabelText(/first name/i);
    expect(within(document.body).queryByText(/sign in/i)).not.toBeInTheDocument();
  });
});

// The block above proves `SignupForm` does not *need* an account; it does
// not prove the *route* a participant actually reaches avoids one --
// `App.tsx` still wraps its whole router in `<AuthProvider>`, and only
// route-matching order keeps `/signup/:eventId` from ever falling through
// to `Shell`'s gate. Rendering `App` itself, through `HashRouter`, is what
// verifies that claim rather than assuming it from the route table.
describe('App -- the signup route in production, not standalone', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    window.location.hash = '';
  });

  it('reaches SignupForm with no sign-in screen', async () => {
    stubKeyFetchOk();
    window.location.hash = '#/signup/mrg-042';
    render(<App />);

    await screen.findByLabelText(/first name/i);
    expect(screen.queryByText(/for the team/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^sign in$/i)).not.toBeInTheDocument();
  });

  it('editing the event id in the address bar never mixes an old event\'s key into a new one\'s registration', async () => {
    // Two distinct events, two distinct keys -- the only way to prove a
    // registration was sealed under the *right* one rather than merely
    // "a" one.
    const eventA = await generateEventKeyPair();
    const eventB = await generateEventKeyPair();
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example/');
    const calls: { body: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, opts?: RequestInit) => {
        const u = String(url);
        if (u.endsWith('/keys/events/mrg-042.pub')) {
          return { ok: true, text: async () => eventA.publicPem } as Response;
        }
        if (u.endsWith('/keys/events/mrg-043.pub')) {
          return { ok: true, text: async () => eventB.publicPem } as Response;
        }
        if (u === 'https://signup-relay.example/') {
          calls.push({ body: String(opts?.body ?? '') });
          return { ok: true } as Response;
        }
        throw new Error(`unexpected fetch in test: ${u}`);
      }),
    );

    window.location.hash = '#/signup/mrg-042';
    render(<App />);
    fireEvent.change(await screen.findByLabelText(/first name/i), {
      target: { value: 'stale text from the previous event' },
    });

    // `HashRouter` makes this reachable without a page load: editing the
    // address bar from one event to another, mid-session. react-router's
    // hash history listens for `popstate`, not `hashchange` (confirmed by
    // reading `node_modules/react-router/dist/.../chunk-4N6VE7H7.mjs`), and
    // jsdom does not dispatch either on its own from a plain assignment --
    // so `popstate` is fired explicitly here, the event a real browser
    // raises after a hash-only address bar edit.
    act(() => {
      window.location.hash = '#/signup/mrg-043';
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    // A fresh instance -- the earlier text must not have survived the
    // switch, which is the remount actually taking effect, not merely the
    // right key eventually being used.
    const firstName = await screen.findByLabelText(/first name/i);
    expect(firstName).toHaveValue('');

    fireEvent.change(firstName, { target: { value: 'Ada' } });
    fireEvent.change(screen.getByLabelText(/surname/i), { target: { value: 'Lovelace' } });
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'ada@example.org' },
    });
    fireEvent.click(screen.getByRole('button', { name: /register/i }));

    await screen.findByText(/registration sent/i);
    expect(calls).toHaveLength(1);
    const sent = JSON.parse(calls[0].body);
    expect(sent.event_id).toBe('mrg-043');

    // The decisive check: only mrg-043's own private key can recover this.
    // If the stale mrg-042 public key had sealed this registration instead
    // -- the bug this test targets -- decrypting with mrg-043's private key
    // would throw, since RSA-OAEP cannot be decrypted under the wrong key,
    // rather than silently recovering the wrong plaintext.
    const recovered = await decryptEnvelopeFields(eventB.privateKey, sent);
    expect(recovered).toEqual({
      first_name: 'Ada',
      surname: 'Lovelace',
      email: 'ada@example.org',
      institution: '',
      membership_opt_in: false,
    });
  });
});
