/**
 * The manual and the code describe the same rule for joining the Board.
 *
 * `docs/handbook/governance/board-rules.md` is the whole of what binds a
 * Board member, and it says of itself that it describes the rules *as the
 * application actually applies them*. `app/src/state/board.ts` is what
 * applies them. Those are two statements of one rule, and until this file
 * existed the only thing holding them together was somebody reading both on
 * the same day.
 *
 * That is the failure this repository has already paid for twice: the
 * preparation countdown drifted six windows out of date under a marker
 * claiming it could not, and the schema appendix did it twice. A marker is
 * not a control. `pipeline-and-manual.test.ts` beside this one binds the
 * pipeline the manual describes to the one the workspace runs; this binds
 * the numbers the Board's own page prints to the numbers the code computes.
 *
 * **Three things, not two.** A page and a module can agree with each other
 * while both disagree with the screen a member actually presses. So the
 * sentence that carries the rule is looked for in `screens/Board.tsx` as
 * well, verbatim.
 *
 * The numbers are compared as numbers and the table row by row, so a page
 * that changed one row of the bar and left the rest is red -- which is
 * exactly the shape a hand-edited table drifts in.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import {
  NOMINATION_MINIMUM_SUPPORTS,
  NOMINATION_WINDOW_DAYS,
  nominationBar,
} from '../../src/state/board';
import { NOMINATION_OUTCOMES } from '../../src/data/validate';

const ROOT = resolve(__dirname, '../../..');
const PAGE = readFileSync(
  resolve(ROOT, 'docs/handbook/governance/board-rules.md'),
  'utf-8',
);
const SCREEN = readFileSync(resolve(ROOT, 'app/src/screens/Board.tsx'), 'utf-8');

/** The rule's own section, from its numbered heading to the next one, so a
 *  number printed elsewhere on this long page is never read as this rule's. */
function section(): string {
  const from = PAGE.indexOf('### The Board has to say yes (G-05)');
  expect(from).toBeGreaterThan(-1);
  const rest = PAGE.slice(from + 1);
  const to = rest.indexOf('\n### ');
  expect(to).toBeGreaterThan(-1);
  return rest.slice(0, to);
}

/** The bar the page prints, as `[eligible, supports]` pairs read out of the
 *  table under its own header row. */
function barTable(): [number, number][] {
  const rows: [number, number][] = [];
  let seen = false;
  for (const line of section().split('\n')) {
    if (line.startsWith('| Eligible members | Supports needed |')) {
      seen = true;
      continue;
    }
    if (!seen) continue;
    const cells = /^\|\s*(\d+)\s*\|\s*(\d+)\s*\|$/.exec(line.trim());
    if (!cells) {
      if (line.trim().startsWith('|')) continue;
      if (rows.length > 0) break;
      continue;
    }
    rows.push([Number(cells[1]), Number(cells[2])]);
  }
  return rows;
}

describe('the Board’s page and the code state one nomination rule', () => {
  it('reads a rule out of the page, so an empty read cannot pass', () => {
    expect(section()).toContain('Silence counts as refusal');
    expect(barTable().length).toBeGreaterThan(4);
  });

  it('states the window the code counts, in the rule itself', () => {
    const stated = /\*\*The window is (\d+) calendar days\*\*/.exec(section());
    expect(stated, 'the rule no longer states its window in words').not.toBeNull();
    expect(Number(stated![1])).toBe(NOMINATION_WINDOW_DAYS);
  });

  it('states the same window again in the table of units, and in calendar days', () => {
    // The page carries two windows of fourteen and one of three, and the
    // whole point of that table is that nothing converts between the units.
    // A window that moved in the rule and not in the table would leave a
    // reader two numbers to choose from.
    const row = new RegExp(`^\\| Nomination window \\((\\d+)\\) \\| Calendar days \\|$`, 'm').exec(
      PAGE,
    );
    expect(row, 'the table of units no longer carries the nomination window').not.toBeNull();
    expect(Number(row![1])).toBe(NOMINATION_WINDOW_DAYS);
  });

  it('prints the bar the code computes, row for row', () => {
    for (const [eligible, supports] of barTable()) {
      expect(supports, `the page says ${eligible} eligible members need ${supports}`).toBe(
        nominationBar(eligible),
      );
    }
  });

  it('prints the floor the code refuses to go below', () => {
    expect(barTable()[0][1]).toBe(NOMINATION_MINIMUM_SUPPORTS);
    expect(section()).toContain('never fewer than three supports');
  });

  it('names the outcomes the reader can be given, and no others', () => {
    // The page's own promise, on the list of things that never happen: the
    // vocabulary holds no refusal, so none can be written. Read off the
    // reader's page and compared with the vocabulary the loader enforces.
    const bullet = /The outcomes a nomination can reach are ([^.]+)\./.exec(PAGE);
    expect(bullet).not.toBeNull();
    const named = [...bullet![1].matchAll(/\*(\w+)\*/g)].map(m => m[1]).sort();
    expect(named).toEqual([...NOMINATION_OUTCOMES].filter(o => o !== '').sort());
  });

  it('says the same thing on the screen a member presses', () => {
    // Verbatim, and in the direction that matters: the sentence a member
    // reads beside the control is the sentence the manual binds them to.
    expect(SCREEN).toContain('Silence counts as refusal');
    expect(SCREEN).toContain('NOMINATION_WINDOW_DAYS');
    expect(PAGE).toContain('**Silence counts as refusal.**');
  });

  it('cites the rule by the number the page states it under', () => {
    // `board.ts` heads its nomination block with the rule's number. A page
    // that renumbered the rule and left the code citing the old one would
    // send a reader to whatever rule had taken that number.
    const board = readFileSync(resolve(ROOT, 'app/src/state/board.ts'), 'utf-8');
    expect(board).toContain('Nominations (G-05)');
    expect(PAGE).toContain('### The Board has to say yes (G-05)');
  });
});
