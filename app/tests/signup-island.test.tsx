import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SignupForm } from '../src/islands/signup/SignupForm';
import cases from '../../tools/tests/fixtures/governance-cases.json';

// Task 6: this suite replaces `signup-form.test.tsx`, which tested
// `app/src/signup/SignupForm.tsx` (the operators' application's own
// `/signup/:eventId` route -- see git history). The form is now
// `app/src/islands/signup/SignupForm.tsx`, an island with no router of its
// own: `eventId` is a plain prop here, not a `useParams` read, so every
// test below renders the component directly rather than through a
// `MemoryRouter`. Remount-by-event-id discipline moved to its own file,
// `signup-island-mount.test.tsx`, which exercises `main.tsx::
// mountSignupIsland` -- the thing that actually applies `key={eventId}`
// now that `App.tsx`'s `SignupRoute` no longer exists to do it.
//
// The data-protection notice suite (`SignupForm -- the notice`, in the
// old file) is gone too, not merely moved: that text no longer renders
// from this component at all (see `SignupForm.tsx`'s own module comment)
// -- `tools/tests/test_site.py` already covers the static copy
// `site/src/event.njk` carries instead.

const FIXTURE = cases.event_registration_encryption;
const VALID_PEM = FIXTURE.public_pem;

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

function renderSignup(eventId: string | undefined = 'mrg-042') {
  return render(<SignupForm eventId={eventId} />);
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

// Spec S:5's two matching boundaries -- "present without having
// registered" and "joined by telephone" -- named on the event page itself,
// not only in docs/reference/operations.md. `event.njk` carries no copy of
// this text (unlike the data-protection notice, which the njk template
// now owns alone), so the island keeps rendering it -- a test here, rather
// than trusting the JSX to keep saying it, is what makes removing it a red
// build instead of a silent regression.
describe('SignupForm -- the two matching boundaries', () => {
  it('shows both boundaries before any field, not after', async () => {
    stubKeyFetchOk();
    renderSignup();
    await screen.findByLabelText(/first name/i);

    const text = document.body.textContent ?? '';
    const boundariesAt = text.indexOf('About your certificate');
    const firstFieldAt = text.indexOf('First name');
    expect(boundariesAt).toBeGreaterThanOrEqual(0);
    expect(firstFieldAt).toBeGreaterThan(boundariesAt);
  });

  it('states that turning up without registering is not eligible', async () => {
    stubKeyFetchOk();
    renderSignup();
    await screen.findByLabelText(/first name/i);

    const text = document.body.textContent ?? '';
    expect(text).toMatch(/turning up without registering does not make you eligible/i);
  });

  it('states that a telephone joiner cannot be matched, and why', async () => {
    stubKeyFetchOk();
    renderSignup();
    await screen.findByLabelText(/first name/i);

    const text = document.body.textContent ?? '';
    expect(text).toMatch(/joining by telephone cannot be matched/i);
    expect(text).toMatch(/no address and no display name for a phone connection/i);
  });

  it('shows both boundaries even while the key is still loading or unavailable', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 }) as Response));
    renderSignup();
    expect(screen.getByText('About your certificate')).toBeInTheDocument();
  });
});

// Regression guard for the extraction itself: `event.njk` now renders the
// data-protection notice as static HTML ahead of this island's own mount
// point (see SignupForm.tsx's module comment). If this component ever grew
// that text back, a built event page would show it twice.
describe('SignupForm -- does not duplicate the event page\'s own notice', () => {
  it('renders no copy of the "before you register" data-protection notice', async () => {
    stubKeyFetchOk();
    renderSignup();
    await screen.findByLabelText(/first name/i);

    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/before you register/i);
    expect(text).not.toMatch(/90 days/);
  });

  it('renders no copy of the notice even while the key is loading or unavailable', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 }) as Response));
    renderSignup();
    expect(screen.queryByText(/before you register/i)).not.toBeInTheDocument();
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

  it('caps every text field at the same length the relay and the handler enforce (Important 1, branch review)', async () => {
    stubKeyFetchOk();
    renderSignup();

    const firstName = await screen.findByLabelText(/first name/i);
    const surname = screen.getByLabelText(/surname/i);
    const email = screen.getByLabelText(/email address/i);
    const institution = screen.getByLabelText(/institution/i);

    for (const field of [firstName, surname, email, institution]) {
      expect(field).toHaveAttribute('maxLength', '200');
    }
  });

  it('fetches the event public key from the event-scoped, same-origin path', async () => {
    stubKeyFetchOk();

    renderSignup('mrg-042');
    await screen.findByLabelText(/first name/i);

    expect(fetch).toHaveBeenCalledTimes(1);
    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    expect(url).toMatch(/\/keys\/events\/mrg-042\.pub$/);
    // The path-suffix check above alone would also pass for
    // `https://evil.example/keys/events/mrg-042.pub` -- same suffix,
    // different origin entirely. A root-relative path (no scheme, no
    // host) is what actually keeps this fetch same-origin: `fetch('/x')`
    // resolves against the page's own origin by construction, which a
    // hardcoded third-party absolute URL would not.
    expect(url).not.toMatch(/^[a-z][a-z0-9+.-]*:\/\//i);
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

    const privateKey = await importPrivateKeyPem(FIXTURE.private_pem);
    const recovered = await decryptEnvelopeFields(privateKey, sent);
    expect(recovered).toEqual({
      first_name: 'Ada',
      surname: 'Lovelace',
      email: 'ada@example.org',
      institution: 'Analytical Engines Institute',
      membership_opt_in: true,
    });

    for (const spy of consoleSpies) expect(spy).not.toHaveBeenCalled();
    expect(storageSpy).not.toHaveBeenCalled();
  });

  it('sends the announce-list opt-in as exactly what was left unticked -- not a hard-coded value', async () => {
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
    expect(screen.getByLabelText(/first name/i)).toHaveValue('Ada');
    expect(screen.getByLabelText(/surname/i)).toHaveValue('Lovelace');
    expect(screen.getByLabelText(/email address/i)).toHaveValue('ada@example.org');
  });

  it('a hung submit eventually refuses too, rather than saying "Sending…" forever', async () => {
    const controller = new AbortController();
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(controller.signal);
    try {
      vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example/');
      vi.stubGlobal(
        'fetch',
        vi.fn(async (url: string, opts?: RequestInit) => {
          if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
            return { ok: true, text: async () => VALID_PEM } as Response;
          }
          if (String(url) === 'https://signup-relay.example/') {
            return new Promise<Response>((_resolve, reject) => {
              opts?.signal?.addEventListener('abort', () => {
                reject(new DOMException('The operation was aborted.', 'TimeoutError'));
              });
            });
          }
          throw new Error(`unexpected fetch in test: ${url}`);
        }),
      );

      renderSignup('mrg-042');
      await fillForm();
      fireEvent.click(screen.getByRole('button', { name: /register/i }));

      expect(await screen.findByRole('button', { name: /sending/i })).toBeDisabled();

      await vi.waitFor(() => expect(timeoutSpy).toHaveBeenCalledWith(15_000));

      act(() => controller.abort());

      await screen.findByText(/could not be sent/i);
      expect(screen.queryByText(/sending…/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/could not be encrypted/i)).not.toBeInTheDocument();
    } finally {
      timeoutSpy.mockRestore();
    }
  });
});

// Fix round 1 (task 11's manual pass flagged this; task 11's own report
// names the "sent" panel's `sentPanelRef.current?.focus()`, a few lines
// above `submit` in SignupForm.tsx, as the exact precedent the error
// path was missing). Real Chrome drops `document.activeElement` to
// `<body>` the instant its focused element becomes `disabled` -- jsdom
// does not reproduce that on its own (confirmed by hand: setting
// `.disabled = true` on the focused element in jsdom leaves
// `document.activeElement` unchanged). Without correcting for that gap,
// a test asserting "focus survives an error" would pass against the
// broken component too, since jsdom would never have moved focus away
// in the first place -- exactly the "one artefact checking another"
// trap. This observer makes jsdom's focus behaviour match the real
// browser it stands in for, for the one property this suite needs, by
// blurring whatever element the `disabled` attribute lands on while it
// still holds focus.
function simulateBrowserBlurOnDisable(): () => void {
  const observer = new MutationObserver(mutations => {
    for (const mutation of mutations) {
      const target = mutation.target as HTMLButtonElement;
      if (!target.disabled || document.activeElement !== target) continue;
      // jsdom's own `blur()` is a no-op on an element that is *already*
      // disabled (checked by hand) -- unlike real Chrome, which drops
      // focus the instant the attribute lands. Toggling `disabled` off
      // just long enough to call the real `blur()`, then restoring it,
      // reaches the same end state real Chrome reaches directly: this
      // element loses focus, `disabled` stays `true`.
      target.disabled = false;
      target.blur();
      target.disabled = true;
    }
  });
  observer.observe(document.body, { attributes: true, attributeFilter: ['disabled'], subtree: true });
  return () => observer.disconnect();
}

describe('SignupForm -- focus after a failed submission', () => {
  async function fillForm() {
    fireEvent.change(await screen.findByLabelText(/first name/i), {
      target: { value: 'Ada' },
    });
    fireEvent.change(screen.getByLabelText(/surname/i), { target: { value: 'Lovelace' } });
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'ada@example.org' },
    });
  }

  it('returns focus to the Register button, not to <body>, once the relay-not-configured error appears', async () => {
    stubKeyFetchOk();
    const stopSimulating = simulateBrowserBlurOnDisable();
    try {
      renderSignup('mrg-042');
      await fillForm();
      const button = screen.getByRole('button', { name: /register/i });
      button.focus();
      expect(document.activeElement).toBe(button);

      fireEvent.click(button);
      await screen.findByText(/registration is not open for this event yet/i);

      // Assert on where focus actually landed, not that a ref was
      // touched: a fix that focused the wrong element (the alert's own
      // text, say, via a stray tabIndex) would satisfy "some ref got
      // focus()'d" without satisfying this.
      expect(document.activeElement).toBe(screen.getByRole('button', { name: /register/i }));
      expect(document.activeElement).not.toBe(document.body);
    } finally {
      stopSimulating();
    }
  });

  it('returns focus to the Register button, not to <body>, after a relay error response too', async () => {
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
    const stopSimulating = simulateBrowserBlurOnDisable();
    try {
      renderSignup('mrg-042');
      await fillForm();
      const button = screen.getByRole('button', { name: /register/i });
      button.focus();

      fireEvent.click(button);
      await screen.findByText(/could not be sent/i);

      expect(document.activeElement).toBe(screen.getByRole('button', { name: /register/i }));
      expect(document.activeElement).not.toBe(document.body);
    } finally {
      stopSimulating();
    }
  });
});

describe('SignupForm -- reachable with no eventId at all', () => {
  it('treats a missing eventId prop as an unavailable key rather than crashing', async () => {
    render(<SignupForm />);
    await screen.findByText(/registration is not available right now/i);
  });
});

// Sanity check that this component alone -- with no AuthProvider and no
// DataProvider in the tree at all -- is the proof that it needs neither: a
// screen requiring one would fail to render, not silently omit it.
describe('SignupForm -- needs no organiser account', () => {
  it('renders without AuthProvider or DataProvider in the tree', async () => {
    stubKeyFetchOk();
    renderSignup();
    await screen.findByLabelText(/first name/i);
    expect(screen.queryByText(/sign in/i)).not.toBeInTheDocument();
  });
});
