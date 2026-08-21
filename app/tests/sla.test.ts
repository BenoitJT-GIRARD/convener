import { describe, expect, it } from 'vitest';
import {
  SLA_STEPS,
  STEP_LABELS,
  SUMMARY_ITEM,
  byUrgency,
  dueDate,
  lateness,
  overdueDays,
  overdueText,
  waitingSince,
  type Lateness,
  type Overdue,
} from '../src/state/sla';
import type { Config, Speaker, SpeakerStatus } from '../src/data/types';
import { speaker as double } from './data-doubles';

/** The values `data/config.yml` actually carries, so the arithmetic is pinned
 *  against the real turnaround times and not against round numbers. */
const config: Config = {
  season: 2026, vw_counter: 5, overlap_window_days: 7,
  seminar_duration_minutes: 90, eligibility_share: 0.6666666666666666, board: [], nominations: [],
  board_min: 5, board_max: 9, vote_window_days: 14,
  objection_window_working_days: 3, inactivity_months: 6,
  balance_window_months: 24,
  view_count_window_days: 30,
  sla_days: {
    invitation_follow_up: 30,
    summary_after_delivery: 7,
    recording_after_delivery: 14,
  },
  channels: [],
  instructions: '',
};

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
function speaker(status: SpeakerStatus, overrides: Partial<Speaker> = {}): Speaker {
  return double({
    id: 'spk-001', name: 'A Speaker', gender: 'undisclosed', career_stage: 'undisclosed',
    email: '', affiliation: '', country: '', title: '', abstract: '',
    conflicts_of_interest: '', source: 'organizer', proposed_by: '', assigned_to: '',
    links: [], host_1: '', host_2: '', status,
    selection: { ballots: [], opened_on: '', decided_on: '' },
    publication: {
      consent: 'pending', approved_by: '', approved_on: '', objections: [], outcome: '',
    },
    edition_code: '', date: '', time: '', zoom_link: '', youtube_url: '',
    forum_thread: '', runbook_progress: {}, notes: '',
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
    ...overrides,
  });
}

function lead(opened_on: string): Speaker {
  return speaker('lead', { selection: { ballots: [], opened_on, decided_on: '' } });
}

function invited(decided_on: string): Speaker {
  return speaker('invited', { selection: { ballots: [], opened_on: '2026-01-01', decided_on } });
}

/** Delivered with neither artefact in: both wrap-up clocks running. */
function delivered(date: string, overrides: Partial<Speaker> = {}): Speaker {
  return speaker('delivered', { date, ...overrides });
}

// ─────────────────────────────────────────────────────────── the four deadlines

describe('dueDate', () => {
  it('gives the board 14 calendar days from the day the vote window opened', () => {
    expect(dueDate(lead('2026-08-18'), config)).toEqual({
      step: 'Board decision', due: '2026-09-01', since: '2026-08-18',
    });
  });

  it('gives the invitation 30 calendar days before a follow-up is due', () => {
    expect(dueDate(invited('2026-08-18'), config)).toEqual({
      step: 'Invitation follow-up', due: '2026-09-17', since: '2026-08-18',
    });
  });

  it('gives the summary 7 days from delivery, and it is the sooner of the two', () => {
    expect(dueDate(delivered('2026-08-01'), config)).toEqual({
      step: 'Forum summary', due: '2026-08-08', since: '2026-08-01',
    });
  });

  it('gives the recording 14 days from delivery, once the summary is posted', () => {
    const s = delivered('2026-08-01', { runbook_progress: { [SUMMARY_ITEM]: true } });
    expect(dueDate(s, config)).toEqual({
      step: 'Recording', due: '2026-08-15', since: '2026-08-01',
    });
  });

  it('follows the config when it is the recording that is given the tighter target', () => {
    // The four values are adjustable without code (spec section 7), so which
    // of the two wrap-up steps comes first must not be baked in here.
    const tighter: Config = {
      ...config,
      sla_days: { ...config.sla_days, summary_after_delivery: 14, recording_after_delivery: 3 },
    };
    expect(dueDate(delivered('2026-08-01'), tighter)).toEqual({
      step: 'Recording', due: '2026-08-04', since: '2026-08-01',
    });
  });

  it('counts calendar days, so a window opened on a Friday is not pushed past a weekend', () => {
    // 2026-08-14 is a Friday. Fourteen working days would land on 2026-09-03;
    // fourteen calendar days land on 2026-08-28. The unit is calendar.
    expect(dueDate(lead('2026-08-14'), config)?.due).toBe('2026-08-28');
  });

  it('crosses a month and a leap-year February without drifting', () => {
    expect(dueDate(lead('2028-02-20'), config)?.due).toBe('2028-03-05');
  });
});

describe('dueDate with nothing applicable', () => {
  it('has no deadline for a lead whose vote window was never opened', () => {
    expect(dueDate(lead(''), config)).toBeNull();
  });

  it('has no deadline for an invitation with no recorded decision day', () => {
    expect(dueDate(invited(''), config)).toBeNull();
  });

  it('has no deadline for a delivered talk with no recorded date', () => {
    expect(dueDate(delivered(''), config)).toBeNull();
  });

  it('stops having a wrap-up deadline once both artefacts are in', () => {
    const done = delivered('2026-08-01', {
      runbook_progress: { [SUMMARY_ITEM]: true },
      youtube_url: 'https://youtu.be/x',
    });
    expect(dueDate(done, config)).toBeNull();
  });

  it('keeps the recording clock when only the summary is posted, and the reverse', () => {
    const noRecording = delivered('2026-08-01', {
      runbook_progress: { [SUMMARY_ITEM]: true },
    });
    const noSummary = delivered('2026-08-01', { youtube_url: 'https://youtu.be/x' });
    expect(dueDate(noRecording, config)?.step).toBe('Recording');
    expect(dueDate(noSummary, config)?.step).toBe('Forum summary');
  });

  it.each<SpeakerStatus>(['approved', 'confirmed', 'scheduled', 'archived', 'parked',
    'decline-board', 'decline-speaker'])(
    'sets no turnaround time on a %s record',
    status => {
      expect(dueDate(speaker(status, { date: '2026-08-01' }), config)).toBeNull();
    },
  );
});

// ────────────────────────────────────────────────────────────────── overdueDays

describe('overdueDays', () => {
  it('is 0 before the deadline', () => {
    expect(overdueDays(lead('2026-08-18'), config, '2026-08-25')).toBe(0);
  });

  it('is 0 on the due day itself, which is still within the target', () => {
    expect(overdueDays(lead('2026-08-18'), config, '2026-09-01')).toBe(0);
  });

  it('is positive the day after, and grows by one a day', () => {
    expect(overdueDays(lead('2026-08-18'), config, '2026-09-02')).toBe(1);
    expect(overdueDays(lead('2026-08-18'), config, '2026-09-05')).toBe(4);
  });

  it('is 0, never negative, when there is no deadline at all', () => {
    expect(overdueDays(lead(''), config, '2026-09-05')).toBe(0);
  });
});

// ─────────────────────────────────────────────────────── the zero is not drawable

describe('lateness', () => {
  it('carries no day count at all while a step is still within its target', () => {
    const l = lateness(lead('2026-08-18'), config, '2026-08-25');
    expect(l.state).toBe('due');
    expect(l).not.toHaveProperty('days');
  });

  it('carries no day count for a step with no deadline', () => {
    const l = lateness(lead(''), config, '2026-08-25');
    expect(l).toEqual({ state: 'none' });
  });

  it('never reports a lateness of zero days', () => {
    // Every day either side of the boundary, for a fortnight: whenever a
    // `days` count exists it is at least 1, so no "0 days overdue" can be
    // built from any state this function can return.
    for (let i = 0; i < 30; i++) {
      const today = new Date(Date.parse('2026-08-18T00:00:00Z') + i * 86_400_000)
        .toISOString().slice(0, 10);
      const l = lateness(lead('2026-08-18'), config, today);
      if (l.state === 'overdue') expect(l.days).toBeGreaterThanOrEqual(1);
    }
  });

  it('reports the day count and the day it has been waiting since', () => {
    expect(lateness(lead('2026-08-18'), config, '2026-09-04')).toEqual({
      state: 'overdue', days: 3, step: 'Board decision',
      due: '2026-09-01', since: '2026-08-18',
    });
  });
});

// ───────────────────────────────────────────────────────────────────── the sort

const none: Lateness = { state: 'none' };
const overdue = (days: number, due: string): Overdue => ({
  state: 'overdue', days, step: 'Board decision', due, since: '2026-08-18',
});
const due = (d: string): Lateness => ({
  state: 'due', step: 'Board decision', due: d, since: '2026-08-18',
});

describe('byUrgency', () => {
  it('puts the longest-waiting step first and items with no deadline last', () => {
    const rows: Lateness[] = [
      none,
      due('2026-09-30'),
      overdue(3, '2026-09-01'),
      none,
      overdue(40, '2026-07-25'),
      due('2026-09-10'),
    ];
    const sorted = [...rows].sort(byUrgency);
    expect(sorted.map(l => (l.state === 'none' ? 'none' : `${l.state}:${l.due}`))).toEqual([
      'overdue:2026-07-25',
      'overdue:2026-09-01',
      'due:2026-09-10',
      'due:2026-09-30',
      'none',
      'none',
    ]);
  });

  it('never floats an item with no deadline above one that is late', () => {
    // The load-bearing half: a numeric key that reads "no deadline" as zero
    // would put these 7 undated records at the top and bury everything real.
    expect(byUrgency(none, overdue(40, '2026-07-25'))).toBeGreaterThan(0);
    expect(byUrgency(overdue(40, '2026-07-25'), none)).toBeLessThan(0);
    expect(byUrgency(none, due('2026-09-30'))).toBeGreaterThan(0);
    expect(byUrgency(due('2026-09-30'), none)).toBeLessThan(0);
  });

  it('treats two items with no deadline, and two with the same one, as ties', () => {
    expect(byUrgency(none, none)).toBe(0);
    expect(byUrgency(overdue(3, '2026-09-01'), overdue(3, '2026-09-01'))).toBe(0);
  });
});

// ──────────────────────────────────────────────────────── the wording, and whom
//                                                          it is about

describe('the wording a volunteer reads', () => {
  it('is a readable phrase about the step, not a code', () => {
    expect(overdueText(overdue(3, '2026-09-01'))).toBe(
      'Board decision is 3 days overdue',
    );
    expect(waitingSince(overdue(3, '2026-09-01'))).toBe(
      'waiting since 2026-08-18',
    );
  });

  it('says "1 day" rather than "1 days"', () => {
    expect(overdueText(overdue(1, '2026-09-01'))).toBe(
      'Board decision is 1 day overdue',
    );
  });

  it('names a step, never anyone who might be holding it', () => {
    // Every name a record can carry, on each of the three statuses that bear a
    // deadline. `assigned_to` is the board member who owns the lead and
    // `proposed_by` is whoever submitted it -- neither may reach this wording,
    // and nor may the speaker or the hosts.
    const names = {
      assigned_to: 'Anonymous', proposed_by: 'Anonymous',
      host_1: 'Anonymous', host_2: 'Anonymous', name: 'Anonymous',
    };
    const late = [
      speaker('lead', {
        ...names, selection: { ballots: [], opened_on: '2026-01-05', decided_on: '' },
      }),
      speaker('invited', {
        ...names, selection: { ballots: [], opened_on: '2026-01-05', decided_on: '2026-01-20' },
      }),
      delivered('2025-02-05', names),
      delivered('2025-02-05', { ...names, runbook_progress: { [SUMMARY_ITEM]: true } }),
    ];
    for (const s of late) {
      const l = lateness(s, config, '2026-08-18');
      if (l.state !== 'overdue') throw new Error('expected an overdue step');
      const shown = `${l.step} | ${overdueText(l)} | ${waitingSince(l)}`;
      for (const person of ['Anonymous', 'Anonymous', 'Anonymous', 'Anonymous', 'Anonymous',
        'Anonymous', 'Anonymous', 'Anonymous']) {
        expect(shown).not.toContain(person);
      }
    }
  });

  it('has no vocabulary of blame anywhere in what it can say', () => {
    // Same instinct as the board-inactivity sweep, which describes the ballot
    // record rather than the member. There is no free slot these words could
    // enter through, and this pins that they have not crept into the labels.
    const banned = ['removed', 'expelled', 'dropped', 'failed', 'negligent',
      'left', 'blame', 'fault', 'ignored', 'forgot', 'responsible', 'owner',
      'nobody', 'chase'];
    const everything = [
      ...Object.values(STEP_LABELS),
      overdueText(overdue(1, '2026-09-01')),
      overdueText(overdue(9, '2026-09-01')),
      waitingSince(overdue(9, '2026-09-01')),
    ].join(' ').toLowerCase();
    for (const word of banned) {
      expect(everything).not.toMatch(new RegExp(`\\b${word}`));
    }
  });

  it('labels every configured step, and labels none of them as a role', () => {
    expect(Object.keys(STEP_LABELS).sort()).toEqual([...SLA_STEPS].sort());
    // Three of the four steps are read off `sla_days`; the board's decision
    // is timed by `vote_window_days`, so the config has exactly one number
    // per deadline and no key a second one could live in (F-13).
    expect(Object.keys(STEP_LABELS).sort()).toEqual(
      [...Object.keys(config.sla_days), 'lead_decision'].sort(),
    );
    for (const label of Object.values(STEP_LABELS)) {
      expect(label).not.toMatch(/\b(board member|volunteer|host|you)\b/i);
    }
  });
});

// ───────────────────────────────────────────── honesty on the repository's data

describe('on the data this repository actually holds', () => {
  /** 24 leads whose vote window was opened in one go by the backfill, plus the
   *  7 speakers that carry no `opened_on` at all. */
  const backfilled = Array.from({ length: 24 }, () => lead('2026-08-18'));
  const undated = Array.from({ length: 7 }, () => lead(''));

  it('shows nothing as late on the day of the backfill', () => {
    for (const s of [...backfilled, ...undated]) {
      expect(lateness(s, config, '2026-08-18').state).not.toBe('overdue');
    }
  });

  it('invents no deadline for the 7 records with no recorded day', () => {
    for (const s of undated) expect(dueDate(s, config)).toBeNull();
  });

  it('shows the one shared start day when all 24 fall due together', () => {
    // They will, on 2026-09-02, all reading the same lateness. The display is
    // honest about why: one identical "waiting since" across all of them says
    // this was a single bulk opening, not 24 separate slips.
    const lines = backfilled.map(s => {
      const l = lateness(s, config, '2026-09-02');
      if (l.state !== 'overdue') throw new Error('expected an overdue step');
      return `${overdueText(l)}, ${waitingSince(l)}`;
    });
    expect(new Set(lines).size).toBe(1);
    expect(lines[0]).toBe('Board decision is 1 day overdue, waiting since 2026-08-18');
  });

  it('leaves the four delivered talks at the top and the undated ones at the bottom', () => {
    const rows = [
      ...undated,
      ...backfilled,
      delivered('2025-02-05'),
      delivered('2026-04-02'),
    ];
    const sorted = rows
      .map(s => lateness(s, config, '2026-08-18'))
      .sort(byUrgency);
    expect(sorted[0]).toMatchObject({ state: 'overdue', step: 'Forum summary' });
    expect(sorted[1]).toMatchObject({ state: 'overdue', step: 'Forum summary' });
    expect(sorted.slice(-7).every(l => l.state === 'none')).toBe(true);
  });
});
