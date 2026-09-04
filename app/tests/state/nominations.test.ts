import { describe, expect, it } from 'vitest';
import cases from '../../../tools/tests/fixtures/governance-cases.json';
import {
  NOMINATION_MIN_CO_HOSTED,
  NOMINATION_MINIMUM_SUPPORTS,
  isUnsettled,
  activeBoard,
  declareUnavailability,
  NOMINATION_WINDOW_DAYS,
  NominationRejected,
  nominationBar,
  nominationBlocker,
  nominationStanding,
  objectionBlocker,
  objectToNomination,
  openNomination,
  resolveNominations,
  supportBlocker,
  supportNomination,
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

/** A nomination the board has carried: opened, then supported by every
 *  other active member. The board here is three, so the bar is three and
 *  the sponsor's own support (written by `openNomination`) is one of them. */
function backed(
  cfg: Config,
  candidate: string,
  sponsor: string,
  on: string,
  speakers: Speaker[] = SPEAKERS,
): Config {
  const opened = openNomination(speakers, cfg, candidate, sponsor, on);
  return opened.board
    .filter(m => m.status === 'active' && m.login !== sponsor)
    .reduce((carrying, m) => supportNomination(carrying, candidate, m.login, on), opened);
}

describe('openNomination', () => {
  it('records the candidate, the sponsor and the opening date, with no outcome', () => {
    const next = openNomination(SPEAKERS, config(), 'dan', 'alice', '2026-03-01');
    expect(next.nominations).toEqual([
      {
        candidate: 'dan',
        sponsor: 'alice',
        opened_on: '2026-03-01',
        // Opening one is saying yes to it: a sponsor among the silent would
        // be counted against their own candidate.
        supports: [{ member: 'alice', date: '2026-03-01' }],
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
      supports: [],
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
      supports: [],
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
      supports: [],
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
      supports: [],
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

describe('supportNomination', () => {
  const opened = openNomination(SPEAKERS, config(), 'dan', 'alice', '2026-03-01');

  it('records the member and the day, and counts towards the bar', () => {
    const next = supportNomination(opened, 'dan', 'bob', '2026-03-03');
    expect(next.nominations[0].supports).toEqual([
      { member: 'alice', date: '2026-03-01' },
      { member: 'bob', date: '2026-03-03' },
    ]);
    expect(nominationStanding(next, next.nominations[0], '2026-03-03')).toEqual({
      eligible: 3,
      bar: 3,
      supports: 2,
      elapsed: 2,
      carried: false,
    });
  });

  it('carries the nomination once the bar is reached, and no sooner', () => {
    const two = supportNomination(opened, 'dan', 'bob', '2026-03-03');
    expect(nominationStanding(two, two.nominations[0], '2026-03-03').carried).toBe(false);
    const three = supportNomination(two, 'dan', 'carol', '2026-03-04');
    expect(nominationStanding(three, three.nominations[0], '2026-03-04').carried).toBe(true);
  });

  it('refuses a second support from the same member', () => {
    expect(supportBlocker(opened, 'dan', 'alice', '2026-03-02')).toContain('already supported');
    expect(() => supportNomination(opened, 'dan', 'alice', '2026-03-02')).toThrow(
      NominationRejected,
    );
  });

  it('refuses a support from someone who is not an active board member', () => {
    expect(supportBlocker(opened, 'dan', 'erin', '2026-03-02')).toContain('active board member');
    expect(() => supportNomination(opened, 'dan', 'erin', '2026-03-02')).toThrow(
      NominationRejected,
    );
  });

  it('refuses a support once the window has run', () => {
    // Silence counts as refusal, so the days have to mean something: a
    // support recorded on the twentieth day cannot carry a nomination the
    // board let run out.
    const blocker = supportBlocker(opened, 'dan', 'bob', '2026-03-21');
    expect(blocker).toContain(`${NOMINATION_WINDOW_DAYS} days`);
    expect(blocker).toContain('meeting');
    expect(() => supportNomination(opened, 'dan', 'bob', '2026-03-21')).toThrow(
      NominationRejected,
    );
  });

  it('refuses a support on a nomination nobody has opened', () => {
    expect(supportBlocker(config(), 'dan', 'bob', '2026-03-02')).toContain('no open nomination');
  });

  it('offers nothing on a deferred, waiting or accepted nomination', () => {
    const deferred = objectToNomination(opened, 'dan', 'bob', 'too soon', '2026-03-02');
    expect(supportBlocker(deferred, 'dan', 'carol', '2026-03-03')).toContain('no open nomination');
    const settled = resolveNominations(backed(config(), 'dan', 'alice', '2026-03-01'), '2026-03-02');
    expect(supportBlocker(settled, 'dan', 'carol', '2026-03-03')).toContain('no open nomination');
  });

  it('lets a member who is away record one, and counts it when they are back', () => {
    // Away is out of today's count, never off the board -- the same reading
    // the two-thirds bar takes of an absence.
    const away = declareUnavailability(opened, 'bob', '2026-03-10');
    expect(supportBlocker(away, 'dan', 'bob', '2026-03-05')).toBe('');
    const next = supportNomination(away, 'dan', 'bob', '2026-03-05');
    expect(nominationStanding(next, next.nominations[0], '2026-03-05').supports).toBe(1);
    expect(nominationStanding(next, next.nominations[0], '2026-03-11').supports).toBe(2);
  });

  it('takes a supporter off the count when they object instead', () => {
    const supported = supportNomination(opened, 'dan', 'bob', '2026-03-03');
    const objected = objectToNomination(supported, 'dan', 'bob', 'changed my mind', '2026-03-04');
    expect(objected.nominations[0].supports).toEqual([{ member: 'alice', date: '2026-03-01' }]);
  });

  it('never mutates the config it is given', () => {
    supportNomination(opened, 'dan', 'bob', '2026-03-03');
    expect(opened.nominations[0].supports).toHaveLength(1);
  });

  it('shows a refusal as an explanation, not as a raw error', () => {
    let message = '';
    try {
      supportNomination(opened, 'dan', 'erin', '2026-03-02');
    } catch (e) {
      message = friendlyError(e, 'save');
    }
    expect(message).toContain('active board member');
    expect(message).not.toContain('GitHub is not responding');
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
      supports: [{ member: 'alice', date: '2026-03-01' }],
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
    const resolved = resolveNominations(backed(config(), 'dan', 'alice', '2026-03-01'), '2026-03-20');
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
      supports: [],
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

  it('re-opens the nomination and restarts the window from the withdrawal', () => {
    const next = withdrawObjection(deferred, 'dan', 'bob', '2026-04-01');
    expect(next.nominations).toHaveLength(1);
    expect(next.nominations[0]).toEqual({
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '2026-04-01',
      // Recorded on the day the nomination was first opened, and still
      // counted: there is no lower bound on the window, so a restart does
      // not ask a member who has already said yes to say it again.
      supports: [{ member: 'alice', date: '2026-03-01' }],
      objections: [],
      outcome: '',
    });
    // The spent original window does not settle it: a board that was told the
    // nomination was deferred gets a real window on it again. On the original
    // opening this would already have run out.
    expect(resolveNominations(next, '2026-04-05').nominations[0].outcome).toBe('');
    expect(resolveNominations(next, '2026-04-16').nominations[0].outcome).toBe('deferred');
  });

  it('keeps counting a support recorded before the window restarted', () => {
    // The other half of the same rule, on a nomination the board actually
    // carries: two members had said yes before the objection, and the
    // withdrawal does not send them back to the screen to say it twice.
    const carrying = backed(config(), 'dan', 'alice', '2026-03-01');
    const objected = objectToNomination(carrying, 'dan', 'bob', 'too soon', '2026-03-02');
    const reopened = withdrawObjection(objected, 'dan', 'bob', '2026-04-01');

    expect(reopened.nominations[0].supports.map(s => s.member)).toEqual(['alice', 'carol']);
    expect(nominationStanding(reopened, reopened.nominations[0], '2026-04-02').supports).toBe(2);
    // Two of the three it takes, so the withdrawal alone seats nobody.
    expect(resolveNominations(reopened, '2026-04-02').nominations[0].outcome).toBe('');
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
      supports: [],
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
  /** One support -- the sponsor's -- on a board of three, so the bar is not
   *  met and the days are what settle it. */
  const opened = openNomination(SPEAKERS, config(), 'dan', 'alice', '2026-03-01');
  /** The same nomination with the board behind it. */
  const carried = backed(config(), 'dan', 'alice', '2026-03-01');

  it('leaves a nomination alone before the window closes', () => {
    const next = resolveNominations(opened, '2026-03-07');
    expect(next).toEqual(opened);
    expect(next.nominations[0].outcome).toBe('');
  });

  it('defers a nomination the board never carried once the window has run', () => {
    // Silence counts as refusal. Nobody objected, nobody but the sponsor
    // said yes, and the days running out settles the question instead of
    // granting it.
    const day = new Date(Date.parse('2026-03-01') + NOMINATION_WINDOW_DAYS * 86400000)
      .toISOString()
      .slice(0, 10);
    const next = resolveNominations(opened, day);
    expect(next.nominations[0].outcome).toBe('deferred');
    expect(next.board).toHaveLength(3);
  });

  it('seats the candidate the moment the supports reach the bar', () => {
    // No waiting for the window: the arithmetic decides and a member writes
    // it down, exactly as a speaker's vote closes on the ballot that reaches
    // the bar.
    const next = resolveNominations(carried, '2026-03-02');
    expect(next.nominations[0].outcome).toBe('accepted');
    expect(next.board.some(m => m.login === 'dan' && m.status === 'active')).toBe(true);
  });

  it('does not count a support recorded after the window closed', () => {
    // The days are the whole of the chance the board gets. A late click on
    // the twentieth day would otherwise carry a nomination the board had
    // already let run out.
    const late = {
      ...opened,
      nominations: [
        {
          ...opened.nominations[0],
          supports: [
            ...opened.nominations[0].supports,
            { member: 'bob', date: '2026-03-25' },
            { member: 'carol', date: '2026-03-26' },
          ],
        },
      ],
    };
    expect(nominationStanding(late, late.nominations[0], '2026-03-26').supports).toBe(1);
    expect(resolveNominations(late, '2026-03-26').nominations[0].outcome).toBe('deferred');
  });

  it('adds the accepted member to the board with joined_on at the resolution date', () => {
    const next = resolveNominations(carried, '2026-03-09');
    expect(next.board).toHaveLength(4);
    expect(next.board[3]).toEqual({
      login: 'dan',
      joined_on: '2026-03-09',
      status: 'active',
      unavailable_until: '',
    });
  });

  it('never records an acceptance without seating the member', () => {
    const next = resolveNominations(carried, '2026-03-09');
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
      nominations: carried.nominations,
    });
    const next = resolveNominations(cfg, '2026-03-09');
    // One entry, now active -- and it keeps the day dan actually joined the
    // board. `joined_on` is not the day of the most recent nomination, and
    // the inactivity rule (G-14) reads it as the start of its window, so
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
        member('carol'),
        member('dan', { joined_on: '2019-04-02', unavailable_until: '2026-06-30' }),
      ],
      nominations: carried.nominations,
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
      nominations: carried.nominations,
    });
    const next = resolveNominations(cfg, '2026-03-09');
    expect(next.board.filter(m => m.login === 'dan')).toEqual([
      { login: 'dan', joined_on: '2019-04-02', status: 'active', unavailable_until: '2026-06-30' },
    ]);
  });

  it('holds the nomination as waiting when the board is already at board_max', () => {
    const cfg = config({ board_max: 3, nominations: carried.nominations });
    const next = resolveNominations(cfg, '2026-03-09');
    expect(next.nominations[0].outcome).toBe('waiting');
    expect(next.board).toHaveLength(3);
  });

  it('leaves a waiting nomination waiting while the board stays full', () => {
    const cfg = config({ board_max: 3, nominations: carried.nominations });
    const waiting = resolveNominations(cfg, '2026-03-09');
    expect(resolveNominations(waiting, '2027-01-01')).toEqual(waiting);
  });

  it('seats a waiting nomination as soon as a seat frees up', () => {
    const cfg = config({ board_max: 3, nominations: carried.nominations });
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
    cfg = backed(cfg, 'dan', 'alice', '2026-03-01', speakers);
    cfg = backed(cfg, 'erin', 'alice', '2026-03-01', speakers);
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
      supports: [],
      objections: [{ member: 'bob', reason: 'hand-edited', date: '2026-03-02' }],
      outcome: '',
    };
    const next = resolveNominations(config({ nominations: [handEdited] }), '2026-06-01');
    expect(next.nominations[0].outcome).toBe('deferred');
  });

  it('never revisits an accepted nomination', () => {
    const accepted = resolveNominations(carried, '2026-03-09');
    const again = resolveNominations(accepted, '2026-04-09');
    expect(again).toEqual(accepted);
    expect(again.board.filter(m => m.login === 'dan')).toHaveLength(1);
  });

  it('never seats anybody on the clock alone, whatever the date', () => {
    // The clock can settle a nomination and it can never grant one. On a
    // nomination the board has not carried, every date this reaches produces
    // an open question or a deferral, and the board is the size it was.
    const outcomes = new Set<string>();
    for (const day of ['2026-03-02', '2026-03-09', '2027-01-01']) {
      const next = resolveNominations(opened, day);
      for (const n of next.nominations) outcomes.add(n.outcome);
      expect(next.board).toHaveLength(3);
    }
    expect([...outcomes].every(o => o === '' || o === 'deferred')).toBe(true);
  });

  it('produces no refusal, because the vocabulary has none', () => {
    // A deferral is a question moved to another room. Nothing anywhere can
    // write an outcome that closes against the candidate, and this is the
    // clause that says the vocabulary is still those three.
    const seen = new Set<string>();
    for (const source of [opened, carried, objectToNomination(opened, 'dan', 'bob', 'x', '2026-03-02')]) {
      for (const day of ['2026-03-02', '2027-01-01']) {
        for (const n of resolveNominations(source, day).nominations) seen.add(n.outcome);
      }
    }
    expect([...seen].every(o => o === '' || o === 'accepted' || o === 'deferred' || o === 'waiting')).toBe(true);
  });

  it('does not accept a nomination whose opening date is unusable', () => {
    const broken: Nomination = {
      candidate: 'dan',
      sponsor: 'alice',
      opened_on: '',
      supports: [],
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
      nominations: carried.nominations,
    });
    const next = resolveNominations(cfg, '2026-03-09');
    expect(next.nominations[0].outcome).toBe('accepted');
    expect(next.board.filter(m => m.login === 'dan')).toHaveLength(1);
  });

  it('never mutates the config it is given', () => {
    resolveNominations(carried, '2026-03-09');
    expect(carried.board).toHaveLength(3);
    expect(carried.nominations[0].outcome).toBe('');
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
  it('asks for two co-hosted webinars, a fortnight, and a majority', () => {
    expect(NOMINATION_MIN_CO_HOSTED).toBe(2);
    expect(NOMINATION_WINDOW_DAYS).toBe(14);
    expect(NOMINATION_MINIMUM_SUPPORTS).toBe(3);
    // More than half, and never below the floor. A board of two would put a
    // majority at one, and one member seating another is the whole of what
    // the floor is there to stop.
    expect([0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(nominationBar)).toEqual([
      3, 3, 3, 3, 3, 3, 4, 4, 5, 5,
    ]);
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
