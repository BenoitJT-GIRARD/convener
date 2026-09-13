import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../src/auth/AuthContext';

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    localStorage.clear();
    sessionStorage.clear();
  });

  const SESSION = 'convener.session';
  const ok = (login = 'alice') =>
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login }) });

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
    // Not "sign in again", which this used to say. Nothing has been
    // established about the token -- the check itself never got an answer --
    // and the sentence now claims only that, with the step that fixes it
    // most often. `friendlyError` draws the same line for every other call
    // this application makes.
    expect(result.current.startupError).toMatch(/could not reach github/i);
    expect(result.current.startupError).toMatch(/connection/i);
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

  // ---------------------------------------------------------------- //
  // What a session survives.
  // ---------------------------------------------------------------- //

  it('picks a stored session up on mount, so a reload is not a device flow', async () => {
    // The whole of the report, in one reading: an operator wrote that
    // refreshing, leaving or going back signed them out and made them do the
    // GitHub code again. The token lived in React state and nowhere else.
    sessionStorage.setItem(SESSION, 'live');
    vi.stubGlobal('fetch', ok());
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    // Not a sign-in screen for even one frame: `ready` is false while the
    // stored token is checked, which renders a spinner rather than the
    // device-code prompt.
    expect(result.current.ready).toBe(false);
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current).toMatchObject({ token: 'live', login: 'alice' });
  });

  it('keeps the session after a sign-in, which is what makes the next reload free', async () => {
    vi.stubGlobal('fetch', ok());
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));

    await act(async () => {
      await result.current.signInWithTokens('fresh');
    });

    expect(sessionStorage.getItem(SESSION)).toBe('fresh');
  });

  it('forgets the session on sign-out', async () => {
    sessionStorage.setItem(SESSION, 'live');
    vi.stubGlobal('fetch', ok());
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));

    act(() => result.current.signOut());

    expect(sessionStorage.getItem(SESSION)).toBeNull();
    expect(result.current.token).toBeNull();
  });

  it('forgets a session GitHub refuses', async () => {
    // An answer: the token is no good, and keeping it would show a spinner
    // and then a sign-out message on every reload for as long as the tab is
    // open.
    sessionStorage.setItem(SESSION, 'revoked');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBeNull();
    expect(sessionStorage.getItem(SESSION)).toBeNull();
  });

  it('keeps a session it could not check, because nothing was established', async () => {
    // Not an answer. Throwing the session away on a moment of bad network
    // would charge a volunteer a full device flow for something that fixed
    // itself, which is the exact cost this change exists to stop paying.
    sessionStorage.setItem(SESSION, 'live');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.startupError).toMatch(/could not reach github/i);
    expect(sessionStorage.getItem(SESSION)).toBe('live');
  });

  it('migrates the legacy key into the session and still deletes it', async () => {
    localStorage.setItem('convener.token', 'good');
    vi.stubGlobal('fetch', ok());
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBe('good');
    expect(localStorage.getItem('convener.token')).toBeNull();
    expect(sessionStorage.getItem(SESSION)).toBe('good');
  });

  it('signs in normally when the storage itself throws', async () => {
    // A private window, blocked site data, a full quota: the accessor throws
    // rather than returning null. A sign-in screen that crashes because it
    // could not write a convenience is worse than one that asks for the code
    // again next time.
    const broken = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
      removeItem: () => {
        throw new Error('blocked');
      },
    };
    vi.stubGlobal('sessionStorage', broken);
    vi.stubGlobal('fetch', ok());
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.ready).toBe(true));

    await act(async () => {
      expect(await result.current.signInWithTokens('fresh')).toBe(true);
    });
    expect(result.current).toMatchObject({ token: 'fresh', login: 'alice' });
  });

  it('keeps the session through a GitHub outage, which is not a refusal', async () => {
    // Written on a day GitHub was returning 5xx from its authorization
    // endpoints. Signing every volunteer out of a working session because the
    // service could not answer is the opposite of what the session is for.
    sessionStorage.setItem(SESSION, 'live');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(sessionStorage.getItem(SESSION)).toBe('live');
    expect(result.current.startupError).toMatch(/could not reach github/i);
  });
});
