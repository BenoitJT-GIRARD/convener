import { describe, it, expect, vi, beforeEach } from 'vitest';
import { detectRole } from '../src/auth/role';
import type { Config } from '../src/data/types';

const cfg: Config = {
  season: 2026,
  vw_counter: 1,
  vote_threshold: 3,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board_members: ['alice'],
};

describe('detectRole', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns board when GitHub team membership is active', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ state: 'active' }),
      }),
    );
    expect(await detectRole('alice', 'tok', cfg)).toBe('board');
  });

  it('returns organizer when team API returns 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    expect(await detectRole('bob', 'tok', cfg)).toBe('organizer');
  });

  it('returns organizer for a pending membership', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: 'pending' }) }),
    );
    expect(await detectRole('alice', 'tok', cfg)).toBe('organizer');
  });

  it('returns organizer on a 404 for a login that is in board_members -- the API wins', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    // 'alice' is in cfg.board_members, but the API gave an authoritative no.
    expect(await detectRole('alice', 'tok', cfg)).toBe('organizer');
  });

  it('falls back to config when fetch throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
    expect(await detectRole('alice', 'tok', cfg)).toBe('board');
    expect(await detectRole('bob', 'tok', cfg)).toBe('organizer');
  });

  it('returns organizer when no config + fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
    expect(await detectRole('alice', 'tok', null)).toBe('organizer');
  });
});
