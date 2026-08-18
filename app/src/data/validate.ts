/**
 * What the browser is allowed to believe about `data/*.yml`.
 *
 * `yaml.load` returns `unknown`, and until this module existed the two
 * readers cast that straight to `Speaker[]` and `Config`. The cast is not a
 * check: it is a promise made on the file's behalf, and a repository edited
 * by hand -- which is the whole point of keeping the data in YAML -- can
 * break that promise in silence. It already did. Three tests round-tripped a
 * `vote_threshold` through `DataProvider` and passed, because the cast let
 * any key survive; they stood as a green, executing specification for
 * storing a threshold the governance rule (G-01) forbids.
 *
 * So every field is narrowed here, and anything that does not match the model
 * stops the read with a sentence naming the file and the field. Three
 * decisions worth stating:
 *
 * - **A missing key is an error, not a default.** `Speaker` and `Config`
 *   declare every field as present; a record read with `date` absent would
 *   still be typed as having one, and the code downstream would compare
 *   `undefined` against a deadline and quietly conclude nothing is late.
 *   `tools/convener_ops/validate.py` requires the same keys on the write side --
 *   this is the same rule, on the side that had none.
 * - **An unknown key is an error too.** That is the `vote_threshold` case:
 *   a setting the app stopped honouring, still sitting in the file, reads to
 *   a volunteer as though it still governs something.
 * - **No new dependency.** Hand-written narrowing, in the style of
 *   `src/state/`, for a repository this size (D-14, rule 2).
 *
 * The message is written for whoever will open GitHub and fix the file, and
 * it never blames the reader: a malformed repository is an operator problem,
 * and the volunteer who happened to open the app that morning did not cause
 * it and cannot be asked to interpret a parser error.
 */
import type {
  Ballot,
  BoardMember,
  Config,
  Nomination,
  Objection,
  Publication,
  PublicationObjection,
  Speaker,
  SpeakerMetrics,
  SpeakerSelection,
} from './types';
import { BALLOT_VALUES, CAREER_STAGES, GENDERS } from './types';

/**
 * A data file the app cannot read as the model it is meant to hold.
 *
 * Carries a plain sentence, and `github/errors.ts` passes it through
 * untouched -- the same arrangement as `BallotRejected` and
 * `NominationRejected`. "GitHub is not responding" would be a lie here, and
 * it would send someone to check their connection over a file that needs
 * editing.
 */
export class DataShapeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DataShapeError';
  }
}

/** The closing half of every message: what to do, addressed to whoever can
 *  do it. Kept in one place so no single field can drift into an accusation
 *  or into jargon. */
const FIX_IT = 'Someone with access to the repository will need to correct it on GitHub.';

function fail(file: string, where: string, problem: string): never {
  throw new DataShapeError(`${file}: ${where} ${problem}. ${FIX_IT}`);
}

/** How a value reads back to a person, short enough to sit in a sentence. */
function shown(value: unknown): string {
  if (value === undefined) return 'nothing';
  if (value === null) return 'an empty value';
  if (Array.isArray(value)) return 'a list';
  if (typeof value === 'object') return 'a block of its own';
  if (typeof value === 'string') return value === '' ? 'an empty text' : `"${value}"`;
  return `"${String(value)}"`;
}

interface Cursor {
  /** The file being read, as a volunteer would name it: `data/config.yml`. */
  file: string;
  /** Where in the file, in the file's own words: `speaker 3 (spk-003)`. */
  where: string;
}

function object(at: Cursor, value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    fail(at.file, at.where, `should be a block of settings but reads as ${shown(value)}`);
  }
  return value as Record<string, unknown>;
}

/** Every key the model declares, and nothing else. Both halves matter: the
 *  missing one would be read as `undefined` behind a type that says it is
 *  there, the extra one reads as a setting that still applies. */
function keys(at: Cursor, raw: Record<string, unknown>, expected: readonly string[]): void {
  for (const key of expected) {
    if (!(key in raw)) fail(at.file, at.where, `is missing "${key}"`);
  }
  for (const key of Object.keys(raw)) {
    if (!expected.includes(key)) {
      fail(at.file, at.where, `has "${key}", which this app does not use`);
    }
  }
}

function text(at: Cursor, raw: Record<string, unknown>, key: string): string {
  const value = raw[key];
  if (typeof value !== 'string') {
    fail(at.file, at.where, `should give "${key}" as text but gives ${shown(value)}`);
  }
  return value;
}

function whole(at: Cursor, raw: Record<string, unknown>, key: string): number {
  const value = raw[key];
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    fail(at.file, at.where, `should give "${key}" as a whole number but gives ${shown(value)}`);
  }
  return value;
}

/** A count that may legitimately be unrecorded. `null` and `0` are different
 *  facts -- nobody counted, versus nobody came -- and both are kept. */
function wholeOrBlank(at: Cursor, raw: Record<string, unknown>, key: string): number | null {
  const value = raw[key];
  if (value === null) return null;
  return whole(at, raw, key);
}

function oneOf<T extends string>(
  at: Cursor,
  raw: Record<string, unknown>,
  key: string,
  allowed: readonly T[],
): T {
  const value = raw[key];
  if (typeof value !== 'string' || !(allowed as readonly string[]).includes(value)) {
    fail(
      at.file,
      at.where,
      `gives "${key}" as ${shown(value)}, but it has to be one of: ${allowed
        .map(a => (a === '' ? '(blank)' : a))
        .join(', ')}`,
    );
  }
  return value as T;
}

function listOf<T>(
  at: Cursor,
  raw: Record<string, unknown>,
  key: string,
  read: (at: Cursor, entry: unknown, index: number) => T,
): T[] {
  const value = raw[key];
  if (!Array.isArray(value)) {
    fail(at.file, at.where, `should give "${key}" as a list but gives ${shown(value)}`);
  }
  return value.map((entry, index) =>
    read({ file: at.file, where: `${at.where}, ${key} entry ${index + 1},` }, entry, index),
  );
}

function textList(at: Cursor, raw: Record<string, unknown>, key: string): string[] {
  return listOf(at, raw, key, (inner, entry) => {
    if (typeof entry !== 'string') {
      fail(inner.file, inner.where, `should be text but reads as ${shown(entry)}`);
    }
    return entry;
  });
}

/** `runbook_progress`: free-form step names, each ticked or not. The names
 *  are not a closed vocabulary (they follow the runbook, which changes), so
 *  only the values are checked. */
function ticks(at: Cursor, raw: Record<string, unknown>, key: string): Record<string, boolean> {
  const value = object({ ...at, where: `${at.where} "${key}"` }, raw[key]);
  const out: Record<string, boolean> = {};
  for (const [step, done] of Object.entries(value)) {
    if (typeof done !== 'boolean') {
      fail(at.file, at.where, `gives "${key}" step "${step}" as ${shown(done)} instead of yes or no`);
    }
    out[step] = done;
  }
  return out;
}

/* ------------------------------------------------------------------ *
 * The closed vocabularies, written as records rather than arrays.
 *
 * A record keyed by the union is exhaustive: add a status to
 * `data/types.ts` and forget it here, and this file stops compiling. An
 * array of the same strings would have compiled happily and rejected the
 * new value at runtime, in front of a volunteer.
 * ------------------------------------------------------------------ */
function vocabulary<T extends string>(members: Record<T, true>): readonly T[] {
  return Object.keys(members) as T[];
}

const STATUSES = vocabulary<Speaker['status']>({
  lead: true, approved: true, invited: true, confirmed: true, scheduled: true,
  delivered: true, archived: true, parked: true,
  'decline-board': true, 'decline-speaker': true,
});
const SOURCES = vocabulary<Speaker['source']>({
  form: true, outreach: true, organizer: true,
});
const CONSENTS = vocabulary<Publication['consent']>({
  granted: true, refused: true, pending: true, '': true,
});
const PUBLICATION_OUTCOMES = vocabulary<Publication['outcome']>({
  published: true, withheld: true, '': true,
});
const NOMINATION_OUTCOMES = vocabulary<Nomination['outcome']>({
  accepted: true, deferred: true, waiting: true, '': true,
});
const BOARD_STATUSES = vocabulary<BoardMember['status']>({
  active: true, inactive: true,
});

/* ------------------------------------------------------------------ *
 * speakers.yml
 * ------------------------------------------------------------------ */

const BALLOT_KEYS = ['voter', 'value', 'comment', 'coi_reason', 'date'] as const;

function readBallot(at: Cursor, entry: unknown): Ballot {
  const raw = object(at, entry);
  keys(at, raw, BALLOT_KEYS);
  return {
    voter: text(at, raw, 'voter'),
    value: oneOf(at, raw, 'value', BALLOT_VALUES),
    comment: text(at, raw, 'comment'),
    coi_reason: text(at, raw, 'coi_reason'),
    date: text(at, raw, 'date'),
  };
}

function readSelection(at: Cursor, value: unknown): SpeakerSelection {
  const inner: Cursor = { file: at.file, where: `${at.where} selection` };
  const raw = object(inner, value);
  keys(inner, raw, ['ballots', 'opened_on', 'decided_on']);
  return {
    ballots: listOf(inner, raw, 'ballots', readBallot),
    opened_on: text(inner, raw, 'opened_on'),
    decided_on: text(inner, raw, 'decided_on'),
  };
}

function readPublicationObjection(at: Cursor, entry: unknown): PublicationObjection {
  const raw = object(at, entry);
  keys(at, raw, ['member', 'reason', 'date', 'resolved_on']);
  return {
    member: text(at, raw, 'member'),
    reason: text(at, raw, 'reason'),
    date: text(at, raw, 'date'),
    resolved_on: text(at, raw, 'resolved_on'),
  };
}

function readPublication(at: Cursor, value: unknown): Publication {
  const inner: Cursor = { file: at.file, where: `${at.where} publication` };
  const raw = object(inner, value);
  keys(inner, raw, ['consent', 'approved_by', 'approved_on', 'objections', 'outcome']);
  return {
    consent: oneOf(inner, raw, 'consent', CONSENTS),
    approved_by: text(inner, raw, 'approved_by'),
    approved_on: text(inner, raw, 'approved_on'),
    objections: listOf(inner, raw, 'objections', readPublicationObjection),
    outcome: oneOf(inner, raw, 'outcome', PUBLICATION_OUTCOMES),
  };
}

function readMetrics(at: Cursor, value: unknown): SpeakerMetrics {
  const inner: Cursor = { file: at.file, where: `${at.where} metrics` };
  const raw = object(inner, value);
  keys(inner, raw, ['registrations', 'live_peak', 'youtube_views_30d', 'forum_replies']);
  return {
    registrations: wholeOrBlank(inner, raw, 'registrations'),
    live_peak: wholeOrBlank(inner, raw, 'live_peak'),
    youtube_views_30d: wholeOrBlank(inner, raw, 'youtube_views_30d'),
    forum_replies: wholeOrBlank(inner, raw, 'forum_replies'),
  };
}

const SPEAKER_KEYS = [
  'id', 'name', 'gender', 'career_stage', 'email', 'affiliation', 'country',
  'title', 'abstract', 'conflicts_of_interest', 'source', 'proposed_by',
  'assigned_to', 'links', 'host_1', 'host_2', 'status', 'selection',
  'publication', 'edition_code', 'date', 'time', 'zoom_link', 'youtube_url',
  'forum_thread', 'runbook_progress', 'metrics', 'notes',
] as const;

function readSpeaker(at: Cursor, entry: unknown): Speaker {
  const raw = object(at, entry);
  // Named by id from here on where there is one: "speaker 12" sends a
  // volunteer counting records in a 1700-line file.
  const id = typeof raw.id === 'string' && raw.id !== '' ? ` (${raw.id})` : '';
  const here: Cursor = { file: at.file, where: `${at.where}${id}` };
  keys(here, raw, SPEAKER_KEYS);
  return {
    id: text(here, raw, 'id'),
    name: text(here, raw, 'name'),
    gender: oneOf(here, raw, 'gender', GENDERS),
    career_stage: oneOf(here, raw, 'career_stage', CAREER_STAGES),
    email: text(here, raw, 'email'),
    affiliation: text(here, raw, 'affiliation'),
    country: text(here, raw, 'country'),
    title: text(here, raw, 'title'),
    abstract: text(here, raw, 'abstract'),
    conflicts_of_interest: text(here, raw, 'conflicts_of_interest'),
    source: oneOf(here, raw, 'source', SOURCES),
    proposed_by: text(here, raw, 'proposed_by'),
    assigned_to: text(here, raw, 'assigned_to'),
    links: textList(here, raw, 'links'),
    host_1: text(here, raw, 'host_1'),
    host_2: text(here, raw, 'host_2'),
    status: oneOf(here, raw, 'status', STATUSES),
    selection: readSelection(here, raw.selection),
    publication: readPublication(here, raw.publication),
    edition_code: text(here, raw, 'edition_code'),
    date: text(here, raw, 'date'),
    time: text(here, raw, 'time'),
    zoom_link: text(here, raw, 'zoom_link'),
    youtube_url: text(here, raw, 'youtube_url'),
    forum_thread: text(here, raw, 'forum_thread'),
    runbook_progress: ticks(here, raw, 'runbook_progress'),
    metrics: readMetrics(here, raw.metrics),
    notes: text(here, raw, 'notes'),
  };
}

/**
 * Narrow whatever `yaml.load` returned for `data/speakers.yml`.
 *
 * An empty file is an empty list, not an error: that is where the repository
 * starts, and it is the one absence that means exactly what it looks like.
 */
export function readSpeakers(loaded: unknown, file = 'data/speakers.yml'): Speaker[] {
  if (loaded === null || loaded === undefined) return [];
  if (!Array.isArray(loaded)) {
    throw new DataShapeError(
      `${file}: the file should be a list of speakers, but it reads as ${shown(loaded)}. ${FIX_IT}`,
    );
  }
  return loaded.map((entry, index) =>
    readSpeaker({ file, where: `speaker ${index + 1}` }, entry),
  );
}

/* ------------------------------------------------------------------ *
 * config.yml
 * ------------------------------------------------------------------ */

function readBoardMember(at: Cursor, entry: unknown): BoardMember {
  const raw = object(at, entry);
  keys(at, raw, ['login', 'joined_on', 'status', 'unavailable_until']);
  return {
    login: text(at, raw, 'login'),
    joined_on: text(at, raw, 'joined_on'),
    status: oneOf(at, raw, 'status', BOARD_STATUSES),
    unavailable_until: text(at, raw, 'unavailable_until'),
  };
}

/** A nomination objection is `{member, reason, date}` -- no `resolved_on`.
 *  It is never resolved: it defers the candidate to the annual meeting, and
 *  the only thing that ends it is its author withdrawing it, which removes
 *  the entry (G-08, `state/board.ts::withdrawObjection`). */
function readObjection(at: Cursor, entry: unknown): Objection {
  const raw = object(at, entry);
  keys(at, raw, ['member', 'reason', 'date']);
  return {
    member: text(at, raw, 'member'),
    reason: text(at, raw, 'reason'),
    date: text(at, raw, 'date'),
  };
}

function readNomination(at: Cursor, entry: unknown): Nomination {
  const raw = object(at, entry);
  keys(at, raw, ['candidate', 'sponsor', 'opened_on', 'objections', 'outcome']);
  return {
    candidate: text(at, raw, 'candidate'),
    sponsor: text(at, raw, 'sponsor'),
    opened_on: text(at, raw, 'opened_on'),
    objections: listOf(at, raw, 'objections', readObjection),
    outcome: oneOf(at, raw, 'outcome', NOMINATION_OUTCOMES),
  };
}

const SLA_KEYS = [
  'lead_decision', 'invitation_follow_up', 'summary_after_delivery',
  'recording_after_delivery',
] as const;

function readSlaDays(at: Cursor, value: unknown): Config['sla_days'] {
  const inner: Cursor = { file: at.file, where: '"sla_days"' };
  const raw = object(inner, value);
  keys(inner, raw, SLA_KEYS);
  return {
    lead_decision: whole(inner, raw, 'lead_decision'),
    invitation_follow_up: whole(inner, raw, 'invitation_follow_up'),
    summary_after_delivery: whole(inner, raw, 'summary_after_delivery'),
    recording_after_delivery: whole(inner, raw, 'recording_after_delivery'),
  };
}

const CONFIG_KEYS = [
  'season', 'vw_counter', 'overlap_window_days', 'seminar_duration_minutes',
  'board', 'nominations', 'board_min', 'board_max', 'vote_window_days',
  'objection_window_working_days', 'inactivity_months', 'balance_window_months',
  'sla_days',
] as const;

/**
 * Narrow whatever `yaml.load` returned for `data/config.yml`.
 *
 * Unlike the speaker list there is no empty case: a config with no settings
 * is not a repository that has not started, it is one whose every window,
 * threshold and board seat would have to be invented by the reader. The app
 * used to invent them, from a constant in `DataContext`; a screen then
 * showed a vote threshold computed from a board nobody had elected. Failing
 * the load is the honest answer, and the one a P2-8 reading demands: the
 * made-up config is not guarded, it does not exist.
 */
export function readConfig(loaded: unknown, file = 'data/config.yml'): Config {
  const at: Cursor = { file, where: 'the file' };
  const raw = object(at, loaded);
  keys(at, raw, CONFIG_KEYS);
  return {
    season: whole(at, raw, 'season'),
    vw_counter: whole(at, raw, 'vw_counter'),
    overlap_window_days: whole(at, raw, 'overlap_window_days'),
    seminar_duration_minutes: whole(at, raw, 'seminar_duration_minutes'),
    board: listOf({ file, where: 'the board' }, raw, 'board', readBoardMember),
    nominations: listOf({ file, where: 'the nominations' }, raw, 'nominations', readNomination),
    board_min: whole(at, raw, 'board_min'),
    board_max: whole(at, raw, 'board_max'),
    vote_window_days: whole(at, raw, 'vote_window_days'),
    objection_window_working_days: whole(at, raw, 'objection_window_working_days'),
    inactivity_months: whole(at, raw, 'inactivity_months'),
    balance_window_months: whole(at, raw, 'balance_window_months'),
    sla_days: readSlaDays(at, raw.sla_days),
  };
}
