import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../src/auth/AuthContext';

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
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

  it('validates a stored token on mount and clears it if invalid', async () => {
    localStorage.setItem('convener.token', 'stale');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    expect(result.current.ready).toBe(false);
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBeNull();
  });

  it('validates a stored token on mount and keeps it if valid', async () => {
    localStorage.setItem('convener.token', 'good');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'alice' }) }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current).toMatchObject({ token: 'good', login: 'alice', ready: true });
  });

  it('signIn stores the token and returns true on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'bob' }) }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));
    let ok = false;
    await act(async () => {
      ok = await result.current.signIn('newtok');
    });
    expect(ok).toBe(true);
    expect(result.current.token).toBe('newtok');
    expect(localStorage.getItem('convener.token')).toBe('newtok');
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
