/**
 * The visual kit: the announcement image, the flyer and the video-call
 * background, kept as source files in the repository rather than inside one
 * person's account on a design tool.
 *
 * What is worth asserting here is not what the templates look like — that is a
 * judgement, not a test — but the three ways this could quietly stop being
 * available to a volunteer:
 *
 * 1. A link in the kit points at a file that is not there.
 * 2. The file is there, but the build never copies it, so the download is a
 *    404 for everyone using the app. This is the failure the previous copy
 *    step had: it walked `.md` only and skipped `docs/assets/` outright, and
 *    the video-call background had been sitting unreachable behind that.
 * 3. A template drifts into a closed format, or grows until nobody wants to
 *    clone the repository — the two ways this kit's own purpose is undone.
 */
import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { InlineContent } from '../src/content/InlineContent';
import { invalidateContent } from '../src/content/fetch';
import { CONTENT_REGISTRY, PUBLIC_ASSETS } from '../src/content/registry';
import { handbookUrl } from '../src/content/fetch';
import { substitute } from '../src/content/render';
import { speaker as double } from './data-doubles';
// The generic doc-tree rule (extension + skip-dir), unrelated to the
// registry-derived allowlist below: still what decides whether a random
// file under docs/ could ever be servable at all.
import { walk, isServed } from '../scripts/handbook-files.mjs';

const KIT_KEY = 'toolkit/visual-kit';
const DOCS = resolve(__dirname, '../../docs');
const TEMPLATES = ['assets/announcement-template.svg', 'assets/flyer-template.svg'];
const BACKGROUND = 'assets/zoom-background.png';
// This used to be a fourth published asset. It was a real
// speaker's own photograph and name, kept without a later, separate
// consent to use them as a sample -- see `PUBLIC_ASSETS`'s own comment.
// Named here so the tests below assert its absence rather than simply
// omitting it -- an omission a later change could not tell apart from an
// oversight.
const WITHDRAWN_EXAMPLE = 'assets/flyer-example.png';

function kit(): string {
  return readFileSync(resolve(DOCS, CONTENT_REGISTRY[KIT_KEY].file), 'utf-8');
}

/** Every markdown link in the kit that points inside the repository. */
function localLinks(): string[] {
  return [...kit().matchAll(/\]\(([^)]+)\)/g)]
    .map(m => m[1])
    .filter(href => !/^[a-z][a-z0-9+.-]*:/i.test(href));
}

let served: string[];
beforeAll(async () => {
  served = (await walk(DOCS)).map((p: string) => p.split('\\').join('/'));
});

describe('the kit is reachable', () => {
  it('is a handbook page like any other', () => {
    expect(CONTENT_REGISTRY[KIT_KEY]).toEqual({ file: 'toolkit/visual-kit.md', anchor: null });
  });

  it('is listed on the templates index', () => {
    const index = readFileSync(resolve(DOCS, 'toolkit/index.md'), 'utf-8');
    expect(index).toContain('(visual-kit.md)');
  });

  it('links only to files that exist', () => {
    for (const href of localLinks()) {
      const path = resolve(DOCS, 'toolkit', href.split('#')[0]);
      expect(statSync(path).isFile(), `${href} is missing`).toBe(true);
    }
  });

  it('offers both templates and the video-call background', () => {
    const links = localLinks();
    for (const file of [...TEMPLATES, BACKGROUND]) {
      expect(links).toContain(`../${file}`);
    }
  });
});

describe('the build serves what the kit links to', () => {
  // `PUBLIC_ASSETS` is the actual allowlist `copy-handbook.mjs` publishes
  // from now on (see `handbook-registry.mjs`) -- unlike `walk(DOCS)` above,
  // asserting against it is asserting against what the build really does,
  // not against a rule the build no longer uses to decide this.
  it('names exactly the kit\'s two templates and its background -- no finished example', () => {
    expect([...PUBLIC_ASSETS].sort()).toEqual([...TEMPLATES, BACKGROUND].sort());
  });

  it.each([...TEMPLATES, BACKGROUND])('%s is in the allowlist the build publishes', file => {
    expect(PUBLIC_ASSETS).toContain(file);
  });

  it('never republishes the withdrawn example -- a real speaker\'s photograph, not a synthetic one', () => {
    expect(PUBLIC_ASSETS).not.toContain(WITHDRAWN_EXAMPLE);
    // Nor does the page still point at it: the row was rewritten to say
    // plainly that the slot is empty, not filled with a substitute. (Not
    // asserted here: that the page's text no longer names the speaker --
    // that would put her real name in the clear in this test file to
    // check for it, which the fix this test is guarding is not allowed to
    // do either.)
    expect(localLinks()).not.toContain(`../${WITHDRAWN_EXAMPLE}`);
  });

  it('turns a link written for the repository into one the app can fetch', () => {
    // Written `../assets/flyer-template.svg` so it works when read on GitHub;
    // resolved against the file's own directory so it works in the app.
    const url = handbookUrl(KIT_KEY, '../assets/flyer-template.svg');
    expect(url.endsWith('/handbook/assets/flyer-template.svg'), url).toBe(true);
    expect(url).not.toContain('..');
    // And the published path is exactly where the copy step puts the file.
    expect(PUBLIC_ASSETS).toContain('assets/flyer-template.svg');
  });

  it('leaves external links alone and drops unsafe schemes', () => {
    expect(handbookUrl(KIT_KEY, 'https://inkscape.org')).toBe('https://inkscape.org');
    expect(handbookUrl(KIT_KEY, 'javascript:alert(1)')).toBe('');
  });

  it('still refuses everything that is not content, under the generic doc-tree rule', () => {
    // Orthogonal to the allowlist above: this is the extension/skip-dir
    // rule that decides whether a random file under docs/ could ever be
    // servable at all, regardless of the registry. Widening it to `docs/`
    // wholesale would let the specs, the plans and whatever else lands
    // there back into scope for that rule -- the registry-derived
    // allowlist above is what actually keeps them out of the build.
    expect(isServed('notes.txt')).toBe(false);
    expect(isServed('archive.zip')).toBe(false);
    expect(served.some(p => p.startsWith('superpowers/'))).toBe(false);
  });
});

describe('the templates stay open, and stay light', () => {
  it.each(TEMPLATES)('%s is SVG source, not a wrapped bitmap', file => {
    const text = readFileSync(resolve(DOCS, file), 'utf-8');
    expect(text).toContain('<svg');
    // An SVG whose content is one embedded base64 image is a binary in a
    // costume: it cannot be edited, and it weighs what the bitmap weighed.
    expect(text).not.toContain('base64');
    // Nor may it reach out to a font or an image on someone's server: that is
    // the shared-account dependency again, one HTTP request further away.
    // (The one URL allowed is the SVG namespace itself, which is an
    // identifier and never fetched.)
    expect(text).not.toMatch(/(?:href|src)\s*=\s*"https?:/i);
    expect(text).not.toMatch(/url\(\s*['"]?https?:/i);
    expect(text).not.toContain('@import');
  });

  it.each(TEMPLATES)('%s stays small enough to clone without thinking', file => {
    expect(statSync(resolve(DOCS, file)).size).toBeLessThan(30_000);
  });

  it('names only substitutions the app can resolve', () => {
    // The placeholders are copied out of the app by hand, so they have to be
    // the app's own names: an invented `{{speaker.institute}}` would send a
    // volunteer looking for a field that does not exist.
    for (const file of TEMPLATES) {
      const filled = substitute(readFileSync(resolve(DOCS, file), 'utf-8'), {
        speaker: double({
          id: 'sp-x',
          name: 'Wren Ashgrove',
          affiliation: 'Institute of Invented Things',
          title: 'Counting what nobody counted',
          edition_code: 'MRG-999',
          date: '2026-11-12',
          time: '12:30',
        }),
      });
      expect(filled, file).not.toMatch(/«missing: [\w.]/);
    }
  });
});

describe('the download link a volunteer actually clicks', () => {
  beforeEach(() => {
    invalidateContent();
    vi.unstubAllGlobals();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => kit() }),
    );
  });

  it('renders the flyer link pointing at the copied file, not at the route', async () => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <InlineContent contentKey={KIT_KEY} variant="page" />
        </AuthProvider>
      </MemoryRouter>,
    );
    const link = await screen.findByRole('link', { name: /^Flyer$/ });
    // Rendered as written -- `../assets/...` -- the browser would resolve this
    // against the templates route and hand back a 404.
    expect(link.getAttribute('href')).toBe(handbookUrl(KIT_KEY, '../assets/flyer-template.svg'));
    expect(link.getAttribute('href')).not.toContain('..');
  });
});
