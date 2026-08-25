import type { Speaker } from '../data/types';
import { isDemoMode } from '../data/demo';
import { editionPrefix } from '../instance';
import { exampleEditionPrefix } from '../settings/example';

export interface OverlapHit {
  speaker: Speaker;
  daysApart: number;
}

const PUBLIC_STATUSES = new Set(['scheduled', 'delivered', 'archived']);

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
 * `instances/example/`: its records, its board, its counter. A prefix
 * taken from the build therefore offered `MRG-4` for a series numbered
 * `MRG-1`, `MRG-2`, `MRG-3` -- a code belonging to neither instance, on
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
 * declares (`config/instance.json::edition_prefix`, phase 11 task 4).
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
