/**
 * Which paths this instance owns, and what each declared integration is
 * for -- read in the browser, from the same two files the tooling reads.
 *
 * The settings screen has to say what it is settling, and
 * the honest answer to "what is the instance's?" is already written down
 * once: `declarations/boundary.yml` names the directories the instance owns
 * whole, and each configuration file `CONFIG_DIRS` holds directly states
 * its own answer in its own `owner:` key.
 * `tools/convener_ops/declaration/boundary.py` is the reader on the other side of the
 * language boundary; this is the browser's, and it reads the same bytes
 * rather than a list somebody typed into a screen. A hand-typed list would
 * be a third home for the boundary, in the one place where being wrong is
 * invisible -- a screen offering to edit a file upstream owns, or quietly
 * omitting one the instance has to.
 *
 * **The default is the product.** Everything the declaration does not name
 * belongs to the product. A path becomes the instance's by being named,
 * never by being forgotten -- so this reader has nothing to guess at, and
 * refuses rather than repairing anything it cannot read: a boundary read
 * wrongly is worse than a boundary not read at all.
 *
 * `tools/tests/declaration/test_boundary.py` is what holds the repository against the
 * declaration; nothing here duplicates that work. What this module does is
 * answer, in the browser, the two questions the screen asks: which paths,
 * and -- for the integrations -- which secrets, and what breaks without
 * each.
 */
import yaml from 'js-yaml';

/** Where the declaration lives, and the two directories whose
 *  configuration files answer for themselves. Named here rather than
 *  repeated at every call site. Mirrors `boundary.CONFIG_DIRS`:
 *  `declarations/` is the product's own and `instance/` is this instance's, and
 *  only the files they hold *directly* state an owner -- `instance/`'s
 *  subdirectories are handed over whole, by the declaration. */
export const BOUNDARY_PATH = 'declarations/boundary.yml';
export const INTEGRATIONS_PATH = 'declarations/integrations.yml';
export const CONFIG_DIRS = ['declarations', 'instance'];

/** What a configuration file may be written in -- `boundary.CONFIG_READERS`
 *  seen as a list of suffixes. */
export const CONFIG_SUFFIXES = ['.yml', '.json'];

/** Whether `path` is a configuration file that answers for itself: one of
 *  `CONFIG_DIRS` holds it directly, in one of `CONFIG_SUFFIXES`. Mirrors
 *  `boundary.states_its_own_owner`. */
export function statesItsOwnOwner(path: string): boolean {
  const cut = path.lastIndexOf('/');
  const parent = cut === -1 ? '' : path.slice(0, cut);
  const name = path.slice(cut + 1);
  return (
    CONFIG_DIRS.includes(parent) && CONFIG_SUFFIXES.some(suffix => name.endsWith(suffix))
  );
}

/** The declaration's own format version, and the integrations file's.
 *  Mirrors `boundary.DECLARATION_VERSION`. A file carrying a version this
 *  reader does not know is refused, never read optimistically. */
const DECLARATION_VERSION = 1;

export const INSTANCE = 'instance';
export const PRODUCT = 'product';

/** The two answers, and the only two -- `boundary.OWNERS`. A third would be
 *  a path nobody has decided about. */
const OWNERS: readonly string[] = [INSTANCE, PRODUCT];

/** A declaration this reader will not read. Refusing is the whole point,
 *  so it is its own class and carries the file it was reading. */
export class DeclarationRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DeclarationRefused';
  }
}

/** One path the product hands to the instance. A directory when the path
 *  ends in `/`; the distinction matters because a directory entry covers
 *  files that do not exist yet, which is what a fresh duplicate has. */
export interface Handed {
  path: string;
  reason: string;
  /** Files the product keeps inside a directory the instance owns. */
  kept: string[];
  /** Rewritten in full by a scheduled job, upstream's own runs included --
   *  `boundary.Handed.regenerated`. A form must never offer to edit one. */
  regenerated: boolean;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown, what: string, named: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new DeclarationRefused(`${named}: ${what} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Parse an already-loaded `declarations/boundary.yml`.
 *
 * Refuses, never repairs -- including the two mistakes `boundary.py`
 * names, because a reader that accepted one and a reader that refused it
 * would disagree about the boundary itself: a configuration path named in the
 * list (its answer belongs in its own header) and an entry with no reason.
 */
export function handedFromData(data: unknown): Handed[] {
  const document = asRecord(data);
  if (document === null || document.v !== DECLARATION_VERSION) {
    throw new DeclarationRefused(`${BOUNDARY_PATH} is not a supported format version`);
  }
  if (document.owner !== PRODUCT) {
    throw new DeclarationRefused(
      `${BOUNDARY_PATH} must declare \`owner: ${PRODUCT}\` — the list of what ` +
        "an instance owns is the product's own statement about itself",
    );
  }
  const raw = document.instance;
  if (!Array.isArray(raw) || raw.length === 0) {
    throw new DeclarationRefused(`${BOUNDARY_PATH}: instance: must be a non-empty list`);
  }
  return raw.map(item => {
    const entry = asRecord(item);
    if (entry === null) {
      throw new DeclarationRefused(
        `${BOUNDARY_PATH}: instance: holds something that is not an entry`,
      );
    }
    const path = nonEmptyString(entry.path, 'an instance path', BOUNDARY_PATH);
    if (statesItsOwnOwner(path)) {
      throw new DeclarationRefused(
        `${BOUNDARY_PATH}: ${path} is a configuration file, whose files state ` +
          'their own owner in their own `owner:` key. Naming it here too would ' +
          'make one fact two places.',
      );
    }
    const kept = Array.isArray(entry.kept)
      ? entry.kept.map(one => nonEmptyString(asRecord(one)?.path, 'a kept path', BOUNDARY_PATH))
      : [];
    return {
      path,
      reason: nonEmptyString(entry.reason, `${path}'s reason`, BOUNDARY_PATH),
      kept,
      regenerated: entry.regenerated === true,
    };
  });
}

/**
 * What one configuration file says it is, from its own header.
 *
 * Every file must answer, in whichever format it is written -- a JSON file
 * states the same `owner` key a YAML one does, in a `_comment` because JSON
 * has nowhere else to put the argument. A file with no `owner` is refused
 * by name rather than defaulted to either side, exactly as
 * `boundary.config_owners` refuses it: the directory that is
 * `declarations/` now filled up by accumulation once, under its old name,
 * and a default here would be that same silence with a friendlier
 * face.
 */
export function configOwner(name: string, text: string): string {
  const loaded: unknown = name.endsWith('.json') ? JSON.parse(text) : yaml.load(text);
  const declared = asRecord(loaded)?.owner;
  if (typeof declared !== 'string' || !OWNERS.includes(declared)) {
    throw new DeclarationRefused(
      `${name} declares no owner. Every configuration file in ` +
        `${CONFIG_DIRS.join('/, ')}/ has to say whether it is the instance's ` +
        `or the product's: add \`owner:\` with one of ${OWNERS.join(', ')}, and ` +
        'the argument for it, to its header.',
    );
  }
  return declared;
}

/**
 * Every path the instance owns, from both halves of the declaration,
 * sorted. Mirrors `boundary.Boundary.instance_paths` -- computed, never
 * retyped.
 */
export function instancePaths(handed: Handed[], configOwners: Record<string, string>): string[] {
  const fromConfig = Object.entries(configOwners)
    .filter(([, owner]) => owner === INSTANCE)
    .map(([name]) => name);
  return [...handed.map(entry => entry.path), ...fromConfig].sort();
}

/** One external dependency the code reads at run time, and what happens
 *  without it. Mirrors `integrations.Integration`, minus the resolved
 *  state: **this screen never asks whether a secret is set**, and the
 *  reason is in `Settings.tsx`'s own header. */
export interface Integration {
  name: string;
  label: string;
  secrets: string[];
  absentBehaviour: string;
  /** True for all but three rows. A row that declares it false is one
   *  whose absence is not a harmless fallback -- data, not a name checked
   *  against a list here. */
  absentIsNormal: boolean;
}

/** Parse an already-loaded `declarations/integrations.yml`. Refuses a row with no
 *  behaviour recorded: a row that cannot say what breaks without it is a
 *  row this screen would render as an empty promise. */
export function integrationsFromData(data: unknown): Integration[] {
  const rows = asRecord(data)?.integrations;
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new DeclarationRefused(
      `${INTEGRATIONS_PATH}: integrations: must be a non-empty list`,
    );
  }
  return rows.map(item => {
    const row = asRecord(item);
    if (row === null) {
      throw new DeclarationRefused(
        `${INTEGRATIONS_PATH}: integrations: holds something that is not a row`,
      );
    }
    const name = nonEmptyString(row.name, 'an integration name', INTEGRATIONS_PATH);
    return {
      name,
      label: nonEmptyString(row.label, `${name}'s label`, INTEGRATIONS_PATH),
      secrets: Array.isArray(row.secrets)
        ? row.secrets.map(one => nonEmptyString(one, `${name}'s secret`, INTEGRATIONS_PATH))
        : [],
      absentBehaviour: nonEmptyString(
        row.absent_behaviour,
        `${name}'s absent_behaviour`,
        INTEGRATIONS_PATH,
      ),
      absentIsNormal: row.absent_is_normal !== false,
    };
  });
}
