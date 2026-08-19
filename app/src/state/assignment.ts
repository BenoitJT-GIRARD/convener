/**
 * Who owes one line of the journey.
 *
 * The checklist the volunteers actually keep puts a name against every line:
 * who makes the visual, who posts on the forum, who writes to the speaker.
 * The app knew about two hosts and nothing else, so it could answer "where is
 * this event up to" and could not answer "what is waiting for me". This module
 * is the second question, and only that.
 *
 * **`assignee` is not `assigned_to`, and neither is ever read from the other.**
 * `Speaker.assigned_to` is the board member who looks after the *lead*;
 * `ChecklistAssignee.assignee` is the person who owes *one line*. Phase 2 paid
 * for merging two notions into one field once already -- `assignLead` wrote
 * over `proposed_by`, and the handbook makes whoever proposed a speaker the
 * person who has to tell them if the board declines, so the overwrite destroyed
 * the record of who owed that message. The non-derivation is not a convention
 * here, it is enforced: `speaker.checklist` is the only thing `itemAssignee`
 * touches, and outside these comments the *code* of this module never names
 * `assigned_to`, `proposed_by`, `host_1` or `host_2`. `assignment.test.ts`
 * reads this file, strips its comments and asserts exactly that, so a fallback
 * cannot be added later -- by anyone, in any of these four fields -- without a
 * red test, which is a stronger guarantee than a test that only checks the one
 * case somebody thought of.
 *
 * **No owner is the normal state, not an unfinished one.** An item nobody is
 * named on is the hosts', which is what every line has always meant. `''`
 * produces no warning, no lateness row and no nag: `itemsWaitingFor` refuses an
 * empty login outright, so "nobody" can never match "me". A tool that scolds
 * volunteers for not filling in a field they never asked for is a tool they
 * stop using.
 *
 * **Nothing here invents wording for a thing that is waiting.** `state/sla.ts`
 * already says `Board decision is 3 days overdue` / `waiting since 2026-08-18`,
 * and the inbox renders exactly those sentences over the rows this module
 * returns. There is no second phrase, and -- as in `sla.ts` -- what the screen
 * describes is a piece of work outstanding, never a person failing: a row
 * carries a `RunbookItem`, whose labels are fixed in `state/phases.ts`, and
 * there is no slot in it a name could occupy.
 *
 * Pure throughout: no clock and no state, so every writer here can run inside a
 * `mutate` transformation replayed against freshly-read data.
 */
import type { Config, Speaker } from '../data/types';
import { PHASES, isItemDone, phaseItems, phaseOf, type RunbookItem } from './phases';

/** Every key the journey has, so a line that is not in it cannot be written
 *  against.
 *
 *  Built rather than listed, and built through `phaseItems`, so an item added
 *  to `PHASES` is assignable the same day -- and so is a promotion channel
 *  added to `data/config.yml`, which is why this is a function of the config
 *  and not a constant. A channel is a line of the journey like any other; a
 *  guard that only knew the static table would have refused every one of them
 *  with "is not a step of the journey", leaving the series a list of places to
 *  announce in that nobody could be put down for. */
function journeyItemKeys(config: Config | null): ReadonlySet<string> {
  return new Set(PHASES.flatMap(phase => phaseItems(phase, config).map(item => item.key)));
}

/** Who a line may be owned by: a GitHub login, the same rule
 *  `tools/convener_ops/validate.py` applies to `checklist[*].assignee` and
 *  `data/validate.ts` now applies when reading the file. It was enforced on
 *  the Python side alone, so `assignItem` -- which is exported, and whose
 *  `<select>` of logins is a screen and not a rule -- could write a record
 *  `convener-validate` refuses. Pinned across both languages by
 *  `checklist_assignee_cases` in
 *  `tools/tests/fixtures/governance-cases.json`. */
const LOGIN = /^[a-zA-Z0-9-]+$/;

/** An assignment that cannot be recorded as asked. The message is a plain
 *  sentence that reaches a volunteer's screen as-is, relayed by
 *  `github/errors.ts` -- the same arrangement as `DateRejected`. */
export class AssignmentRejected extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AssignmentRejected';
  }
}

/**
 * The person named against one line of this record's journey.
 *
 * `''` for a line nobody has been named on -- whether the record holds no
 * entry for it at all, or an entry with an empty name. The two are the same
 * fact and the caller must not have to tell them apart.
 *
 * This reads `speaker.checklist` and nothing else. There is deliberately no
 * fallback to `assigned_to`, to `host_1`, or to anything that would make a
 * name appear here that nobody typed against this line.
 */
export function itemAssignee(speaker: Speaker, itemKey: string): string {
  return speaker.checklist[itemKey]?.assignee ?? '';
}

function withChecklist(
  current: Speaker[],
  speakerId: string,
  itemKey: string,
  config: Config | null,
  update: (checklist: Speaker['checklist']) => Speaker['checklist'],
): Speaker[] {
  if (!journeyItemKeys(config).has(itemKey)) {
    throw new AssignmentRejected(
      `"${itemKey}" is not a step of the journey, so nobody can be put down for it.`,
    );
  }
  return current.map(s => (s.id === speakerId ? { ...s, checklist: update(s.checklist) } : s));
}

/**
 * Put `login` down for one line of one record's journey.
 *
 * Takes and returns the whole list, so it is the transformation `mutate`
 * replays against whatever the file says at write time -- nothing is captured
 * from a rendered screen.
 *
 * An empty `login` unassigns rather than storing a blank owner, because "no
 * owner" already has a spelling in this model and two spellings of one fact is
 * how a filter starts disagreeing with a display.
 *
 * `config` is what makes the promotion channels assignable: they are lines of
 * the journey that live in `data/config.yml`, so which keys exist cannot be
 * answered without it. `null` -- no config loaded -- accepts the lines of the
 * static table and nothing more.
 */
export function assignItem(
  current: Speaker[],
  speakerId: string,
  itemKey: string,
  login: string,
  config: Config | null,
): Speaker[] {
  const owner = login.trim();
  if (owner === '') return unassignItem(current, speakerId, itemKey, config);
  if (!LOGIN.test(owner)) {
    throw new AssignmentRejected(
      `"${owner}" is not a GitHub username, so nobody can be put down under it. ` +
        'A line is owned by an account, never by a person written out by name.',
    );
  }
  return withChecklist(current, speakerId, itemKey, config, checklist => ({
    ...checklist,
    [itemKey]: { assignee: owner },
  }));
}

/**
 * Take the name off one line, returning it to the hosts.
 *
 * Removes the entry rather than blanking it: an unassigned line is one the
 * record says nothing about, which is where every line starts.
 */
export function unassignItem(
  current: Speaker[],
  speakerId: string,
  itemKey: string,
  config: Config | null,
): Speaker[] {
  return withChecklist(current, speakerId, itemKey, config, checklist =>
    Object.fromEntries(Object.entries(checklist).filter(([key]) => key !== itemKey)),
  );
}

/** One outstanding line, with the record it belongs to. */
export interface WaitingItem {
  speaker: Speaker;
  item: RunbookItem;
}

/**
 * The lines this person is down for and has not done yet.
 *
 * Only the current phase of each record is considered: a name left on a line
 * of a phase the event has already left is history, not work, and re-raising
 * it would be the nag this feature is meant not to become. `isItemDone`
 * (`state/phases.ts`) is the one reading of "done" in the app, so a line stops
 * appearing here the moment it stops being outstanding on the speaker page.
 *
 * An empty login gets an empty list. That guard is the whole of the "no owner
 * is not a defect" rule on this side: without it, every unassigned line in the
 * series would match the one person whose login had not loaded yet, and the
 * screen would open on a list of other people's work.
 */
export function itemsWaitingFor(
  speakers: Speaker[],
  login: string | null,
  config: Config | null,
): WaitingItem[] {
  if (!login) return [];
  const waiting: WaitingItem[] = [];
  for (const speaker of speakers) {
    const phase = phaseOf(speaker.status);
    if (!phase) continue;
    for (const item of phaseItems(phase, config)) {
      if (itemAssignee(speaker, item.key) !== login) continue;
      if (isItemDone(speaker, item)) continue;
      waiting.push({ speaker, item });
    }
  }
  return waiting;
}
