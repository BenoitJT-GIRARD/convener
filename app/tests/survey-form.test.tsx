import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SurveyForm } from '../src/survey/SurveyForm';
import { SURVEY_STATUS_FILENAME } from '../src/survey/surveyStatus';
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
  // R-39: the plaintext is padded with trailing zero bytes to a fixed
  // size before encryption (see encrypt.ts::padPlaintext) -- everything
  // up to the first 0x00 is the real JSON, the same unpad
  // `survey-encrypt.test.ts::unpadPlaintext` performs.
  const bytes = new Uint8Array(plaintext);
  const end = bytes.indexOf(0);
  const unpadded = end === -1 ? bytes : bytes.slice(0, end);
  return JSON.parse(new TextDecoder().decode(unpadded));
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

/** Stubs both fetches `SurveyForm` makes before it can render a form: the
 *  event's public key, and R-37's own `survey-status.json` membership
 *  check. `enabledIds` defaults to `['mrg-042']`, matching `renderSurvey`'s
 *  own default event id -- pass a different (or empty) list to exercise
 *  the 'closed' state. */
function stubFetchReady(enabledIds: string[] = ['mrg-042']) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
        return { ok: true, text: async () => VALID_PEM } as Response;
      }
      if (String(url).endsWith('/survey-status.json')) {
        return { ok: true, json: async () => enabledIds } as Response;
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
    stubFetchReady();
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
    stubFetchReady();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });

    const text = document.body.textContent ?? '';
    expect(text).toMatch(/recorded as present/i);
    expect(text).toMatch(/same key.*your registration/i);
    // Minor 3 (fix round 2): pins the claim, not only the number --
    // before this, only `/90 days/` was asserted, so weakening the
    // sentence to "Answers are kept for 90 days" (dropping "destroyed
    // together with the event's key," the actual mechanism task 15's own
    // retention sweep implements) left this test green.
    expect(text).toMatch(/destroyed together with the event.s key 90 days after the event/i);
    expect(text).toContain('reading-group@example.test');
  });

  it('R-38: states the answers are anonymous, and why nothing can be individually shown, corrected or erased', async () => {
    // Critical 1 (fix round 1): the notice used to promise access,
    // correction and erasure "before that date" -- structurally false for
    // an anonymous response. It must now say the opposite, and say why.
    stubFetchReady();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });

    const text = document.body.textContent ?? '';
    expect(text).toMatch(/anonymous/i);
    expect(text).toMatch(/cannot find your own answers/i);
    expect(text).not.toMatch(/access, correct or erase your data/i);
  });

  it('R-38: warns against writing identifying content into the free-text box, both in the notice and beside the field itself', async () => {
    stubFetchReady();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });

    const text = document.body.textContent ?? '';
    // Twice: once in the notice, once right beside the textarea -- the
    // second occurrence is the one Critical 1 named as missing entirely.
    const matches = text.match(/do not (write|include) your name/gi) ?? [];
    expect(matches.length).toBeGreaterThanOrEqual(2);
  });
});

describe('SurveyForm -- what it asks, and nothing else', () => {
  it('asks a five-point rating, a yes/no recommendation, and optional free-text feedback', async () => {
    stubFetchReady();
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
    stubFetchReady();

    renderSurvey('mrg-042');
    await screen.findByRole('group', { name: /rate this session overall/i });

    const calls = vi.mocked(fetch).mock.calls.map(c => String(c[0]));
    expect(calls.some(u => /\/keys\/events\/mrg-042\.pub$/.test(u))).toBe(true);
  });

  it('fetches survey-status.json before rendering the form -- R-37', async () => {
    stubFetchReady();

    renderSurvey('mrg-042');
    await screen.findByRole('group', { name: /rate this session overall/i });

    const calls = vi.mocked(fetch).mock.calls.map(c => String(c[0]));
    expect(calls.some(u => u.endsWith('/survey-status.json'))).toBe(true);
  });

  it('requests exactly BASE/survey-status.json, not merely a URL ending in that filename (R-42, fix round 2)', async () => {
    // R-42: a suffix-only match here is exactly what let SurveyForm.tsx's
    // own fetch URL drift while every test in this file (including the
    // one just above) stayed green -- `${BASE}/data/survey-status.json`
    // still ends in "/survey-status.json", and the round proved
    // `surveyStatusUrl` pointed at an arbitrary third-party origin passed
    // too. Exact equality against BASE, independently recomputed rather
    // than imported from SurveyForm.tsx, actually pins the whole URL, not
    // only the leaf filename.
    stubFetchReady();

    renderSurvey('mrg-042');
    await screen.findByRole('group', { name: /rate this session overall/i });

    const calls = vi.mocked(fetch).mock.calls.map(c => String(c[0]));
    const base = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
    expect(calls).toContain(`${base}/${SURVEY_STATUS_FILENAME}`);
  });

  it('the submit button starts disabled until both required questions are answered', async () => {
    stubFetchReady();
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

  it('Important 3: the free-text box refuses more than 2000 characters, with a visible counter', async () => {
    stubFetchReady();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });

    const textarea = screen.getByLabelText(
      /anything else you would like to tell us/i,
    ) as HTMLTextAreaElement;
    expect(textarea.maxLength).toBe(2000);

    fireEvent.change(textarea, { target: { value: 'x'.repeat(2500) } });
    // A real browser enforces `maxLength` at the DOM level on user typing;
    // `fireEvent.change` bypasses that and sets the value directly, so
    // this asserts the *attribute* is correct (what actually stops a real
    // participant) rather than re-deriving jsdom's own enforcement.
    expect(textarea.maxLength).toBe(2000);

    fireEvent.change(textarea, { target: { value: 'a short answer' } });
    expect(screen.getByText('14 / 2000')).toBeInTheDocument();
  });
});

describe('SurveyForm -- the public key cannot be fetched', () => {
  it('refuses to send, says so, and never asks for anything to send in the clear', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 }) as Response));
    renderSurvey();

    await screen.findByText(/this survey is not available right now/i);

    expect(screen.queryByRole('group', { name: /rate this session overall/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument();
  });
});

describe('SurveyForm -- R-37: the survey switch, checked at the page layer', () => {
  it('renders a closed message, never the form, when the event is not in survey-status.json', async () => {
    stubFetchReady([]); // key is fine; nothing is enabled
    renderSurvey('mrg-042');

    await screen.findByText(/this survey is not open/i);
    expect(screen.queryByRole('group', { name: /rate this session overall/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument();
  });

  it('renders a closed message when survey-status.json fetch fails outright -- fail closed, not open', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        if (String(url).endsWith('/survey-status.json')) {
          return { ok: false, status: 500 } as Response;
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );
    renderSurvey('mrg-042');

    await screen.findByText(/this survey is not open/i);
  });

  it('renders a closed message when survey-status.json is not a JSON array -- fail closed, not open', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        if (String(url).endsWith('/survey-status.json')) {
          return { ok: true, json: async () => ({ 'mrg-042': true }) } as Response;
        }
        throw new Error(`unexpected fetch in test: ${url}`);
      }),
    );
    renderSurvey('mrg-042');

    await screen.findByText(/this survey is not open/i);
  });

  it('renders the form when the event is in survey-status.json', async () => {
    stubFetchReady(['mrg-041', 'mrg-042', 'mrg-043']);
    renderSurvey('mrg-042');

    await screen.findByRole('group', { name: /rate this session overall/i });
  });

  it('a different event\'s presence in survey-status.json does not enable this one', async () => {
    stubFetchReady(['mrg-999']);
    renderSurvey('mrg-042');

    await screen.findByText(/this survey is not open/i);
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
        if (String(url).endsWith('/survey-status.json')) {
          return { ok: true, json: async () => ['mrg-042'] } as Response;
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
        if (String(url).endsWith('/survey-status.json')) {
          return { ok: true, json: async () => ['mrg-042'] } as Response;
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
        if (String(url).endsWith('/survey-status.json')) {
          return { ok: true, json: async () => ['mrg-042'] } as Response;
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

  it('when the relay is not configured, says submitting is not available yet -- distinct wording from the closed-survey message', async () => {
    stubFetchReady();
    renderSurvey('mrg-042');
    await answer();
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    await screen.findByText(/submitting answers is not available yet/i);
    // Minor 7: must not read the same as the 'closed' state's own message,
    // which would tell a participant whose survey *is* open to give up.
    expect(screen.queryByText(/this survey is not open$/i)).not.toBeInTheDocument();
  });

  it('reports a relay error without pretending the answers were sent, and keeps what was answered', async () => {
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).match(/\/keys\/events\/.+\.pub$/)) {
          return { ok: true, text: async () => VALID_PEM } as Response;
        }
        if (String(url).endsWith('/survey-status.json')) {
          return { ok: true, json: async () => ['mrg-042'] } as Response;
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

  it('R-40: an answer that would overflow the pad target once encrypted is refused cleanly, not an unhandled crash', async () => {
    // `maxLength` on the real textarea caps this in the browser, but
    // `fireEvent.change` sets the DOM value directly the same way an
    // adversarial or buggy caller bypassing that attribute would --
    // exactly the "if this ever got past the character cap" scenario
    // `survey.py`'s own equivalent test (`test_to_survey_response_
    // refuses_rather_than_lets_pad_raise`) simulates on the Python side.
    // `padPlaintext` (encrypt.ts) throws when this happens; the point of
    // this test is that `submit`'s own try/catch turns that throw into
    // the same clean, existing error state a relay failure produces --
    // never an uncaught exception reaching React.
    stubFetchReady();
    renderSurvey('mrg-042');
    const ratingGroup = await screen.findByRole('group', { name: /rate this session overall/i });
    fireEvent.click(within(ratingGroup).getAllByRole('radio')[4]); // 5
    const recommendGroup = screen.getByRole('group', { name: /recommend this series/i });
    fireEvent.click(within(recommendGroup).getByRole('radio', { name: 'Yes' }));
    fireEvent.change(screen.getByLabelText(/anything else you would like to tell us/i), {
      // 2100 emoji at 4 UTF-8 bytes each = 8400 bytes alone, already past
      // PLAINTEXT_PAD_BYTES (8192) before the JSON envelope around it.
      target: { value: '\u{1F600}'.repeat(2100) },
    });

    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    await screen.findByText(/could not be encrypted/i);
    expect(screen.queryByText(/your answers have been sent/i)).not.toBeInTheDocument();
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
    stubFetchReady();
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
    stubFetchReady();
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
        if (u.endsWith('/survey-status.json')) {
          return { ok: true, json: async () => ['mrg-042', 'mrg-043'] } as Response;
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
