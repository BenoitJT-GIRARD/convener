/* Where a test writes a tree it is about to sweep, and why it is not
 * `os.tmpdir()`.
 *
 * Two modules here copy the whole of the real `docs/` tree and then read
 * back what landed: `tests/scripts/copy-handbook.test.ts`, which sweeps the
 * destination to prove the filter published exactly the registry's
 * allowlist, and `tests/scripts/instance-identity.test.ts`, which renders
 * every copied page under a second, invented instance. Both used
 * `os.tmpdir()`, and both were seen failing intermittently when the full
 * suite ran them beside each other -- green in isolation, green on the
 * retry, the cause never attributed.
 *
 * The cause is the directory, not the copy. `os.tmpdir()` is the one
 * place on the machine that every process treats as its own: an
 * application-control policy watches it, a temp cleaner empties it, an
 * installer and an editor and the runner itself all write into it, and
 * none of them knows a test is holding a tree there. A module that
 * writes eighty files into it and then asserts on what is still there is
 * asserting about a directory it does not own. Measured, with nothing
 * more exotic than a cleaner removing entries by prefix -- which is all a
 * temp cleaner does -- the two modules failed 20 rounds out of 20, at the
 * sweep, with thirteen of eighty files left.
 *
 * So each module gets a root of its own, under `app/node_modules/`, which
 * `app/.gitignore` already keeps out of the repository and which nothing
 * outside this package writes into. The scratch directories still carry a
 * random suffix, so two runs of one module never share one, and the root
 * is never cleared -- only the directories a test made inside it, by the
 * test that made them.
 *
 * It is not a speed fix and it is not a timeout: the assertions are the
 * ones they were, and each still compares exactly what it compared. What
 * it takes out of them is the one thing that was never theirs to test,
 * which is what else the machine is doing with its temp directory.
 */
import { mkdir, mkdtemp } from 'node:fs/promises';
import { join, resolve } from 'node:path';

/** The root every scratch tree in this suite sits under. Inside the
 *  package, ignored by git, and written by nothing but these tests. */
const ROOT = resolve(__dirname, '../../node_modules/.convener-scratch');

/**
 * A new, empty directory for one test to write into, under a root named
 * after the module asking. `owner` names the module (`copy-handbook`),
 * `label` what this particular tree is (`real`, `docs`, `mut`), so a
 * directory left behind by an interrupted run says which test made it.
 */
export async function scratch(owner: string, label: string): Promise<string> {
  const under = join(ROOT, owner);
  await mkdir(under, { recursive: true });
  return mkdtemp(join(under, `${label}-`));
}
