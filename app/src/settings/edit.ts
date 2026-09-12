/**
 * Changing one number in a configuration file without losing the argument for
 * it.
 *
 * These files are not data. `instance/queue-drain.yml` is five and a half
 * kilobytes, of which two lines are values and the rest is the reasoning:
 * why the floor is two drain periods and not one, why the ceiling is the
 * lane threshold minus the same, what happens to a participant when either
 * is wrong. `instance/registration-lanes.yml` and
 * `instance/actions-budget.yml` are the same shape. That prose is the only
 * place those decisions are written down, and this repository's whole
 * method rests on it.
 *
 * So a write here is **not** a parse-and-serialise. `js-yaml` drops every
 * comment on the way in and would emit two lines where a file used to
 * argue its own case -- the cockpit would silently delete the reasoning
 * behind the very number it just changed. What happens instead is a
 * replacement of exactly one line, in place, leaving every other byte
 * alone: the same discipline `instance/data/speakers.yml`'s own writer keeps for a
 * different reason (`data/yaml.ts`'s `DUMP` options exist so the browser
 * and PyYAML write identical bytes).
 *
 * The replacement is then **read back**. A surgical edit that produced a
 * file whose key no longer parses to the intended value would be worse
 * than a round trip, because it would look like it worked; so the result
 * is parsed and the value checked before it is offered to anybody, and a
 * mismatch throws rather than being written.
 */
import { loadDocument } from '../data/yaml';

/** A file this module will not edit -- because the key is not there, is
 *  there twice, or does not read back. Its own class so the screen can show
 *  the sentence rather than a stack. */
export class EditRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'EditRefused';
  }
}

/** A top-level scalar assignment: the key at column nought, a colon, and
 *  the value to the end of the line. Anchored per line, and deliberately
 *  unable to match an indented key -- a nested `max_silent_days:` under
 *  some future block is a different setting, and matching it would be the
 *  quiet kind of wrong. */
function assignment(key: string): RegExp {
  // Every key this module is ever given comes from the parsed document's
  // own top level, and `settingKey` in `state/decisions.ts` refuses
  // anything that is not word characters -- so there is nothing here to
  // escape for the pattern.
  return new RegExp(`^${key}:[^\\n]*$`, 'gm');
}

/** How a number is written into YAML: JavaScript's own shortest
 *  representation that reads back to the same double, so `0.75` stays
 *  `0.75` in a tracked file rather than acquiring a tail of digits. The
 *  read-back below is what makes that a checked claim rather than a hoped
 *  one -- an exponent form, say, would fail there rather than land. */
function renderScalar(value: number): string {
  return String(value);
}

/**
 * `text` with `key`'s value replaced, and nothing else touched.
 *
 * Refuses -- never repairs -- when the key is absent (the file is not the
 * one this screen thought it was reading), when it appears more than once
 * (whichever is read last would win, silently), or when the result does not
 * parse back to the value asked for.
 */
export function setScalar(text: string, key: string, value: number): string {
  const pattern = assignment(key);
  const found = text.match(pattern);
  if (found === null) {
    throw new EditRefused(
      `${key} is not a top-level setting in this file, so there is nothing here ` +
        'to change. Nothing was written.',
    );
  }
  if (found.length > 1) {
    throw new EditRefused(
      `${key} appears ${found.length} times at the top level of this file. ` +
        'Whichever line was read last would decide, which is not a decision ' +
        'anybody made. Nothing was written.',
    );
  }
  const next = text.replace(assignment(key), `${key}: ${renderScalar(value)}`);
  const loaded: unknown = loadDocument(next);
  const readBack =
    loaded !== null && typeof loaded === 'object'
      ? (loaded as Record<string, unknown>)[key]
      : undefined;
  if (readBack !== value) {
    throw new EditRefused(
      `${key} was written as ${renderScalar(value)} and reads back as ` +
        `${JSON.stringify(readBack ?? null)}. Nothing was written.`,
    );
  }
  return next;
}

/** Whether a file already says this, so a save that changes nothing writes
 *  no commit. `mutate` makes the same comparison on the whole text; this is
 *  what lets the screen say so before asking. */
export function alreadySays(text: string, key: string, value: number): boolean {
  // A file this reader cannot parse at all has not been checked to say
  // anything, so it does not say this. The refusal that matters comes from
  // `setScalar`, which reads the *result* back; answering `false` here only
  // means the save is attempted rather than skipped.
  let loaded: unknown;
  try {
    loaded = loadDocument(text);
  } catch {
    return false;
  }
  return (
    loaded !== null &&
    typeof loaded === 'object' &&
    (loaded as Record<string, unknown>)[key] === value
  );
}
