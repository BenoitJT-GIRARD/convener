/**
 * The manual describes the same sequence the workspace implements.
 *
 * `docs/handbook/workflow/overview.md` tells a volunteer who is planning, in
 * a chair, what the pipeline does; `app/src/state/phases.ts` is what a
 * volunteer clicking meets. They are the same sequence written twice, and a
 * page describing a state the code no longer produces is the failure this
 * repository has already paid for: the preparation countdown drifted six
 * windows out of date under a marker claiming it could not, and the schema
 * appendix did it twice. A marker is not a control.
 *
 * `preparation-countdown.test.ts` beside this one holds the steps *inside*
 * the scheduled status. This one holds the statuses themselves: which of them
 * there are, in what order, and what takes a record out of each. That is what
 * the maintainer's three frictions turned out to be about -- the button that
 * *records* an action arriving before what makes the action possible -- so it
 * is the half most worth binding.
 *
 * **Three things, not two.** A table in a page and a table in a module can
 * agree with each other while both disagree with the button a volunteer
 * actually presses. So each control's wording is also looked for in the
 * source of the component that draws it. Reworded in one place and not the
 * other two, this is red.
 *
 * The wording is compared verbatim, in order. A looser rule -- contains,
 * starts with -- is what let "Meeting link in hand" pass in both the drifted
 * countdown and the live journey while everything around it had moved.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { PHASES } from '../../src/state/phases';

const ROOT = resolve(__dirname, '../../..');
const PAGE = resolve(ROOT, 'docs/handbook/workflow/overview.md');

/** The components that draw a closing control. Every string in a phase's
 *  `closes` has to appear in one of them. */
const DRAWN_IN = [
  'app/src/components/ActionButtons.tsx',
  'app/src/components/DatePanel.tsx',
  'app/src/components/PublicationGate.tsx',
].map(relative => readFileSync(resolve(ROOT, relative), 'utf-8'));

interface Row {
  status: string;
  controls: string[];
}

/**
 * The table of closing controls, read out of the page: one row per status,
 * with the bold spans of the second cell as the controls it names.
 *
 * Read from the heading rather than from the first table on the page, so a
 * table added above it does not silently become the one this suite checks.
 */
function table(): Row[] {
  const lines = readFileSync(PAGE, 'utf-8').split('\n');
  const from = lines.findIndex(line => line.trim() === '## What closes each status');
  expect(from).toBeGreaterThan(-1);
  const rows: Row[] = [];
  for (const line of lines.slice(from + 1)) {
    if (line.startsWith('## ')) break;
    const cells = line.trim().match(/^\|(.+)\|$/);
    if (!cells) continue;
    const [status, controls] = cells[1].split('|').map(cell => cell.trim());
    if (controls === undefined || /^-+$/.test(status) || status === 'Status') continue;
    rows.push({
      status: status.toLowerCase(),
      controls: [...controls.matchAll(/\*\*(.+?)\*\*/g)].map(m => m[1]),
    });
  }
  return rows;
}

describe('the manual and the workspace describe one pipeline', () => {
  it('reads a table out of the page, so an empty read cannot pass', () => {
    expect(table()).toHaveLength(PHASES.length);
    expect(PHASES.length).toBeGreaterThan(4);
  });

  it('names the same statuses, in the same order', () => {
    expect(table().map(r => r.status)).toEqual(PHASES.map(p => p.status));
  });

  it.each(PHASES.map(p => [p.status, p.closes] as const))(
    'names what closes %s, in order and word for word',
    (status, closes) => {
      const row = table().find(r => r.status === status)!;
      expect(row.controls).toEqual(closes);
    },
  );

  it.each(PHASES.flatMap(p => p.closes.map(control => [p.status, control] as const)))(
    'draws the control %s names as "%s"',
    (_status, control) => {
      // Present in the source, rather than equal to a whole label: a button
      // carries an arrow, and two of them carry an alternative wording for a
      // second state. A reword takes the string out of the file entirely,
      // which is what this catches.
      expect(DRAWN_IN.some(source => source.includes(control))).toBe(true);
    },
  );

  it('names the same control on the page a host reads on the day', () => {
    // `3-hosting.md` ends the session, and the last thing it asks for is the
    // control that closes the status. Naming it there and rewording it here
    // would leave two hosts looking for a button that is not on the screen.
    const hosting = readFileSync(resolve(ROOT, 'docs/handbook/workflow/3-hosting.md'), 'utf-8');
    for (const control of PHASES.find(p => p.status === 'scheduled')!.closes) {
      expect(hosting).toContain(control);
    }
  });

  it('describes the two closing lists the way the workspace splits them', () => {
    // `the-workspace.md` is the page a volunteer reads to know which tab
    // holds what, and the agenda and the archive share no status.
    const workspace = readFileSync(resolve(ROOT, 'docs/handbook/the-workspace.md'), 'utf-8');
    expect(workspace).toMatch(/The two lists never hold the same event/);
    expect(workspace).toMatch(/Agenda holds what still owes you\s+something/);
    expect(workspace).toMatch(/Archive holds what is closed/);
  });

  it('ends every status a volunteer works through with a control of its own', () => {
    // A status whose last line is a field or a tick is a status with no way
    // out, which is what `scheduled` was: the header changed by itself when
    // the clock passed the talk, and the checklist under it did not.
    for (const phase of PHASES) {
      expect(phase.closes.length, phase.status).toBeGreaterThan(0);
    }
  });
});
