/**
 * Every registered page links only to another registered page, or leaves
 * the repository entirely (an absolute URL, a mailto:, or an anchor within
 * itself).
 *
 * This was once not true: `docs/operating/operations.md` was
 * linked from eight registered pages, and `docs/handbook/governance/register.md`
 * from two, neither of them registered. Fixing those nine links one at a
 * time -- rewriting the prose, or registering the two pages that turned out
 * to deserve it -- closes today's instances and nothing else: exactly the
 * argument this project's own `public_data.py` already makes against a
 * denylist, applied to links instead of fields. This test closes the
 * *class*: it is a sweep over `Object.values(CONTENT_REGISTRY)`, generated
 * once per registered page at collection time, so a page added next month
 * with a stray relative link to something unregistered fails here, on its
 * own, without anyone having named it in advance.
 *
 * "Unregistered" is deliberately about `CONTENT_REGISTRY` alone, not
 * `PUBLIC_ASSETS`: a registered page's local link is markdown-to-markdown
 * prose, never a download to an image, so the file it can legitimately
 * reach this way is another rendered page, not an asset.
 */
import { readFileSync } from 'node:fs';
import { dirname, join, normalize, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { CONTENT_REGISTRY } from '../../src/content/registry';

const DOCS = resolve(__dirname, '../../../docs');

function page(file: string): string {
  return readFileSync(resolve(DOCS, file), 'utf-8');
}

/** Local (in-repository) markdown links in `text`: no URL scheme, not a
 *  same-page `#anchor`, and ending in `.md` once any anchor is stripped --
 *  the exact shape `visual-kit.test.tsx::localLinks` filters for assets,
 *  narrowed here to the page-to-page case. */
function localMdLinks(text: string): string[] {
  return [...text.matchAll(/\]\(([^)]+)\)/g)]
    .map(m => m[1])
    .filter(href => !/^[a-z][a-z0-9+.-]*:/i.test(href))
    .filter(href => !href.startsWith('#'))
    .map(href => href.split('#')[0])
    .filter(href => href.endsWith('.md'));
}

/** Where a link written inside `fromFile` resolves to, as a docs-relative,
 *  slash-separated path -- the same directory arithmetic `handbookUrl`
 *  applies to a URL at runtime, done here against the filesystem instead. */
function resolveLink(fromFile: string, href: string): string {
  return normalize(join(dirname(fromFile), href)).split('\\').join('/');
}

describe('every registered page links only to other registered pages', () => {
  const registryFiles = new Set(Object.values(CONTENT_REGISTRY).map(e => e.file));

  it('is a real sweep: at least one registered page links to another one', () => {
    // An empty sweep would pass every case below vacuously -- the same
    // guard `message-templates.test.ts` puts on its own walk of `docs/`.
    const anyLinks = [...registryFiles].some(f => localMdLinks(page(f)).length > 0);
    expect(anyLinks).toBe(true);
  });

  for (const file of [...registryFiles].sort()) {
    it(`${file} links only to registered pages, or leaves the repository`, () => {
      const broken = localMdLinks(page(file))
        .map(href => ({ href, target: resolveLink(file, href) }))
        .filter(({ target }) => !registryFiles.has(target));
      expect(broken, `${file} links to: ${JSON.stringify(broken)}`).toEqual([]);
    });
  }
});
