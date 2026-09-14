/**
 * Edits a volunteer has made and this tab has not written yet.
 *
 * **What this is for, measured.** Every tick of a runbook box is a commit, and
 * every commit is a push that wakes the repository's workflows. On the
 * instance this product was derived for, one operator walking the runbook for
 * two seminars made 53 commits in 47 minutes and spent 1175 billed Actions
 * minutes — more than half a GitHub Free month — in a single session.
 * Narrowing what each push wakes fixed most of that
 * (`docs/operating/what-the-automation-costs.md`); what is left is the floor,
 * because every job bills a whole minute however fast it is. The remaining
 * lever is the number of commits, and 53 for two seminars is one per checkbox.
 *
 * **What may be batched, and what may never be.** The distinction is already
 * in the model, so this does not invent one:
 *
 * * a `checkbox` is a *task* and a `field` is a *fact* (`phases.ts::itemKind`)
 *   — both record something that already happened elsewhere, and nothing reads
 *   them synchronously. Of the 38 runbook lines, six are read by name anywhere
 *   in the codebase, and every one of those readers runs later: a gate over
 *   retrieval evidence, an SLA clock, the panel that says which drafted text
 *   to open. These queue.
 * * a `button-group` is a **transition**. It changes the status, and a status
 *   change publishes an edition, mints a key, opens registration or sends
 *   somebody a message. These never queue, and a transition *flushes* the
 *   queue before it writes — see `DataContext`, which does that at the one
 *   place every write passes through rather than asking each caller to
 *   remember.
 *
 * **One record at a time.** A queue holding edits to two speakers would write
 * a commit whose subject can only name one of them. Handing this an edit for a
 * different record returns the old queue to be written first; nothing merges
 * across records.
 *
 * **Pure.** No clock, no timer, no storage: a queue in, a queue out. What
 * decides *when* to flush is the provider, which is where the timer and the
 * navigation handlers live, and this module can be read and tested without
 * either.
 */
import { dataEdit, identifier, type Edit, type Subject } from '../state/decisions';
import type { Speaker } from './types';

/** One edit, held until it is written.
 *
 *  `apply` is a transformation of a single record rather than an already-made
 *  copy of it: the write replays its transformation against freshly-read data,
 *  so a queued edit has to be re-derived against whatever the file says at the
 *  moment it lands, not against what the screen was showing when the box was
 *  ticked. `edit` is what the commit subject is built from, never a string. */
export interface QueuedEdit {
  apply: (s: Speaker) => Speaker;
  edit: Edit;
}

export interface Queue {
  /** The record every edit here belongs to. */
  id: string;
  edits: QueuedEdit[];
}

/** What `enqueue` returns: the queue to keep, and the queue to write first.
 *
 *  `flush` is non-null only when the new edit belongs to a different record
 *  from the one being held. */
export interface Enqueued {
  queue: Queue;
  flush: Queue | null;
}

export function enqueue(queue: Queue | null, id: string, item: QueuedEdit): Enqueued {
  if (queue !== null && queue.id !== id) {
    return { queue: { id, edits: [item] }, flush: queue };
  }
  return {
    queue: { id, edits: queue === null ? [item] : [...queue.edits, item] },
    flush: null,
  };
}

/**
 * `speakers`, with everything held for that record applied in order.
 *
 * The same function serves both readers, deliberately: the screen draws from
 * it so a box stays ticked the moment it is clicked, and the write transforms
 * with it so what lands is what the volunteer saw. Two functions here would be
 * two answers to "what did they do", and the one on screen would be the one
 * nobody could check.
 *
 * Order is the order the edits were made, so a box ticked and then unticked
 * ends where the volunteer left it.
 */
export function applyPending(queue: Queue | null, speakers: Speaker[]): Speaker[] {
  if (queue === null || queue.edits.length === 0) return speakers;
  return speakers.map(s =>
    s.id === queue.id ? queue.edits.reduce((acc, one) => one.apply(acc), s) : s,
  );
}

/**
 * The commit subject for a queue.
 *
 * A queue of one renders exactly what that edit rendered before there was a
 * queue — `runbook <key>=true`, `set title` — so batching changed no subject
 * that already existed. Only a queue of several needs a phrase of its own, and
 * it counts rather than lists: a subject is one line, permanent, and a list of
 * nine keys in it would be unreadable in every tool that shows one. The diff
 * is where the nine are.
 */
export function pendingSubject(queue: Queue): Subject {
  const entity = identifier(queue.id);
  if (queue.edits.length === 1) return dataEdit(entity, queue.edits[0].edit);
  return dataEdit(entity, { part: 'checklist', lines: queue.edits.length });
}

/** How many edits are waiting, for the screen that has to say so. */
export function pendingCount(queue: Queue | null): number {
  return queue === null ? 0 : queue.edits.length;
}
