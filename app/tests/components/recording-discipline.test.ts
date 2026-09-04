/**
 * The recording sequence, as the volunteers actually run it.
 *
 * Start the recording for the talk, stop it before the discussion begins,
 * start it again for the discussion. The two recordings are kept apart
 * because the talk is published and the discussion is not, and every mistake
 * in the sequence is final: a talk nobody recorded is gone, and a discussion
 * recorded by mistake holds people speaking freely on the understanding that
 * they were not being recorded.
 *
 * So the tests here are about three things and no others -- that the sequence
 * is three steps and not one tick, that the second cannot be ticked before
 * the first, and that the volunteer who did it in another order can still
 * write down what actually happened. The third matters as much as the second:
 * a checklist that cannot describe the day is a checklist people keep
 * somewhere else.
 *
 * Written with `createElement` rather than JSX so the file can stay `.ts`
 * alongside the rest of the state tests.
 */
import { createElement } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, cleanup } from '@testing-library/react';
import { Checklist } from '../../src/components/Checklist';
import { PHASES, phaseOf, phaseItems, stepBefore, itemByKey } from '../../src/state/phases';
import type { Speaker } from '../../src/data/types';
import { config, speaker } from '../helpers/data-doubles';

const TALK = 'scheduled/T-0/recording-talk-started';
const STOP = 'scheduled/T-0/recording-stopped-before-discussion';
const DISCUSSION = 'scheduled/T-0/recording-discussion-started';

/** The day of the talk: the sequence is not a thing anyone does earlier. */
const TODAY = '2026-09-01';

function onTheDay(progress: Record<string, boolean> = {}): Speaker {
  return speaker({ status: 'scheduled', date: TODAY, runbook_progress: progress });
}

function show(s: Speaker) {
  cleanup();
  render(
    createElement(Checklist, {
      speaker: s,
      onToggle: () => {},
      onField: () => {},
      today: TODAY,
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

/** The checkbox of one line, by the wording a volunteer reads next to it. */
function box(label: string): HTMLInputElement {
  const input = row(label).querySelector('input[type="checkbox"]');
  if (!(input instanceof HTMLInputElement)) throw new Error(`no checkbox for ${label}`);
  return input;
}

/** The way out offered on a held line, for a volunteer whose day went
 *  differently. */
function release(label: string): HTMLElement {
  const button = row(label).querySelector('button');
  if (!(button instanceof HTMLButtonElement)) throw new Error(`no way out of ${label}`);
  return button;
}

describe('the recording sequence is three steps, not one tick', () => {
  it('carries a step of its own for each of the three', () => {
    const keys = phaseItems(phaseOf('scheduled')!, config()).map(i => i.key);
    expect(keys).toContain(TALK);
    expect(keys).toContain(STOP);
    expect(keys).toContain(DISCUSSION);
  });

  it('runs them in the order the day runs, last of the work of the runbook', () => {
    // Last of the *work*: the line after them is the control that closes the
    // status, which is not a step of the day.
    const keys = phaseItems(phaseOf('scheduled')!, config()).map(i => i.key);
    expect(keys.slice(-4, -1)).toEqual([TALK, STOP, DISCUSSION]);
  });

  it('says which of the three was skipped, because that is the whole question', () => {
    // Two of three done. A single "recording done" box would say the same
    // nothing here as it would if all three had been missed.
    const s = onTheDay({ [TALK]: true, [STOP]: true });
    expect(!!s.runbook_progress[TALK]).toBe(true);
    expect(!!s.runbook_progress[STOP]).toBe(true);
    expect(!!s.runbook_progress[DISCUSSION]).toBe(false);
  });

  it('is a line of the day itself, not one a volunteer meets three weeks out', () => {
    for (const key of [TALK, STOP, DISCUSSION]) {
      expect(itemByKey(key)!.window).toBe(0);
    }
  });
});

describe('the wording carries the risk', () => {
  it('says on the stopping step why it is there, in one short sentence', () => {
    const note = itemByKey(STOP)!.note!;
    expect(note).toBe(
      'The discussion is not published, and a discussion recorded by mistake cannot be unrecorded.',
    );
    // One sentence, and short enough that it is read rather than skipped.
    expect(note.split('. ').length).toBe(1);
    expect(note.length).toBeLessThan(120);
  });

  it('puts that sentence on the screen, at the step it belongs to', () => {
    show(onTheDay());
    expect(row('Recording stopped before the discussion begins').textContent).toContain(
      'cannot be unrecorded',
    );
  });

  it('leaves the reason at the point of use and nowhere else', () => {
    // The reason belongs to the step that carries the risk. Repeating it on
    // the two neighbours -- or on the rest of the runbook they sit in --
    // would turn it into wallpaper.
    const phase = PHASES.find(p => p.status === 'scheduled')!;
    const noted = phase.items.filter(i => i.note !== undefined);
    expect(noted.map(i => i.key)).toEqual([STOP]);
    for (const key of [TALK, DISCUSSION]) expect(itemByKey(key)!.note).toBeUndefined();
  });
});

describe('the order is constrained where a volunteer meets it', () => {
  it('holds the stopping step until the talk recording has been started', () => {
    show(onTheDay());
    expect(box('Recording stopped before the discussion begins').disabled).toBe(true);
    expect(box('Recording started for the talk').disabled).toBe(false);
  });

  it('releases it the moment the step before it is ticked', () => {
    show(onTheDay({ [TALK]: true }));
    expect(box('Recording stopped before the discussion begins').disabled).toBe(false);
  });

  it('holds the third step until the second, one step at a time', () => {
    show(onTheDay({ [TALK]: true }));
    expect(box('Recording started again for the discussion').disabled).toBe(true);
    show(onTheDay({ [TALK]: true, [STOP]: true }));
    expect(box('Recording started again for the discussion').disabled).toBe(false);
  });

  it('names the step that comes first rather than refusing in silence', () => {
    show(onTheDay());
    expect(row('Recording stopped before the discussion begins').textContent).toContain(
      'Comes after “Recording started for the talk”',
    );
  });

  it('constrains only the sequence, and leaves the rest of the runbook alone', () => {
    show(onTheDay());
    expect(box('Visuals + flyer made').disabled).toBe(false);
    expect(box('Speaker registered on the forum and to their own talk').disabled).toBe(false);
    const held = PHASES.flatMap(p => p.items).filter(i => i.after !== undefined);
    expect(held.map(i => i.key)).toEqual([STOP, DISCUSSION]);
  });

  it('never holds a line that is already ticked, so a mistake can be unticked', () => {
    // Out of order on the record -- however it got there -- must stay
    // correctable. A constraint that freezes the wrong answer in place is
    // worse than none.
    const s = onTheDay({ [DISCUSSION]: true });
    expect(stepBefore(s, itemByKey(DISCUSSION)!)).toBeUndefined();
    show(s);
    expect(box('Recording started again for the discussion').disabled).toBe(false);
  });
});

describe('the volunteer who did it in another order is not stuck', () => {
  it('offers a way to tick it anyway, at the held step', () => {
    show(onTheDay());
    expect(row('Recording stopped before the discussion begins').textContent).toContain(
      'It happened in another order',
    );
  });

  it('lets the tick through once the volunteer says so', () => {
    const onToggle = vi.fn();
    render(
      createElement(Checklist, {
        speaker: onTheDay(),
        onToggle,
        onField: () => {},
        today: TODAY,
      }),
    );
    fireEvent.click(release('Recording stopped before the discussion begins'));
    const stop = box('Recording stopped before the discussion begins');
    expect(stop.disabled).toBe(false);
    fireEvent.click(stop);
    expect(onToggle).toHaveBeenCalledWith(STOP, true);
  });

  it('records the step and nothing about the order it was ticked in', () => {
    // What the file keeps is which steps happened. "This was ticked out of
    // order" is a fact about a screen, not about the event, and storing it
    // would invite somebody to report on it later.
    const onToggle = vi.fn();
    render(
      createElement(Checklist, {
        speaker: onTheDay(),
        onToggle,
        onField: () => {},
        today: TODAY,
      }),
    );
    fireEvent.click(release('Recording stopped before the discussion begins'));
    fireEvent.click(box('Recording stopped before the discussion begins'));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle.mock.calls[0]).toEqual([STOP, true]);
  });
});

describe('stepBefore', () => {
  it('is undefined for the ordinary line, which nothing comes before', () => {
    expect(stepBefore(onTheDay(), itemByKey('scheduled/T-30/visuals')!)).toBeUndefined();
  });

  it('names the outstanding step for a line that follows one', () => {
    expect(stepBefore(onTheDay(), itemByKey(STOP)!)?.key).toBe(TALK);
  });

  it('is undefined once the step before is done', () => {
    expect(stepBefore(onTheDay({ [TALK]: true }), itemByKey(STOP)!)).toBeUndefined();
  });

  it('knows nothing of a key the journey does not have', () => {
    expect(itemByKey('scheduled/T-0/nothing-like-this')).toBeUndefined();
  });
});
