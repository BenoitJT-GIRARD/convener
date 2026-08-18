import { describe, expect, it } from 'vitest';
import { activeBoard, assignLead, coHostedCount, isBoardMember } from '../src/state/board';
import type { BoardMember, Config, Speaker } from '../src/data/types';
import cases from '../../tools/tests/fixtures/governance-cases.json';

function member(overrides: Partial<BoardMember> = {}): BoardMember {
  return {
    login: 'alice',
    joined_on: '2024-01-01',
    status: 'active',
    unavailable_until: '',
    ...overrides,
  };
}

function config(board: BoardMember[]): Config {
  return {
    season: 2026,
    vw_counter: 1,
    overlap_window_days: 7,
    seminar_duration_minutes: 90,
    board,
    nominations: [],
    board_min: 3,
    board_max: 9,
    vote_window_days: 10,
    objection_window_working_days: 5,
    inactivity_months: 6,
    balance_window_months: 12,
    sla_days: {
      lead_decision: 14,
      invitation_follow_up: 7,
      summary_after_delivery: 5,
      recording_after_delivery: 10,
    },
  };
}

function speaker(overrides: Partial<Speaker> = {}): Speaker {
  return {
    id: 'spk-001',
    name: 'A',
    gender: 'undisclosed',
    career_stage: 'undisclosed',
    email: '',
    affiliation: '',
    country: '',
    title: '',
    abstract: '',
    conflicts_of_interest: '',
    source: 'organizer',
    proposed_by: '',
    links: [],
    host_1: '',
    host_2: '',
    status: 'lead',
    selection: { ballots: [], opened_on: '', decided_on: '' },
    publication: {
      consent: 'pending',
      approved_by: '',
      approved_on: '',
      objections: [],
      outcome: '',
    },
    edition_code: '',
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    metrics: {
      registrations: null,
      live_peak: null,
      youtube_views_30d: null,
      forum_replies: null,
    },
    notes: '',
    ...overrides,
  };
}

describe('activeBoard', () => {
  it('excludes an inactive member entirely', () => {
    const cfg = config([member({ login: 'alice', status: 'active' }), member({ login: 'bob', status: 'inactive' })]);
    const board = activeBoard(cfg, '2026-08-18');
    expect(board.logins).toEqual(['alice']);
  });

  it('lists a member whose unavailable_until is a future date as unavailable', () => {
    const cfg = config([member({ login: 'alice', unavailable_until: '2026-09-01' })]);
    const board = activeBoard(cfg, '2026-08-18');
    expect(board.unavailable).toEqual(['alice']);
  });

  it('treats unavailable_until as inclusive: the member is still unavailable on that exact day', () => {
    const cfg = config([member({ login: 'alice', unavailable_until: '2026-08-18' })]);
    const board = activeBoard(cfg, '2026-08-18');
    expect(board.unavailable).toEqual(['alice']);
  });

  it('treats the day after unavailable_until as available again', () => {
    const cfg = config([member({ login: 'alice', unavailable_until: '2026-08-18' })]);
    const board = activeBoard(cfg, '2026-08-19');
    expect(board.unavailable).toEqual([]);
  });
});

describe('isBoardMember', () => {
  it('is true for an active member with no declared absence', () => {
    const cfg = config([member({ login: 'alice' })]);
    expect(isBoardMember(cfg, 'alice', '2026-08-18')).toBe(true);
  });

  it('is false for a login not on the board', () => {
    const cfg = config([member({ login: 'alice' })]);
    expect(isBoardMember(cfg, 'mallory', '2026-08-18')).toBe(false);
  });

  it('is false for an inactive member even if the login matches', () => {
    const cfg = config([member({ login: 'alice', status: 'inactive' })]);
    expect(isBoardMember(cfg, 'alice', '2026-08-18')).toBe(false);
  });
});

describe('coHostedCount', () => {
  it('counts delivered and archived events hosted in either host slot', () => {
    const speakers = [
      speaker({ host_1: 'alice', status: 'delivered' }),
      speaker({ host_2: 'alice', status: 'archived' }),
      speaker({ host_1: 'bob', status: 'delivered' }),
    ];
    expect(coHostedCount(speakers, 'alice')).toBe(2);
  });

  it('does not count a scheduled event -- it has not been co-hosted yet', () => {
    const speakers = [speaker({ host_1: 'alice', status: 'scheduled' })];
    expect(coHostedCount(speakers, 'alice')).toBe(0);
  });
});

describe('assignLead', () => {
  it('chooses the eligible member carrying the fewest open leads', () => {
    const cfg = config([member({ login: 'alice' }), member({ login: 'bob' })]);
    const speakers = [
      speaker({ id: 'spk-001', status: 'lead', proposed_by: 'alice' }),
      speaker({ id: 'spk-002', status: 'lead', proposed_by: 'alice' }),
      speaker({ id: 'spk-003', status: 'lead', proposed_by: 'bob' }),
    ];
    expect(assignLead(speakers, cfg, '2026-08-18')).toBe('bob');
  });

  it('breaks a tie reproducibly across repeated calls with the same input', () => {
    const cfg = config([member({ login: 'alice' }), member({ login: 'bob' })]);
    const speakers = [
      speaker({ id: 'spk-001', status: 'lead', proposed_by: 'alice' }),
      speaker({ id: 'spk-002', status: 'lead', proposed_by: 'bob' }),
    ];
    const first = assignLead(speakers, cfg, '2026-08-18');
    const second = assignLead(speakers, cfg, '2026-08-18');
    expect(first).toBe(second);
  });

  it('never chooses an unavailable member, even one carrying no leads', () => {
    const cfg = config([
      member({ login: 'alice', unavailable_until: '2026-08-18' }),
      member({ login: 'bob' }),
    ]);
    const speakers = [speaker({ id: 'spk-001', status: 'lead', proposed_by: 'bob' })];
    expect(assignLead(speakers, cfg, '2026-08-18')).toBe('bob');
  });

  it('returns an empty string, never throws, when no member is available', () => {
    const cfg = config([member({ login: 'alice', unavailable_until: '2026-08-18' })]);
    expect(() => assignLead([], cfg, '2026-08-18')).not.toThrow();
    expect(assignLead([], cfg, '2026-08-18')).toBe('');
  });

  interface AssignLeadCase {
    name: string;
    board: BoardMember[];
    speakers: Array<Pick<Speaker, 'id' | 'status' | 'proposed_by'>>;
    on: string;
    expected: string;
  }

  it.each(cases.assign_lead_cases as AssignLeadCase[])('shared fixture: $name', c => {
    const cfg = config(c.board);
    const speakers = c.speakers.map(s => speaker(s));
    expect(assignLead(speakers, cfg, c.on)).toBe(c.expected);
  });
});
