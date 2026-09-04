/**
 * No link the cockpit renders opens a raw markdown file.
 *
 * Every page of the handbook is written to be read in the repository, so
 * its cross-references are relative paths to other `.md` files. Rendered
 * in the application those resolved under `docs/`, which is where the
 * build publishes the files themselves -- so clicking *Editorial line*
 * inside the frame a lead is validated from left the cockpit and showed
 * the source text of a markdown file, with no way back. It was never
 * three links: it is every cross-reference every rendered page carries,
 * and a page added next month would carry more.
 *
 * So this is a sweep rather than a list. It reads the same registry the
 * application renders from, walks each page's own links, and refuses any
 * that still resolves to a markdown address. A page whose link points
 * somewhere the registry does not render fails
 * `registered-links.test.ts` first, which is the other half of the same
 * rule: that one says every target is a page this application can
 * render, this one says every one of them is actually rendered by it.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { CONTENT_REGISTRY } from '../../src/content/registry';
import { handbookUrl } from '../../src/content/fetch';

const DOCS = resolve(__dirname, '../../../docs');

function page(file: string): string {
  return readFileSync(resolve(DOCS, file), 'utf-8');
}

/** Every link written in `text` that stays inside the repository: no URL
 *  scheme and not a same-page anchor. Assets included -- the point of
 *  this sweep is what each one *resolves to*, and an asset resolving to
 *  a file is the correct answer for an asset. */
function localLinks(text: string): string[] {
  return [...text.matchAll(/\]\(([^)]+)\)/g)]
    .map(m => m[1])
    .filter(href => !/^[a-z][a-z0-9+.-]*:/i.test(href))
    .filter(href => !href.startsWith('#'));
}

/** The address, with any fragment cut off it: what a browser would ask a
 *  server for. */
function withoutFragment(url: string): string {
  const at = url.indexOf('#', 1);
  return at === -1 ? url : url.slice(0, at);
}

describe('a cockpit link never resolves to a markdown file', () => {
  const keys = Object.keys(CONTENT_REGISTRY).sort();

  it('is a real sweep: the registered pages do carry local links', () => {
    // The guard `registered-links.test.ts` puts on its own walk, for the
    // same reason: an empty sweep passes every case below vacuously.
    const links = keys.flatMap(key => localLinks(page(CONTENT_REGISTRY[key].file)));
    expect(links.length).toBeGreaterThan(100);
  });

  for (const key of keys) {
    it(`${key} sends every one of its links to a page or to an asset`, () => {
      const raw = localLinks(page(CONTENT_REGISTRY[key].file))
        .map(href => ({ href, url: handbookUrl(key, href) }))
        .filter(({ url }) => withoutFragment(url).endsWith('.md'));
      expect(raw, `${key} still opens markdown: ${JSON.stringify(raw)}`).toEqual([]);
    });
  }
});

describe('where a link inside a handbook page lands', () => {
  it('a page the registry renders becomes a route of this application', () => {
    // The first of the three links R29 named, from the frame a lead is
    // validated from.
    expect(handbookUrl('governance/selection-criteria', 'editorial-line.md')).toBe(
      '#/handbook/governance/editorial-line',
    );
  });

  it('a fragment and nothing more, so the demonstration survives a click', () => {
    // `?demo=1` lives in the query string and the router lives in the
    // fragment: an address composed here would drop the flag and drop
    // the visitor on a sign-in screen.
    expect(handbookUrl('governance/selection-criteria', 'conflict-of-interest.md')).toMatch(
      /^#\//,
    );
  });

  it('carries a section anchor through to the page it opens', () => {
    expect(
      handbookUrl(
        'governance/conflict-of-interest',
        '../toolkit/run-of-show.md#results-that-have-not-been-peer-reviewed',
      ),
    ).toBe('#/handbook/toolkit/run-of-show#results-that-have-not-been-peer-reviewed');
  });

  it('leaves an asset addressing the file, because there the file is the destination', () => {
    expect(handbookUrl('toolkit/visual-kit', '../assets/flyer-template.svg')).toContain(
      '/docs/handbook/assets/flyer-template.svg',
    );
  });

  it('resolves a markdown file nothing renders to the file, and says so by doing it', () => {
    // `operating/operations.md` is deliberately unregistered -- it is
    // operational detail rather than handbook content -- and no
    // registered page links to it any more (`registered-links.test.ts`).
    // If one ever does, this is what it gets, and that test is what
    // refuses it.
    expect(
      handbookUrl('governance/editorial-line', '../../operating/operations.md'),
    ).toContain('/docs/operating/operations.md');
  });
});
