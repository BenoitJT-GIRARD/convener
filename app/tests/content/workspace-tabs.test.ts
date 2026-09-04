/**
 * The page that says what each tab answers, against the tabs there are.
 *
 * `docs/handbook/the-workspace.md` is the canonical home for *what each
 * screen of the app is for* (`docs/engineering/content-rules.md`'s own
 * table), and it is where a volunteer who has never opened a screen finds
 * out what it is. It had been left one tab behind: the heading said nine,
 * the table listed nine, and the workspace had ten. The missing one was
 * Settings -- the screen whose whole difficulty is that a reader cannot
 * tell from it what it is for.
 *
 * Nothing read the page against the navigation, which is why nothing
 * noticed. This is that reading: every tab the workspace shows is named in
 * the table, the heading counts them, and no row describes a tab that is
 * not there.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { TABS } from '../../src/components/tabs';

const PAGE = resolve(__dirname, '../../..', 'docs/handbook/the-workspace.md');

/** The words this page counts in. Ten is where the workspace is; the two
 *  either side are what the sentence would have to become. */
const WRITTEN: Record<number, string> = {
  8: 'eight',
  9: 'nine',
  10: 'ten',
  11: 'eleven',
  12: 'twelve',
};

function page(): string {
  return readFileSync(PAGE, 'utf-8');
}

/** The tab each row of the table is about, from its own first cell. */
function described(text: string): string[] {
  return [...text.matchAll(/^\| \*\*([^*]+)\*\* \|/gm)].map(match => match[1]);
}

describe('the page that says what each tab is for', () => {
  it('reads a table, so an empty match cannot pass', () => {
    expect(TABS.length).toBeGreaterThan(5);
    expect(described(page()).length).toBeGreaterThan(5);
  });

  it('describes every tab the workspace shows, and no other', () => {
    expect(described(page())).toEqual(TABS.map(link => link.label));
  });

  it('counts them in its own heading', () => {
    const written = WRITTEN[TABS.length];
    expect(written, `no word for ${TABS.length} tabs`).not.toBeUndefined();
    expect(page()).toContain(`## The ${written} tabs`);
  });
});
