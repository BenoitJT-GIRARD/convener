/**
 * The example instance's own data, on its way into the demonstration.
 *
 * `instances/example/` is a whole second instance, invented -- the one
 * `tools/tests/test_second_instance.py` lays into this repository's own
 * holes to prove that a build made as somebody else carries nothing of the
 * series that happens to run it. It belongs to the product rather than to
 * an instance, and this is the task that makes it the product's first
 * consumer as well as its proof: `src/data/demo.ts` used to hold five
 * speaker records and a governance configuration of its own invention, and
 * two of that invention's strings named *this* organisation's forum and
 * its LinkedIn page. They were compiled into the cockpit's bundle, so a
 * duplicate shipped them too -- which is why
 * `tools/tests/instance_identity.py`'s deferred register carried an entry
 * for that file until this task removed it.
 *
 * Read as bytes, never parsed here. `src/data/demo.ts` parses them with
 * `src/data/yaml.ts`, the very reader every real `data/speakers.yml` goes
 * through, so the demonstration is the example instance read exactly the
 * way a repository's own data is read -- and an example that stopped
 * matching the model would stop the demonstration loudly instead of
 * rendering half of it.
 *
 * `vite.config.ts` carries the result into the bundle through Vite's own
 * `define`, for the reason it already carries the published address and
 * the identity that way: the cockpit is a static bundle and no file can be
 * read where it runs. The alternative -- publishing these two files into
 * `dist/` with a seventh `copy-*.mjs` and fetching them at run time --
 * would have made the demonstration's own data asynchronous where it is
 * resolved synchronously today (`DataContext`'s own `initialState`), put a
 * request on the wire in the one mode narrowed to
 * "reads only from the origin that served it", and published
 * one instance's example data at another instance's public address.
 *
 * Throws rather than defaulting, the same rule `published.mjs` follows: a
 * build that cannot read the example cannot demonstrate it, and the
 * alternative to stopping is a cockpit whose demonstration is an empty
 * table.
 */

import { readFileSync } from 'node:fs';

/** `instances/example/data/`, from this file's own location -- the app's
 *  build runs with `app/` as its working directory, so a path relative to
 *  the process is not the same thing. */
const DATA = new URL('../../instances/example/data/', import.meta.url);

const NAMED = 'instances/example/data';

function read(name) {
  const text = readFileSync(new URL(name, DATA), 'utf8');
  if (text.trim() === '') {
    throw new Error(`${NAMED}/${name} is empty -- there would be nothing to demonstrate`);
  }
  return text;
}

/**
 * The two files the cockpit's demonstration is built from, as text.
 *
 * Both, always, and in one call: the two are one instance, and a build
 * that carried the speakers of one and the governance of another would be
 * demonstrating a repository nobody has.
 */
export function exampleInstance() {
  return { config: read('config.yml'), speakers: read('speakers.yml') };
}
