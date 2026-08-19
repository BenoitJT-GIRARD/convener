/**
 * A repeated passage is included from its source, never copied.
 *
 * Three things are asserted, and the third is the one that will still be
 * working in a year:
 *
 * 1. **The mechanism does what it claims.** A fragment key renders one section
 *    of one file; an include line becomes that section, under a line naming
 *    where it is kept.
 * 2. **A reader can find the source.** The attribution is not a comment in the
 *    markdown, it is a link in the rendered page, because the reader who needs
 *    it is the one about to act on a procedure — and the procedures included
 *    this way are the ones whose mistakes cannot be undone.
 * 3. **No include anywhere under `docs/` points at nothing.** Swept over the
 *    real tree, walked with the build's own rule, so a page written next month
 *    with a mistyped key fails here rather than showing a volunteer a marker
 *    where the publication gate should be.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, beforeAll } from 'vitest';
import { CONTENT_REGISTRY } from '../src/content/registry';
import {
  INCLUDE_RE,
  expandIncludes,
  pageTitle,
  sectionOf,
  slugify,
  sourceUrl,
} from '../src/content/transclude';
import { walk } from '../scripts/handbook-files.mjs';

const DOCS = resolve(__dirname, '../../docs');

function page(relative: string): string {
  return readFileSync(resolve(DOCS, relative), 'utf-8');
}

/** The same loader the app uses, reading the repository instead of the network. */
const fromDisk = async (file: string) => page(file);

const includesIn = (text: string) =>
  [...text.matchAll(new RegExp(INCLUDE_RE.source, 'gm'))].map(m => m[1]);

let servedPages: string[];
beforeAll(async () => {
  servedPages = (await walk(DOCS))
    .map((p: string) => p.split('\\').join('/'))
    .filter((p: string) => p.endsWith('.md'));
});

describe('slugify follows the anchors the handbook already links to', () => {
  it('drops punctuation rather than replacing it, and lowercases the rest', () => {
    expect(slugify('Inactivity (G-09)')).toBe('inactivity-g-09');
    expect(slugify("The speaker's — which must be present")).toBe(
      'the-speakers--which-must-be-present',
    );
    expect(slugify('Publishing a recording: two permissions, and they are not alike')).toBe(
      'publishing-a-recording-two-permissions-and-they-are-not-alike',
    );
  });
});

describe('a fragment is a window onto one section, not a second copy of it', () => {
  const SAMPLE = [
    '# A page',
    '',
    'Front matter.',
    '',
    '## Wanted',
    '',
    'The passage.',
    '',
    '### Under it',
    '',
    'Still wanted.',
    '',
    '## Not wanted',
    '',
    'Somebody else.',
  ].join('\n');

  it('stops at the next heading of the same level or higher', () => {
    const s = sectionOf(SAMPLE, 'wanted')!;
    expect(s.title).toBe('Wanted');
    expect(s.body).toContain('The passage.');
    expect(s.body).toContain('Still wanted.');
    expect(s.body).not.toContain('Somebody else.');
  });

  it('leaves the heading behind, because the including page brings its own', () => {
    expect(sectionOf(SAMPLE, 'wanted')!.body.startsWith('The passage.')).toBe(true);
  });

  it('is null when no heading answers to the anchor', () => {
    expect(sectionOf(SAMPLE, 'invented')).toBeNull();
  });

  it('ignores a "#" inside a fenced block, which is a comment and not a heading', () => {
    const fenced = ['## Wanted', '', '```sh', '# not a heading', '```', '', 'Body.'].join('\n');
    expect(sectionOf(fenced, 'wanted')!.body).toContain('Body.');
  });

  it('reads the page title from the file, so no label is kept by hand', () => {
    expect(pageTitle(SAMPLE, 'a/page.md')).toBe('A page');
    expect(pageTitle('no heading here', 'a/page.md')).toBe('a/page.md');
  });
});

describe('an included passage says where it is maintained', () => {
  it('carries a link to the section in the repository, not just a name', () => {
    const url = sourceUrl('fragments/board-rules-publication-gate');
    expect(url).toContain('/docs/governance/board-rules.md');
    expect(url).toContain('#publishing-a-recording-two-permissions-and-they-are-not-alike');
  });

  it('puts the attribution above the passage, in the rendered markdown', async () => {
    const out = await expandIncludes(
      '{{> fragments/board-rules-publication-gate }}',
      fromDisk,
    );
    const [first] = out.split('\n');
    expect(first).toMatch(/^> \*\*Included from \[/);
    expect(first).toContain("The Board's rules, in detail");
    expect(first).toContain('Publishing a recording');
    expect(first).toContain(sourceUrl('fragments/board-rules-publication-gate'));
    // And then the passage itself, not a summary of it.
    expect(out).toContain('Silence is never consent.');
  });

  it('renders nothing of the source page outside the section named', async () => {
    const out = await expandIncludes(
      '{{> fragments/board-rules-publication-gate }}',
      fromDisk,
    );
    expect(out).not.toContain('Two thirds of the eligible Board');
  });
});

describe('the expansion refuses to hang or to lie', () => {
  const cyclic = async (file: string) =>
    file === 'roles.md' ? '# Roles\n\n## No ladder to climb\n\n{{> fragments/roles-no-ladder }}\n' : '';

  it('marks a key nobody registered instead of dropping the line', async () => {
    const out = await expandIncludes('{{> fragments/invented }}', fromDisk);
    expect(out).toBe('«missing include: fragments/invented»');
  });

  it('marks an anchor no heading answers to', async () => {
    const out = await expandIncludes('{{> fragments/roles-no-ladder }}', async () => '# Roles\n');
    expect(out).toContain('«missing section: no-ladder-to-climb');
  });

  it('marks a circle rather than following it', async () => {
    const out = await expandIncludes('{{> fragments/roles-no-ladder }}', cyclic);
    expect(out).toContain('«circular include: fragments/roles-no-ladder»');
  });

  it('expands every occurrence, not every other one', async () => {
    const out = await expandIncludes(
      '{{> fragments/roles-no-ladder }}\n\nmiddle\n\n{{> fragments/roles-no-ladder }}',
      fromDisk,
    );
    expect(out.split('There is no ladder to climb').length - 1).toBe(2);
  });

  it('leaves a line that only mentions an include in prose alone', async () => {
    const prose = 'A page includes one by writing `{{> fragments/roles-no-ladder }}` on a line.';
    expect(await expandIncludes(prose, fromDisk)).toBe(prose);
  });
});

describe('every include under docs/ resolves, over the tree the build serves', () => {
  it('walks a tree with the handbook in it, so an empty walk cannot pass this suite', () => {
    expect(servedPages).toContain('workflow/4-after.md');
    expect(servedPages).toContain('governance/board-rules.md');
  });

  it('uses the mechanism at all — a rule nothing applies is a rule nobody keeps', () => {
    const using = servedPages.filter(p => includesIn(page(p)).length > 0);
    expect(using.length).toBeGreaterThan(0);
  });

  it('names, for every include, a registry entry scoped to a heading', () => {
    for (const p of servedPages) {
      for (const key of includesIn(page(p))) {
        const entry = CONTENT_REGISTRY[key];
        expect(entry, `${p} includes ${key}, which is not in the registry`).toBeDefined();
        // An include of a whole page would put a second `# Title` in the
        // middle of another one, and would mean a fragment nobody scoped.
        expect(entry.anchor, `${key} is included but carries no anchor`).not.toBeNull();
      }
    }
  });

  it('leaves no marker in any page the app renders', async () => {
    const broken: string[] = [];
    for (const key of Object.keys(CONTENT_REGISTRY)) {
      const entry = CONTENT_REGISTRY[key];
      const raw = page(entry.file);
      const scoped = entry.anchor ? sectionOf(raw, entry.anchor)?.body : raw;
      if (scoped === undefined) {
        broken.push(`${key}: no section «${entry.anchor}» in ${entry.file}`);
        continue;
      }
      const out = await expandIncludes(scoped, fromDisk, [key]);
      if (/«(missing include|missing section|circular include|include too deep)/.test(out)) {
        broken.push(`${key}: ${/«[^»]+»/.exec(out)![0]}`);
      }
      if (includesIn(out).length > 0) broken.push(`${key}: an include survived expansion`);
    }
    expect(broken).toEqual([]);
  });
});

describe('the passages this task moved are read from their source', () => {
  it('the publication gate is stated once, in the Board rules', async () => {
    const after = page('workflow/4-after.md');
    expect(includesIn(after)).toContain('fragments/board-rules-publication-gate');
    // The retelling is gone from the workflow page...
    expect(after).not.toMatch(/three working days/);
    // ...and present in what a volunteer actually reads there.
    const rendered = await expandIncludes(after, fromDisk, ['handbook/after']);
    expect(rendered).toMatch(/three working days/);
  });

  it('the split between the two hosts is stated once, in Roles', async () => {
    const hosting = page('workflow/3-hosting.md');
    expect(includesIn(hosting)).toContain('fragments/roles-host-pair');
    expect(hosting).not.toMatch(/introduces the speaker, runs the questions/);
    const rendered = await expandIncludes(hosting, fromDisk, ['handbook/hosting']);
    expect(rendered).toMatch(/introduces the speaker, runs the questions/);
  });

  it('the sentence about there being no ladder is stated once, in Roles', async () => {
    const start = page('start-here/index.md');
    expect(includesIn(start)).toContain('fragments/roles-no-ladder');
    expect(start).not.toMatch(/There is no ladder to climb/);
    const rendered = await expandIncludes(start, fromDisk, ['handbook/overview']);
    expect(rendered).toMatch(/There is no ladder to climb/);
  });
});
