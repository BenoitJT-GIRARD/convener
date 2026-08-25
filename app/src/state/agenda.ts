import type { Speaker } from '../data/types';
import { editionCodePrefix } from '../instance';

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
 * The next edition code to offer, under the prefix *this* instance
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
