import type { Speaker, SpeakerStatus } from '../data/types';
import { isDemoMode } from '../data/demo';
import { editionPrefix } from '../instance';
import { exampleEditionPrefix } from '../settings/example';

export interface OverlapHit {
  speaker: Speaker;
  daysApart: number;
}

const PUBLIC_STATUSES = new Set(['scheduled', 'delivered', 'archived']);

/**
 * The working board: one column per status that still asks somebody for
 * work, in the order the work happens.
 *
 * **Here, beside the other two lists, and that is the correction.** The
 * boundary below was written over the agenda and the archive and applied to
 * those two screens alone, while the columns lived in `screens/Pipeline.tsx`
 * as a table of their own. So `delivered` -- the status with the most work
 * left in it: the attendance, the recording, the certificates -- was placed
 * on the agenda, taken off the archive, and never looked for on the board.
 * It ended up on a calendar and on no work surface at all.
 *
 * Three lists, one home, one rule over all three, and `agenda.test.ts` holds
 * it over every status the model has rather than over the ones somebody
 * happened to be looking at.
 *
 * The two overlaps with the agenda are deliberate and are not a boundary
 * being broken: a booked talk and a talk that has been given are both work
 * in hand *and* a date in the diary. What may not overlap is the board with
 * the archive, and the agenda with the archive -- a record cannot be both
 * open and closed.
 */
export const BOARD_COLUMNS: readonly { key: SpeakerStatus; label: string }[] = [
  { key: 'lead', label: 'Leads' },
  { key: 'approved', label: 'Approved' },
  { key: 'invited', label: 'Invited' },
  { key: 'confirmed', label: 'Confirmed' },
  { key: 'scheduled', label: 'Scheduled' },
  { key: 'delivered', label: 'Delivered' },
];

/** The board's side of the rule, derived from the columns the screen
 *  actually draws rather than written a second time. */
export const BOARD_STATUSES: readonly SpeakerStatus[] = BOARD_COLUMNS.map(c => c.key);

/**
 * The boundary between the two screens a record ends up on.
 *
 * > The agenda holds what still owes you something. The archive holds what
 * > is closed.
 *
 * They used to share `delivered`, and the agenda additionally carried
 * `archived` -- so the one screen a volunteer opens to see what is coming
 * grew by one line for every event the series had ever run, and a talk that
 * was over but not wrapped up appeared on both. The consequence of the rule
 * is the point of it: **the agenda empties as the work is done**. It is a
 * horizon, not a journal.
 *
 * A `delivered` event is not finished -- the attendance, the recording and
 * the certificates are all still owed -- so it stays on the agenda until
 * somebody archives it. `archived` is the one gesture that says there is
 * nothing left, and it is what moves a record across.
 *
 * The two lists are here, together, rather than one in each screen: the rule
 * is that they share nothing, and a rule about two lists cannot be stated
 * where only one of them is. `agenda.test.ts` holds it over every status the
 * model has, so the next status somebody adds has to be placed on one side
 * or neither, and cannot quietly land on both.
 */
export const AGENDA_STATUSES: readonly SpeakerStatus[] = ['scheduled', 'delivered'];

/** One group of the archive screen: what it is called, what it holds, and
 *  which way round it reads. Here rather than in the screen because the
 *  other half of the boundary is here, and a rule about two lists cannot be
 *  stated where only one of them is. */
export interface ArchiveGroup {
  key: 'past' | 'cancelled' | 'parked' | 'declined-board' | 'declined-speaker';
  num: string;
  label: string;
  hint: string;
  statuses: SpeakerStatus[];
  /** Past webinars read newest first; the rest read by name, because a
   *  parked lead's date says nothing about when anybody looked at it. */
  sortDesc: boolean;
}

export const ARCHIVE_GROUPS: ArchiveGroup[] = [
  {
    key: 'past',
    num: '01',
    label: 'Past webinars',
    // `delivered` used to be here as well as on the agenda, so a talk that
    // was over but not wrapped up was on both screens at once. A boundary
    // that a status sits on both sides of is not a boundary.
    hint: 'Closed: wrapped up and nothing outstanding',
    statuses: ['archived'],
    sortDesc: true,
  },
  {
    key: 'cancelled',
    num: '02',
    label: 'Cancelled',
    // Closed, not owed. The obligation a cancellation creates -- telling the
    // people who registered -- is discharged by the act itself: cancelling
    // dispatches `cancel-edition.yml`, the way locking a date dispatches and
    // retention dispatches. A status that waited for somebody to send those
    // messages by hand would be a status on the agenda for as long as nobody
    // did, which is the shape this project refuses everywhere else.
    //
    // It reads newest first, like past webinars: a cancelled edition has a
    // date, and the date is what a reader is looking for.
    hint: 'Announced and did not happen — registrants were told',
    statuses: ['cancelled'],
    sortDesc: true,
  },
  {
    key: 'parked',
    num: '03',
    label: 'Parked',
    hint: 'Set aside by the board — can be reactivated',
    statuses: ['parked'],
    sortDesc: false,
  },
  {
    key: 'declined-board',
    num: '04',
    label: 'Declined (board)',
    hint: 'The board chose not to invite',
    statuses: ['decline-board'],
    sortDesc: false,
  },
  {
    key: 'declined-speaker',
    num: '05',
    label: 'Declined (speaker)',
    hint: 'Speaker turned down the invitation',
    statuses: ['decline-speaker'],
    sortDesc: false,
  },
];

/** The other side of the same boundary, derived from the groups rather than
 *  written twice: a group added to the screen is on this side of the rule the
 *  same day, and cannot be added to the agenda's side as well without
 *  `agenda.test.ts` going red. */
export const ARCHIVE_STATUSES: readonly SpeakerStatus[] = ARCHIVE_GROUPS.flatMap(g => g.statuses);

export function findOverlaps(
  candidateDate: string,
  speakers: Speaker[],
  windowDays: number,
  excludeId?: string,
): OverlapHit[] {
  const target = Date.parse(candidateDate);
  if (Number.isNaN(target)) return [];
  const hits: OverlapHit[] = [];
  for (const s of speakers) {
    if (s.id === excludeId) continue;
    if (!PUBLIC_STATUSES.has(s.status)) continue;
    if (!s.date) continue;
    const days = Math.abs(Math.round((Date.parse(s.date) - target) / 86400000));
    if (days <= windowDays) hits.push({ speaker: s, daysApart: days });
  }
  return hits.sort((a, b) => a.daysApart - b.daysApart);
}

/**
 * `MRG-` -- what an edition code starts with, separator included, for the
 * instance whose records are on screen. The hyphen is the product's, not
 * the declaration's: see `published.py::EditionPrefix.code_prefix`.
 *
 * Here rather than beside `editionPrefix` in `../instance.ts`, and that
 * is the whole correction. `instance.ts` answers one question -- what
 * does the instance that *built this bundle* declare -- and in demo mode
 * that is the wrong instance to ask. The demonstration shows
 * `examples/the-example-collective/`: its records, its board, its counter. A prefix
 * taken from the build therefore offered `MRG-4` for a series numbered
 * `MRG-1` upwards -- a code belonging to neither instance, on
 * the first control a visitor touches on a screen that invites them to
 * number an edition. The demo band did not cover it either: it says
 * where the *records* come from, not where an offered code comes from.
 *
 * Nothing new is carried to fix it. The example's own declaration is
 * already in this bundle for the settings screen, and
 * `settings/example.ts` is the one reader of it.
 */
export function editionCodePrefix(): string {
  return `${isDemoMode() ? exampleEditionPrefix() : editionPrefix()}-`;
}

/**
 * The next edition code to offer, under the prefix the instance on screen
 * declares (`instance/config.json::edition_prefix`).
 *
 * The two letters used to be written here, so every duplicate of this
 * repository numbered its own editions after this series' initials --
 * and the code it composes goes straight into a published address, an
 * issued certificate and a key filename, none of which can be renumbered
 * afterwards.
 */
export function nextEditionCode(speakers: Speaker[], counter: number): string {
  const prefix = editionCodePrefix();
  const used = new Set(speakers.map(s => s.edition_code).filter(Boolean));
  let n = counter;
  while (used.has(`${prefix}${n}`)) n++;
  return `${prefix}${n}`;
}

/**
 * The number in an edition code, or `null` when the code does not carry one
 * under this instance's prefix.
 *
 * A code is the instance's own prefix and then digits: the twelfth
 * edition is 12. A prefix with nothing after it, digits that are not
 * digits, and a code from some other series are all neither. Read rather
 * than assumed, because the counter below is raised from it and a silent
 * misread would move a high-water mark to somewhere no edition is.
 */
export function editionNumber(editionCode: string): number | null {
  const prefix = editionCodePrefix();
  if (!editionCode.startsWith(prefix)) return null;
  const rest = editionCode.slice(prefix.length);
  if (!/^[0-9]+$/.test(rest)) return null;
  return Number(rest);
}

/**
 * What `next_edition_number` should read once `editionCode` is assigned.
 *
 * **A floor that only ever rises.** The counter is a high-water mark rather
 * than a count of rows -- `test_published.py` holds it that way, and for a
 * reason a duplicate meets: rows can be cleared, and a counter derived from
 * the rows that remain would renumber editions that already exist on posters
 * and in sent mail. So this takes the larger of the two, never the newer.
 *
 * It exists because nothing raised the mark at all. Measured on a live
 * instance: the cockpit assigned the first edition, the counter stayed at
 * 1, and `sh gates.sh` went red on the first edition that instance ever
 * scheduled -- naming a key the operator has never heard of and cannot
 * reach from any screen, one moment after a screen told them their edition
 * was locked in.
 */
export function raisedEditionCounter(counter: number, editionCode: string): number {
  const assigned = editionNumber(editionCode);
  if (assigned === null) return counter;
  return Math.max(counter, assigned + 1);
}

/**
 * The event id of an edition, which is its code lower-cased and nothing else.
 *
 * The rule `tools/convener_ops/journey/platform.py::find_speaker` states,
 * read here rather than spelled again wherever a path or an address needs
 * it: `content/render.ts` composes the public sign-up address from it and
 * `paths.ts` composes the sign-up file's own path, and a second spelling of
 * "lower-cased" would be a second answer to where an event's files live.
 */
export function eventIdOf(editionCode: string): string {
  return editionCode.toLowerCase();
}
