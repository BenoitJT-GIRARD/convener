import { describe, it, expect, vi, beforeEach } from 'vitest';
import { detectRole } from '../src/auth/role';
import type { Config } from '../src/data/types';

const cfg: Config = {
  season: 2026,
  vw_counter: 1,
  vote_threshold: 3,
  overlap_window_days: 7,
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
