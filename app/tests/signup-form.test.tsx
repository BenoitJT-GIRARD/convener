import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SignupForm } from '../src/signup/SignupForm';

const VALID_PEM = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2q9C/nOAfN0W7tQYWCpg
sYcPH+nFDiMCILfIv5cnifwiufU4sT7xdoVtHYz2WOrHyWTeMr+DPW+UUqdXZ81N
hcohxPhg1oGg/xsk4lQcAEMk4QlrH0ZG29aM0QDuSfdk+3Kssda+k0cnc809ZmXx
8fUasGWNFUZey+KOpwqljGSKBj62Ws5htQuZbLIJI7aY+c4iX+He+y5Flez+D1dW
ZswiFANLZaoefye8BS6hdhTrZ2fbf1u5lRIa6Q8XTQoEdLyUkYaIgR616KM4ay3m
CmViYCB+8zbeKvNwDGihEGDxzdewbP6DIT3fNq/fkybvcKPciybTpvDYxkZJbeq0
nwIDAQAB
-----END PUBLIC KEY-----
`;

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

  it('when the relay is configured, sends only the encrypted envelope -- never the plaintext -- and confirms', async () => {
    vi.stubEnv('VITE_SIGNUP_RELAY_URL', 'https://signup-relay.example/');
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
    // The property the whole design rests on, checked again at the wire:
    // nothing recognisable about the participant appears in what actually
    // left the browser.
    expect(calls[0].body).not.toContain('Ada');
    expect(calls[0].body).not.toContain('Lovelace');
    expect(calls[0].body).not.toContain('ada@example.org');
    expect(calls[0].body).not.toContain('Analytical Engines Institute');
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

  it('reports a relay error without pretending the registration was sent', async () => {
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
// screen requiring one would fail to render, not silently omit it.
describe('SignupForm -- needs no organiser account', () => {
  it('renders without AuthProvider or DataProvider in the tree', async () => {
    stubKeyFetchOk();
    renderSignup();
    await screen.findByLabelText(/first name/i);
    expect(within(document.body).queryByText(/sign in/i)).not.toBeInTheDocument();
  });
});
