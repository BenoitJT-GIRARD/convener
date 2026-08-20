import { describe, expect, it } from 'vitest';
import {
  activeBoard,
  assignLead,
  coHostedCount,
  isBoardMember,
  resolveNominations,
} from '../src/state/board';
import type { BoardMember, Config, Speaker } from '../src/data/types';
import cases from '../../tools/tests/fixtures/governance-cases.json';
import { speaker as double } from './data-doubles';

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
    view_count_window_days: 30,
    sla_days: {
      invitation_follow_up: 7,
      summary_after_delivery: 5,
      recording_after_delivery: 10,
    },
    channels: [],
    instructions: '',
  };
}

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
function speaker(overrides: Partial<Speaker> = {}): Speaker {
  return double({
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
    assigned_to: '',
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
  });
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

  interface ActiveBoardCase {
    name: string;
    board: BoardMember[];
    on: string;
    logins: string[];
    unavailable: string[];
    eligible: string[];
  }

  // The BoardMember -> (logins, unavailable) step, pinned across both
  // languages: `tools/tests/test_governance_fixture.py` runs these same cases
  // through `convener_ops.governance.active_board`. `decision_cases` start from
  // flat login lists, so they never covered this mapping -- which is where the
  // Python copies of it once drifted apart with both suites still green.
  it.each(cases.active_board_cases as ActiveBoardCase[])('shared fixture: $name', c => {
    const board = activeBoard(config(c.board), c.on);
    expect(board.logins).toEqual(c.logins);
    expect(board.unavailable).toEqual(c.unavailable);
    const away = new Set(board.unavailable);
    expect(board.logins.filter(login => !away.has(login))).toEqual(c.eligible);
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
      speaker({ id: 'spk-001', status: 'lead', assigned_to: 'alice' }),
      speaker({ id: 'spk-002', status: 'lead', assigned_to: 'alice' }),
      speaker({ id: 'spk-003', status: 'lead', assigned_to: 'bob' }),
    ];
    expect(assignLead(speakers, cfg, '2026-08-18')).toBe('bob');
  });

  it('breaks a tie reproducibly across repeated calls with the same input', () => {
    const cfg = config([member({ login: 'alice' }), member({ login: 'bob' })]);
    const speakers = [
      speaker({ id: 'spk-001', status: 'lead', assigned_to: 'alice' }),
      speaker({ id: 'spk-002', status: 'lead', assigned_to: 'bob' }),
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
    const speakers = [speaker({ id: 'spk-001', status: 'lead', assigned_to: 'bob' })];
    expect(assignLead(speakers, cfg, '2026-08-18')).toBe('bob');
  });

  it('returns an empty string, never throws, when no member is available', () => {
    const cfg = config([member({ login: 'alice', unavailable_until: '2026-08-18' })]);
    expect(() => assignLead([], cfg, '2026-08-18')).not.toThrow();
    expect(assignLead([], cfg, '2026-08-18')).toBe('');
  });

  it('loads leads by assigned_to, not proposed_by -- the two are independent fields', () => {
    // A form submission's proposed_by carries the visitor's own name, which
    // never matches a board login. If assignLead counted by proposed_by it
    // would see no open leads for anyone and could not load-balance at all.
    const cfg = config([member({ login: 'alice' }), member({ login: 'bob' })]);
    const speakers = [
      speaker({ id: 'spk-001', status: 'lead', proposed_by: 'A community member', assigned_to: 'alice' }),
      speaker({ id: 'spk-002', status: 'lead', proposed_by: 'Another visitor', assigned_to: 'alice' }),
    ];
    expect(assignLead(speakers, cfg, '2026-08-18')).toBe('bob');
  });

  interface AssignLeadCase {
    name: string;
    board: BoardMember[];
    speakers: Array<Pick<Speaker, 'id' | 'status' | 'assigned_to'>>;
    on: string;
    expected: string;
  }

  it.each(cases.assign_lead_cases as AssignLeadCase[])('shared fixture: $name', c => {
    const cfg = config(c.board);
    const speakers = c.speakers.map(s => speaker(s));
    expect(assignLead(speakers, cfg, c.on)).toBe(c.expected);
  });
});

describe('the seat count, pinned to the validator', () => {
  interface HeadcountCase {
    name: string;
    board: BoardMember[];
    board_min: number;
    board_max: number;
    active: number;
    within: boolean;
  }

  // `tools/tests/test_validate.py` runs these same cases through
  // `validate_config`. The two used to disagree: this side counted active
  // members before seating, the validator counted entries, so a board with an
  // inactive entry could be seated up to `board_max` by the app and then
  // rejected in CI by `convener-validate` -- on the very file the app had just
  // written. One number, read from both sides, is what stops that.
  it.each(cases.board_headcount_cases as HeadcountCase[])('shared fixture: $name', c => {
    const cfg = { ...config(c.board), board_min: c.board_min, board_max: c.board_max };
    expect(activeBoard(cfg, '2024-06-01').logins.length).toBe(c.active);
    expect(c.active >= c.board_min && c.active <= c.board_max).toBe(c.within);
  });

  it('never seats past the ceiling the validator enforces', () => {
    const board = [
      member({ login: 'alice' }),
      member({ login: 'bob' }),
      member({ login: 'carol' }),
      member({ login: 'dave', status: 'inactive' }),
    ];
    const cfg: Config = {
      ...config(board),
      board_min: 3,
      board_max: 3,
      nominations: [
        {
          candidate: 'erin',
          sponsor: 'alice',
          opened_on: '2026-01-01',
          objections: [],
          outcome: '',
        },
      ],
    };
    const next = resolveNominations(cfg, '2026-03-01');
    expect(next.nominations[0].outcome).toBe('waiting');
    expect(next.board.filter(m => m.status === 'active').length).toBe(3);
  });

  it('lets an inactive entry be reseated without overshooting the ceiling', () => {
    // The inactive entry is not a seat, so seating its own login is a
    // reactivation rather than a tenth member -- and the count the validator
    // reads is unchanged by the entry sitting there beforehand.
    const board = [
      member({ login: 'alice' }),
      member({ login: 'bob' }),
      member({ login: 'carol', status: 'inactive' }),
    ];
    const cfg: Config = {
      ...config(board),
      board_min: 2,
      board_max: 3,
      nominations: [
        {
          candidate: 'carol',
          sponsor: 'alice',
          opened_on: '2026-01-01',
          objections: [],
          outcome: '',
        },
      ],
    };
    const next = resolveNominations(cfg, '2026-03-01');
    expect(next.nominations[0].outcome).toBe('accepted');
    expect(next.board.filter(m => m.status === 'active').length).toBe(3);
    expect(next.board.length).toBe(3);
  });
});
