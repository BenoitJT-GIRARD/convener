/**
 * Everything the settings screen reads, and where each piece comes from.
 *
 * Six files answer the two questions this screen asks --
 * what does this instance own, and what may each of its numbers be --
 * and none of them is a list typed into a component:
 *
 * - `config/boundary.yml` names the directories the instance owns whole;
 * - every configuration file `CONFIG_DIRS` holds directly states its own
 *   owner in its own header, so those directories are listed rather than
 *   enumerated here: a file added to one of them appears on this screen
 *   because it exists, not because somebody remembered;
 * - `config/integrations.yml` says what each external dependency is for
 *   and what breaks without it;
 * - `.github/workflows/sweep-and-notify.yml` carries the drain's own cron,
 *   which is where every threshold's floor comes from.
 *
 * Two ways in, one reader
 * -----------------------
 * Signed in, the six files are read from the repository through
 * `github/contents.ts` -- the same door `instance/data/speakers.yml` comes through,
 * because a bound computed from a stale copy of `queue_beyond_hours` is a
 * bound that is wrong exactly when it matters. In demo mode nothing may be
 * read from anywhere but the origin that served the page, so the same six
 * travel in the bundle (`scripts/example-settings.mjs`) and are parsed by
 * this same module. The demonstration therefore exercises the code the
 * cockpit runs, rather than a shape laid out to look like it.
 *
 * Why the whole workflow, for one cron
 * ------------------------------------
 * Because the alternative is a number. `registration_routing.floor_hours`
 * and `queue_watch.alarm_bounds` both derive their margin from that
 * schedule rather than restating it, and a browser that restated it would
 * be the second source this project spends its time deleting -- one that
 * disagrees silently the day somebody moves the drain to twice a day.
 */
import yaml from 'js-yaml';
import { gh } from '../github/client';
import { getFile } from '../github/contents';
import { isDemoMode } from '../data/demo';
import { exampleSettings } from './example';
import {
  BOUNDARY_PATH,
  CONFIG_DIRS,
  CONFIG_SUFFIXES,
  INTEGRATIONS_PATH,
  configOwner,
  handedFromData,
  instancePaths,
  integrationsFromData,
  type Handed,
  type Integration,
} from './declaration';
import {
  DRAIN_WORKFLOW,
  QUEUE_DRAIN_FILE,
  REGISTRATION_LANES_FILE,
  drainCadence,
  drainSchedule,
  type Coupling,
} from './bounds';

/** What the screen renders. Every field is derived from bytes this module
 *  read; nothing here is a default. */
export interface SettingsDocument {
  /** Every configuration file, by its repository path, as text. Kept as
   *  text and not only as parsed values because an edit is a *surgical*
   *  replacement of one line in it -- see `./edit.ts` for why. */
  files: Record<string, string>;
  /** Each of those files' declared owner. */
  owners: Record<string, string>;
  /** The directories the declaration hands to the instance whole. */
  handed: Handed[];
  /** Both halves, sorted -- `boundary.Boundary.instance_paths`. */
  instancePaths: string[];
  integrations: Integration[];
  /** The drain's own cadence, or `null` when the workflow's schedule is a
   *  shape nothing here will put a number on. `null` is not a default: it
   *  means every bound on this screen is unavailable, and the screen says
   *  so instead of inventing one.
   *
   *  The *cadence* is stored and the coupling is not, deliberately. A
   *  coupling holds two threshold values, and those change the moment
   *  somebody saves one -- a stored one would go on refusing a value that
   *  had just become legal, which is the same defect as a bound read from
   *  a stale file. `couplingOf` recomputes it from `files` every render. */
  cadence: { hours: number; cron: string } | null;
  /** Why `cadence` is null, when it is. */
  cadenceRefusal: string | null;
}

/** One entry of a configuration directory's listing. */
interface DirectoryEntry {
  name: string;
  path: string;
  type: string;
}

function isConfigFile(entry: DirectoryEntry): boolean {
  return entry.type === 'file' && CONFIG_SUFFIXES.some(suffix => entry.name.endsWith(suffix));
}

/** The number one key holds in an already-parsed file, or `null`. Used only
 *  for the two values a bound is computed *from*; every value the form
 *  offers is read through `./form.ts` with its own refusal. */
function numberAt(text: string, key: string): number | null {
  let loaded: unknown;
  try {
    loaded = yaml.load(text);
  } catch {
    // A file that will not parse holds no number this can read, and the
    // screen already refuses to save while a bound is unavailable.
    return null;
  }
  if (loaded === null || typeof loaded !== 'object') return null;
  const value = (loaded as Record<string, unknown>)[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** The drain's cadence, or the sentence saying why there is none. Separate
 *  from the reads above so that a workflow nobody can read a period out of
 *  leaves the rest of the screen standing. */
export function cadenceFrom(workflow: unknown): {
  cadence: { hours: number; cron: string } | null;
  cadenceRefusal: string | null;
} {
  try {
    return { cadence: drainCadence(drainSchedule(workflow)), cadenceRefusal: null };
  } catch (error) {
    return {
      cadence: null,
      cadenceRefusal:
        error instanceof Error
          ? error.message
          : `${DRAIN_WORKFLOW} could not be read for the drain's own cadence`,
    };
  }
}

/**
 * The two coupled thresholds as the document holds them *right now*,
 * together with the cadence that bounds them.
 *
 * Recomputed from `files` rather than stored: saving one of the two moves
 * the other's bound, and a coupling frozen at load would go on refusing a
 * value that had just become legal -- the same defect as a bound read from
 * a stale copy, which is the defect this whole screen exists to close.
 */
export function couplingOf(document: SettingsDocument): Coupling | null {
  if (document.cadence === null) return null;
  const queueBeyondHours = numberAt(
    document.files[REGISTRATION_LANES_FILE] ?? '',
    'queue_beyond_hours',
  );
  const alarmAfterHours = numberAt(document.files[QUEUE_DRAIN_FILE] ?? '', 'alarm_after_hours');
  if (queueBeyondHours === null || alarmAfterHours === null) return null;
  return {
    periodHours: document.cadence.hours,
    cron: document.cadence.cron,
    queueBeyondHours,
    alarmAfterHours,
  };
}

/** Assemble the document from bytes, whichever way they arrived. */
function documentFrom(files: Record<string, string>, workflow: unknown): SettingsDocument {
  const owners: Record<string, string> = {};
  for (const [name, text] of Object.entries(files)) owners[name] = configOwner(name, text);
  const handed = handedFromData(yaml.load(files[BOUNDARY_PATH] ?? ''));
  const integrations = integrationsFromData(yaml.load(files[INTEGRATIONS_PATH] ?? ''));
  return {
    files,
    owners,
    handed,
    instancePaths: instancePaths(handed, owners),
    integrations,
    ...cadenceFrom(workflow),
  };
}

/**
 * Read the whole document.
 *
 * In demo mode this touches nothing: the bytes are in the bundle. Signed
 * in, it is one directory listing, one read per file in it, and one read of
 * the drain's workflow -- all through `github/contents.ts`, all `GET`, and
 * all in parallel, because they are independent and a settings screen that
 * took eight round trips in series would be a settings screen nobody waits
 * for.
 */
export async function loadSettings(token: string): Promise<SettingsDocument> {
  if (isDemoMode()) {
    const example = exampleSettings();
    return documentFrom(example.files, example.drainTriggers);
  }
  const listings = (await Promise.all(
    CONFIG_DIRS.map(directory =>
      gh(`/contents/${directory}`, { token, method: 'GET' }),
    ),
  )) as DirectoryEntry[][];
  CONFIG_DIRS.forEach((directory, index) => {
    if (!Array.isArray(listings[index])) {
      throw new Error(
        `${directory}/ is not a directory in this repository, so there are no ` +
          'declarations to settle',
      );
    }
  });
  const names = listings
    .flat()
    .filter(isConfigFile)
    .map(entry => entry.path);
  const [texts, workflowText] = await Promise.all([
    Promise.all(names.map(name => getFile(name, token))),
    getFile(DRAIN_WORKFLOW, token),
  ]);
  const files: Record<string, string> = {};
  names.forEach((name, index) => {
    files[name] = texts[index].text;
  });
  return documentFrom(files, yaml.load(workflowText.text));
}
