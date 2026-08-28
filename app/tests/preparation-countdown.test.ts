/**
 * The handbook's countdown, against the journey the app actually runs.
 *
 * `docs/workflow/2-preparation.md` counts the preparation down day by day, and
 * `app/src/state/phases.ts` is what a volunteer ticks. They are the same list
 * written twice, and the second copy drifted exactly as the schema appendix
 * did: the block that stood here until this phase was six windows and four
 * steps out of date -- *underneath a marker claiming it was single-sourced*,
 * left behind by a generator that no longer exists. A marker is not a control.
 *
 * This is the control. The page is not generated -- it is a page a volunteer
 * reads, with its own admonitions, its own links and its own reasons, and
 * generating it would mean moving that prose into a script where nobody would
 * find it. What has to agree with the code is narrower than the page: the
 * countdown's windows, and the steps under each of them. So that is what is
 * compared, against `phaseItems` rather than against `PHASES.items`, because
 * the promotion channels are configuration and enter the journey through the
 * former.
 *
 * The comparison is on the step's own wording, verbatim: a line may carry an
 * aside after an em dash -- a link to the visual kit, a note about what
 * "registration" means -- and nothing else. A looser rule (contains, starts
 * with) would have passed on the drifted block, since "Meeting link in hand"
 * appeared in both.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { PHASES, phaseItems } from '../src/state/phases';
import { channelItem, channelsOf } from '../src/state/channels';
import type { RunbookItem } from '../src/state/phases';
import { config as double } from './data-doubles';

const PAGE = resolve(__dirname, '../../docs/workflow/2-preparation.md');

/** The one line of the countdown that stands for a list this file cannot
 *  know: the channels are `instance/data/config.yml`'s, so the page names the file
 *  instead of restating seven lines that a Board edit would falsify. */
const CHANNELS_LINE = 'One line per promotion channel';

const SCHEDULED = PHASES.find(p => p.status === 'scheduled')!;

/** The journey as a volunteer meets it, channels included. The config is the
 *  test double's, so the number of channels the Board happens to have set
 *  today cannot change what this test asserts. */
const ITEMS: RunbookItem[] = phaseItems(SCHEDULED, double());

/** The channel lines, which the page stands in for with `CHANNELS_LINE`
 *  rather than restating. They now carry the window they are placed in --
 *  that is what puts them in the inbox and on the record page under the same
 *  name -- so the step comparison below has to leave them out explicitly
 *  instead of relying on them having no window at all. */
const CHANNEL_KEYS = new Set(channelsOf(double()).map(c => channelItem(c).key));

/** The windows the countdown covers: everything before the day itself. The
 *  `T-0` lines are the recording sequence, which the handbook keeps on the
 *  hosting page, where the person doing it is looking. */
const WINDOWS = [...new Set(ITEMS.map(i => i.window).filter((w): w is number => !!w))];

interface Section {
  window: number;
  lines: string[];
}

/** The countdown, read out of the page: one section per `### T-n` heading,
 *  each holding its checkbox lines with the markdown taken off. */
function countdown(): Section[] {
  const sections: Section[] = [];
  for (const line of readFileSync(PAGE, 'utf-8').split('\n')) {
    const heading = /^### T-(\d+) days?$/.exec(line.trim());
    if (heading) {
      sections.push({ window: Number(heading[1]), lines: [] });
      continue;
    }
    if (line.startsWith('### ') || line.startsWith('## ')) continue;
    const box = /^- \[ \] (.+)$/.exec(line.trim());
    if (box && sections.length > 0) sections[sections.length - 1].lines.push(box[1]);
  }
  return sections;
}

/** One checkbox line as the step it stands for: bold markers off, the aside
 *  after an em dash dropped. Everything else has to match the label. */
function step(line: string): string {
  return line.split(' — ')[0].replaceAll('**', '').trim();
}

describe('the preparation countdown and the journey the app runs', () => {
  it('reads a countdown out of the page, so an empty read cannot pass', () => {
    expect(countdown().length).toBeGreaterThan(3);
    expect(WINDOWS.length).toBeGreaterThan(3);
  });

  it('counts down the same windows, in the same order', () => {
    expect(countdown().map(s => s.window)).toEqual(WINDOWS);
  });

  it.each(WINDOWS)('lists the steps of T-%d, in order and word for word', window => {
    const section = countdown().find(s => s.window === window)!;
    const expected = ITEMS.filter(i => i.window === window && !CHANNEL_KEYS.has(i.key)).map(
      i => i.label,
    );
    const listed = section.lines.filter(l => !l.startsWith(CHANNELS_LINE)).map(step);
    expect(listed).toEqual(expected);
  });

  it('stands the promotion channels in for a list only the config holds', () => {
    // The channels enter the journey after one named step and are as many as
    // `instance/data/config.yml` says. The page names the file rather than the seven,
    // and says so once, in the window that step falls in.
    const after = ITEMS.find(i => i.key === SCHEDULED.channelsAfter)!;
    const section = countdown().find(s => s.window === after.window)!;
    const named = section.lines.filter(l => l.startsWith(CHANNELS_LINE));
    expect(named).toHaveLength(1);
    expect(named[0]).toContain('`channels` in `instance/data/config.yml`');
    expect(section.lines.indexOf(named[0])).toBe(section.lines.length - 1);
    expect(countdown().flatMap(s => s.lines).filter(l => l.startsWith(CHANNELS_LINE))).toHaveLength(
      1,
    );
  });

  it('keeps the on-the-day recording steps off the countdown', () => {
    // They are three lines of the journey with `window: 0`, and they live on
    // the hosting page. A copy here would be a fourth place to tick them.
    const onTheDay = ITEMS.filter(i => i.window === 0).map(i => i.label);
    expect(onTheDay.length).toBe(3);
    const page = readFileSync(PAGE, 'utf-8');
    for (const label of onTheDay) expect(page).not.toContain(label);
  });
});
