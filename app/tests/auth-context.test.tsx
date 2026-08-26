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
    // `example-alba`: demo mode signs the visitor in
    // as a member of the example instance's own board, because a login that
    // board does not hold is refused by every transition (see
    // `src/data/demo.ts`'s own `DEMO_USER`).
    expect(result.current).toMatchObject({
      token: 'demo',
      login: 'example-alba',
      ready: true,
    });
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

  it('reaches a terminal ready state, with a message, when validating the legacy token fails on the network', async () => {
    localStorage.setItem('convener.token', 'stale');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fail')));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    expect(result.current.ready).toBe(false);
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBeNull();
    expect(result.current.startupError).toMatch(/sign in again/i);
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

  it('signIn returns false, not a rejected promise, when the network fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fail')));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    let ok = true;
    await act(async () => {
      ok = await result.current.signIn('newtok');
    });
    expect(ok).toBe(false);
  });

  it('signInWithTokens keeps the access token in memory on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'grace' }) }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    let ok = false;
    await act(async () => {
      ok = await result.current.signInWithTokens('acc1');
    });
    expect(ok).toBe(true);
    expect(result.current).toMatchObject({ token: 'acc1', login: 'grace' });
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

  it('signInWithTokens returns false, not a rejected promise, when the network fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fail')));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    let ok = true;
    await act(async () => {
      ok = await result.current.signInWithTokens('acc1');
    });
    expect(ok).toBe(false);
  });

  it('signOut clears the token and demo flag', async () => {
    localStorage.setItem('convener.demo', '1');
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    act(() => result.current.signOut());
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem('convener.demo')).toBeNull();
  });

  it('useAuth throws when used outside a provider', () => {
    expect(() => renderHook(() => useAuth())).toThrow(/outside provider/);
  });
});
