/**
 * A conflict of interest that was never declared, coming to light after the
 * board has already accepted the speaker.
 *
 * The rule: the acceptance is cancelled. It was reached with someone in the
 * denominator who should not have been there, so it does not stand and is not
 * re-confirmed by the same people -- the speaker goes back to `lead` and the
 * window reopens. Everything here is one pure call on `applyTransition`; the
 * form that drives it lives in `components/AdminOverride.tsx` and is covered
 * in `admin-override.test.tsx`.
 */
import { describe, it, expect } from 'vitest';
import { applyTransition, canTransition, type Transition } from '../src/state/transitions';
import { BallotRejected } from '../src/state/ballots';
import { decide } from '../src/state/governance';
import { activeBoard } from '../src/state/board';
import { friendlyError } from '../src/github/errors';
import { substitute } from '../src/content/render';
import type { Ballot, BoardMember, Config, Speaker, SpeakerStatus } from '../src/data/types';

const TODAY = '2026-06-10';

function board(logins: string[]): BoardMember[] {
  return logins.map(login => ({
    login,
    joined_on: '2024-01-01',
    status: 'active' as const,
    unavailable_until: '',
  }));
}

function cfg(logins: string[]): Config {
  return {
    season: 2026,
    vw_counter: 1,
    overlap_window_days: 7,
    seminar_duration_minutes: 90,
    board: board(logins),
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
}

/** Four active members, so `thresholdFor(4)` is 3 -- and 3 again once one of
 *  them is recused out of the count, since `MINIMUM_YES` is the floor. */
const FOUR = cfg(['ana', 'ben', 'cleo', 'dai']);

function ballot(voter: string, overrides: Partial<Ballot> = {}): Ballot {
  return { voter, value: 'yes', comment: '', coi_reason: '', date: '2026-05-20', ...overrides };
}

function speaker(overrides: Partial<Speaker> = {}): Speaker {
  return {
    id: 'spk-042',
    name: 'Rita Levi',
    gender: 'F',
    career_stage: 'group-leader',
    email: 'rita@example.org',
    affiliation: 'Institute of Things',
    country: 'IT',
    title: 'On learning',
    abstract: 'A talk about learning.',
    conflicts_of_interest: '',
    source: 'form',
    proposed_by: 'Someone Outside',
    assigned_to: 'ana',
    links: [],
    host_1: 'ben',
    host_2: 'dai',
    status: 'approved',
    selection: {
      ballots: [ballot('ana'), ballot('ben'), ballot('cleo')],
      opened_on: '2026-05-01',
      decided_on: '2026-05-20',
    },
    publication: {
      consent: 'pending',
      approved_by: '',
      approved_on: '',
      objections: [],
      outcome: '',
    },
    edition_code: 'MRG-9',
    date: '2026-09-15',
    time: '12:30',
    zoom_link: 'https://zoom.example/9',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: { 'approved/invitation-sent': true },
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
    notes: '',
    ...overrides,
  };
}

function reopen(s: Speaker, actor: string, member: string, reason: string, config = FOUR): Speaker {
  return applyTransition(s, 'vote-reopen', actor, config, TODAY, { member, reason });
}

describe('vote-reopen: who may do it', () => {
  it('is the board’s to use and no one else’s', () => {
    const s = speaker();
    expect(canTransition(s, 'vote-reopen', 'board')).toBe(true);
    expect(canTransition(s, 'vote-reopen', 'organizer')).toBe(false);
  });

  it('is offered wherever a board acceptance is still live', () => {
    const live: SpeakerStatus[] = [
      'lead',
      'approved',
      'invited',
      'confirmed',
      'scheduled',
      'parked',
      'decline-board',
    ];
    for (const status of live) {
      expect(canTransition(speaker({ status }), 'vote-reopen', 'board')).toBe(true);
    }
  });

  it('is refused once there is nothing left to cancel', () => {
    // The talk was given, or the speaker took themselves out. Reopening the
    // vote would rewrite history rather than withdraw an acceptance.
    const done: SpeakerStatus[] = ['delivered', 'archived', 'decline-speaker'];
    for (const status of done) {
      expect(canTransition(speaker({ status }), 'vote-reopen', 'board')).toBe(false);
    }
  });
});

describe('vote-reopen: what it does to the vote', () => {
  it('turns the concealed voter’s ballot into a recusal carrying the reason', () => {
    const next = reopen(speaker(), 'ana', 'cleo', 'Co-author on a paper in review');
    const theirs = next.selection.ballots.find(b => b.voter === 'cleo');
    expect(theirs?.value).toBe('recused');
    expect(theirs?.coi_reason).toContain('Co-author on a paper in review');
    expect(theirs?.date).toBe(TODAY);
  });

  it('records who declared it, so the act has an author in the data itself', () => {
    // No scheduled job has an author. The register naming a person is what
    // makes this a human act rather than something a cron run could produce.
    const next = reopen(speaker(), 'ana', 'cleo', 'Same lab until last year');
    const theirs = next.selection.ballots.find(b => b.voter === 'cleo');
    expect(theirs?.coi_reason).toContain('recorded by ana');
    expect(theirs?.coi_reason).toContain(TODAY);
  });

  it('replaces the ballot in place rather than adding a second one', () => {
    const next = reopen(speaker(), 'ana', 'cleo', 'Family tie');
    expect(next.selection.ballots.map(b => b.voter)).toEqual(['ana', 'ben', 'cleo']);
  });

  it('keeps the member’s own comment instead of erasing it', () => {
    const s = speaker({
      selection: {
        ballots: [ballot('ana'), ballot('ben'), ballot('cleo', { comment: 'Strong record.' })],
        opened_on: '2026-05-01',
        decided_on: '2026-05-20',
      },
    });
    const next = reopen(s, 'ana', 'cleo', 'Family tie');
    expect(next.selection.ballots.find(b => b.voter === 'cleo')?.comment).toBe('Strong record.');
  });

  it('clears the decision and reopens the window from today', () => {
    const next = reopen(speaker(), 'ana', 'cleo', 'Family tie');
    expect(next.selection.decided_on).toBe('');
    expect(next.selection.opened_on).toBe(TODAY);
  });

  it('cancels the acceptance and brings a speaker who had moved on back to lead', () => {
    for (const status of ['approved', 'invited', 'confirmed', 'scheduled'] as SpeakerStatus[]) {
      const next = reopen(speaker({ status }), 'ana', 'cleo', 'Family tie');
      expect(next.status).toBe('lead');
    }
  });

  it('recomputes the count immediately, on the shrunken board', () => {
    const next = reopen(speaker(), 'ana', 'cleo', 'Family tie');
    const { logins, unavailable } = activeBoard(FOUR, TODAY);
    const outcome = decide({ board: logins, unavailable, ballots: next.selection.ballots });
    // ana, ben, dai remain eligible; the floor of 3 holds the bar where it
    // was, and only two yes ballots are left, so the lead no longer passes.
    expect(outcome.eligible).toBe(3);
    expect(outcome.threshold).toBe(3);
    expect(outcome.yes).toBe(2);
    expect(outcome.decided).toBe(false);
  });

  it('cancels even when the remaining ballots would still clear the lower bar', () => {
    // Six members, bar of 4, five yes ballots. Recusing one leaves five
    // eligible, a bar of 4, and four yes -- `decide` says decided. The
    // acceptance is cancelled all the same: it was obtained on a false
    // basis, so it is not confirmed by the very people who reached it.
    const six = cfg(['ana', 'ben', 'cleo', 'dai', 'eve', 'fay']);
    const s = speaker({
      selection: {
        ballots: ['ana', 'ben', 'cleo', 'dai', 'eve'].map(v => ballot(v)),
        opened_on: '2026-05-01',
        decided_on: '2026-05-20',
      },
    });
    const next = reopen(s, 'fay', 'eve', 'Undisclosed grant with the speaker', six);
    const { logins, unavailable } = activeBoard(six, TODAY);
    const outcome = decide({ board: logins, unavailable, ballots: next.selection.ballots });
    expect(outcome.decided).toBe(true);
    expect(next.status).toBe('lead');
    expect(next.selection.decided_on).toBe('');
  });

  it('lets the board decide again, through a fresh ballot', () => {
    const reopened = reopen(speaker(), 'ana', 'cleo', 'Family tie');
    const next = applyTransition(reopened, 'ballot-cast', 'dai', FOUR, '2026-06-12', {
      value: 'yes',
      comment: '',
      coiReason: '',
    });
    expect(next.status).toBe('approved');
    expect(next.selection.decided_on).toBe('2026-06-12');
  });

  it('leaves the speaker it was given untouched', () => {
    const s = speaker();
    const before = JSON.parse(JSON.stringify(s));
    reopen(s, 'ana', 'cleo', 'Family tie');
    expect(s).toEqual(before);
  });
});

describe('vote-reopen: what it refuses, in words a volunteer can act on', () => {
  function rejection(fn: () => void): BallotRejected {
    try {
      fn();
    } catch (e) {
      expect(e).toBeInstanceOf(BallotRejected);
      return e as BallotRejected;
    }
    throw new Error('expected the transition to refuse');
  }

  it('refuses a declaration with no written reason', () => {
    const e = rejection(() => reopen(speaker(), 'ana', 'cleo', '   '));
    expect(e.message).toContain('written reason');
    // What the volunteer sees is the sentence, not a stack trace or a
    // GitHub status code.
    expect(friendlyError(e, 'save')).toBe(e.message);
  });

  it('refuses a name that is not on the board today', () => {
    const e = rejection(() => reopen(speaker(), 'ana', 'nobody', 'Family tie'));
    expect(e.message).toContain('not an active board member');
    expect(friendlyError(e, 'save')).toBe(e.message);
  });

  it('refuses when the member had already recused themselves', () => {
    // Nothing was concealed, and this must not become a general-purpose
    // button for cancelling an acceptance somebody dislikes.
    const s = speaker({
      selection: {
        ballots: [
          ballot('ana'),
          ballot('ben'),
          ballot('cleo', { value: 'recused', coi_reason: 'Former student' }),
        ],
        opened_on: '2026-05-01',
        decided_on: '',
      },
    });
    const e = rejection(() => reopen(s, 'ana', 'cleo', 'Family tie'));
    expect(e.message).toContain('already recused');
    expect(friendlyError(e, 'save')).toBe(e.message);
  });
});

describe('vote-reopen: the member is named in the register, never in what goes out', () => {
  /** Every placeholder `content/render.ts::buildContext` exposes. A field
   *  added there must be added here, or this test stops proving anything. */
  const OUTGOING = [
    'speaker.id',
    'speaker.name',
    'speaker.first_name',
    'speaker.email',
    'speaker.affiliation',
    'speaker.country',
    'speaker.gender',
    'speaker.title',
    'speaker.abstract',
    'speaker.edition_code',
    'speaker.date',
    'speaker.time',
    'speaker.zoom_link',
    'speaker.youtube_url',
    'speaker.forum_thread',
    'host_1.name',
    'host_2.name',
    'proposed_by.name',
  ];

  it('never writes the member’s name into anything a speaker email renders', () => {
    // A distinctive login, so a single substring check is conclusive.
    const config = cfg(['ana', 'ben', 'qwixby', 'dai']);
    const s = speaker({
      selection: {
        ballots: [ballot('ana'), ballot('ben'), ballot('qwixby')],
        opened_on: '2026-05-01',
        decided_on: '2026-05-20',
      },
    });
    const next = reopen(s, 'ana', 'qwixby', 'Undisclosed co-authorship', config);

    const template = OUTGOING.map(p => `{{${p}}}`).join('\n');
    const rendered = substitute(template, { speaker: next, today: TODAY });
    expect(rendered).not.toContain('qwixby');
    // The reason is not leaked either -- it explains a board member's
    // conflict, and it is nobody's business but the board's.
    expect(rendered).not.toContain('Undisclosed co-authorship');
  });

  it('changes nothing outside the status and the ballot register', () => {
    const before = speaker();
    const next = reopen(before, 'ana', 'cleo', 'Family tie');
    const stripped = (s: Speaker) => {
      const { status, selection, ...rest } = s;
      void status;
      void selection;
      return rest;
    };
    expect(stripped(next)).toEqual(stripped(before));
  });

  it('does name the member in the register, which is where it belongs', () => {
    const next = reopen(speaker(), 'ana', 'cleo', 'Family tie');
    expect(next.selection.ballots.some(b => b.voter === 'cleo' && b.value === 'recused')).toBe(
      true,
    );
  });
});

describe('vote-reopen: no automated path can reach it', () => {
  it('is board-only, like every other transition that can undo a decision', () => {
    // `sweep.py` parks a stale lead and can do nothing else; there is no
    // role in this app other than `board` and `organizer`, and the
    // organizer is refused. So the only way here is a signed-in board
    // member pressing a button.
    const undoing: Transition[] = ['vote-reopen', 'ballot-withdraw', 'override'];
    for (const t of undoing) {
      expect(canTransition(speaker({ status: 'lead' }), t, 'organizer')).toBe(false);
    }
  });

  it('never produces a refusal: the worst it can do is send a lead back to the queue', () => {
    for (const status of ['approved', 'invited', 'confirmed', 'scheduled'] as SpeakerStatus[]) {
      const next = reopen(speaker({ status }), 'ana', 'cleo', 'Family tie');
      expect(next.status).not.toBe('decline-board');
      expect(next.status).not.toBe('parked');
      expect(next.status).toBe('lead');
    }
  });
});
