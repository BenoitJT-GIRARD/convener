/**
 * Demo mode shows the example instance, and not an invention of its own.
 *
 * `src/data/demo.ts` used to hold five speaker records, a board and a
 * governance configuration written by hand -- a third fictional instance,
 * beside the one that runs this repository and the one
 * `examples/the-example-collective/` already is. Two of its strings named *this*
 * organisation's forum and its LinkedIn page, compiled into the cockpit's
 * own bundle, which is why `tools/tests/helpers/instance_identity.py`'s deferred
 * register once carried an entry for the file.
 *
 * The assertions below read `examples/the-example-collective/instance/data/` off the disk and
 * compare it with what the bundle actually holds. That is deliberately not
 * a comparison of one constant with itself: what reaches this bundle came
 * through `scripts/example-instance.mjs` and `vite.config.ts`'s own
 * `define`, so a copy of those records typed back into `demo.ts` -- the
 * exact regression this test exists to end -- fails here by name.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { DEMO_USER, demoConfig, demoSpeakers } from '../../src/data/demo';
import { parseConfig, parseSpeakers } from '../../src/data/yaml';
import type { SpeakerStatus } from '../../src/data/types';
import { shifted, today } from '../../scripts/example-dates.mjs';
import { MIN_REPORTING_BASIS, distribution } from '../../src/state/diversity';
import {
  NOMINATION_WINDOW_DAYS,
  coHostedCount,
  nominationStanding,
  resolveNominations,
} from '../../src/state/board';
import { parisToday } from '../../src/state/derived';
import { lateness } from '../../src/state/sla';

/** Every status the model has. Written out rather than imported: the type
 *  is a union of string literals and has no run-time form, and a status
 *  added to the union without a record behind it is exactly what the
 *  clause below exists to refuse -- so the list being a second statement
 *  of the vocabulary is the point of it. TypeScript refuses a member that
 *  is not one. */
const EVERY_STATUS: SpeakerStatus[] = [
  'lead',
  'approved',
  'invited',
  'confirmed',
  'scheduled',
  'delivered',
  'archived',
  'parked',
  'decline-board',
  'decline-speaker',
];

const REPOSITORY = resolve(dirname(fileURLToPath(import.meta.url)), '../..', '..');
const EXAMPLE = resolve(REPOSITORY, 'examples', 'the-example-collective', 'instance', 'data');

/** One of the example's own files, dated the way the build dates it.
 *  `scripts/example-instance.mjs` moves every day in these two by whole
 *  weeks on the way into the bundle, so the file on disk and the records
 *  the cockpit holds are the same records at two different ages -- and a
 *  comparison against the raw file would agree only during the anchor's
 *  own week and start failing on its own the following Thursday. */
function example(name: string): string {
  return shifted(readFileSync(resolve(EXAMPLE, name), 'utf8'), today());
}

describe('the demonstration', () => {
  it("holds the example instance's own records, out of its own file", () => {
    const own = parseSpeakers(example('speakers.yml'));
    // Non-vacuity first: two empty lists are equal, and the comparison
    // below would then be saying nothing at all.
    expect(own.length).toBeGreaterThan(0);
    expect(demoSpeakers()).toEqual(own);
  });

  it("holds the example instance's own governance, out of its own file", () => {
    const own = parseConfig(example('config.yml'));
    expect(own.board.length).toBeGreaterThan(0);
    expect(demoConfig()).toEqual(own);
  });

  it('signs the visitor in as a member of that instance\'s own board', () => {
    // Half of what this cockpit does is keyed on who you are: a ballot
    // counts only from an active member, `applyTransition` refuses a login
    // the board does not hold, the inbox is what is waiting for *you*. A
    // visitor signed in as somebody that board has never heard of would be
    // shown a cockpit in which none of that works, and shown it silently.
    const board = demoConfig().board.map(member => member.login);
    expect(board).toContain(DEMO_USER.login);
    expect(
      demoConfig().board.find(member => member.login === DEMO_USER.login)?.status,
    ).toBe('active');
  });

  it('renders the states the invention it replaced never reached', () => {
    // A demonstration with only a nominal case is what this project has
    // lost five defects to. The example was written to
    // exercise states rather than to be plausible, and this is the clause
    // that stops it being thinned back to one.
    const speakers = demoSpeakers();
    const statuses = new Set(speakers.map(s => s.status));
    for (const status of ['delivered', 'scheduled', 'confirmed', 'lead']) {
      expect(statuses, `no ${status} record to render`).toContain(status);
    }
    expect(speakers.some(s => s.publication.consent === 'granted' && s.youtube_url !== '')).toBe(
      true,
    );
    expect(speakers.some(s => s.publication.consent === 'refused')).toBe(true);
    expect(speakers.some(s => s.candidate_dates.length > 0)).toBe(true);
    expect(speakers.some(s => s.selection.ballots.some(b => b.value === 'recused'))).toBe(true);
    // A title outside the Latin script, because a demonstration that only
    // ever renders ASCII proves nothing about the one that does not.
    expect(speakers.some(s => /[^\u0020-\u007e]/.test(s.title))).toBe(true);
  });

  it('carries a record at every status the pipeline has', () => {
    // The fixture the pipeline is verified against. A status with no
    // record behind it is a status verified by reading the code, and this
    // is what ends that: every one of them can be opened.
    const held = new Set(demoSpeakers().map(s => s.status));
    for (const status of EVERY_STATUS) {
      expect(held, `no ${status} record to open`).toContain(status);
    }
  });

  it('is recent enough that no step of it is past its own turnaround time', () => {
    // The defect this closes read "Forum summary is 281 days overdue" on a
    // talk the example gave the autumn before last. The records are
    // written for one day (`scripts/example-dates.mjs`) and moved into the
    // week they are read in, so the demonstration opens on a pipeline
    // nobody is late on -- whichever day it is opened on.
    const config = demoConfig();
    for (const one of demoSpeakers()) {
      const late = lateness(one, config, parisToday());
      expect(late.state, `${one.id} is ${JSON.stringify(late)}`).not.toBe('overdue');
    }
  });

  it('walks the nomination rule: one window open, one run out in silence', () => {
    // The rule a reader cannot check by reading (G-05). The example carries
    // one nomination the board is still answering and one it never answered,
    // so a visitor sees the count against the bar on one and the outcome
    // silence produces on the other -- and sees them on whichever day the
    // demonstration is opened, because these days move with the week.
    const config = demoConfig();
    const speakers = demoSpeakers();
    const today = parisToday();

    expect(config.nominations).toHaveLength(2);
    const [open, elapsed] = config.nominations;
    expect(open.outcome).toBe('');
    expect(elapsed.outcome).toBe('');

    // Both candidates could be nominated: the eligibility this rule asks for
    // is read off the event records, and a demonstration whose candidates
    // failed it would be showing a nomination nobody could have opened.
    for (const n of config.nominations) {
      expect(coHostedCount(speakers, n.candidate), n.candidate).toBeGreaterThanOrEqual(2);
    }

    const live = nominationStanding(config, open, today);
    expect(live.elapsed).toBeLessThan(NOMINATION_WINDOW_DAYS);
    expect(live.supports).toBeGreaterThan(0);
    expect(live.supports).toBeLessThan(live.bar);
    expect(live.carried).toBe(false);

    const quiet = nominationStanding(config, elapsed, today);
    expect(quiet.elapsed).toBeGreaterThanOrEqual(NOMINATION_WINDOW_DAYS);
    // The member who opened it, and nobody else: this is what silence looks
    // like on the record.
    expect(quiet.supports).toBe(1);
    expect(quiet.carried).toBe(false);

    // What the Board screen offers to record, and what it does to the board.
    const settled = resolveNominations(config, today);
    expect(settled.nominations.map(n => n.outcome)).toEqual(['', 'deferred']);
    expect(settled.board).toEqual(config.board);
  });

  it('measures on the Diversity screen instead of saying there is too little', () => {
    // `state/diversity.ts` refuses a share below MIN_REPORTING_BASIS
    // declared answers, and it asks its question of two populations. The
    // example carried five records, so both panels of that screen said
    // "not enough declared answers" and the screen demonstrated nothing
    // but its own refusal.
    const dist = distribution(
      demoSpeakers(),
      demoConfig().balance_window_months,
      parisToday(),
    );
    for (const population of [dist.applicants, dist.selected]) {
      expect(population.gender.declared).toBeGreaterThanOrEqual(MIN_REPORTING_BASIS);
      expect(population.career_stage.declared).toBeGreaterThanOrEqual(MIN_REPORTING_BASIS);
      expect(population.country.declared).toBeGreaterThanOrEqual(MIN_REPORTING_BASIS);
    }
    // And an undisclosed answer is still there, because it is an answer: a
    // fixture where everybody declares would demonstrate a screen this
    // project does not have.
    expect(dist.applicants.gender.total).toBeGreaterThan(dist.applicants.gender.declared);
  });
});
