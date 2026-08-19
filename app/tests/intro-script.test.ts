/**
 * The words the two hosts say, and the deck that carries them.
 *
 * Three claims, all made against the real files on disk rather than against a
 * fixture of what they are supposed to say:
 *
 * 1. Nothing variable is written out in longhand. Every mention of the
 *    speaker, their affiliation, the title and the edition code is a
 *    substitution the app resolves -- an example left in a script is the
 *    sentence that gets read aloud by mistake.
 * 2. Every substitution used resolves. A token nobody feeds shows up as
 *    «missing: …» in front of an audience.
 * 3. The script, the deck and the run of show agree on the order of the
 *    session. Each script is headed by the slide number it is spoken over,
 *    and those numbers are read back out of the run of show's own table, so
 *    renumbering the session in one file and not the others fails here.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { CONTENT_REGISTRY } from '../src/content/registry';
import { substitute } from '../src/content/render';
import type { Speaker } from '../src/data/types';
import { speaker as double } from './data-doubles';

const SCRIPT_KEY = 'toolkit/intro-scripts';
const DECK_KEY = 'toolkit/slides/presentation-template';
const SHOW_KEY = 'toolkit/run-of-show';

function source(key: string): string {
  return readFileSync(resolve(__dirname, '../../docs', CONTENT_REGISTRY[key].file), 'utf-8');
}

/** A record with nothing in common with any real session, so that a value
 *  reaching the page can only have come through a substitution. */
function invented(): Speaker {
  return double({
    id: 'sp-x',
    name: 'Wren Ashgrove',
    affiliation: 'Institute of Invented Things',
    title: 'Counting what nobody counted',
    bio: 'Wren studies things nobody has counted, at an institute that does not exist.',
    edition_code: 'MRG-999',
    date: '2026-11-12',
    time: '12:30',
    forum_thread: 'https://forum.example.org/t/999',
    host_1: 'alice',
    host_2: 'bob',
  });
}

/** Slide numbers in the order the run of show's table lists them. */
function runOfShowSlides(): { number: number; speaks: string }[] {
  const rows = source(SHOW_KEY)
    .split('\n')
    .map(l => l.split('|').map(c => c.trim()))
    .filter(cells => cells.length > 5 && /^\d+$/.test(cells[1]));
  return rows.map(cells => ({ number: Number(cells[1]), speaks: cells[4] }));
}

describe('what is variable is substituted, never written out', () => {
  it.each([
    ['the script', SCRIPT_KEY],
    ['the deck', DECK_KEY],
  ])('%s names the speaker, affiliation and title only as substitutions', (_label, key) => {
    const s = invented();
    const rendered = substitute(source(key), { speaker: s });
    for (const value of [s.name, s.affiliation, s.title]) {
      // Absent from the file, present once it is filled: that is what
      // "substituted" means, and a hard-coded example fails the first half.
      expect(source(key)).not.toContain(value);
      expect(rendered).toContain(value);
    }
  });

  it('the deck carries the edition code as a substitution', () => {
    const s = invented();
    expect(source(DECK_KEY)).not.toContain(s.edition_code);
    expect(substitute(source(DECK_KEY), { speaker: s })).toContain(s.edition_code);
  });

  it('carries no worked example of a past speaker', () => {
    // The script this one replaces ended on a filled-in paragraph about a real
    // past speaker. It read as an instruction to say those words.
    expect(source(SCRIPT_KEY)).not.toContain('Example from a past session');
  });

  it.each([
    ['the script', SCRIPT_KEY],
    ['the deck', DECK_KEY],
  ])('%s resolves every token it uses', (_label, key) => {
    // Matched on a real path rather than on the bare marker: the script shows
    // the reader what an unfilled token looks like, and that illustration is
    // not itself an unfilled token.
    expect(substitute(source(key), { speaker: invented() })).not.toMatch(/«missing: [\w.]/);
  });
});

describe('the script, the deck and the run of show agree on the order', () => {
  it('reads nine slides out of the run of show', () => {
    expect(runOfShowSlides().map(s => s.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it('heads every script with a slide the run of show has, in its order', () => {
    const scripted = [...source(SCRIPT_KEY).matchAll(/^## Slide (\d+) —/gm)].map(m => Number(m[1]));
    expect(scripted.length).toBeGreaterThan(0);
    const known = runOfShowSlides().map(s => s.number);
    for (const n of scripted) expect(known).toContain(n);
    expect(scripted).toEqual([...scripted].sort((a, b) => a - b));
  });

  it('gives each script to the host the run of show gives that slide to', () => {
    const byNumber = new Map(runOfShowSlides().map(s => [s.number, s.speaks]));
    const headings = [...source(SCRIPT_KEY).matchAll(/^## Slide (\d+) — .+ \((Host \d)\)$/gm)];
    expect(headings.length).toBeGreaterThan(0);
    for (const [, n, host] of headings) expect(byNumber.get(Number(n))).toBe(host);
  });

  it('describes every slide of the session in the deck, once, in order', () => {
    const deck = [...source(DECK_KEY).matchAll(/^### (\d+) —/gm)].map(m => Number(m[1]));
    expect(deck).toEqual(runOfShowSlides().map(s => s.number));
  });
});

describe('what belongs to another page is pointed at, not restated', () => {
  it('leaves the recording sequence to the run of show', () => {
    const script = source(SCRIPT_KEY);
    expect(script).toContain('run-of-show.md');
    // The three steps live in one place. Two copies of a sequence whose
    // mistakes cannot be repaired is worse than one.
    expect(script).not.toContain('Start recording again');
    expect(script).not.toContain('Stop recording');
  });

  it('leaves the conflict-of-interest slide to its owners', () => {
    const deck = source(DECK_KEY);
    expect(deck).toContain('run-of-show.md');
    expect(deck).toContain('talk-details.md');
    // It is the speaker's slide; the deck says so and stops there.
    expect(deck).not.toContain('three separate ticks');
  });

  it('reaches the app through the fragment mechanism, like every template', () => {
    expect(CONTENT_REGISTRY[DECK_KEY]).toEqual({
      file: 'toolkit/slides/presentation-template.md',
      anchor: null,
    });
    expect(CONTENT_REGISTRY[SCRIPT_KEY]).toEqual({
      file: 'toolkit/intro-scripts.md',
      anchor: null,
    });
  });
});
