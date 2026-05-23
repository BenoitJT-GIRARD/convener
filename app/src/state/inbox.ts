import type { Speaker } from '../data/types';
import { phaseOf } from './phases';

export type InboxKind = 'vote' | 'action' | 'awareness';

export interface InboxRow {
  kind: InboxKind;
  speaker: Speaker;
  label: string;
  /** runbook key when kind === 'action' or 'awareness' */
  itemKey?: string;
  /** for scheduled phase: days until event date (negative = past) */
  daysUntil?: number;
  /** sort key: lower (incl. negative) = more urgent */
  urgency: number;
}

function daysBetween(from: string, to: string): number {
  if (!from || !to) return Number.POSITIVE_INFINITY;
  return Math.round((Date.parse(to) - Date.parse(from)) / 86400000);
}

export function deriveInbox(
  speakers: Speaker[],
  login: string | null,
  role: 'board' | 'organizer' | null,
  today: string,
): InboxRow[] {
  if (!login || !role) return [];
  const rows: InboxRow[] = [];

  for (const s of speakers) {
    const phase = phaseOf(s.status);
    if (!phase) continue;
    const mine = s.host === login || s.co_hosts.includes(login);

    // votes (board only, when not yet voted)
    if (s.status === 'lead' && role === 'board') {
      if (!s.selection.votes_for.includes(login)) {
        rows.push({
          kind: 'vote',
          speaker: s,
          label: `Vote on lead: ${s.name}`,
          urgency: -100,
        });
      }
    }

    // actions on speakers I shepherd (or anyone, if I'm board)
    if (mine || role === 'board') {
      if (['approved', 'invited', 'confirmed', 'delivered'].includes(s.status)) {
        for (const item of phase.items) {
          if (item.gate && !s.runbook_progress[item.key]) {
            rows.push({
              kind: 'action',
              speaker: s,
              label: item.label,
              itemKey: item.key,
              urgency: 0,
            });
          }
        }
      }
      if (s.status === 'scheduled' && s.date) {
        const days = daysBetween(today, s.date);
        for (const item of phase.items) {
          if (item.window === undefined) continue;
          if (s.runbook_progress[item.key]) continue;
          if (days <= item.window) {
            rows.push({
              kind: 'action',
              speaker: s,
              label: `${item.label} (T-${item.window})`,
              itemKey: item.key,
              daysUntil: days,
              urgency: days,
            });
          }
        }
      }
      if (s.status === 'wrapped') {
        for (const item of phase.items) {
          if (s.runbook_progress[item.key]) continue;
          rows.push({
            kind: 'awareness',
            speaker: s,
            label: item.label,
            itemKey: item.key,
            urgency: 100,
          });
        }
      }
    }
  }

  return rows.sort((a, b) => a.urgency - b.urgency);
}
