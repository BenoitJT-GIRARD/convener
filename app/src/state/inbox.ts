import type { Config, Speaker } from '../data/types';
import { activeBoard } from './board';
import { decide } from './governance';
import { phaseItems, phaseOf, fieldValue } from './phases';
import { itemAssignee } from './assignment';

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

/**
 * What each person still has to do, today.
 *
 * `config` is read for one thing only: whether a lead's ballots already clear
 * the threshold. The migration to schema v3 produced six leads carrying
 * enough yes ballots to be approved but stuck at `status: lead`, and nothing
 * downstream could move them -- `sweep.expire_votes` skips a lead whose vote
 * is decided, so they never park, and `ballot-cast` is the only writer of
 * `approved`, so they never advance either. They simply sat in the pipeline.
 *
 * The fix is to *show* them, not to settle them: this adds a row, and a
 * board member recording their own ballot on it is what moves the record. No
 * decision is taken on the board's behalf anywhere in this module -- nothing
 * here writes at all.
 *
 * **The lines of a phase are read through `phaseItems`, never `phase.items`.**
 * `state/phases.ts` says so of everything that walks them, and names this
 * module among the three. It did not: the promotion channels live in
 * `instance/data/config.yml` and enter the journey through `phaseItems`, so the seven
 * places an event is announced were the only T-window boxes in the whole
 * journey that never raised a reminder here -- invisible everywhere but the
 * speaker page, which is where nobody goes looking for what is due.
 *
 * **A line somebody is named on is not raised here.** `Inbox.tsx` shows two
 * lists side by side: this one, "what is due on the records I look after",
 * and `assignment.itemsWaitingFor`, "what I am down for". A line with an
 * owner belongs to the second, so raising it in both put the same line twice
 * on one screen -- which was the common case, since a host is exactly the
 * person named on lines of their own record. An unowned line is the hosts',
 * which is what it has always meant, and that is the one this module raises.
 */
export function deriveInbox(
  speakers: Speaker[],
  config: Config | null,
  login: string | null,
  role: 'board' | 'organizer' | null,
  today: string,
): InboxRow[] {
  if (!login || !role) return [];
  const rows: InboxRow[] = [];
  const board = config ? activeBoard(config, today) : null;

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
      const settled =
        board !== null &&
        decide({
          board: board.logins,
          unavailable: board.unavailable,
          ballots: s.selection.ballots,
        }).decided;
      if (settled) {
        // Above every other vote: the board has already agreed and the record
        // does not say so. Recording a ballot here is what writes `approved`.
        rows.push({
          kind: 'vote',
          speaker: s,
          label: `Threshold already reached, still open: ${s.name}`,
          urgency: -200,
        });
      } else if (!s.selection.ballots.some(b => b.voter === login)) {
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
      // Every line of this phase is due in a window, the promotion channels
      // included: `phaseItems` lends each channel the window of the line it
      // is spliced after, because where the promotion lines fall is the
      // phase's placement and not the channel's. That used to be worked out
      // here, which made this the only screen that knew it -- the record
      // page showed the same line with no window at all. Without a window
      // the seven places an event is announced are the only lines of the
      // journey that never reach anybody's inbox, and an unowned channel --
      // the default -- is visible nowhere but the speaker page.
      for (const item of phaseItems(phase, config)) {
        if (item.form !== 'checkbox') continue;
        const window = item.window;
        if (window === undefined) continue;
        if (s.runbook_progress[item.key]) continue;
        if (itemAssignee(s, item.key) !== '') continue;
        if (days <= window) {
          rows.push({
            kind: 'action',
            speaker: s,
            label: `${item.label} (T-${window})`,
            itemKey: item.key,
            daysUntil: days,
            urgency: days,
          });
        }
      }
    }

    // ── delivered: required fields + required checkboxes
    if (s.status === 'delivered') {
      for (const item of phaseItems(phase, config)) {
        if (!item.required) continue;
        // Owned lines leave this list, exactly as they do in the scheduled
        // branch above: a line with a name against it is that person's, and
        // `itemsWaitingFor` raises it there -- for field lines as well as
        // checkbox ones. Raising it here too would put it in front of
        // everybody, which is what "nobody in particular" is supposed to
        // mean and this is not.
        if (itemAssignee(s, item.key) !== '') continue;
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
