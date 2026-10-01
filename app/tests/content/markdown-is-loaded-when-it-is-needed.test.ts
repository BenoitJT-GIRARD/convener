/**
 * The markdown renderer reaches a volunteer when a screen renders content, and
 * not before.
 *
 * `react-markdown` and `remark-gfm` bring seventy-one packages of the unified
 * pipeline. Measured in this bundle, by building once with them and once
 * without: **45,808 B gzip, 21% of it.** One file imported them, and most
 * screens a volunteer opens render no handbook content at all — the pipeline,
 * the agenda, the board, the settings. Every one of those was paying for a
 * markdown renderer on arrival.
 *
 * `site/scripts/check-performance-budget.mjs` weighs the cockpit's document
 * plus every resource that document asks for, which is what a volunteer
 * downloads before anything is on screen. After the split that reading is
 * 183,818 B against a 235,520 B budget, where it had been 229,700 against the
 * same — and the budget's own comment says there is no raise left, because any
 * ceiling above it stops catching the bundle that once carried 69 KB of a file
 * no screen draws.
 *
 * **Why a reading of the source and not only of the number.** The number moves
 * for all sorts of reasons and somebody chasing it would not know what broke;
 * this names the one line that breaks it. A static `import ReactMarkdown` in
 * `InlineContent.tsx` puts the pipeline straight back into the entry chunk,
 * and nothing on screen changes — the application behaves identically, every
 * test passes, and the only trace is forty-five kilobytes a volunteer
 * downloads to look at a list of speakers.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const CONTENT = resolve(__dirname, '../../src/content');

/** A static import of `name`, in the forms this codebase writes them. A
 *  `import type` is erased at build time and is not one: it costs nothing and
 *  `Markdown.tsx` needs `Components` to type its own overrides. */
function staticallyImports(source: string, name: string): boolean {
  const pattern = new RegExp(
    String.raw`^\s*import\s+(?!type\s)[^;]*?from\s+'${name}'`,
    'm',
  );
  return pattern.test(source);
}

const PIPELINE = ['react-markdown', 'remark-gfm'];

describe('the markdown pipeline is fetched, not shipped', () => {
  it('is imported by one module and no other', () => {
    // Derived rather than listed: a second file importing it would put it
    // back in the entry chunk through its own importers, however careful
    // `InlineContent` was.
    const importers = readdirSync(CONTENT)
      .filter(name => name.endsWith('.ts') || name.endsWith('.tsx'))
      .filter(name => {
        const source = readFileSync(resolve(CONTENT, name), 'utf-8');
        return PIPELINE.some(pkg => staticallyImports(source, pkg));
      });

    expect(importers).toEqual(['Markdown.tsx']);
  });

  it('is reached from InlineContent by a dynamic import', () => {
    const source = readFileSync(resolve(CONTENT, 'InlineContent.tsx'), 'utf-8');

    expect(source).toMatch(/lazy\(\(\) => import\('\.\/Markdown'\)\)/);
    for (const pkg of PIPELINE) {
      expect(staticallyImports(source, pkg), pkg).toBe(false);
    }
  });

  it('is rendered inside a boundary that can wait for it', () => {
    // A `lazy` component thrown without a `Suspense` above it is a runtime
    // error on the first content screen somebody opens, which is the one
    // failure this split can introduce and the one no bundle measurement
    // would see.
    const source = readFileSync(resolve(CONTENT, 'InlineContent.tsx'), 'utf-8');

    expect(source).toContain('<Suspense');
    expect(source.indexOf('<Suspense')).toBeLessThan(source.indexOf('<Markdown'));
  });

  it('reads a static import for what it is', () => {
    // Positive control, on probes: a reader that matched nothing would let
    // the first assertion pass over an empty list and the second over a file
    // that imports whatever it likes.
    expect(staticallyImports("import ReactMarkdown from 'react-markdown';", 'react-markdown')).toBe(
      true,
    );
    expect(staticallyImports("import remarkGfm from 'remark-gfm';", 'remark-gfm')).toBe(true);
    expect(
      staticallyImports("import type { Components } from 'react-markdown';", 'react-markdown'),
      'a type-only import is erased and costs nothing',
    ).toBe(false);
    expect(
      staticallyImports("const M = lazy(() => import('./Markdown'));", 'react-markdown'),
      'a dynamic import of a local module is the shape this test is for',
    ).toBe(false);
  });
});
