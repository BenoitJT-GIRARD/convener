import { describe, it, expect, vi, beforeEach } from 'vitest';
import { checkToken, validateToken } from '../../src/auth/api';

describe('validateToken', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the login when the token is valid', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ login: 'alice' }) }),
    );
    expect(await validateToken('tok')).toEqual({ login: 'alice' });
  });

  it('returns null when the token is rejected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    expect(await validateToken('bad')).toBeNull();
  });

  it('returns null, not a rejected promise, when the network fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fail')));
    await expect(validateToken('tok')).resolves.toBeNull();
  });
});

describe('checkToken', () => {
  const answer = (init: { ok: boolean; status?: number; login?: string }) =>
    vi.fn().mockResolvedValue({
      ok: init.ok,
      status: init.status ?? (init.ok ? 200 : 401),
      json: async () => ({ login: init.login ?? 'alice' }),
    });

  it('reads a good token as valid, with the login', async () => {
    vi.stubGlobal('fetch', answer({ ok: true, login: 'alice' }));
    expect(await checkToken('t')).toEqual({ outcome: 'valid', login: 'alice' });
  });

  it('reads a 401 as a refusal, which is an answer about the token', async () => {
    vi.stubGlobal('fetch', answer({ ok: false, status: 401 }));
    expect(await checkToken('t')).toEqual({ outcome: 'refused' });
  });

  it('reads a 502 as unreachable, because it is an answer about GitHub', async () => {
    // The distinction the caller in `AuthContext` turns into whether a
    // volunteer keeps their session. GitHub answering that it cannot answer
    // says nothing about the token, and treating it as a refusal signs
    // somebody out of a working session during an incident.
    vi.stubGlobal('fetch', answer({ ok: false, status: 502 }));
    expect(await checkToken('t')).toEqual({ outcome: 'unreachable' });
  });

  it('reads a rejected request as unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    expect(await checkToken('t')).toEqual({ outcome: 'unreachable' });
  });

  it('still collapses all three for validateToken, whose callers want that', async () => {
    vi.stubGlobal('fetch', answer({ ok: false, status: 502 }));
    expect(await validateToken('t')).toBeNull();
    vi.stubGlobal('fetch', answer({ ok: true, login: 'alice' }));
    expect(await validateToken('t')).toEqual({ login: 'alice' });
  });
});
