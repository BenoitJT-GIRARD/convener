import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { SurveyForm } from '../../src/islands/survey/SurveyForm';
import { SURVEY_STATUS_FILENAME } from '../../src/survey/surveyStatus';
import cases from '../../../tools/tests/fixtures/governance-cases.json';

// This suite replaces `survey-form.test.tsx`, which tested
// `app/src/survey/SurveyForm.tsx` (the operators' application's own
// `/survey/:eventId` route -- see git history). The form is now
// `app/src/islands/survey/SurveyForm.tsx`, an island with no router of its
// own: `eventId` is a plain prop here, not a `useParams` read, so every
// test below renders the component directly rather than through a
// `MemoryRouter`. Remount-by-event-id discipline moved to its own file,
// `survey-island-mount.test.tsx`, which exercises `main.tsx::
// mountSurveyIsland` -- the thing that actually applies `key={eventId}`
// now that `App.tsx`'s former `SurveyRoute` no longer exists to do it.
//
// The data-protection notice suite (`SurveyForm -- the notice`, in the
// old file) is gone too, not merely moved: that text no longer renders
// from this component at all (see `SurveyForm.tsx`'s own module comment)
// -- `tools/tests/repository/test_site.py` already covers the static copy
// `site/src/survey.njk` carries instead.

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
  // The plaintext is padded with trailing zero bytes to a fixed
  // size before encryption (see encrypt.ts::padPlaintext) -- everything
  // up to the first 0x00 is the real JSON, the same unpad
  // `survey-encrypt.test.ts::unpadPlaintext` performs.
  const bytes = new Uint8Array(plaintext);
  const end = bytes.indexOf(0);
  const unpadded = end === -1 ? bytes : bytes.slice(0, end);
  return JSON.parse(new TextDecoder().decode(unpadded));
}

function renderSurvey(eventId: string | undefined = 'mrg-042') {
  return render(<SurveyForm eventId={eventId} />);
}

/** Stubs both fetches `SurveyForm` makes before it can render a form: the
 *  event's public key, and the `survey-status.json` membership
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

// Regression guard for the extraction itself: `site/src/survey.njk` now
// renders the data-protection notice as static HTML ahead of this
// island's own mount point (see SurveyForm.tsx's module comment). If this
// component ever grew that text back, a built survey page would show it
// twice -- the same guard `signup-island.test.tsx` keeps for registration.
describe('SurveyForm -- does not duplicate the survey page\'s own notice', () => {
  it('renders no copy of the "before you answer" data-protection notice', async () => {
    stubFetchReady();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });

    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/before you answer/i);
    expect(text).not.toMatch(/90 days/);
    expect(text).not.toMatch(/recorded as present/i);
  });

  it('renders no copy of the notice even while the key is loading or unavailable', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 }) as Response));
    renderSurvey();
    expect(screen.queryByText(/before you answer/i)).not.toBeInTheDocument();
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

  it('warns against writing identifying content beside the free-text field', async () => {
    stubFetchReady();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });

    expect(screen.getByText(/do not include your name, email address/i)).toBeInTheDocument();
  });

  it('fetches the event public key from the event-scoped, same-origin path -- the same key registration uses', async () => {
    stubFetchReady();

    renderSurvey('mrg-042');
    await screen.findByRole('group', { name: /rate this session overall/i });

    const calls = vi.mocked(fetch).mock.calls.map(c => String(c[0]));
    expect(calls.some(u => /\/keys\/events\/mrg-042\.pub$/.test(u))).toBe(true);
  });

  it('fetches survey-status.json before rendering the form', async () => {
    stubFetchReady();

    renderSurvey('mrg-042');
    await screen.findByRole('group', { name: /rate this session overall/i });

    const calls = vi.mocked(fetch).mock.calls.map(c => String(c[0]));
    expect(calls.some(u => u.endsWith('/survey-status.json'))).toBe(true);
  });

  it('requests exactly BASE/survey-status.json, not merely a URL ending in that filename', async () => {
    // A suffix-only match here is exactly what let SurveyForm.tsx's
    // own fetch URL drift while every test in this file (including the
    // one just above) stayed green -- `${BASE}/data/survey-status.json`
    // still ends in "/survey-status.json", and a review proved
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

  it('the free-text box refuses more than 2000 characters, with a visible counter', async () => {
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

    expect(
      screen.queryByRole('group', { name: /rate this session overall/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument();
  });
});

describe('SurveyForm -- the survey switch, checked at the page layer', () => {
  it('renders a closed message, never the form, when the event is not in survey-status.json', async () => {
    stubFetchReady([]); // key is fine; nothing is enabled
    renderSurvey('mrg-042');

    await screen.findByText(/this survey is not open/i);
    expect(
      screen.queryByRole('group', { name: /rate this session overall/i }),
    ).not.toBeInTheDocument();
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

  it("a different event's presence in survey-status.json does not enable this one", async () => {
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
    // Distinct wording from the 'closed' state's own message, which would
    // tell a participant whose survey *is* open to give up.
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

  it('an answer that would overflow the pad target once encrypted is refused cleanly, not an unhandled crash', async () => {
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
  it('treats a missing eventId prop as an unavailable key rather than crashing', async () => {
    render(<SurveyForm />);
    await screen.findByText(/this survey is not available right now/i);
  });
});

// Sanity check that this component alone -- with no AuthProvider and no
// DataProvider in the tree at all -- is the proof that it needs neither: a
// screen requiring one would fail to render, not silently omit it.
describe('SurveyForm -- needs no organiser account', () => {
  it('renders without AuthProvider or DataProvider in the tree', async () => {
    stubFetchReady();
    renderSurvey();
    await screen.findByRole('group', { name: /rate this session overall/i });
    expect(within(document.body).queryByText(/sign in/i)).not.toBeInTheDocument();
  });
});
