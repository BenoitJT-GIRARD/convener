import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AuthProvider } from '../src/auth/AuthContext';
import { Login } from '../src/auth/Login';

describe('Login -- token strategy (default, nothing configured)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    localStorage.clear();
  });

  it('explains why the token path is active', () => {
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    expect(
      screen.getByText(/Sign-in with a short code is not configured yet/),
    ).toBeInTheDocument();
  });

  it('shows an error when the token is rejected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.change(screen.getByPlaceholderText('github_pat_...'), {
      target: { value: 'bad-token' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }));
    await waitFor(() => expect(screen.getByText(/did not work/)).toBeInTheDocument());
  });

  it('signs in successfully, keeping the access token out of localStorage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'alice' }) }),
    );
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.change(screen.getByPlaceholderText('github_pat_...'), {
      target: { value: 'good-token' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }));
    await waitFor(() => expect(screen.queryByText(/did not work/)).not.toBeInTheDocument());
    expect(localStorage.getItem('convener.token')).toBeNull();
    expect(localStorage.getItem('convener.refresh')).toBeNull();
  });

  it('activates demo mode and reloads when the demo button is clicked', () => {
    const reloadSpy = vi.fn();
    // jsdom's `window.location` is neither writable nor deletable, and its
    // `reload` is non-configurable, so the whole object is swapped for a
    // stand-in through defineProperty and put back at the end of the test.
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { ...originalLocation, reload: reloadSpy },
    });

    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /View a live demo/ }));
    expect(localStorage.getItem('convener.demo')).toBe('1');
    expect(reloadSpy).toHaveBeenCalled();

    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
  });
});

describe('Login -- device strategy (relay fully configured)', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    localStorage.clear();
    vi.stubEnv('VITE_AUTH_PROXY_URL', 'https://relay.example');
    vi.stubEnv('VITE_GITHUB_APP_CLIENT_ID', 'Iv1.abc');
  });

  function stubFetch(oauthResponse: () => { ok: boolean; json?: () => Promise<unknown> }) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const href = String(url);
        if (href.includes('/login/device/code')) {
          return {
            ok: true,
            json: async () => ({
              device_code: 'devcode',
              user_code: 'WDJB-MJHT',
              verification_uri: 'https://github.com/login/device',
              interval: 0,
              expires_in: 900,
            }),
          };
        }
        if (href.includes('/login/oauth/access_token')) {
          return oauthResponse();
        }
        // GitHub /user, for validateToken.
        return { ok: true, json: async () => ({ login: 'grace' }) };
      }),
    );
  }

  it('shows the "sign in with GitHub" button, not the token form', () => {
    vi.stubGlobal('fetch', vi.fn());
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    expect(screen.getByRole('button', { name: /Sign in with GitHub/ })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('github_pat_...')).not.toBeInTheDocument();
  });

  it('walks the happy path: shows the code, then completes sign-in', async () => {
    stubFetch(() => ({ ok: true, json: async () => ({ access_token: 'acc1' }) }));
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Sign in with GitHub/ }));
    await waitFor(() => expect(screen.getByText('WDJB-MJHT')).toBeInTheDocument());
    // No error surfaces once the token exchange completes successfully.
    await waitFor(() => expect(screen.queryByText(/failed/)).not.toBeInTheDocument());
  });

  it('opens the verification URL in a new tab', async () => {
    stubFetch(() => ({ ok: true, json: async () => ({ access_token: 'acc1' }) }));
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Sign in with GitHub/ }));
    await waitFor(() => expect(screen.getByText('WDJB-MJHT')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Open GitHub/ }));
    expect(openSpy).toHaveBeenCalledWith(
      'https://github.com/login/device',
      '_blank',
      'noopener,noreferrer',
    );
  });

  it('surfaces the DeviceFlowError message verbatim and allows starting again', async () => {
    stubFetch(() => ({ ok: true, json: async () => ({ error: 'access_denied' }) }));
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Sign in with GitHub/ }));
    await waitFor(() =>
      expect(screen.getByText('Sign-in was refused on GitHub.')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /Start again/ }));
    expect(screen.getByRole('button', { name: /Sign in with GitHub/ })).toBeInTheDocument();
  });

  it('surfaces an error when GitHub issues a token but it is then rejected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const href = String(url);
        if (href.includes('/login/device/code')) {
          return {
            ok: true,
            json: async () => ({
              device_code: 'devcode',
              user_code: 'WDJB-MJHT',
              verification_uri: 'https://github.com/login/device',
              interval: 0,
              expires_in: 900,
            }),
          };
        }
        if (href.includes('/login/oauth/access_token')) {
          return { ok: true, json: async () => ({ access_token: 'acc1' }) };
        }
        // GitHub /user rejects the freshly issued token.
        return { ok: false };
      }),
    );
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Sign in with GitHub/ }));
    await waitFor(() =>
      expect(screen.getByText(/token was rejected/)).toBeInTheDocument(),
    );
  });

  it('surfaces an error when the device code request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Sign in with GitHub/ }));
    await waitFor(() =>
      expect(
        screen.getByText(/Could not reach GitHub/),
      ).toBeInTheDocument(),
    );
  });
});
