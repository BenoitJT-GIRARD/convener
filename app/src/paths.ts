/**
 * Where the instance's own paths sit, on the application's side of the
 * language boundary.
 *
 * One declaration -- `declarations/boundary.yml` -- and one reader per
 * language: `tools/convener_ops/declaration/paths.py` for Python,
 * `app/scripts/instance-paths.mjs` for this build. This module is how the
 * paths that build read reach the browser, where no file can be read at
 * all. `vite.config.ts` substitutes them into every bundle through Vite's
 * own `define`, as it already does for the published address and the
 * identity.
 *
 * The route has to be the `define`. `DataContext` asks GitHub for
 * `instance/data/speakers.yml` before anything has been fetched, and demo mode
 * asks for nothing at all, so the declaration is not in hand at the
 * moment the paths are needed. `settings/declaration.ts` parses the same
 * file in the browser for the settings screen, from text the Contents API
 * returns to a signed-in volunteer; that arrives too late and only on one
 * screen.
 *
 * Throws rather than defaulting, the rule `instance.ts` follows. A bundle
 * built without the define would ask GitHub for `undefined/speakers.yml`
 * and report the answer as a missing file.
 */

/** The declared instance paths, keyed by their final component --
 *  `data`, `keys`, `public-data`, `register.md`. The key is what the path
 *  holds, so a declaration that moves one of them keeps answering to the
 *  same key (`scripts/instance-paths.mjs::byLastComponent`,
 *  `paths.by_last_component`). */
export type InstancePaths = Record<string, string>;

let cached: InstancePaths | null = null;

/** Every path this instance owns, as the declaration writes them: a
 *  directory carries its trailing slash. */
export function instancePaths(): InstancePaths {
  if (cached) return cached;
  const raw = import.meta.env.VITE_INSTANCE_PATHS as string | undefined;
  if (!raw) {
    throw new Error(
      'VITE_INSTANCE_PATHS is unset: this bundle was built without ' +
        "vite.config.ts's own define, so it cannot say where this instance's " +
        'own files are (see declarations/boundary.yml)',
    );
  }
  cached = JSON.parse(raw) as InstancePaths;
  return cached;
}

/** The declared instance path whose final component is `name`. */
function handed(name: string): string {
  const found = instancePaths();
  const path = Object.hasOwn(found, name) ? found[name] : undefined;
  if (path === undefined) {
    throw new Error(
      `declarations/boundary.yml hands the instance no path ending in '${name}'. It ` +
        `hands over ${Object.keys(found).sort().join(', ')}.`,
    );
  }
  return path;
}

/** The instance's own records and its governance configuration. */
export function dataDir(): string {
  return handed('data');
}

/** The instance's published public keys, event keys and signing keys both. */
export function keysDir(): string {
  return handed('keys');
}

/** Everything the instance publishes about itself, derived from `dataDir()`
 *  by the product's own commands. */
export function publicDataDir(): string {
  return handed('public-data');
}

/** The decision register, re-rendered from this repository's own commit
 *  history on every push. */
export function registerPath(): string {
  return handed('register.md');
}

/** The speaker and event records, which five screens read and write
 *  through the Contents API. */
export function speakersFile(): string {
  return `${dataDir()}speakers.yml`;
}

/** The board, its thresholds and the promotion channels. */
export function configFile(): string {
  return `${dataDir()}config.yml`;
}

/**
 * Where one event's sign-ups are kept, one encrypted envelope per person
 * (`tools/convener_ops/journey/registration.py`).
 *
 * The cockpit never decrypts it and never asks to: what it reads is how many
 * entries the list has, which is JSON structure rather than anybody's data.
 */
export function registrationsFile(eventId: string): string {
  return `${dataDir()}events/${eventId}/registrations.enc`;
}
