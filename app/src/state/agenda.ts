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
  key: 'past' | 'parked' | 'declined-board' | 'declined-speaker';
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
    key: 'parked',
    num: '02',
    label: 'Parked',
    hint: 'Set aside by the board — can be reactivated',
    statuses: ['parked'],
    sortDesc: false,
  },
  {
    key: 'declined-board',
    num: '03',
    label: 'Declined (board)',
    hint: 'The board chose not to invite',
    statuses: ['decline-board'],
    sortDesc: false,
  },
  {
    key: 'declined-speaker',
    num: '04',
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
