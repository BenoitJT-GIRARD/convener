/**
 * The example instance's own settings, on their way into the
 * demonstration.
 *
 * The settings screen reads every configuration file `declarations/` and
 * `instance/` hold directly -- the product's own in the first, this
 * instance's in the second. Signed in, it lists both directories and reads
 * what it finds, through `github/contents.ts`. In demo mode it cannot: a
 * demonstration reads only from the origin that served it
 * (`src/net/request.ts`), and it has no repository at all.
 *
 * So the demonstration reads the example instance instead -- the same one
 * `src/data/demo.ts` already shows, the one
 * `tools/tests/repository/test_second_instance.py` lays into this repository's own
 * holes on every run. Its four configuration files are in
 * `examples/the-example-collective/instance/`; the product's are this
 * repository's own, because they are the product's and a duplicate does not
 * have its own copy of them.
 *
 * Read as bytes, never parsed here -- exactly as `example-instance.mjs`
 * reads the example's data. `src/settings/declaration.ts` parses them, the
 * very reader the signed-in path parses the real files with, so the
 * demonstration exercises the code the cockpit actually runs rather than a
 * shape somebody laid out to look like it.
 *
 * The one exception is the drain's schedule, and the exception is
 * deliberate. `.github/workflows/sweep-and-notify.yml` is fifty-four
 * kilobytes and carries every step of the daily job; what the bounds need
 * out of it is its `on:` block. This module converts that one subtree from
 * YAML to JSON and carries it -- a change of format, not a reading of
 * meaning. Which cron shapes may be put a number on, and what number, stays
 * where it belongs: `src/settings/bounds.ts::drainPeriodHours`, pinned to
 * `registration_routing.drain_period_hours` by
 * `tools/tests/fixtures/instance-settings.json`.
 *
 * Throws rather than defaulting, the same rule `published.mjs` and
 * `example-instance.mjs` both follow: a build that cannot read the example
 * cannot demonstrate it, and the alternative to stopping is a settings
 * screen whose every bound reads `undefined`.
 */

import { readdirSync, readFileSync } from 'node:fs';
import yaml from 'js-yaml';

/** This repository's own root, from this file's location -- the app's build
 *  runs with `app/` as its working directory, so a path relative to the
 *  process is not the same thing. */
const ROOT = new URL('../../', import.meta.url);

/** What a configuration file is called, mirroring `CONFIG_SUFFIXES` in
 *  `src/settings/declaration.ts` and `boundary.CONFIG_READERS` behind it. */
const CONFIG_SUFFIXES = ['.yml', '.json'];

/** The files `declarations/` holds, read off the directory rather than
 *  listed. The signed-in path lists that directory and reads what is in it,
 *  so a list typed here would be a second answer to the same question --
 *  and the demonstration would go on showing the files somebody remembered
 *  the day one was added. Not taken from `examples/the-example-collective/`,
 *  which does not hold them and must not: they are the product's, and a
 *  duplicate inherits them rather than writing its own. */
function productFiles() {
  const found = readdirSync(new URL('declarations/', ROOT))
    .filter(name => CONFIG_SUFFIXES.some(suffix => name.endsWith(suffix)))
    .sort()
    .map(name => `declarations/${name}`);
  if (found.length === 0) {
    throw new Error(
      'declarations/ holds no configuration file, so the demonstration would ' +
        'have no product declaration to show',
    );
  }
  return found;
}

/** The four the instance owns, read from the example's own copies. Named by
 *  their `instance/` path, which is where they sit in the tree the screen
 *  describes -- `examples/the-example-collective/` is where this build finds them, not
 *  what they are. */
const INSTANCE_FILES = [
  'instance/actions-budget.yml',
  'instance/config.json',
  'instance/queue-drain.yml',
  'instance/registration-lanes.yml',
];

const DRAIN_WORKFLOW = '.github/workflows/sweep-and-notify.yml';

function read(relative, named) {
  const text = readFileSync(new URL(relative, ROOT), 'utf8');
  if (text.trim() === '') {
    throw new Error(`${named} is empty -- the demonstration would have no ${named} to show`);
  }
  return text;
}

/**
 * The whole of what the demonstration's settings screen reads, as text.
 *
 * Every file, always, and in one call: they are one repository's answer
 * to one question, and a build that carried the boundary of one and the
 * thresholds of another would be describing an instance nobody has.
 */
export function exampleSettings() {
  const files = {};
  for (const name of productFiles()) files[name] = read(name, name);
  for (const name of INSTANCE_FILES) {
    files[name] = read(`examples/the-example-collective/${name}`, `examples/the-example-collective/${name}`);
  }

  const workflow = yaml.load(read(DRAIN_WORKFLOW, DRAIN_WORKFLOW));
  // `on:` resolves to the string key under this reader and to the boolean
  // `true` under PyYAML's YAML-1.1 resolver; `drainSchedule` in
  // `src/settings/bounds.ts` reads both, so what is carried here is the
  // whole `on:` block under whichever key it was found, and nothing here
  // decides anything about it.
  const triggers = workflow?.on ?? workflow?.true;
  if (triggers === undefined) {
    throw new Error(
      `${DRAIN_WORKFLOW} declares no \`on:\` block, so the demonstration has ` +
        "no drain cadence to derive the queue alarm's bounds from",
    );
  }
  return { files, drainTriggers: { on: triggers } };
}
