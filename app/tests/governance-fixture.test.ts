import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import cases from '../../tools/tests/fixtures/governance-cases.json';
import { decide, thresholdFor } from '../src/state/governance';
import type { BallotLike } from '../src/state/governance';
import { lateness, overdueText, waitingSince } from '../src/state/sla';
import { isBallotValue } from '../src/data/types';
import type { Config, Speaker, SpeakerStatus } from '../src/data/types';
import { speaker as double } from './data-doubles';

/** The fixture is JSON, so every ballot value arrives as a bare string. It is
 *  narrowed through the same guard the app uses rather than cast: a typo in the
 *  shared fixture then fails here instead of quietly counting as a non-yes. */
function ballot(raw: { voter: string; value: string }): BallotLike {
  if (!isBallotValue(raw.value)) {
    throw new Error(`unknown ballot value in the shared fixture: ${raw.value}`);
  }
  return { voter: raw.voter, value: raw.value };
}

describe('the shared governance fixture', () => {
  it.each(cases.threshold_cases)('$name', ({ eligible, expected }) => {
    expect(thresholdFor(eligible)).toBe(expected);
  });

  it.each(cases.decision_cases)('$name', c => {
    const outcome = decide({
      board: c.board,
      unavailable: c.unavailable,
      ballots: c.ballots.map(ballot),
    });
    expect(outcome.eligible).toBe(c.eligible);
    expect(outcome.threshold).toBe(c.threshold);
    expect(outcome.yes).toBe(c.yes);
    expect(outcome.decided).toBe(c.decided);
    expect(outcome.suspended).toBe(c.suspended);
  });
});

/**
 * One `lateness_cases` entry.
 *
 * `days`, `overdue_text` and `waiting_since` are optional here for the same
 * reason `Lateness` carries `days` on one arm only: a step that is not late
 * has no day count and no sentence, so the fixture has nothing to record for
 * it. The JSON import types the array as a union of the shapes present, which
 * is not a shape a test can index; this interface is the one place that is
 * reconciled, and every access below is still checked against it.
 */
interface LatenessCase {
  name: string;
  speaker: {
    status: string;
    selection: { opened_on: string; decided_on: string };
    date: string;
    youtube_url: string;
    runbook_progress: Record<string, boolean>;
  };
  config: { vote_window_days: number; sla_days: Config['sla_days'] };
  today: string;
  state: 'none' | 'due' | 'overdue';
  step?: string;
  due?: string;
  since?: string;
  days?: number;
  overdue_text?: string;
  waiting_since?: string;
}

const latenessCases = cases.lateness_cases as unknown as LatenessCase[];

/** The two windows the case names, in a config the reader will take. Both
 *  come from the fixture, so a case that moves the vote window moves the
 *  board-decision deadline with it -- there is no second number here that
 *  could stay at 14 (F-13). */
function configFor(c: LatenessCase): Config {
  return {
    season: 2026, next_edition_number: 5, overlap_window_days: 7,
    seminar_duration_minutes: 90, eligibility_share: 0.6666666666666666, board: [], nominations: [],
    board_min: 5, board_max: 9, vote_window_days: c.config.vote_window_days,
    objection_window_working_days: 3, inactivity_months: 6,
    balance_window_months: 24, view_count_window_days: 30,
    sla_days: c.config.sla_days, channels: [],
    instructions: '',
  };
}

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
function speakerFor(c: LatenessCase): Speaker {
  return double({
    id: 'spk-001', name: '', gender: 'undisclosed', career_stage: 'undisclosed',
    email: '', affiliation: '', country: '', title: '', abstract: '',
    conflicts_of_interest: '', source: 'organizer', proposed_by: '', assigned_to: '',
    links: [], host_1: '', host_2: '',
    status: c.speaker.status as SpeakerStatus,
    selection: { ballots: [], ...c.speaker.selection },
    publication: {
      consent: 'pending', approved_by: '', approved_on: '', objections: [], outcome: '',
    },
    edition_code: '', date: c.speaker.date, time: '', zoom_link: '',
    youtube_url: c.speaker.youtube_url, forum_thread: '',
    runbook_progress: c.speaker.runbook_progress, notes: '',
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  });
}

describe('the overdue wording, shared with the daily digest', () => {
  /* These sentences are rendered on the screens by `sla.ts` and posted in the
   * notification digest by `tools/convener_ops/notify.py`. One sentence, two
   * readers: a reword that reaches only one side fails here and in
   * `tools/tests/test_governance_fixture.py` at the same time. */
  it.each(latenessCases)('$name', c => {
    const l = lateness(speakerFor(c), configFor(c), c.today);
    expect(l.state).toBe(c.state);
    if (l.state === 'none') return;

    expect(l.step).toBe(c.step);
    expect(l.due).toBe(c.due);
    expect(l.since).toBe(c.since);
    if (l.state !== 'overdue') return;

    expect(l.days).toBe(c.days);
    expect(overdueText(l)).toBe(c.overdue_text);
    expect(waitingSince(l)).toBe(c.waiting_since);
  });
});

/** Every underscore-prefixed key of the fixture is a prose comment
 *  documenting a neighbouring block, not data either language reads -- see
 *  the sibling comment in `tools/tests/test_governance_fixture.py`. */
const topLevelCaseKeys = Object.keys(cases).filter(key => !key.startsWith('_'));

function escapeForRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Every file under `dir` whose name matches `suffix`, read as one blob --
 *  the same flat `readdirSync` walk `dates.test.ts`'s cast-site sweep uses,
 *  narrowed to a suffix filter since neither `tools/tests/` nor
 *  `app/tests/` nests test files in subdirectories. */
function corpus(dir: string, suffix: string): string {
  return readdirSync(dir)
    .filter(name => name.endsWith(suffix))
    .map(name => readFileSync(resolve(dir, name), 'utf-8'))
    .join('\n');
}

/** Whether `key` is used as a fixture lookup somewhere in `text`: a quoted
 *  subscript (`CASES["name"]`, the shape every Python reader of this
 *  fixture uses) or a dotted property access (`cases.name`, the shape this
 *  file and its TypeScript neighbours use). A bare, unquoted mention in
 *  prose matches neither, so a comment that merely names a block does not
 *  count as reading it. */
function isReadSomewhere(key: string, text: string): boolean {
  const escaped = escapeForRegExp(key);
  const quoted = new RegExp(`(['"])${escaped}\\1`).test(text);
  const dotted = new RegExp(`\\.${escaped}\\b`).test(text);
  return quoted || dotted;
}

describe('every top-level fixture key is read by somebody -- entry 4 of the deferred-work register', () => {
  // An empty key list would pass the check below vacuously.
  it('is a real sweep: the fixture actually has top-level blocks to check', () => {
    expect(topLevelCaseKeys.length).toBeGreaterThan(0);
  });

  it('every block is read by at least one test, in either language', () => {
    // Neither this module nor `tools/tests/test_governance_fixture.py` used
    // to assert full coverage of `governance-cases.json` -- only the named
    // blocks each happened to already read. A block could be added and go
    // unread on both sides indefinitely, which is exactly the drift D-14's
    // shared fixture exists to prevent: it links the two implementations
    // only for the cases somebody actually wired up.
    //
    // "Read by somebody" does not require both languages to read the same
    // block -- some blocks describe a rule with no browser-side counterpart
    // (the webhook-signature cases, for instance, exercised only on the
    // Python side) -- only that at least one real test, in either
    // language, actually looks the block up.
    const toolsTests = resolve(__dirname, '../../tools/tests');
    const text = [
      corpus(toolsTests, '.py'),
      corpus(__dirname, '.test.ts'),
      corpus(__dirname, '.test.tsx'),
    ].join('\n');

    const unread = topLevelCaseKeys.filter(key => !isReadSomewhere(key, text));
    expect(unread, `fixture key(s) read by nobody: ${JSON.stringify(unread)}`).toEqual([]);
  });
});
