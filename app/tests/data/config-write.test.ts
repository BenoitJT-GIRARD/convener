import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { configTextFor } from '../../src/data/config-write';
import { parseConfig, CONFIG_HEADER } from '../../src/data/yaml';
import type { Config } from '../../src/data/types';

/** The repository root, two levels up from `app/tests/`. */
const ROOT = resolve(__dirname, '../../..');

/** The shipped `instance/data/config.yml`, because this is a defect about a
 *  real file's real prose and a hand-written fixture would have proved
 *  nothing: what was lost on a live instance was thirty lines of exactly this
 *  shape, and the point is that it survives *this*. */
const SHIPPED = readFileSync(resolve(ROOT, 'instance/data/config.yml'), 'utf-8');

function comments(text: string): string[] {
  return text.split('\n').filter(line => line.trimStart().startsWith('#'));
}

/** Every "comment line then key line" pair the file holds, as one string
 *  each: what it means for a comment to be about the key under it. */
function adjacentPairs(text: string): string[] {
  const lines = text.split('\n');
  const pairs: string[] = [];
  for (let i = 1; i < lines.length; i++) {
    if (lines[i - 1].trimStart().startsWith('#') && /^[A-Za-z_]/.test(lines[i])) {
      pairs.push(`${lines[i - 1]}\n${lines[i]}`);
    }
  }
  return pairs;
}

function keys(text: string): string[] {
  return text
    .split('\n')
    .filter(line => /^[A-Za-z_][A-Za-z0-9_]*:/.test(line))
    .map(line => line.split(':')[0]);
}

describe('writing config.yml without deleting the reasoning in it', () => {
  it('keeps every comment when one integer changes', () => {
    // The reported defect, on the file it was reported against. Advancing the
    // edition counter took a live instance's config.yml from 31 comment lines
    // to 1, in a commit whose subject said it had advanced a counter.
    const before = parseConfig(SHIPPED);
    const next: Config = { ...before, next_edition_number: before.next_edition_number + 1 };

    const written = configTextFor(SHIPPED, next);

    expect(comments(written)).toEqual(comments(SHIPPED));
    expect(comments(written).length).toBeGreaterThan(20);
  });

  it('keeps the file own header rather than substituting a constant', () => {
    const before = parseConfig(SHIPPED);
    const written = configTextFor(SHIPPED, {
      ...before,
      next_edition_number: before.next_edition_number + 1,
    });

    expect(written.startsWith(SHIPPED.split('\n')[0])).toBe(true);
  });

  it('keeps the order the file was arranged in', () => {
    // The other half of the damage. A write that moved one integer also
    // reordered every key, because the canonical dump order is not the order
    // somebody had arranged the file in.
    const before = parseConfig(SHIPPED);
    const written = configTextFor(SHIPPED, {
      ...before,
      next_edition_number: before.next_edition_number + 1,
    });

    expect(keys(written)).toEqual(keys(SHIPPED));
  });

  it('actually writes the value that changed', () => {
    // Non-vacuity, and the one that a writer preserving everything would
    // fail: a file kept perfectly and never updated is not a fix.
    const before = parseConfig(SHIPPED);
    const next: Config = { ...before, next_edition_number: 42 };

    const written = configTextFor(SHIPPED, next);

    expect(parseConfig(written).next_edition_number).toBe(42);
  });

  it('round-trips to exactly the value it was given', () => {
    // The property everything else here is in service of: whatever bytes come
    // out, reading them back has to give the record the caller meant to
    // write. A preserving writer that preserved a stale value would be worse
    // than the defect.
    const before = parseConfig(SHIPPED);
    const next: Config = {
      ...before,
      next_edition_number: 7,
      board_min: before.board_min + 1,
    };

    expect(parseConfig(configTextFor(SHIPPED, next))).toEqual(next);
  });

  it('rewrites only the block that changed', () => {
    const before = parseConfig(SHIPPED);
    const written = configTextFor(SHIPPED, { ...before, next_edition_number: 99 });

    const differing = written
      .split('\n')
      .filter((line, i) => line !== SHIPPED.split('\n')[i]);
    expect(differing).toEqual(['next_edition_number: 99']);
  });

  it('carries a comment with the key it belongs to', () => {
    // On the shipped file, because a hand-written fixture is not a `Config`
    // and `parseConfig` refuses one -- which is the right behaviour and is
    // read below, but makes a toy fixture prove nothing about this.
    const before = parseConfig(SHIPPED);
    const written = configTextFor(SHIPPED, { ...before, board_min: before.board_min + 1 });

    for (const pair of adjacentPairs(SHIPPED)) {
      expect(written, pair).toContain(pair);
    }
  });

  it('lets a removed key take its own explanation with it', () => {
    // A comment is about the key under it. Orphaning one above the next key
    // would leave a file explaining something that is no longer there, which
    // is worse than losing it.
    const original = ['# the header', 'season: 2026', '# about a gone key', 'gone: 1', ''].join(
      '\n',
    );
    const next = { season: 2026 } as unknown as Config;

    const written = configTextFor(original, next);

    expect(written).not.toContain('about a gone key');
    expect(written).not.toContain('gone:');
  });

  it('writes a fresh file when there is nothing to preserve', () => {
    const next = { season: 2026 } as unknown as Config;

    expect(configTextFor('', next).startsWith(CONFIG_HEADER)).toBe(true);
    expect(configTextFor('   \n', next).startsWith(CONFIG_HEADER)).toBe(true);
  });

  it('falls back rather than refusing when the original cannot be read', () => {
    // A file that does not parse has no blocks to keep, and a writer that
    // threw here would leave a volunteer unable to save anything at all
    // because of a file they may not have written.
    const next = { season: 2026 } as unknown as Config;

    const written = configTextFor('season: [unclosed\n', next);

    expect(written.startsWith(CONFIG_HEADER)).toBe(true);
    expect(written).toContain('season: 2026');
  });

  it('never has to add a key, because a file missing one is refused first', () => {
    // Why there is no branch in the writer for a key the dump has and the
    // file does not: the reader refuses such a file outright rather than
    // defaulting it, so the writer falls back to a fresh dump and never
    // reaches the question. Read here so the absent branch stays absent for a
    // reason somebody can check.
    const without = SHIPPED.split('\n')
      .filter(line => !line.startsWith('instructions:'))
      .join('\n');

    expect(() => parseConfig(without)).toThrow(/missing "instructions"/);
  });
});
