/**
 * What this instance numbers its editions, on this side of the language
 * boundary.
 *
 * `tools/convener_ops/governance/validate.py` used to fix an edition code as
 * `MRG-` and one to four digits -- the initials of the series that happens
 * to run this repository, written into the *product's* own validator --
 * and `state/agenda.ts::nextEditionCode` composed `MRG-${n}` from a
 * literal to match. Neither could be caught by the one sweep that
 * compares two instances, because both instances were forced to write it.
 *
 * Two claims live here, and they are different claims:
 *
 * 1. **The two readers of `instance/config.json::edition_prefix` agree
 *    about what a prefix is.** `tools/tests/fixtures/edition-prefix.json`
 *    holds the cases and both sides answer them --
 *    `tools/tests/declaration/test_published.py` against `published.EDITION_PREFIX_RE`
 *    there, `isEditionPrefix` here. A prefix the build accepts and the
 *    validator refuses is a repository that can be built and cannot be
 *    validated, which is the kind of disagreement a worked example
 *    catches and a comment does not (D-14).
 * 2. **Nothing in the bundle composes a code from a literal any more.**
 *    `nextEditionCode` runs under a *second, invented* prefix and carries
 *    nothing of this instance's, the same shape
 *    `instance-identity.test.ts` already applies to the identity.
 *
 * `src/instance.ts` parses its define once and caches it, exactly as a
 * real bundle does, so each case resets the module registry rather than
 * poking at the cache.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isEditionPrefix } from '../scripts/published.mjs';
import { speaker } from './data-doubles';

interface PrefixCase {
  value: string;
  accepted: boolean;
  why: string;
}

const FIXTURE = resolve(
  __dirname,
  '..',
  '..',
  'tools',
  'tests',
  'fixtures',
  'edition-prefix.json',
);
const cases: PrefixCase[] = JSON.parse(readFileSync(FIXTURE, 'utf-8')).cases;

/** A second instance's prefix, invented and nothing like this one's --
 *  the point being that an assertion which passed under `MRG` would pass
 *  just as well if the literal were still in the source. */
const OTHER = 'QZL';

/** The agenda module, loaded with a given prefix in the bundle. */
async function agendaWith(prefix: string | null) {
  vi.resetModules();
  vi.stubEnv('VITE_INSTANCE_EDITION_PREFIX', prefix === null ? '' : prefix);
  return import('../src/state/agenda');
}

beforeEach(() => {
  vi.unstubAllEnvs();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('the shape a declared prefix may take', () => {
  it('answers every shared case the way the other reader does', () => {
    expect(cases.length).toBeGreaterThan(4);
    for (const one of cases) {
      expect(isEditionPrefix(one.value), `${one.value}: ${one.why}`).toBe(one.accepted);
    }
  });

  it('has cases on both sides, so neither verdict passes for free', () => {
    expect(cases.some(one => one.accepted)).toBe(true);
    expect(cases.some(one => !one.accepted)).toBe(true);
  });

  it('refuses anything that is not a string at all', () => {
    for (const value of [undefined, null, 7, ['MRG'], { value: 'MRG' }]) {
      expect(isEditionPrefix(value)).toBe(false);
    }
  });
});

describe('the next edition code', () => {
  it('is composed from whatever the declaration holds', async () => {
    const { nextEditionCode } = await agendaWith(OTHER);
    expect(nextEditionCode([], 1)).toBe(`${OTHER}-1`);
  });

  it('skips a number another edition already holds under that prefix', async () => {
    const { nextEditionCode } = await agendaWith(OTHER);
    const used = [
      speaker({ id: 'a', edition_code: `${OTHER}-1` }),
      speaker({ id: 'b', edition_code: `${OTHER}-3` }),
    ];
    expect(nextEditionCode(used, 1)).toBe(`${OTHER}-2`);
    expect(nextEditionCode(used, 4)).toBe(`${OTHER}-4`);
  });

  it('does not read another instance numbering as taken', async () => {
    const { nextEditionCode } = await agendaWith(OTHER);
    expect(nextEditionCode([speaker({ edition_code: 'MRG-1' })], 1)).toBe(`${OTHER}-1`);
  });

  it('stops rather than composing a code from a define that is not there', async () => {
    // Not a default and not an ordinary state: a bundle with no define is
    // a broken build, and the alternative to throwing is a cockpit
    // offering `undefined-6` as the next edition of a series -- an
    // edition code being the one value here that cannot be corrected
    // afterwards, since it is in a published address, on an issued
    // certificate and in a key filename.
    const { nextEditionCode } = await agendaWith(null);
    expect(() => nextEditionCode([], 1)).toThrow(/VITE_INSTANCE_EDITION_PREFIX/);
  });
});
