import { describe, it, expect, vi, beforeEach } from 'vitest';
import { validateToken } from '../../src/auth/api';

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
