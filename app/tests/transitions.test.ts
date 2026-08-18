import { describe, it, expect } from 'vitest';
import { canTransition, applyTransition } from '../src/state/transitions';
import { BallotRejected } from '../src/state/ballots';
import type { Ballot, BallotValue, Config, Speaker } from '../src/data/types';

/** Four active board members, so `thresholdFor(4)` is 3 — the same bar the
 *  old fixed `voteThreshold: 3` argument stood for. */
const cfg: Config = {
  season: 2026,
  vw_counter: 1,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board: ['a', 'b', 'c', 'd'].map(login => ({
    login,
    joined_on: '2024-01-01',
    status: 'active' as const,
    unavailable_until: '',
  })),
  nominations: [],
  board_min: 3,
  board_max: 9,
  vote_window_days: 14,
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

function ballot(voter: string, value: BallotValue = 'yes'): Ballot {
  return { voter, value, comment: '', coi_reason: '', date: '2026-05-20' };
}

/** A plain yes ballot payload, the shape `ballot-cast` expects. */
function cast(value: BallotValue = 'yes', coiReason = '', comment = '') {
  return { value, comment, coiReason };
}

const base: Speaker = {
  id: 'x',
  name: 'X',
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
  selection: { ballots: [], opened_on: '2026-05-01', decided_on: '' },
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
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
};

describe('transitions v2', () => {
  it('allows board to vote on a lead; refuses organizer', () => {
    expect(canTransition(base, 'ballot-cast', 'board')).toBe(true);
    expect(canTransition(base, 'ballot-cast', 'organizer')).toBe(false);
  });

  it('promotes lead to approved when vote threshold reached', () => {
    const s: Speaker = { ...base, selection: { ...base.selection, ballots: [ballot('a'), ballot('b')] } };
    const next = applyTransition(s, 'ballot-cast', 'c', cfg, '2026-05-23', cast());
    expect(next.status).toBe('approved');
    expect(next.selection.ballots.map(b => b.voter)).toContain('c');
    expect(next.selection.decided_on).toBe('2026-05-23');
  });

  it('does not promote below threshold', () => {
    const s: Speaker = { ...base, selection: { ...base.selection, ballots: [ballot('a')] } };
    const next = applyTransition(s, 'ballot-cast', 'b', cfg, '2026-05-23', cast());
    expect(next.status).toBe('lead');
    expect(next.selection.decided_on).toBe('');
    expect(next.selection.ballots.map(b => b.voter)).toEqual(['a', 'b']);
  });

  it('does not double-count repeat votes from same actor', () => {
    const s: Speaker = { ...base, selection: { ...base.selection, ballots: [ballot('a'), ballot('b')] } };
    const next = applyTransition(s, 'ballot-cast', 'a', cfg, '2026-05-23', cast());
    expect(next.selection.ballots.map(b => b.voter)).toEqual(['a', 'b']);
    expect(next.status).toBe('lead');
  });

  it('recusals shrink the eligible board, and below the minimum the vote is suspended', () => {
    const s: Speaker = {
      ...base,
      selection: {
        ...base.selection,
        ballots: [ballot('a'), ballot('c', 'recused'), ballot('d', 'recused')],
      },
    };
    // Eligible drops from 4 to 2, but MINIMUM_ELIGIBLE suspends the vote there
    // rather than letting two voices approve a speaker.
    const next = applyTransition(s, 'ballot-cast', 'b', cfg, '2026-05-23', cast());
    expect(next.status).toBe('lead');
    expect(next.selection.decided_on).toBe('');
  });

  it('withdraw vote removes login', () => {
    const s: Speaker = { ...base, selection: { ...base.selection, ballots: [ballot('a'), ballot('b')] } };
    const next = applyTransition(s, 'ballot-withdraw', 'a', cfg, '2026-05-23');
    expect(next.selection.ballots.map(b => b.voter)).toEqual(['b']);
  });

  it('an abstention counts as no yes, and does not lower the bar the way a recusal does', () => {
    const s: Speaker = { ...base, selection: { ...base.selection, ballots: [ballot('a'), ballot('b')] } };
    // Three yes out of four eligible would decide; two yes and one abstain
    // does not, because the abstainer stays in the denominator.
    const next = applyTransition(s, 'ballot-cast', 'c', cfg, '2026-05-23', cast('abstain'));
    expect(next.selection.ballots.find(b => b.voter === 'c')?.value).toBe('abstain');
    expect(next.status).toBe('lead');
  });

  it('records a recusal with its written reason', () => {
    const next = applyTransition(base, 'ballot-cast', 'a', cfg, '2026-05-23', cast('recused', 'co-author'));
    const mine = next.selection.ballots.find(b => b.voter === 'a');
    expect(mine?.value).toBe('recused');
    expect(mine?.coi_reason).toBe('co-author');
  });

  it('refuses a recusal with no written reason', () => {
    expect(() =>
      applyTransition(base, 'ballot-cast', 'a', cfg, '2026-05-23', cast('recused')),
    ).toThrow(BallotRejected);
  });

  it('withdrawing a ballot never undoes a decision already taken', () => {
    // The business rule a reader could believe is missing: three yes votes
    // approved this speaker, and one of them steps back afterwards. The count
    // drops below the threshold, but the speaker stays `approved` and
    // `decided_on` stands -- a decision announced is not silently reversed.
    // Only the concealed-conflict procedure (task 9) reopens a vote.
    const decided: Speaker = {
      ...base,
      status: 'approved',
      selection: {
        ...base.selection,
        ballots: [ballot('a'), ballot('b'), ballot('c')],
        decided_on: '2026-05-23',
      },
    };
    const next = applyTransition(decided, 'ballot-withdraw', 'c', cfg, '2026-05-30');
    expect(next.selection.ballots.map(b => b.voter)).toEqual(['a', 'b']);
    expect(next.status).toBe('approved');
    expect(next.selection.decided_on).toBe('2026-05-23');
  });

  it('a suspended vote never decides, however many yes ballots it holds', () => {
    // Two active members: below MINIMUM_ELIGIBLE, so there is no bar to clear.
    const tiny: Config = {
      ...cfg,
      board: cfg.board.slice(0, 2),
    };
    const s: Speaker = { ...base, selection: { ...base.selection, ballots: [ballot('a')] } };
    const next = applyTransition(s, 'ballot-cast', 'b', tiny, '2026-05-23', cast());
    expect(next.status).toBe('lead');
    expect(next.selection.decided_on).toBe('');
  });

  it('park / decline-board are board only and only from lead', () => {
    expect(canTransition(base, 'lead-park', 'organizer')).toBe(false);
    expect(canTransition(base, 'lead-park', 'board')).toBe(true);
    expect(canTransition({ ...base, status: 'approved' }, 'lead-park', 'board')).toBe(false);
  });

  it('reactivate goes from parked or decline-board back to lead', () => {
    const parked: Speaker = { ...base, status: 'parked' };
    expect(applyTransition(parked, 'reactivate', '', cfg, '2026-05-23').status).toBe('lead');
    const declined: Speaker = { ...base, status: 'decline-board' };
    expect(applyTransition(declined, 'reactivate', '', cfg, '2026-05-23').status).toBe('lead');
  });

  it('send-invitation requires host_1 and host_2 set', () => {
    const noHosts: Speaker = { ...base, status: 'approved' };
    expect(canTransition(noHosts, 'send-invitation', 'organizer')).toBe(false);
    const withHosts: Speaker = { ...noHosts, host_1: 'a', host_2: 'b' };
    expect(canTransition(withHosts, 'send-invitation', 'organizer')).toBe(true);
  });

  it('send-invitation moves approved → invited and ticks the gate', () => {
    const s: Speaker = { ...base, status: 'approved', host_1: 'a', host_2: 'b' };
    const next = applyTransition(s, 'send-invitation', '', cfg, '2026-05-23');
    expect(next.status).toBe('invited');
    expect(next.runbook_progress['approved/invitation-sent']).toBe(true);
  });

  it('invited-accept → confirmed; invited-decline → decline-speaker', () => {
    const s: Speaker = { ...base, status: 'invited' };
    expect(applyTransition(s, 'invited-accept', '', cfg, '2026-05-23').status).toBe('confirmed');
    expect(applyTransition(s, 'invited-decline', '', cfg, '2026-05-23').status).toBe('decline-speaker');
  });

  it('lock-date locks date + time + edition', () => {
    const s: Speaker = { ...base, status: 'confirmed' };
    const next = applyTransition(s, 'lock-date', '', cfg, '2026-05-23', {
      date: '2026-08-01',
      edition_code: 'MRG-07',
      time: '14:30',
    });
    expect(next.status).toBe('scheduled');
    expect(next.date).toBe('2026-08-01');
    expect(next.edition_code).toBe('MRG-07');
    expect(next.time).toBe('14:30');
  });

  it('finalize-archive moves delivered → archived', () => {
    const s: Speaker = { ...base, status: 'delivered' };
    expect(canTransition(s, 'finalize-archive', 'organizer')).toBe(true);
    expect(applyTransition(s, 'finalize-archive', '', cfg, '2026-05-23').status).toBe('archived');
  });

  it('override is board only', () => {
    expect(canTransition(base, 'override', 'organizer')).toBe(false);
    expect(canTransition(base, 'override', 'board')).toBe(true);
  });

  it('override forces an arbitrary status', () => {
    const next = applyTransition(base, 'override', '', cfg, '2026-05-23', { status: 'archived' });
    expect(next.status).toBe('archived');
  });

  it('invited-accept/invited-decline are only allowed from invited', () => {
    expect(canTransition({ ...base, status: 'invited' }, 'invited-accept', 'organizer')).toBe(true);
    expect(canTransition({ ...base, status: 'invited' }, 'invited-decline', 'organizer')).toBe(true);
    expect(canTransition(base, 'invited-accept', 'organizer')).toBe(false);
  });

  it('lock-date is only allowed from confirmed', () => {
    expect(canTransition({ ...base, status: 'confirmed' }, 'lock-date', 'organizer')).toBe(true);
    expect(canTransition(base, 'lock-date', 'organizer')).toBe(false);
  });

  it('unknown/unsupported transitions are refused', () => {
    expect(canTransition({ ...base, status: 'archived' }, 'finalize-archive', 'organizer')).toBe(false);
  });
});
