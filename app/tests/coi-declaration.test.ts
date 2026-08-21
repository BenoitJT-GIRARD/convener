/**
 * The conflict declared to the audience, and the run of show that surrounds it.
 *
 * **Three boxes, not one.** G-16 names three facts -- a slide of its own, said
 * out loud, written into the video description -- and the reason it names three
 * is a problem the series has watched happen: a slide flashed up for two
 * seconds while nobody says anything, which a single "conflicts declared" tick
 * calls done. So the guarantee these tests hold is that the three are three:
 * three lines, three keys, three ticks, and a record with two of them says
 * plainly which one is missing.
 *
 * **This is not the board's conflict of interest.** `conflicts_of_interest` on
 * the record is what a speaker tells the board so the board can apply its own
 * recusal rules to a vote (`hidden-coi.test.ts` is that story). These lines are
 * the speaker's or the hosts' declaration to the audience, in the room, on the
 * day. Different people, a different moment -- and nothing here is derived from
 * that field, which is asserted over the source rather than over one case.
 *
 * **The run of show is a template.** It reaches the screen at the point of use
 * through the same fragment mechanism as every other piece of guidance, and
 * nothing anywhere reads whether the hosts followed it.
 *
 * Written with `createElement` rather than JSX so the file can stay `.ts`
 * alongside the rest of the state tests.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createElement } from 'react';
import { describe, it, expect } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { Checklist } from '../src/components/Checklist';
import { CONTENT_REGISTRY } from '../src/content/registry';
import {
  PHASES,
  blockers,
  canFinalize,
  itemByKey,
  phaseItems,
  phaseOf,
} from '../src/state/phases';
import type { Speaker } from '../src/data/types';
import { config, speaker } from './data-doubles';

const SLIDE = 'delivered/coi-slide-shown';
const SPOKEN = 'delivered/coi-spoken-aloud';
const DESCRIPTION = 'delivered/coi-in-video-description';
const THREE = [SLIDE, SPOKEN, DESCRIPTION];

const TODAY = '2026-09-08';

/** Everything the wrap-up asks for, so a test about the declaration is not
 *  quietly about the metrics. */
const WRAPPED_UP = {
  status: 'delivered' as const,
  metrics: { registrations: 50, live_peak: 40, youtube_views_30d: null, forum_replies: null },
  runbook_progress: {
    'scheduled/T-14/speaker_registered': true,
    'delivered/forum-summary': true,
    'delivered/thank-you': true,
  },
};

function wrappedUp(overrides: Partial<Speaker> = {}): Speaker {
  return speaker({ ...WRAPPED_UP, ...overrides });
}

function show(s: Speaker) {
  cleanup();
  render(
    createElement(Checklist, {
      speaker: s,
      onToggle: () => {},
      onField: () => {},
      today: TODAY,
      config: config(),
    }),
  );
}

/** One rendered line of the journey, by the wording it opens with. */
function row(label: string): HTMLElement {
  const found = Array.from(document.querySelectorAll<HTMLElement>('div.border')).find(el =>
    (el.querySelector('p')?.textContent ?? '').startsWith(label),
  );
  if (!found) throw new Error(`no row for ${label}`);
  return found;
}

describe('the declaration is three checks, not one', () => {
  it('carries a line of its own for each of the three facts G-16 names', () => {
    const keys = phaseItems(phaseOf('delivered')!, config()).map(i => i.key);
    for (const key of THREE) expect(keys).toContain(key);
    // Three distinct lines, and not one line counted three times.
    expect(new Set(THREE).size).toBe(3);
    expect(keys.filter(k => THREE.includes(k))).toHaveLength(3);
  });

  it('says the three things in three sentences a volunteer can check separately', () => {
    expect(itemByKey(SLIDE)!.label).toBe(
      'Conflict of interest: dedicated slide shown in the session',
    );
    expect(itemByKey(SPOKEN)!.label).toBe(
      'Conflict of interest: declaration spoken aloud in the session',
    );
    expect(itemByKey(DESCRIPTION)!.label).toBe(
      'Conflict of interest: declaration written in the video description',
    );
  });

  it('names a different fact on each of the three, so no two are the same tick', () => {
    const labels = THREE.map(k => itemByKey(k)!.label);
    expect(new Set(labels).size).toBe(3);
    // The slide, the voice, the written record: the three media the decision
    // asks for, one per line.
    expect(labels.some(l => l.includes('slide'))).toBe(true);
    expect(labels.some(l => l.includes('spoken aloud'))).toBe(true);
    expect(labels.some(l => l.includes('video description'))).toBe(true);
  });

  it('records which of the three was missed, which is the whole point of three', () => {
    // A single box would say exactly the same nothing here as it would if all
    // three had been skipped.
    const s = wrappedUp({
      runbook_progress: { ...WRAPPED_UP.runbook_progress, [SLIDE]: true, [SPOKEN]: true },
    });
    expect(!!s.runbook_progress[SLIDE]).toBe(true);
    expect(!!s.runbook_progress[SPOKEN]).toBe(true);
    expect(!!s.runbook_progress[DESCRIPTION]).toBe(false);
  });

  it('puts all three on the wrap-up screen, each with its own box', () => {
    show(wrappedUp());
    const boxes = THREE.map(key => {
      const input = row(itemByKey(key)!.label).querySelector('input[type="checkbox"]');
      if (!(input instanceof HTMLInputElement)) throw new Error(`no checkbox for ${key}`);
      return input;
    });
    expect(boxes).toHaveLength(3);
    for (const box of boxes) expect(box.disabled).toBe(false);
  });

  it('is where the host meets it: the wrap-up, not the runbook', () => {
    const delivered = phaseOf('delivered')!.items.map(i => i.key);
    for (const key of THREE) expect(delivered).toContain(key);
    const elsewhere = PHASES.filter(p => p.status !== 'delivered').flatMap(p =>
      p.items.map(i => i.key),
    );
    for (const key of THREE) expect(elsewhere).not.toContain(key);
  });
});

describe('it is the audience declaration, never the board one', () => {
  /**
   * The structural half. The distinction is explained in the comments of
   * `state/phases.ts`, so the comments are stripped and the *code* is read: a
   * gate derived from `conflicts_of_interest` cannot be written there without
   * turning this red, including a derivation nobody has thought of yet.
   */
  it('never reads the field the speaker declared to the board', () => {
    const source = readFileSync(resolve(__dirname, '../src/state/phases.ts'), 'utf-8');
    const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
    expect(code).not.toContain('conflicts_of_interest');
    // The stripping itself has to be doing something, or the assertion above
    // would pass on an empty string.
    expect(code).toContain(SLIDE);
  });


  it('borrows no word from the board vocabulary in what a volunteer reads', () => {
    // Recusal, ballots and objections belong to a vote about a speaker. What
    // these lines describe happened in a room, in front of an audience.
    for (const key of THREE) {
      const label = itemByKey(key)!.label.toLowerCase();
      for (const word of ['recus', 'ballot', 'board', 'vote', 'objection']) {
        expect(label).not.toContain(word);
      }
    }
  });

  it('behaves the same whether or not the record carries a board declaration', () => {
    const without = wrappedUp({ conflicts_of_interest: '' });
    const declared = wrappedUp({
      conflicts_of_interest: 'Co-authored a paper with a board member.',
    });
    expect(canFinalize(without)).toBe(canFinalize(declared));
    expect(blockers(without)).toEqual(blockers(declared));
  });
});

describe('what the three checks do not do', () => {
  it('does not stop the archive, with nothing to declare or with something', () => {
    // The decision asks for the three when a conflict is declared, and the app
    // has no way of knowing that one was. A box that has to be ticked on every
    // record, including the ones with nothing to declare, is a box people
    // learn to tick without reading -- which is the failure these three exist
    // to answer, reintroduced by the gate meant to enforce them.
    const s = wrappedUp();
    for (const key of THREE) expect(s.runbook_progress[key]).toBeUndefined();
    expect(blockers(s)).toEqual([]);
    expect(canFinalize(s)).toBe(true);
  });

  it('adds no note of its own, and leaves the device rare', () => {
    // Three lines whose wording already says what each of them is would only
    // turn the device into wallpaper. The whole journey's notes are listed
    // here rather than counted, so that a fourth one has to be argued for in
    // this test before it reaches a volunteer's screen: they are the steps
    // whose cost, once skipped, cannot be paid back -- a discussion recorded
    // by mistake, a recording released on a tick that was never true (task
    // 17: a false delivered/recording-retrieved risks losing it for good,
    // the same bar the other two already meet), and a publication announced
    // before it was allowed.
    const noted = PHASES.flatMap(p => p.items).filter(i => i.note !== undefined);
    expect(noted.map(i => i.key)).toEqual([
      'scheduled/T-0/recording-stopped-before-discussion',
      'delivered/recording-retrieved',
      'delivered/video-online',
    ]);
    for (const key of THREE) expect(itemByKey(key)!.note).toBeUndefined();
  });

  it('constrains no order between the three', () => {
    // The slide and the words happen in the session, the description at
    // upload. Nothing about doing them in another order is a sign that
    // something went wrong, so nothing is held.
    for (const key of THREE) expect(itemByKey(key)!.after).toBeUndefined();
  });
});

describe('the run of show is offered, not imposed', () => {
  const PLAN_DAY = 'scheduled/T-7/plan-day';

  it('reaches the screen through the fragment mechanism, like every other template', () => {
    expect(CONTENT_REGISTRY['toolkit/run-of-show']).toEqual({
      file: 'toolkit/run-of-show.md',
      anchor: null,
    });
  });

  it('is attached to the moment the two hosts divide the session', () => {
    expect(itemByKey(PLAN_DAY)!.contentKey).toBe('toolkit/run-of-show');
    expect(itemByKey(PLAN_DAY)!.label).toBe('Plan for the day agreed between hosts');
  });

  it('offers it on the line rather than opening it over the runbook', () => {
    show(speaker({ status: 'scheduled', date: '2026-09-10' }));
    expect(row('Plan for the day agreed between hosts').textContent).toContain('Show content');
  });

  it('blocks nothing and orders nothing: a pair who agree another split are fine', () => {
    const item = itemByKey(PLAN_DAY)!;
    expect(item.blocksFinalisation).toBeUndefined();
    expect(item.required).toBeUndefined();
    expect(item.after).toBeUndefined();
    const s = wrappedUp();
    expect(s.runbook_progress[PLAN_DAY]).toBeUndefined();
    expect(canFinalize(s)).toBe(true);
  });

  it('carries the split between the two hosts, which is what it is for', () => {
    const text = readFileSync(resolve(__dirname, '../../docs/toolkit/run-of-show.md'), 'utf-8');
    expect(text).toContain('Host 1');
    expect(text).toContain('Host 2');
    // Said in the document itself, so a host reading it knows it is not a rule.
    expect(text).toContain('This is a template, not a rule.');
  });
});

describe('two registration checks, a week apart, that cannot be read for each other', () => {
  const SPEAKER_REGISTERED = 'scheduled/T-14/speaker_registered';
  const FINAL_REMINDER = 'scheduled/T-1/final-reminder';

  it('says what the T-1 line is about: the link the audience uses', () => {
    expect(itemByKey(FINAL_REMINDER)!.label).toBe('Final reminder sent, room link checked');
  });

  it('says what the T-14 line is about: the speaker being signed up', () => {
    expect(itemByKey(SPEAKER_REGISTERED)!.label).toBe(
      'Speaker registered on the forum and to their own talk',
    );
  });

  it('leaves no wording either could be mistaken for', () => {
    const week = itemByKey(SPEAKER_REGISTERED)!.label;
    const day = itemByKey(FINAL_REMINDER)!.label;
    expect(week).not.toBe(day);
    // The bare phrase "registration check" belonged to both, and so, once
    // phase 4 gave the app's own signup page the same name, did "registration
    // link". Critical 2 (branch review) renamed the T-1 line to "room link" --
    // neither line now carries the word "registration" at all, so no wording
    // either could be mistaken for the other survives.
    for (const label of [week, day]) {
      expect(label).not.toContain('registration check');
      expect(label).not.toContain('registration link');
    }
    expect(day).toContain('room link');
    expect(week).toContain('Speaker registered');
  });

  it('keeps them a week apart and keeps only one of them blocking', () => {
    expect(itemByKey(SPEAKER_REGISTERED)!.window).toBe(14);
    expect(itemByKey(FINAL_REMINDER)!.window).toBe(1);
    expect(itemByKey(SPEAKER_REGISTERED)!.blocksFinalisation).toBe(true);
    expect(itemByKey(FINAL_REMINDER)!.blocksFinalisation).toBeUndefined();
  });
});
