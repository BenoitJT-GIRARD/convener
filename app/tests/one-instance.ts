/* Whether the instance running this repository is the product's own
 * example -- the condition under which a test about the *difference*
 * between two instances has no subject.
 *
 * `convener_ops.derivation.derivation` lays `instances/example/` into every path
 * `config/boundary.yml` hands to the instance, because a product
 * repository with those paths merely deleted neither starts its own
 * suite nor builds: several modules read an instance path while they
 * load, `paths.repo_root` finds a repository by `instance/data/config.yml`, and
 * the product's default charter has no `motif`. The consequence is exact
 * and is not a compromise -- **in the derived repository the instance
 * and the example are the same instance**, so every declared value
 * agrees with itself, and a build made as the example legitimately
 * carries the example's identity.
 *
 * A test whose subject is that difference therefore has nothing to be
 * about there, and asserting it anyway makes it fail for the one reason
 * it cannot fix. It comes back the moment a duplicate declares its own
 * identity -- the same moment `unconfigured()` stops naming anything and
 * the same moment the cockpit's own banner goes quiet. One condition,
 * three readers: this file, `tools/tests/instance_identity.py`, and the
 * banner itself.
 *
 * Asked of `scripts/published.mjs::unconfiguredFrom`, which is the
 * product's own definition rather than a second opinion on it. The two
 * files are read here rather than there because a module the test runner
 * transformed has no `file:` `import.meta.url`, so `unconfigured()`'s
 * own reads throw under vitest -- which is exactly why that function was
 * split in two.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { unconfiguredFrom } from '../scripts/published.mjs';

const ROOT = resolve(__dirname, '..', '..');

function declaration(relative: string): unknown {
  return JSON.parse(readFileSync(resolve(ROOT, relative), 'utf8')) as unknown;
}

/** True while this repository's declaration is still the example's. */
export const ONE_INSTANCE: boolean =
  unconfiguredFrom(
    declaration('instance/config.json'),
    declaration('instances/example/instance/config.json'),
  ).length > 0;

/** Why a skipped test is skipped, in the words a reader needs. */
export const ONE_INSTANCE_REASON =
  'the instance running this repository is the product\'s own example, so ' +
  'there is no second instance for this to be about -- it runs again as ' +
  'soon as a duplicate declares its own';
