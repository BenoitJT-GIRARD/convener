/**
 * What the demonstration composes, and which instance each part of it came
 * from.
 *
 * A defect found late and left standing for a while.
 * Demo mode shows `examples/the-example-collective/`: its own
 * records, its board, its counter. Three values *around* those records
 * were still taken from the instance that built the bundle, and each one
 * came out belonging to neither instance:
 *
 * - the next edition code the date lock offers -- `MRG-4` for a series
 *   numbered `MRG-1` upwards, on the first control a visitor
 *   touches on a screen that invites them to number an edition;
 * - the placeholder in the field that code is typed into, `MRG-N`;
 * - the registration link a promotion draft prints for one of those
 *   records: this instance's own published root with the example's own
 *   `events/mrg-1/` under it, an address neither instance serves, and
 *   one the demonstration offers a Copy button for.
 *
 * The demo band covers none of them: it says where the *records* come
 * from, not where a value composed beside them comes from.
 *
 * Every expected value below is derived from the example instance's own
 * files on disk, never typed here -- an assertion written against `MRG`
 * would pass just as well the day somebody put a literal back. And each
 * one is checked through `disagree` first: two instances that declared
 * the same value would make the assertion that follows say nothing at
 * all.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import * as yaml from 'js-yaml';
import { AuthProvider } from '../../src/auth/AuthContext';
import { DataProvider } from '../../src/data/DataContext';
import { DatePanel } from '../../src/components/DatePanel';
import { demoConfig, demoSpeakers } from '../../src/data/demo';
import { editionCodePrefix, nextEditionCode } from '../../src/state/agenda';
import { substitute } from '../../src/content/render';
import { ONE_INSTANCE } from '../helpers/one-instance';
import type { Speaker } from '../../src/data/types';

const ROOT = resolve(__dirname, '../..', '..');

function declaration(relative: string): Record<string, string> {
  return JSON.parse(readFileSync(resolve(ROOT, relative), 'utf8')) as Record<string, string>;
}

/** The two declarations, read where each one lives. Never a constant in
 *  this file: the point of the whole suite is that nothing composes one of
 *  these values from a literal. */
const THIS_INSTANCE = declaration('instance/config.json');
const EXAMPLE = declaration('examples/the-example-collective/instance/config.json');

/** The example's own counter, out of its own governance file -- the same
 *  number `demoConfig()` carries, read from the other end so the assertion
 *  is not the bundle agreeing with itself. */
const EXAMPLE_COUNTER = (
  yaml.load(
    readFileSync(
      resolve(ROOT, 'examples', 'the-example-collective', 'instance', 'data', 'config.yml'),
      'utf8',
    ),
  ) as { next_edition_number: number }
).next_edition_number;

/** An assertion is only worth making about a value the two instances
 *  actually declare differently. */
function disagree(key: string): void {
  expect(EXAMPLE[key], `both instances declare the same ${key}`).not.toBe(
    THIS_INSTANCE[key],
  );
}

/** The example instance's own record waiting for a date to be locked --
 *  the one state that puts the edition-code field on screen. Taken from
 *  the records the demonstration actually serves, not invented here. */
function confirmedExampleRecord(): Speaker {
  const record = demoSpeakers().find(s => s.status === 'confirmed');
  expect(
    record,
    'the example instance holds no confirmed record to lock a date for',
  ).toBeDefined();
  return record as Speaker;
}

/** Its own record that already has a code, for the address a promotion
 *  draft prints. */
function scheduledExampleRecord(): Speaker {
  const record = demoSpeakers().find(s => s.status === 'scheduled' && !!s.edition_code);
  expect(
    record,
    'the example instance holds no scheduled record carrying a code',
  ).toBeDefined();
  return record as Speaker;
}

function inDemo() {
  localStorage.setItem('convener.demo', '1');
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
});

describe.skipIf(ONE_INSTANCE)('the edition code the demonstration offers', () => {
  it('is numbered under the example instance own prefix, not this one', () => {
    disagree('edition_prefix');
    inDemo();
    expect(editionCodePrefix()).toBe(`${EXAMPLE.edition_prefix}-`);
    expect(nextEditionCode(demoSpeakers(), demoConfig().next_edition_number)).toBe(
      `${EXAMPLE.edition_prefix}-${EXAMPLE_COUNTER}`,
    );
  });

  it('carries nothing of the instance that built the bundle', () => {
    disagree('edition_prefix');
    inDemo();
    const offered = nextEditionCode(demoSpeakers(), demoConfig().next_edition_number);
    expect(offered.startsWith(`${THIS_INSTANCE.edition_prefix}-`)).toBe(false);
  });

  it('skips a number the example own records already hold', () => {
    // Non-vacuity for the counter: the example numbers three sessions
    // already, so an offer that ignored them would collide with one.
    inDemo();
    const used = demoSpeakers()
      .map(s => s.edition_code)
      .filter(Boolean);
    expect(used.length).toBeGreaterThan(0);
    expect(used).not.toContain(nextEditionCode(demoSpeakers(), demoConfig().next_edition_number));
  });

  it('is still this instance own outside the demonstration', () => {
    // The correction must not have moved the value the other way: a
    // signed-in operator numbers *this* series, and an edition code is
    // the one value here that cannot be corrected after the fact.
    disagree('edition_prefix');
    expect(editionCodePrefix()).toBe(`${THIS_INSTANCE.edition_prefix}-`);
    expect(nextEditionCode([], 6)).toBe(`${THIS_INSTANCE.edition_prefix}-6`);
  });
});

describe.skipIf(ONE_INSTANCE)('the field that code is typed into', () => {
  function lockScreen() {
    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <DatePanel speaker={confirmedExampleRecord()} role="board" mode="lock" />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );
  }

  it('shows the example instance own prefix while the demonstration runs', async () => {
    disagree('edition_prefix');
    inDemo();
    lockScreen();
    // `tests/setup.ts` leaves `fetch` throwing, so getting this far is
    // also the assertion that nothing was read from anywhere.
    const field = await waitFor(() =>
      screen.getByPlaceholderText(`${EXAMPLE.edition_prefix}-N`),
    );
    expect(field).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText(`${THIS_INSTANCE.edition_prefix}-N`),
    ).not.toBeInTheDocument();
  });

  it('fills in the example instance own next code when asked to suggest one', async () => {
    disagree('edition_prefix');
    inDemo();
    lockScreen();
    const suggest = await waitFor(() => screen.getByText('Suggest the next code'));
    suggest.click();
    await waitFor(() =>
      expect(screen.getByPlaceholderText(`${EXAMPLE.edition_prefix}-N`)).toHaveValue(
        `${EXAMPLE.edition_prefix}-${EXAMPLE_COUNTER}`,
      ),
    );
  });
});

describe.skipIf(ONE_INSTANCE)('the registration link a demonstration draft prints', () => {
  const TEMPLATE = 'Register here: {{ speaker.signup_link }}';

  it('is under the example instance own published address', () => {
    disagree('published_url');
    inDemo();
    const record = scheduledExampleRecord();
    const out = substitute(TEMPLATE, { speaker: record });
    expect(out).toBe(
      `Register here: ${EXAMPLE.published_url}events/${record.edition_code.toLowerCase()}/`,
    );
    expect(out).not.toContain(THIS_INSTANCE.published_url);
  });

  it('is under this instance own address outside the demonstration', () => {
    disagree('published_url');
    const record = scheduledExampleRecord();
    const out = substitute(TEMPLATE, { speaker: record });
    expect(out).toBe(
      `Register here: ${THIS_INSTANCE.published_url}events/${record.edition_code.toLowerCase()}/`,
    );
  });
});

describe('what the demonstration refuses to compose from', () => {
  // A refusal that has never been run is a refusal nobody has checked --
  // and each of these three is the difference between a demonstration that
  // stops by name and one that offers `undefined-4` as the next edition of
  // a series. `src/settings/example.ts` caches what it takes out of the
  // define, exactly as a real bundle does, so each case resets the module
  // registry rather than poking at the cache.
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  async function exampleWith(settings: string | null) {
    vi.resetModules();
    vi.stubEnv('VITE_EXAMPLE_SETTINGS', settings === null ? '' : settings);
    return import('../../src/settings/example');
  }

  it('stops when the bundle was built without the define at all', async () => {
    const { exampleEditionPrefix } = await exampleWith(null);
    expect(() => exampleEditionPrefix()).toThrow(/VITE_EXAMPLE_SETTINGS/);
  });

  it('stops when the define carries no declaration for the example instance', async () => {
    const { exampleEditionPrefix } = await exampleWith(
      JSON.stringify({ files: {}, drainTriggers: {} }),
    );
    expect(() => exampleEditionPrefix()).toThrow(/instance\/config\.json/);
  });

  it('stops when that declaration names no value to compose from', async () => {
    const { examplePublishedUrl } = await exampleWith(
      JSON.stringify({
        files: { 'instance/config.json': '{"edition_prefix": "MRG"}' },
        drainTriggers: {},
      }),
    );
    expect(() => examplePublishedUrl()).toThrow(/published_url/);
  });
});
