import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../src/auth/AuthContext';

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    localStorage.clear();
  });

  it('starts ready with no session when there is no stored token', () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    expect(result.current).toMatchObject({ token: null, login: null, ready: true });
  });

  it('starts in demo mode when the demo flag is set', () => {
    localStorage.setItem('convener.demo', '1');
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    expect(result.current).toMatchObject({ token: 'demo', login: 'demo', ready: true });
  });

  it('validates a stored legacy token on mount and clears it if invalid', async () => {
    localStorage.setItem('convener.token', 'stale');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    expect(result.current.ready).toBe(false);
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem('convener.token')).toBeNull();
  });

  it('validates a stored legacy token on mount, keeps it in memory, and removes the legacy key', async () => {
    localStorage.setItem('convener.token', 'good');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'alice' }) }),
    );
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current).toMatchObject({ token: 'good', login: 'alice', ready: true });
    // The legacy key is read once and deleted -- never written back.
    expect(localStorage.getItem('convener.token')).toBeNull();
  });

  it('exchanges a stored refresh token for a fresh access token on startup', async () => {
    vi.stubEnv('VITE_AUTH_PROXY_URL', 'https://relay.example');
    vi.stubEnv('VITE_GITHUB_APP_CLIENT_ID', 'Iv1.abc');
    localStorage.setItem('convener.refresh', 'rt1');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/login/oauth/access_token')) {
          return {
            ok: true,
            json: async () => ({ access_token: 'at1', refresh_token: 'rt2' }),
          };
        }
        return { ok: true, json: async () => ({ login: 'dora' }) };
      }),
    );
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    expect(result.current.ready).toBe(false);
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current).toMatchObject({ token: 'at1', login: 'dora', ready: true });
    expect(localStorage.getItem('convener.refresh')).toBe('rt2');
    // The access token never lands in localStorage.
    expect(localStorage.getItem('convener.token')).toBeNull();
  });

  it('clears the refresh token when the exchange fails', async () => {
    vi.stubEnv('VITE_AUTH_PROXY_URL', 'https://relay.example');
    vi.stubEnv('VITE_GITHUB_APP_CLIENT_ID', 'Iv1.abc');
    localStorage.setItem('convener.refresh', 'rt1');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem('convener.refresh')).toBeNull();
  });

  it('drops a stale refresh token when the device flow is not configured', async () => {
    localStorage.setItem('convener.refresh', 'rt1');
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem('convener.refresh')).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('signIn keeps the token in memory only and returns true on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'bob' }) }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    let ok = false;
    await act(async () => {
      ok = await result.current.signIn('newtok');
    });
    expect(ok).toBe(true);
    expect(result.current.token).toBe('newtok');
    expect(localStorage.getItem('convener.token')).toBeNull();
    expect(localStorage.getItem('convener.refresh')).toBeNull();
  });

  it('signIn returns false and does not persist on rejection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    let ok = true;
    await act(async () => {
      ok = await result.current.signIn('badtok');
    });
    expect(ok).toBe(false);
    expect(localStorage.getItem('convener.token')).toBeNull();
  });

  it('signInWithTokens stores the refresh token and keeps the access token in memory', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'grace' }) }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    let ok = false;
    await act(async () => {
      ok = await result.current.signInWithTokens('acc1', 'ref1');
    });
    expect(ok).toBe(true);
    expect(result.current).toMatchObject({ token: 'acc1', login: 'grace' });
    expect(localStorage.getItem('convener.refresh')).toBe('ref1');
    expect(localStorage.getItem('convener.token')).toBeNull();
  });

  it('signInWithTokens returns false when the access token is rejected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    let ok = true;
    await act(async () => {
      ok = await result.current.signInWithTokens('bad');
    });
    expect(ok).toBe(false);
  });

  it('signOut clears the token, refresh token, and demo flag', async () => {
    localStorage.setItem('convener.demo', '1');
    localStorage.setItem('convener.refresh', 'ref1');
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    act(() => result.current.signOut());
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem('convener.demo')).toBeNull();
    expect(localStorage.getItem('convener.refresh')).toBeNull();
  });

  it('useAuth throws when used outside a provider', () => {
    expect(() => renderHook(() => useAuth())).toThrow(/outside provider/);
  });
});
