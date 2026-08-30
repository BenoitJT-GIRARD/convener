/**
 * Where the instance's own paths sit, read from `config/boundary.yml` --
 * this build's side of it.
 *
 * `tools/convener_ops/declaration/paths.py` is Python's reader of the same
 * declaration. Each of them names the declared paths once and every
 * caller builds the files it touches out of those names, so moving
 * `instance/data/` in the declaration moves them with it.
 *
 * Read at build time, in Node, with `node:fs`: the copy scripts under
 * this directory run before `vite build` and `vite.config.ts` loads in
 * Node too. The browser is served by `src/paths.ts`, which reads the
 * result back out of the `define` `vite.config.ts` puts it in.
 *
 * `src/settings/declaration.ts` reads the same file for the settings
 * screen, from text fetched through the Contents API, and answers a
 * different question: the whole of each entry, its reason and what the
 * product keeps inside it. This one answers where each declared path is.
 *
 * Throws rather than defaulting. A build that cannot read this file does
 * not know where the instance's records are, and the alternative to
 * stopping is a bundle asking GitHub for `undefined/speakers.yml`.
 */

import { readFileSync } from 'node:fs';
import yaml from 'js-yaml';

/** `config/boundary.yml`, from this file's own location -- the app's
 *  build runs with `app/` as its working directory, so a path relative
 *  to the process is not the same thing. */
const DECLARATION = new URL('../../config/boundary.yml', import.meta.url);

const NAMED = 'config/boundary.yml';

/** Mirrors `boundary.DECLARATION_VERSION`. A file carrying a version this
 *  reader does not know is refused. */
const DECLARATION_VERSION = 1;

const PRODUCT = 'product';

/** The two directories whose configuration files state their own owner,
 *  and what such a file may be written in. Mirrors `boundary.CONFIG_DIRS`
 *  and `boundary.CONFIG_READERS`. */
const CONFIG_DIRS = ['config', 'instance'];
const CONFIG_SUFFIXES = ['.yml', '.json'];

/** Whether `path` is a configuration file that answers for itself.
 *  Mirrors `boundary.states_its_own_owner`. */
function statesItsOwnOwner(path) {
  const cut = path.lastIndexOf('/');
  const parent = cut === -1 ? '' : path.slice(0, cut);
  const name = path.slice(cut + 1);
  return (
    CONFIG_DIRS.includes(parent) && CONFIG_SUFFIXES.some(suffix => name.endsWith(suffix))
  );
}

/**
 * The declared paths, keyed by their final component.
 *
 * The key is what the path holds -- `data`, `keys`, `public-data`,
 * `register.md` -- so a declaration that moves one of them keeps
 * answering to the same key. Mirrors `paths.by_last_component`, refusal
 * included: two entries sharing a final component leave a caller no way
 * to say which of the two it meant.
 */
export function byLastComponent(paths) {
  const found = {};
  for (const path of paths) {
    const trimmed = path.replace(/\/+$/, '');
    const name = trimmed.slice(trimmed.lastIndexOf('/') + 1);
    if (Object.hasOwn(found, name)) {
      throw new Error(
        `${NAMED}: two declared instance paths end in '${name}' (${found[name]} ` +
          `and ${path}), so a name built on this one has no way to say which of ` +
          'the two it means'
      );
    }
    found[name] = path;
  }
  return found;
}

/**
 * Every path an already-loaded declaration hands to the instance.
 *
 * The checks mirror `boundary.declaration_from_data` and
 * `src/settings/declaration.ts::handedFromData`, including the
 * configuration file that would put one fact in two places: each of those
 * states its own answer in its own `owner:` key.
 */
export function handedFrom(data) {
  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error(`${NAMED} is not a supported format version`);
  }
  if (data.v !== DECLARATION_VERSION) {
    throw new Error(`${NAMED} is not a supported format version`);
  }
  if (data.owner !== PRODUCT) {
    throw new Error(
      `${NAMED} must declare \`owner: ${PRODUCT}\` -- the list of what an ` +
        "instance owns is the product's own statement about itself"
    );
  }
  const raw = data.instance;
  if (!Array.isArray(raw) || raw.length === 0) {
    throw new Error(`${NAMED}: instance: must be a non-empty list`);
  }
  return raw.map(item => {
    const path = item === null || typeof item !== 'object' ? undefined : item.path;
    if (typeof path !== 'string' || path.trim() !== path || path === '') {
      throw new Error(`${NAMED}: instance: holds an entry whose path is ${path}`);
    }
    if (statesItsOwnOwner(path)) {
      throw new Error(
        `${NAMED}: ${path} is a configuration file, whose files state their own ` +
          'owner in their own `owner:` key. Naming it here too would make one ' +
          'fact two places.'
      );
    }
    return path;
  });
}

let cached = null;

/** The declared instance paths, keyed by their final component. */
export function instancePaths() {
  cached ??= byLastComponent(handedFrom(yaml.load(readFileSync(DECLARATION, 'utf8'))));
  return cached;
}

/** The declared instance path whose final component is `name`. */
export function handed(name) {
  const found = instancePaths();
  if (!Object.hasOwn(found, name)) {
    throw new Error(
      `${NAMED} hands the instance no path ending in '${name}'. It hands over ` +
        `${Object.keys(found).sort().join(', ')}.`
    );
  }
  return found[name];
}

/** The instance's own records and its governance configuration. */
export function dataDir() {
  return handed('data');
}

/** The instance's published public keys, event keys and signing keys both. */
export function keysDir() {
  return handed('keys');
}

/** Everything the instance publishes about itself, derived from `dataDir()`
 *  by the product's own commands. */
export function publicDataDir() {
  return handed('public-data');
}

/** The decision register, re-rendered from this repository's own commit
 *  history on every push. */
export function registerPath() {
  return handed('register.md');
}
