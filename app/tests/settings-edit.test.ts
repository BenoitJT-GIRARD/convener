/**
 * Changing a number in a `config/` file without deleting the argument for
 * it.
 *
 * `config/queue-drain.yml` is five and a half kilobytes of which two lines
 * are values: the rest is why the floor is two drain periods and not one,
 * why the ceiling is the lane threshold minus the same, and what happens to
 * a participant when either is wrong. A parse-and-serialise through
 * `js-yaml` would emit two lines and drop all of it -- the cockpit deleting
 * the reasoning behind the very number it had just changed, quietly, in a
 * commit whose subject says only that a setting moved.
 *
 * So the tests below are driven against **this repository's own files**,
 * not against a sample laid out to make the edit easy. What is asserted is
 * a byte count and a diff of exactly one line.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { EditRefused, alreadySays, setScalar } from '../src/settings/edit';

const ROOT = resolve(__dirname, '..', '..');

function repositoryFile(relative: string): string {
  return readFileSync(resolve(ROOT, relative), 'utf-8');
}

/** The lines that differ between two texts, as `-`/`+` pairs. */
function differing(before: string, after: string): string[] {
  const left = before.split('\n');
  const right = after.split('\n');
  expect(left.length).toBe(right.length);
  const out: string[] = [];
  left.forEach((line, index) => {
    if (line !== right[index]) out.push(`-${line}`, `+${right[index]}`);
  });
  return out;
}

describe('one number, changed in place', () => {
  it('moves exactly one line of the real queue-drain declaration', () => {
    const before = repositoryFile('config/queue-drain.yml');
    const after = setScalar(before, 'alarm_after_hours', 72);
    expect(differing(before, after)).toEqual(['-alarm_after_hours: 48', '+alarm_after_hours: 72']);
  });

  it('keeps every word of the argument the file makes for itself', () => {
    const before = repositoryFile('config/queue-drain.yml');
    const after = setScalar(before, 'alarm_after_hours', 72);
    // Every comment line the file had, still there. A YAML round trip
    // takes all of them out and nothing would have said so.
    //
    // Two of its sentences were quoted here once, and
    // they were one instance's: `config/queue-drain.yml` is the
    // instance's file, so a product test quoting its prose asserted
    // which repository it was running in. The example instance's copy
    // of that file argues its case in four lines rather than forty.
    const comments = before.split('\n').filter(line => line.trimStart().startsWith('#'));
    expect(comments.length).toBeGreaterThan(2);
    comments.forEach(line => expect(after).toContain(line));
    expect(after.length - before.length).toBe(0);
  });

  it('writes a share without a tail of digits', () => {
    const before = repositoryFile('config/actions-budget.yml');
    const after = setScalar(before, 'warn_at_share', 0.9);
    expect(differing(before, after)).toEqual(['-warn_at_share: 0.75', '+warn_at_share: 0.9']);
  });

  it('changes the file the key is in and no other key in it', () => {
    const before = repositoryFile('config/actions-budget.yml');
    const after = setScalar(before, 'max_silent_days', 3);
    expect(after).toContain('max_runs: 200');
    expect(after).toContain('monthly_minutes: 2000');
    expect(differing(before, after)).toEqual(['-max_silent_days: 2', '+max_silent_days: 3']);
  });

  it('leaves the owner header alone, so the file still answers for itself', () => {
    const after = setScalar(repositoryFile('config/registration-lanes.yml'), 'queue_beyond_hours', 168);
    expect(after).toContain('owner: instance');
  });
});

describe('what it refuses rather than repairs', () => {
  it('refuses a key the file does not hold', () => {
    expect(() => setScalar('alarm_after_hours: 48\n', 'queue_beyond_hours', 96)).toThrow(
      EditRefused,
    );
    expect(() => setScalar('alarm_after_hours: 48\n', 'queue_beyond_hours', 96)).toThrow(
      /nothing here to change/,
    );
  });

  it('refuses a key the file holds twice, rather than picking one', () => {
    const twice = 'alarm_after_hours: 48\nmax_silent_days: 2\nalarm_after_hours: 96\n';
    expect(() => setScalar(twice, 'alarm_after_hours', 72)).toThrow(/appears 2 times/);
  });

  it('does not match an indented key of the same name', () => {
    const nested = 'sla_days:\n  alarm_after_hours: 48\n';
    expect(() => setScalar(nested, 'alarm_after_hours', 72)).toThrow(/nothing here to change/);
  });

  it('refuses a value that does not read back as itself', () => {
    // The read-back is what makes the surgical edit safe rather than
    // merely quick: a value the reader would give back as something else
    // never reaches a commit.
    expect(() => setScalar('alarm_after_hours: 48\n', 'alarm_after_hours', Number.NaN)).toThrow(
      /reads back as/,
    );
  });

  it('says nothing was written, in every refusal', () => {
    const attempts: Array<() => unknown> = [
      () => setScalar('a: 1\n', 'b', 2),
      () => setScalar('a: 1\na: 2\n', 'a', 3),
      () => setScalar('a: 1\n', 'a', Number.NaN),
    ];
    for (const attempt of attempts) {
      expect(attempt).toThrow(/Nothing was written/);
    }
  });
});

describe('a save that changes nothing', () => {
  it('is recognised before anything is asked of GitHub', () => {
    const text = repositoryFile('config/queue-drain.yml');
    expect(alreadySays(text, 'alarm_after_hours', 48)).toBe(true);
    expect(alreadySays(text, 'alarm_after_hours', 72)).toBe(false);
    expect(alreadySays('not: yaml: at: all', 'alarm_after_hours', 48)).toBe(false);
  });
});
