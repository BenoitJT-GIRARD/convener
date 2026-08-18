import type { Speaker } from '../data/types';

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

export function nextEditionCode(speakers: Speaker[], counter: number): string {
  const used = new Set(speakers.map(s => s.edition_code).filter(Boolean));
  let n = counter;
  while (used.has(`MRG-${n}`)) n++;
  return `MRG-${n}`;
}
