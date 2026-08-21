import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SurveyForm } from '../src/survey/SurveyForm';
import { App } from '../src/App';
import cases from '../../tools/tests/fixtures/governance-cases.json';

// Reuses the registration fixture's own key pair -- see
// `survey-encrypt.test.ts`'s own comment for why one pair is pinned for
// both intake pages rather than a second one generated here.
const FIXTURE = cases.event_registration_encryption;
const VALID_PEM = FIXTURE.public_pem;

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function importPrivateKeyPem(pem: string): Promise<CryptoKey> {
  const body = pem
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line.length > 0 && !line.startsWith('-----'))
    .join('');
  const binary = atob(body);
  const der = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) der[i] = binary.charCodeAt(i);
  return crypto.subtle.importKey('pkcs8', der, { name: 'RSA-OAEP', hash: 'SHA-256' }, false, [
    'decrypt',
  ]);
}

/** The test's own, deliberately separate decryption -- `encrypt.ts` exposes
 *  no decrypt function, on purpose (see `survey-encrypt.test.ts`). */
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

function renderSurvey(eventId = 'mrg-042') {
  return render(
    <MemoryRouter initialEntries={[`/survey/${eventId}`]}>
      <Routes>
        <Route path="/survey/:eventId" element={<SurveyForm />} />
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

describe('SurveyForm -- the notice', () => {
  it('shows the data-protection notice before any field, not after', async () => {
    stubKeyFetchOk();
    renderSurvey();

    await screen.findByRole('group', { name: /rate this session overall/i });

    const text = document.body.textContent ?? '';
    const noticeAt = text.indexOf('Before you answer');
    const firstFieldAt = text.indexOf('How would you rate');
    expect(noticeAt).toBeGreaterThanOrEqual(0);
    expect(firstFieldAt).toBeGreaterThan(noticeAt);
  });

  it('shows the notice even while the key is still loading or unavailable', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 }) as Response));
    renderSurvey();
    expect(screen.getByText('Before you answer')).toBeInTheDocument();
  });

  it('states only people recorded present receive this, same-key encryption, the 90-day retention and a real contact address', async () => {
    stubKeyFetchOk();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });

    const text = document.body.textContent ?? '';
    expect(text).toMatch(/recorded as present/i);
    expect(text).toMatch(/same key.*your registration/i);
    expect(text).toMatch(/90 days/);
    expect(text).toContain('reading-group@example.test');
  });
});

describe('SurveyForm -- what it asks, and nothing else', () => {
  it('asks a five-point rating, a yes/no recommendation, and optional free-text feedback', async () => {
    stubKeyFetchOk();
    renderSurvey();

    const ratingGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    expect(within(ratingGroup).getAllByRole('radio')).toHaveLength(5);

    const recommendGroup = screen.getByRole('group', { name: /recommend this series/i });
    const yes = within(recommendGroup).getByRole('radio', { name: 'Yes' });
    const no = within(recommendGroup).getByRole('radio', { name: 'No' });
    expect(yes).toBeInTheDocument();
    expect(no).toBeInTheDocument();

    const feedback = screen.getByLabelText(/anything else you would like to tell us/i);
    expect(feedback).not.toBeRequired();
  });

  it('fetches the event public key from the event-scoped, same-origin path -- the same key registration uses', async () => {
    stubKeyFetchOk();

    renderSurvey('mrg-042');
    await screen.findByRole('group', { name: /rate this session overall/i });

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toMatch(/\/keys\/events\/mrg-042\.pub$/);
  });

  it('the submit button starts disabled until both required questions are answered', async () => {
    stubKeyFetchOk();
    renderSurvey();
    const ratingGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    const submit = screen.getByRole('button', { name: /submit/i });
    expect(submit).toBeDisabled();

    fireEvent.click(within(ratingGroup).getAllByRole('radio')[4]);
    expect(submit).toBeDisabled();

    const recommendGroup = screen.getByRole('group', { name: /recommend this series/i });
    fireEvent.click(within(recommendGroup).getByRole('radio', { name: 'Yes' }));
    expect(submit).not.toBeDisabled();
  });
});

describe('SurveyForm -- the public key cannot be fetched', () => {
  it('refuses to send, says so, and never asks for anything to send in the clear', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 }) as Response));
    renderSurvey();

    await screen.findByText(/this survey is not available right now/i);

    expect(screen.queryByRole('group', { name: /rate this session overall/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('SurveyForm -- sending', () => {
  async function answer() {
    const ratingGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    fireEvent.click(within(ratingGroup).getAllByRole('radio')[4]); // 5
    const recommendGroup = screen.getByRole('group', { name: /recommend this series/i });
    fireEvent.click(within(recommendGroup).getByRole('radio', { name: 'Yes' }));
    fireEvent.change(screen.getByLabelText(/anything else you would like to tell us/i), {
      target: { value: 'Loved the live Q&A.' },
    });
  }

  it('posts to the relay URL with /survey appended, not the bare registration URL', async () => {
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example');
    const calls: { url: string; body: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, opts?: RequestInit) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        calls.push({ url: String(url), body: String(opts?.body ?? '') });
        return { ok: true } as Response;
      }),
    );

    renderSurvey('mrg-042');
    await answer();
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    await screen.findByText(/your answers have been sent/i);

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('https://signup-relay.example/survey');
  });

  it('when the relay is configured, sends only the encrypted envelope -- and it decrypts to exactly what was answered', async () => {
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
        if (String(url) === 'https://signup-relay.example/survey') {
          calls.push({ url: String(url), body: String(opts?.body ?? '') });
          return { ok: true } as Response;
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );

    renderSurvey('mrg-042');
    await answer();
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    await screen.findByText(/your answers have been sent/i);

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
      overall_rating: 5,
      recommend: true,
      feedback: 'Loved the live Q&A.',
    });

    for (const spy of consoleSpies) expect(spy).not.toHaveBeenCalled();
    expect(storageSpy).not.toHaveBeenCalled();
  });

  it('sends a "no" recommendation and blank feedback as exactly that -- not a hard-coded value', async () => {
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example');
    const calls: { body: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, opts?: RequestInit) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        if (String(url) === 'https://signup-relay.example/survey') {
          calls.push({ body: String(opts?.body ?? '') });
          return { ok: true } as Response;
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );

    renderSurvey('mrg-042');
    const ratingGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    fireEvent.click(within(ratingGroup).getAllByRole('radio')[1]); // 2
    const recommendGroup = screen.getByRole('group', { name: /recommend this series/i });
    fireEvent.click(within(recommendGroup).getByRole('radio', { name: 'No' }));
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    await screen.findByText(/your answers have been sent/i);

    const sent = JSON.parse(calls[0].body);
    const privateKey = await importPrivateKeyPem(FIXTURE.private_pem);
    const recovered = await decryptEnvelopeFields(privateKey, sent);
    expect(recovered).toEqual({ overall_rating: 2, recommend: false, feedback: '' });
  });

  it('when the relay is not configured, says the survey is not open yet and sends nothing', async () => {
    stubKeyFetchOk();
    renderSurvey('mrg-042');
    await answer();
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    await screen.findByText(/this survey is not open yet/i);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('reports a relay error without pretending the answers were sent, and keeps what was answered', async () => {
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        return { ok: false, status: 502 } as Response;
      }),
    );

    renderSurvey('mrg-042');
    await answer();
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    await screen.findByText(/could not be sent/i);
    expect(screen.queryByText(/your answers have been sent/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/anything else you would like to tell us/i)).toHaveValue(
      'Loved the live Q&A.',
    );
  });
});

describe('SurveyForm -- reachable with no eventId at all', () => {
  it('treats a route with no eventId as an unavailable key rather than crashing', async () => {
    render(
      <MemoryRouter initialEntries={['/survey/']}>
        <Routes>
          <Route path="/survey/:eventId?" element={<SurveyForm />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText(/this survey is not available right now/i);
  });
});

describe('SurveyForm -- needs no organiser account', () => {
  it('renders without AuthProvider or DataProvider in the tree', async () => {
    stubKeyFetchOk();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });
    expect(within(document.body).queryByText(/sign in/i)).not.toBeInTheDocument();
  });
});

// The block above proves `SurveyForm` does not *need* an account; this
// proves the production *route* actually reaches it without one either --
// the same "route order, not component design" property
// `signup-form.test.tsx`'s own identical block asserts for `/signup`.
describe('App -- the survey route in production, not standalone', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    window.location.hash = '';
  });

  it('reaches SurveyForm with no sign-in screen', async () => {
    stubKeyFetchOk();
    window.location.hash = '#/survey/mrg-042';
    render(<App />);

    await screen.findByRole('group', { name: /rate this session overall/i });
    expect(screen.queryByText(/for the team/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^sign in$/i)).not.toBeInTheDocument();
  });

  it('editing the event id in the address bar forces a full remount, the same discipline SignupRoute uses', async () => {
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const u = String(url);
        if (u.endsWith('/keys/events/mrg-042.pub') || u.endsWith('/keys/events/mrg-043.pub')) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        throw new Error(`unexpected fetch in test: ${u}`);
      }),
    );

    window.location.hash = '#/survey/mrg-042';
    render(<App />);
    const ratingGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    fireEvent.click(within(ratingGroup).getAllByRole('radio')[4]);

    act(() => {
      window.location.hash = '#/survey/mrg-043';
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    const freshGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    // A fresh instance: the earlier selection must not have survived the
    // switch, proving the remount actually happened rather than merely a
    // new key eventually being fetched.
    expect(within(freshGroup).getAllByRole('radio').every(r => !(r as HTMLInputElement).checked)).toBe(
      true,
    );
  });
});
