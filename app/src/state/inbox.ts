import type { Speaker } from '../data/types';
import { phaseOf, fieldValue } from './phases';

export type InboxKind = 'vote' | 'action' | 'awareness';

export interface InboxRow {
  kind: InboxKind;
  speaker: Speaker;
  label: string;
  itemKey?: string;
  daysUntil?: number;
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

    // `assigned_to`, not `proposed_by`: the submitter is often someone
    // outside the team who self-reported a name through the public form, so
    // matching on it made "my leads" mean nothing. Ownership is what this
    // filter is about.
    const mine =
      s.host_1 === login ||
      s.host_2 === login ||
      s.assigned_to === login;

    // ── votes (board only)
    if (s.status === 'lead' && role === 'board') {
      if (!s.selection.ballots.some(b => b.voter === login)) {
        rows.push({ kind: 'vote', speaker: s, label: `Vote on lead: ${s.name}`, urgency: -100 });
      }
    }

    if (!(mine || role === 'board')) continue;

    // ── approved: hosts + invitation
    if (s.status === 'approved') {
      if (!s.host_1) {
        rows.push({ kind: 'action', speaker: s, label: 'Assign Host 1', urgency: 0 });
      } else if (!s.host_2) {
        rows.push({ kind: 'action', speaker: s, label: 'Assign Host 2', urgency: 0 });
      } else {
        rows.push({ kind: 'action', speaker: s, label: 'Send invitation', urgency: 0 });
      }
    }

    // ── invited
    if (s.status === 'invited') {
      rows.push({
        kind: 'action',
        speaker: s,
        label: 'Log speaker reply (accept / decline)',
        urgency: 0,
      });
    }

    // ── confirmed
    if (s.status === 'confirmed') {
      if (!s.title) rows.push({ kind: 'action', speaker: s, label: 'Capture talk title', urgency: 0 });
      if (!s.abstract)
        rows.push({ kind: 'action', speaker: s, label: 'Capture talk abstract', urgency: 0 });
      if (!s.date || !s.edition_code || !s.time) {
        rows.push({ kind: 'action', speaker: s, label: 'Lock date, time and edition code', urgency: 0 });
      }
    }

    // ── scheduled: checkbox items in their T-window
    if (s.status === 'scheduled' && s.date) {
      const days = daysBetween(today, s.date);
      for (const item of phase.items) {
        if (item.form !== 'checkbox' || item.window === undefined) continue;
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

    // ── delivered: required fields + required checkboxes
    if (s.status === 'delivered') {
      for (const item of phase.items) {
        if (!item.required) continue;
        if (item.form === 'field' && item.fieldKey) {
          const val = fieldValue(s, item.fieldKey);
          if (val === '' || val === null || val === undefined) {
            rows.push({ kind: 'action', speaker: s, label: `Fill ${item.label}`, urgency: 0 });
          }
        }
        if (item.form === 'checkbox' && !s.runbook_progress[item.key]) {
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
  }

  return rows.sort((a, b) => a.urgency - b.urgency);
}
