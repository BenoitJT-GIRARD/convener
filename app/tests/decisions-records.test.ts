/**
 * The architecture decision records under `docs/engineering/decisions/`: the edited,
 * published form of the decisions this project took while it was built.
 * Four properties are pinned here rather than trusted by inspection:
 *
 * 1. Every `D-NN` file on disk is registered in `CONTENT_REGISTRY` under a
 *    `decisions/d-NN` key, and every such key names a file that exists --
 *    the two-way check `copy-handbook.test.ts` already runs generically
 *    for the whole registry, repeated here narrowly so a broken decisions
 *    entry is reported as a decisions problem, not a registry-wide one.
 * 2. The index names every record and every record is named by the index --
 *    checked as a real sweep of `index.md`'s own links against the files on
 *    disk, in both directions, so removing a record from either side fails
 *    here on its own.
 * 3. Each record carries the minimum an ADR needs: a status line, and
 *    `Context`, `Decision`, `Rejected` and `Cost` sections.
 * 4. Nothing under `docs/engineering/decisions/` links into `docs/superpowers/` --
 *    the working record, which stays local and is never published.
 *    `registered-links.test.ts` already forbids this indirectly, because
 *    nothing under `docs/superpowers/` is registered; this test pins the
 *    same guarantee directly, so it holds even if that indirect route ever
 *    changed.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { CONTENT_REGISTRY } from '../src/content/registry';

const DECISIONS_DIR = resolve(__dirname, '../../docs/engineering/decisions');

function page(file: string): string {
  return readFileSync(resolve(DECISIONS_DIR, file), 'utf-8');
}

/** The `d-NN-*.md` files actually on disk, sorted -- never a hard-coded
 *  count, so adding or removing a record changes what this test expects
 *  without anyone having to update a number here. */
function recordFilesOnDisk(): string[] {
  return readdirSync(DECISIONS_DIR)
    .filter(name => /^d-\d\d-.+\.md$/.test(name))
    .sort();
}

/** Local (in-repository) `.md` links in `text`, the same shape
 *  `registered-links.test.ts::localMdLinks` filters for. */
function localMdLinks(text: string): string[] {
  return [...text.matchAll(/\]\(([^)]+)\)/g)]
    .map(m => m[1])
    .filter(href => !/^[a-z][a-z0-9+.-]*:/i.test(href))
    .filter(href => !href.startsWith('#'))
    .map(href => href.split('#')[0])
    .filter(href => href.endsWith('.md'));
}

describe('every decision record on disk is registered, and vice versa', () => {
  const onDisk = recordFilesOnDisk();

  it('is a real sweep: at least one record file exists on disk', () => {
    expect(onDisk.length).toBeGreaterThan(0);
  });

  it('every decisions/d-NN registry entry names a file that exists on disk', () => {
    const decisionEntries = Object.entries(CONTENT_REGISTRY).filter(([key]) =>
      /^decisions\/d-\d\d$/.test(key),
    );
    expect(decisionEntries.length).toBeGreaterThan(0);
    const missing = decisionEntries
      .map(([key, entry]) => ({ key, file: entry.file }))
      .filter(({ file }) => !onDisk.includes(file.replace('engineering/decisions/', '')));
    expect(missing).toEqual([]);
  });

  it('every d-NN-*.md file on disk is registered under decisions/d-NN', () => {
    const registeredFiles = new Set(
      Object.values(CONTENT_REGISTRY)
        .map(e => e.file)
        .filter(f => f.startsWith('engineering/decisions/d-'))
        .map(f => f.replace('engineering/decisions/', '')),
    );
    const unregistered = onDisk.filter(name => !registeredFiles.has(name));
    expect(unregistered).toEqual([]);
  });
});

describe('the index names every record, and every record is named by the index', () => {
  const onDisk = recordFilesOnDisk();
  const indexLinks = new Set(localMdLinks(page('index.md')));

  it('is a real sweep: the index links to at least one record', () => {
    expect(indexLinks.size).toBeGreaterThan(0);
  });

  it('every record file on disk is linked from index.md', () => {
    const missingFromIndex = onDisk.filter(name => !indexLinks.has(name));
    expect(missingFromIndex).toEqual([]);
  });

  it('every link index.md makes to a d-NN file resolves to a real file on disk', () => {
    const onDiskSet = new Set(onDisk);
    const brokenLinks = [...indexLinks].filter(
      href => href.startsWith('d-') && !onDiskSet.has(href),
    );
    expect(brokenLinks).toEqual([]);
  });
});

describe('every record carries the minimum an ADR needs', () => {
  for (const file of recordFilesOnDisk()) {
    it(`${file} has a status line and Context, Decision, Rejected and Cost sections`, () => {
      const text = page(file);
      expect(text).toMatch(/^# D-\d\d — .+$/m);
      expect(text).toMatch(/^\*\*Status:\*\* .+$/m);
      expect(text).toMatch(/^## Context$/m);
      expect(text).toMatch(/^## Decision$/m);
      expect(text).toMatch(/^## Rejected$/m);
      expect(text).toMatch(/^## Cost$/m);
    });
  }
});

describe('nothing under docs/engineering/decisions/ links into docs/superpowers/', () => {
  const files = ['index.md', ...recordFilesOnDisk()];

  it('is a real sweep: at least one of these files carries a local link', () => {
    const anyLinks = files.some(f => localMdLinks(page(f)).length > 0);
    expect(anyLinks).toBe(true);
  });

  for (const file of files) {
    it(`${file} carries no link, and no bare mention, of docs/superpowers/`, () => {
      const text = page(file);
      const superpowersLinks = localMdLinks(text).filter(href => href.includes('superpowers'));
      expect(superpowersLinks).toEqual([]);
      expect(text).not.toContain('superpowers/');
    });
  }
});
