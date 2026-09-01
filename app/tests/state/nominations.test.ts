import { describe, expect, it } from 'vitest';
import cases from '../../../tools/tests/fixtures/governance-cases.json';
import {
  NOMINATION_MIN_CO_HOSTED,
  isUnsettled,
  activeBoard,
  declareUnavailability,
  NOMINATION_WINDOW_DAYS,
  NominationRejected,
  nominationBlocker,
  objectionBlocker,
  objectToNomination,
  openNomination,
  resolveNominations,
  withdrawObjection,
  withdrawalBlocker,
} from '../../src/state/board';
import { friendlyError } from '../../src/github/errors';
import { DecisionRejected, formatDecision, identifier } from '../../src/state/decisions';
import type { BoardMember, Config, Nomination, Speaker } from '../../src/data/types';
import { speaker as double } from '../helpers/data-doubles';

function member(login: string, overrides: Partial<BoardMember> = {}): BoardMember {
  return {
    login,
    joined_on: '2024-01-01',
    status: 'active',
    unavailable_until: '',
    ...overrides,
  };
}

function config(overrides: Partial<Config> = {}): Config {
  return {
    season: 2026,
    next_edition_number: 1,
    overlap_window_days: 7,
    seminar_duration_minutes: 90,
    eligibility_share: 0.6666666666666666,
    board: [member('alice'), member('bob'), member('carol')],
    nominations: [],
    board_min: 3,
    board_max: 9,
    vote_window_days: 10,
    objection_window_working_days: 3,
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
    ...overrides,
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
    status: 'delivered',
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

/** `dan` has co-hosted exactly the two webinars eligibility asks for. */
function coHosted(login: string, count: number, status: Speaker['status'] = 'delivered'): Speaker[] {
  return Array.from({ length: count }, (_, i) =>
    speaker({ id: `spk-${100 + i}`, host_1: login, status }),
  );
}

const SPEAKERS = coHosted('dan', 2);

describe('openNomination', () => {
  it('records the candidate, the sponsor and the opening date, with no outcome', () => {
    const next = openNomination(SPEAKERS, config(), 'dan', 'alice', '2026-03-01');
    expect(next.nominations).toEqual([
      {
        candidate: 'dan',
        sponsor: 'alice',
        opened_on: '2026-03-01',
        objections: [],
        outcome: '',
      },
    ]);
  });

  it('never mutates the config it is given', () => {
    const before = config();
    openNomination(SPEAKERS, before, 'dan', 'alice', '2026-03-01');
    expect(before.nominations).toEqual([]);
  });

  it('refuses a candidate who has not co-hosted two webinars', () => {
    expect(() => openNomination(coHosted('dan', 1), config(), 'dan', 'alice', '2026-03-01')).toThrow(
      NominationRejected,
    );
    expect(nominationBlocker(coHosted('dan', 1), config(), 'dan', 'alice', '2026-03-01')).toContain(
      'co-hosted',
    );
  });

  it('counts only webinars that have actually happened', () => {
    const scheduled = coHosted('dan', 2, 'scheduled');
    expect(nominationBlocker(scheduled, config(), 'dan', 'alice', '2026-03-01')).not.toBe('');
  });

  it('counts a candidate who co-hosted as second host', () => {
    const speakers = [
      speaker({ id: 'spk-101', host_1: 'alice', host_2: 'dan' }),
      speaker({ id: 'spk-102', host_1: 'bob', host_2: 'dan', status: 'archived' }),
    ];
    expect(nominationBlocker(speakers, config(), 'dan', 'alice', '2026-03-01')).toBe('');
  });

  it('refuses a candidate typed as a person rather than a username', () => {
    // The commit subject an accepted nomination writes is permanent. A real
    // name typed into the box would be in the history for good, and the
    // register could not read the line back either -- so this is refused
    // before the button is enabled, with a sentence saying what to type.
    for (const typed of ['Jane Doe', 'Jane Doe (CNRS)', 'jane@example.org', '  ']) {
      const reason = nominationBlocker(SPEAKERS, config(), typed, 'alice', '2026-03-01');
      expect(reason, typed).not.toBe('');
      expect(reason, typed).toContain('username');
    }
  });

  it('never writes a decision line about a person by name', () => {
    // Belt and braces across the two halves: the blocker refuses, and the
    // grammar has no slot for it even if a caller ignored the blocker.
    expect(() =>
      formatDecision({
        kind: 'nomination-open',
        entity: identifier('Jane Doe (CNRS)'),
        actor: identifier('alice'),
      }),
    ).toThrow(DecisionRejected);
  });

  it('refuses a sponsor who is not an active board member', () => {
    expect(nominationBlocker(SPEAKERS, config(), 'dan', 'erin', '2026-03-01')).toContain('sponsor');
    expect(() => openNomination(SPEAKERS, config(), 'dan', 'erin', '2026-03-01')).toThrow(
      NominationRejected,
    );
  });

  it('accepts a sponsor who is away: unavailable is not off the board', () => {
    const cfg = config({
      board: [member('alice', { unavailable_until: '2026-04-01' }), member('bob'), member('carol')],
    });
    expect(nominationBlocker(SPEAKERS, cfg, 'dan', 'alice', '2026-03-01')).toBe('');
  });

  it('refuses a candidate who is already on the board', () => {
    const speakers = coHosted('carol', 2);
    expect(nominationBlocker(speakers, config(), 'carol', 'alice', '2026-03-01')).toContain(
      'already',
    );
  });

  it('refuses a second nomination while one is still open', () => {
    const opened = openNomination(SPEAKERS, config(), 'dan', 'alice', '2026-03-01');
    expect(nominationBlocker(SPEAKERS, opened, 'dan', 'bob', '2026-03-02')).toContain('already');
    expect(() => openNomination(SPEAKERS, opened, 'dan', 'bob', '2026-03-02')).toThrow(
      NominationRejected,
    );
  });

  it('refuses a second nomination while one is waiting for a seat', () => {
    const waiting: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-01-01',
      objections: [],
      outcome: 'waiting',
    };
    expect(
      nominationBlocker(SPEAKERS, config({ nominations: [waiting] }), 'dan', 'bob', '2026-03-01'),
    ).not.toBe('');
  });

  it('refuses to re-open a deferred nomination while the objection stands', () => {
    // The rule this block exists for: an objection written in the morning
    // must not be routed around by nominating the same person again in the
    // afternoon, which would empty the deferral of its purpose.
    const deferred: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-01-01',
      objections: [{ member: 'bob', reason: 'too soon', date: '2026-01-02' }],
      outcome: 'deferred',
    };
    const cfg = config({ nominations: [deferred] });
    const blocker = nominationBlocker(SPEAKERS, cfg, 'dan', 'carol', '2026-03-01');
    expect(blocker).toContain('bob');
    expect(blocker).toContain('withdrawn');
    expect(() => openNomination(SPEAKERS, cfg, 'dan', 'carol', '2026-03-01')).toThrow(
      NominationRejected,
    );
    // Not the objector themselves either, and not on any later date: no
    // delay clears an objection.
    expect(nominationBlocker(SPEAKERS, cfg, 'dan', 'bob', '2030-01-01')).not.toBe('');
  });

  it('names every member whose objection is holding the nomination', () => {
    const deferred: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-01-01',
      objections: [
        { member: 'bob', reason: 'too soon', date: '2026-01-02' },
        { member: 'carol', reason: 'conflict', date: '2026-01-03' },
      ],
      outcome: 'deferred',
    };
    const blocker = nominationBlocker(
      SPEAKERS,
      config({ nominations: [deferred] }),
      'dan',
      'alice',
      '2026-03-01',
    );
    expect(blocker).toContain('bob');
    expect(blocker).toContain('carol');
  });

  it('lets a hand-edited deferral with nothing standing on it be opened again', () => {
    // A `deferred` carrying no objection cannot be produced by any
    // transformation here. If one is typed in by hand there is nothing to
    // withdraw, so locking it would be a state with no way out of it.
    const stale: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-01-01',
      objections: [],
      outcome: 'deferred',
    };
    const cfg = config({ nominations: [stale] });
    expect(nominationBlocker(SPEAKERS, cfg, 'dan', 'carol', '2026-03-01')).toBe('');
    const next = openNomination(SPEAKERS, cfg, 'dan', 'carol', '2026-03-01');
    expect(next.nominations).toHaveLength(2);
    expect(next.nominations[0]).toEqual(stale);
  });

  it('refuses a blank candidate', () => {
    expect(nominationBlocker(SPEAKERS, config(), '  ', 'alice', '2026-03-01')).not.toBe('');
  });

  it('does not depend on the declared headcount matching board_min', () => {
    // `board_min` is a target, and nothing may gate a nomination on it: the
    // board furthest below its target is the one that most needs to admit
    // members, so refusing there would forbid the act that closes the gap.
    // Declared at 9 on a board of three, this must still open.
    const cfg = config({ board_min: 9 });
    expect(nominationBlocker(SPEAKERS, cfg, 'dan', 'alice', '2026-03-01')).toBe('');
  });
});

describe('objectToNomination', () => {
  const opened = openNomination(SPEAKERS, config(), 'dan', 'alice', '2026-03-01');

  it('defers the nomination in the same transformation that records the objection', () => {
    const next = objectToNomination(opened, 'dan', 'bob', 'conflict of interest', '2026-03-02');
    expect(next.nominations[0]).toEqual({
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-03-01',
      objections: [{ member: 'bob', reason: 'conflict of interest', date: '2026-03-02' }],
      outcome: 'deferred',
    });
  });

  it('never leaves an objection standing on an unresolved nomination', () => {
    const next = objectToNomination(opened, 'dan', 'bob', 'wait', '2026-03-02');
    for (const n of next.nominations) {
      if (n.objections.length > 0) expect(n.outcome).toBe('deferred');
    }
  });

  it('replaces an earlier objection from the same member in place', () => {
    const once = objectToNomination(opened, 'dan', 'bob', 'first', '2026-03-02');
    const twice = objectToNomination(once, 'dan', 'carol', 'second', '2026-03-03');
    const thrice = objectToNomination(twice, 'dan', 'bob', 'revised', '2026-03-04');
    expect(thrice.nominations[0].objections).toEqual([
      { member: 'bob', reason: 'revised', date: '2026-03-04' },
      { member: 'carol', reason: 'second', date: '2026-03-03' },
    ]);
  });

  it('refuses an objection without a written reason', () => {
    expect(objectionBlocker(opened, 'dan', 'bob', '   ', '2026-03-02')).toContain('reason');
    expect(() => objectToNomination(opened, 'dan', 'bob', '   ', '2026-03-02')).toThrow(
      NominationRejected,
    );
  });

  it('refuses an objection from someone who is not an active board member', () => {
    expect(objectionBlocker(opened, 'dan', 'erin', 'no', '2026-03-02')).not.toBe('');
    expect(() => objectToNomination(opened, 'dan', 'erin', 'no', '2026-03-02')).toThrow(
      NominationRejected,
    );
  });

  it('refuses an objection to a nomination that is already resolved', () => {
    const resolved = resolveNominations(opened, '2026-03-20');
    expect(resolved.nominations[0].outcome).toBe('accepted');
    expect(objectionBlocker(resolved, 'dan', 'bob', 'late', '2026-03-21')).not.toBe('');
    expect(() => objectToNomination(resolved, 'dan', 'bob', 'late', '2026-03-21')).toThrow(
      NominationRejected,
    );
  });

  it('refuses an objection when there is no nomination at all', () => {
    expect(objectionBlocker(config(), 'dan', 'bob', 'no', '2026-03-02')).not.toBe('');
  });

  it('can still object to a nomination waiting for a seat', () => {
    const waiting: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-01-01',
      objections: [],
      outcome: 'waiting',
    };
    const next = objectToNomination(config({ nominations: [waiting] }), 'dan', 'bob', 'why', '2026-03-02');
    expect(next.nominations[0].outcome).toBe('deferred');
  });

  it('touches only the nomination objected to', () => {
    const speakers = [...coHosted('dan', 2), ...coHosted('erin', 2)];
    const two = openNomination(speakers, opened, 'erin', 'alice', '2026-03-01');
    const next = objectToNomination(two, 'erin', 'bob', 'conflict', '2026-03-02');
    expect(next.nominations[0]).toEqual(opened.nominations[0]);
    expect(next.nominations[1].outcome).toBe('deferred');
  });

  it('never mutates the config it is given', () => {
    objectToNomination(opened, 'dan', 'bob', 'x', '2026-03-02');
    expect(opened.nominations[0].objections).toEqual([]);
    expect(opened.nominations[0].outcome).toBe('');
  });
});

describe('withdrawObjection', () => {
  const opened = openNomination(SPEAKERS, config(), 'dan', 'alice', '2026-03-01');
  const deferred = objectToNomination(opened, 'dan', 'bob', 'too soon', '2026-03-02');

  it('re-opens the nomination and restarts the seven days from the withdrawal', () => {
    const next = withdrawObjection(deferred, 'dan', 'bob', '2026-04-01');
    expect(next.nominations).toHaveLength(1);
    expect(next.nominations[0]).toEqual({
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-04-01',
      objections: [],
      outcome: '',
    });
    // The spent original window does not carry it: a board that was told the
    // nomination was deferred gets a real window on it again.
    expect(resolveNominations(next, '2026-04-05').nominations[0].outcome).toBe('');
    expect(resolveNominations(next, '2026-04-08').nominations[0].outcome).toBe('accepted');
  });

  it('lets nobody withdraw an objection they did not write', () => {
    expect(withdrawalBlocker(deferred, 'dan', 'carol')).toContain('no objection on record');
    expect(() => withdrawObjection(deferred, 'dan', 'carol', '2026-04-01')).toThrow(
      NominationRejected,
    );
    expect(() => withdrawObjection(deferred, 'dan', 'alice', '2026-04-01')).toThrow(
      NominationRejected,
    );
  });

  it('stays deferred while another objection still stands', () => {
    const two = objectToNomination(deferred, 'dan', 'carol', 'conflict', '2026-03-03');
    const next = withdrawObjection(two, 'dan', 'bob', '2026-04-01');
    expect(next.nominations[0].objections).toEqual([
      { member: 'carol', reason: 'conflict', date: '2026-03-03' },
    ]);
    expect(next.nominations[0].outcome).toBe('deferred');
    expect(next.nominations[0].opened_on).toBe('2026-03-01');
    expect(nominationBlocker(SPEAKERS, next, 'dan', 'alice', '2026-04-02')).toContain('carol');
  });

  it('withdraws an objection raised by a member who has since gone inactive', () => {
    // An objection nobody could ever lift is a worse state than the one the
    // rule guards against, so board membership is not a condition here.
    const cfg = {
      ...deferred,
      board: deferred.board.map(m =>
        m.login === 'bob' ? { ...m, status: 'inactive' as const } : m,
      ),
    };
    expect(withdrawalBlocker(cfg, 'dan', 'bob')).toBe('');
    expect(withdrawObjection(cfg, 'dan', 'bob', '2026-04-01').nominations[0].outcome).toBe('');
  });

  it('never re-opens a seat that was granted', () => {
    const handEdited: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-01-01',
      objections: [{ member: 'bob', reason: 'typed in by hand', date: '2026-01-02' }],
      outcome: 'accepted',
    };
    const cfg = config({ nominations: [handEdited] });
    expect(withdrawalBlocker(cfg, 'dan', 'bob')).not.toBe('');
    expect(() => withdrawObjection(cfg, 'dan', 'bob', '2026-04-01')).toThrow(NominationRejected);
  });

  it('never mutates the config it is given', () => {
    withdrawObjection(deferred, 'dan', 'bob', '2026-04-01');
    expect(deferred.nominations[0].objections).toHaveLength(1);
    expect(deferred.nominations[0].outcome).toBe('deferred');
  });

  it('shows a refusal as an explanation, not as a raw error', () => {
    let message = '';
    try {
      withdrawObjection(deferred, 'dan', 'carol', '2026-04-01');
    } catch (e) {
      message = friendlyError(e, 'save');
    }
    expect(message).toContain('no objection on record');
    expect(message).not.toContain('GitHub is not responding');
  });
});

describe('resolveNominations', () => {
  const opened = openNomination(SPEAKERS, config(), 'dan', 'alice', '2026-03-01');

  it('leaves a nomination alone before the window closes', () => {
    const next = resolveNominations(opened, '2026-03-07');
    expect(next).toEqual(opened);
    expect(next.nominations[0].outcome).toBe('');
  });

  it('accepts a nomination with no objection once the window has run', () => {
    const day = new Date(Date.parse('2026-03-01') + NOMINATION_WINDOW_DAYS * 86400000)
      .toISOString()
      .slice(0, 10);
    const next = resolveNominations(opened, day);
    expect(next.nominations[0].outcome).toBe('accepted');
  });

  it('adds the accepted member to the board with joined_on at the resolution date', () => {
    const next = resolveNominations(opened, '2026-03-09');
    expect(next.board).toHaveLength(4);
    expect(next.board[3]).toEqual({
      login: 'dan',
      joined_on: '2026-03-09',
      status: 'active',
      unavailable_until: '',
    });
  });

  it('never records an acceptance without seating the member', () => {
    const next = resolveNominations(opened, '2026-03-09');
    for (const n of next.nominations) {
      if (n.outcome === 'accepted') {
        expect(next.board.some(m => m.login === n.candidate && m.status === 'active')).toBe(true);
      }
    }
  });

  it('reactivates an existing entry rather than adding a second one', () => {
    const cfg = config({
      board: [
        member('alice'),
        member('bob'),
        member('carol'),
        member('dan', { status: 'inactive', joined_on: '2019-04-02' }),
      ],
      nominations: opened.nominations,
    });
    const next = resolveNominations(cfg, '2026-03-09');
    // One entry, now active -- and it keeps the day dan actually joined the
    // board. `joined_on` is not the day of the most recent nomination, and
    // the inactivity rule (G-09) reads it as the start of its window, so
    // rewriting it would restart that clock for someone who has been here
    // since 2019.
    expect(next.board.filter(m => m.login === 'dan')).toEqual([
      { login: 'dan', joined_on: '2019-04-02', status: 'active', unavailable_until: '' },
    ]);
  });

  it('leaves an already-seated member exactly as they were', () => {
    // Reachable without a hand edit: an older nomination whose candidate is
    // already on the board, whose last objection is withdrawn, is resolved
    // here. Seating them again must not reset the day they joined, and must
    // not clear an absence only they may declare and only they may lift.
    const cfg = config({
      board: [
        member('alice'),
        member('bob'),
        member('dan', { joined_on: '2019-04-02', unavailable_until: '2026-06-30' }),
      ],
      nominations: opened.nominations,
    });
    const next = resolveNominations(cfg, '2026-03-09');
    expect(next.nominations[0].outcome).toBe('accepted');
    expect(next.board.filter(m => m.login === 'dan')).toEqual([
      { login: 'dan', joined_on: '2019-04-02', status: 'active', unavailable_until: '2026-06-30' },
    ]);
  });

  it('does not clear a declared absence when it reactivates a member', () => {
    const cfg = config({
      board: [
        member('alice'),
        member('bob'),
        member('carol'),
        member('dan', {
          status: 'inactive',
          joined_on: '2019-04-02',
          unavailable_until: '2026-06-30',
        }),
      ],
      nominations: opened.nominations,
    });
    const next = resolveNominations(cfg, '2026-03-09');
    expect(next.board.filter(m => m.login === 'dan')).toEqual([
      { login: 'dan', joined_on: '2019-04-02', status: 'active', unavailable_until: '2026-06-30' },
    ]);
  });

  it('holds the nomination as waiting when the board is already at board_max', () => {
    const cfg = config({ board_max: 3, nominations: opened.nominations });
    const next = resolveNominations(cfg, '2026-03-09');
    expect(next.nominations[0].outcome).toBe('waiting');
    expect(next.board).toHaveLength(3);
  });

  it('leaves a waiting nomination waiting while the board stays full', () => {
    const cfg = config({ board_max: 3, nominations: opened.nominations });
    const waiting = resolveNominations(cfg, '2026-03-09');
    expect(resolveNominations(waiting, '2027-01-01')).toEqual(waiting);
  });

  it('seats a waiting nomination as soon as a seat frees up', () => {
    const cfg = config({ board_max: 3, nominations: opened.nominations });
    const waiting = resolveNominations(cfg, '2026-03-09');
    const shrunk = {
      ...waiting,
      board: waiting.board.map(m => (m.login === 'carol' ? { ...m, status: 'inactive' as const } : m)),
    };
    const next = resolveNominations(shrunk, '2026-03-20');
    expect(next.nominations[0].outcome).toBe('accepted');
    expect(next.board.some(m => m.login === 'dan' && m.status === 'active')).toBe(true);
  });

  it('fills the last free seat once and holds the rest', () => {
    const speakers = [...coHosted('dan', 2), ...coHosted('erin', 2)];
    let cfg = config({ board_max: 4 });
    cfg = openNomination(speakers, cfg, 'dan', 'alice', '2026-03-01');
    cfg = openNomination(speakers, cfg, 'erin', 'alice', '2026-03-01');
    const next = resolveNominations(cfg, '2026-03-09');
    expect(next.nominations.map(n => n.outcome)).toEqual(['accepted', 'waiting']);
    expect(next.board).toHaveLength(4);
  });

  it('leaves an objected nomination deferred and never accepts it', () => {
    const objected = objectToNomination(opened, 'dan', 'bob', 'conflict', '2026-03-02');
    const next = resolveNominations(objected, '2026-06-01');
    expect(next.nominations[0].outcome).toBe('deferred');
    expect(next.board).toHaveLength(3);
  });

  it('defers a hand-edited nomination that carries objections but no outcome', () => {
    const handEdited: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-03-01',
      objections: [{ member: 'bob', reason: 'hand-edited', date: '2026-03-02' }],
      outcome: '',
    };
    const next = resolveNominations(config({ nominations: [handEdited] }), '2026-06-01');
    expect(next.nominations[0].outcome).toBe('deferred');
  });

  it('never revisits an accepted nomination', () => {
    const accepted = resolveNominations(opened, '2026-03-09');
    const again = resolveNominations(accepted, '2026-04-09');
    expect(again).toEqual(accepted);
    expect(again.board.filter(m => m.login === 'dan')).toHaveLength(1);
  });

  it('never produces a refusal, whatever the date', () => {
    const outcomes = new Set<string>();
    for (const day of ['2026-03-02', '2026-03-09', '2027-01-01']) {
      for (const n of resolveNominations(opened, day).nominations) outcomes.add(n.outcome);
    }
    expect([...outcomes].every(o => o === '' || o === 'accepted' || o === 'waiting')).toBe(true);
  });

  it('does not accept a nomination whose opening date is unusable', () => {
    const broken: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '',
      objections: [],
      outcome: '',
    };
    const next = resolveNominations(config({ nominations: [broken] }), '2027-01-01');
    expect(next.nominations[0].outcome).toBe('');
  });

  it('accepts a candidate already seated by hand without duplicating the entry', () => {
    const cfg = config({
      board: [member('alice'), member('bob'), member('carol'), member('dan')],
      board_max: 4,
      nominations: opened.nominations,
    });
    const next = resolveNominations(cfg, '2026-03-09');
    expect(next.nominations[0].outcome).toBe('accepted');
    expect(next.board.filter(m => m.login === 'dan')).toHaveLength(1);
  });

  it('never mutates the config it is given', () => {
    resolveNominations(opened, '2026-03-09');
    expect(opened.board).toHaveLength(3);
    expect(opened.nominations[0].outcome).toBe('');
  });
});

describe('declareUnavailability', () => {
  it('records the inclusive last day away for the member themselves', () => {
    const next = declareUnavailability(config(), 'bob', '2026-04-10');
    expect(next.board.map(m => m.unavailable_until)).toEqual(['', '2026-04-10', '']);
    expect(activeBoard(next, '2026-04-10').unavailable).toEqual(['bob']);
    expect(activeBoard(next, '2026-04-11').unavailable).toEqual([]);
  });

  it('clears an absence when given an empty date', () => {
    const away = declareUnavailability(config(), 'bob', '2026-04-10');
    expect(declareUnavailability(away, 'bob', '').board[1].unavailable_until).toBe('');
  });

  it('never marks a member who has left the board as merely away', () => {
    const cfg = config({ board: [member('alice'), member('bob', { status: 'inactive' })] });
    expect(declareUnavailability(cfg, 'bob', '2026-04-10').board[1].unavailable_until).toBe('');
  });

  it('never mutates the config it is given', () => {
    const before = config();
    declareUnavailability(before, 'bob', '2026-04-10');
    expect(before.board[1].unavailable_until).toBe('');
  });
});

describe('the rule as a whole', () => {
  it('asks for two co-hosted webinars and a seven-day window', () => {
    expect(NOMINATION_MIN_CO_HOSTED).toBe(2);
    expect(NOMINATION_WINDOW_DAYS).toBe(7);
  });

  it('shows a refusal as an explanation, not as a raw error', () => {
    let message = '';
    try {
      openNomination(coHosted('dan', 0), config(), 'dan', 'alice', '2026-03-01');
    } catch (e) {
      message = friendlyError(e, 'save');
    }
    expect(message).toContain('co-hosted');
    expect(message).not.toContain('GitHub is not responding');
  });
});


/**
 * `isUnsettled` is one half of a rule implemented twice: the other half is
 * `tools/convener_ops/maintenance/sweep.py::_unsettled_candidates`, which keeps a candidate the
 * board is still arguing about off the inactivity proposal. The Python copy
 * mirrored the narrower `isPending` until these cases were written, so a
 * seated member carrying a deferred nomination could be named by the very
 * sweep that read the objection against them. `tools/tests/
 * test_governance_fixture.py` runs the same list.
 */
describe('the shared unsettled-nomination fixture', () => {
  it.each(cases.unsettled_nomination_cases)('$name', c => {
    expect(isUnsettled(c.nomination as Nomination)).toBe(c.unsettled);
  });

  it('covers both a settled and an unsettled deferral, not just one', () => {
    const deferred = cases.unsettled_nomination_cases.filter(
      c => c.nomination.outcome === 'deferred',
    );
    expect(deferred.map(c => c.unsettled).sort()).toEqual([false, true]);
  });
});
