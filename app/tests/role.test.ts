import { describe, it, expect, vi, beforeEach } from 'vitest';
import { detectRole } from '../src/auth/role';
import type { Config } from '../src/data/types';

const cfg: Config = {
  season: 2026,
  next_edition_number: 1,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  eligibility_share: 0.6666666666666666,
  board: [{ login: 'alice', joined_on: '2024-01-01', status: 'active', unavailable_until: '' }],
  nominations: [],
  board_min: 3,
  board_max: 9,
  vote_window_days: 10,
  objection_window_working_days: 5,
  inactivity_months: 6,
  balance_window_months: 12,
  view_count_window_days: 30,
  sla_days: {
    invitation_follow_up: 7,
    summary_after_delivery: 5,
    recording_after_delivery: 10,
  },
  channels: [],
  instructions: '',
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

  it('returns organizer on a 404 for a login on the active board -- the API wins', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    // 'alice' is on cfg.board, but the API gave an authoritative no.
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
