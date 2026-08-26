/**
 * Which step of the pipeline has been waiting longer than the series planned
 * for it.
 *
 * **What this module is about, and what it is deliberately not about.** A lead
 * can sleep for months without anyone noticing. The fix
 * is to make the *waiting* visible. It is not to publish how long each
 * volunteer took. Everyone in this series is unpaid and has a day job, and a
 * screen that reads as a performance record over named people gets either
 * ignored or resented -- both worse than not building it at all. So the unit
 * of measure here is a **step**, never a person:
 *
 * - `Deadline.step` holds a step name ("Board decision", "Forum summary"), and
 *   the labels are fixed in `STEP_LABELS` -- there is no code path that can put
 *   a login, an `assigned_to`, a `host_1` or a `proposed_by` into a string this
 *   module produces. `Speaker` is read for its dates and its status only.
 * - The sentences in `overdueText` and `waitingSince` are the complete set of
 *   user-facing wording. Neither has a slot a name could occupy, in the same
 *   way `formatDecision`'s commit grammar has no free prose slot for a verdict
 *   about a member, and in the same way the board-inactivity sweep describes
 *   the ballot record rather than the member. The vocabulary of blame is not
 *   filtered out of these strings; it has nowhere to enter them.
 *
 * **Calendar days, not working days.** `config.sla_days` is counted in
 * calendar days. This repository holds windows in two units on purpose --
 * `config.objection_window_working_days` says its unit in its own name and is
 * counted with `state/working-days.ts` (G-10), while the nomination window and
 * `config.vote_window_days` are calendar days by rule -- so the unit is a
 * decision to make explicitly, not a default to fall into. Three reasons for
 * calendar here:
 *
 * 1. These windows have always been written as plain days -- "14 j", "30
 *    j", "7 j", "14 j" -- beside others that do spell out working days,
 *    and the key is named `sla_days` rather than `sla_working_days`.
 * 2. Reading them as working days would silently stretch 14 days into 20
 *    calendar days and 30 into 42. That is the exact failure this repository
 *    has already had to back out of once: converging two units moves a real
 *    deadline by real days. Nothing here converts between them.
 * 3. These are indicative service levels for work that is largely
 *    asynchronous, not decision windows that close a vote. Nothing terminal
 *    happens when one elapses -- see below.
 *
 * `state/working-days.ts` is therefore not imported here, and that absence is
 * the point rather than an omission.
 *
 * **Nothing here decides anything.** Passing a deadline produces a line of
 * text and a sort position. It parks nothing, rejects nothing, and writes
 * nothing: this module has no `mutate` call and no writer. `tools/convener_ops/
 * sweep.py` remains the only automated hand on the pipeline, and parking a
 * lead there is not a rejection either.
 *
 * **A deadline that cannot be computed is absent, not guessed.** Every
 * clock here starts from a day the record actually holds. Where that day is
 * empty -- a record migrated from a spreadsheet, or one whose window has not
 * been opened yet -- `dueDate` returns `null`, and `byUrgency` sorts those
 * items last. There is
 * no fallback anchor, because inventing one ("assume the lead arrived when the
 * file was created") would manufacture a number a volunteer would then be
 * looking at as if it were recorded.
 *
 * **The zero is not representable.** `Lateness` carries a `days` count only on
 * its `overdue` arm, so a step that is on time has no lateness number to draw
 * and no "0 days overdue" can reach the screen. `overdueDays` still returns
 * `0` before the deadline -- that is arithmetic rather than display --
 * but nothing renders its result directly.
 */
import type { Config, Speaker } from '../data/types';

/** The four steps the series sets a turnaround time for.
 *
 *  Three are keyed as in `config.sla_days`. `lead_decision` is not a key of
 *  it: the board's deadline is `config.vote_window_days`, the number
 *  `tools/convener_ops/sweep.py` parks an expired lead on, and holding it
 *  twice let a file say the board was on time the very morning the job
 *  parked the lead. */
export const SLA_STEPS = [
  'lead_decision',
  'invitation_follow_up',
  'summary_after_delivery',
  'recording_after_delivery',
] as const;
export type SlaStep = (typeof SLA_STEPS)[number];

/**
 * How each step is named on screen.
 *
 * All four are noun phrases for a piece of work. None is a role, and none can
 * be read as an actor: "Board decision" is the decision, not the board.
 */
export const STEP_LABELS: Record<SlaStep, string> = {
  lead_decision: 'Board decision',
  invitation_follow_up: 'Invitation follow-up',
  summary_after_delivery: 'Forum summary',
  recording_after_delivery: 'Recording',
};

export interface Deadline {
  /** A label from `STEP_LABELS`. */
  step: string;
  /** ISO `YYYY-MM-DD`, the last day the step was expected by. */
  due: string;
  /**
   * The recorded day the clock started.
   *
   * Carried so the screen can show it, which is what keeps the display honest
   * on this repository's actual data: 24 leads had their vote window opened on
   * the same day by a one-off backfill, so they will all fall due together and
   * all report the same lateness. Shown bare, that reads as 24 separate slips
   * appearing at once. Shown with the day each has been waiting since -- one
   * identical date across all 24 -- it reads as what it is, a single bulk
   * opening. The artefact is made legible rather than hidden or smoothed.
   */
  since: string;
}

const MS_PER_DAY = 86_400_000;

/** An ISO calendar day the calendar actually has, written out here rather
 *  than imported from `state/working-days.ts`: that module is deliberately
 *  not a dependency of this one (see the header -- these are calendar days,
 *  and no conversion between the two units may become possible by accident),
 *  and the Python twins do the same, `notify.py` carrying its own `_DATE_RE`
 *  beside `governance.py`'s.
 *
 *  The round-trip and the year-zero refusal are not belt and braces:
 *  JavaScript accepts `2026-02-30` and rolls it forward to 2 March where
 *  `date.fromisoformat` raises, so without them the two languages disagree
 *  about a date a hand edit can easily produce. */
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function parsedDay(day: string): number {
  if (!ISO_DAY.test(day) || day < '0001-01-01') return Number.NaN;
  const epoch = Date.parse(`${day}T00:00:00Z`);
  if (Number.isNaN(epoch)) return Number.NaN;
  // eslint-disable-next-line no-restricted-syntax -- a fixed epoch, not "now".
  return new Date(epoch).toISOString().slice(0, 10) === day ? epoch : Number.NaN;
}

/** Midnight UTC of an ISO day, or `NaN` when the string is not one. Both
 *  arguments are already Paris-anchored days supplied by the caller
 *  (`parisToday()`), so no clock is read here and there is no timezone left to
 *  get wrong -- the same discipline as `state/working-days.ts`.
 *
 *  `data/validate.ts` narrows every field's *type* and checks no date's
 *  *shape*, so `opened_on: 'soon'` arrives here from a hand-edited file. It
 *  used to crash the Inbox with a bare `RangeError: Invalid time value`; a
 *  deadline that cannot be computed is *absent* instead, which is what
 *  `notify.py::_maybe` already answered to the same record. */
function epochOf(day: string): number {
  return parsedDay(day);
}

/** Whole calendar days from `from` to `to`; negative when `to` is earlier. */
function calendarDaysBetween(from: string, to: string): number {
  return Math.round((epochOf(to) - epochOf(from)) / MS_PER_DAY);
}

/** The ISO day `n` calendar days after `from`, or `null` when `from` is not
 *  an ISO day or `n` is not a whole number. */
function addCalendarDays(from: string, n: number): string | null {
  const epoch = epochOf(from);
  if (Number.isNaN(epoch) || !Number.isInteger(n)) return null;
  // A fixed epoch built from an ISO day, never a reading of the clock, so
  // there is no Paris-versus-UTC day to get wrong here; same case as
  // working-days.ts::isoOf.
  // eslint-disable-next-line no-restricted-syntax -- see above.
  return new Date(epoch + n * MS_PER_DAY).toISOString().slice(0, 10);
}

/** `null` when the anchor or the configured number of days is unusable. A
 *  deadline that cannot be computed is absent, never guessed -- the same
 *  answer `notify.py::_maybe` gives, and the reason it is `null` here rather
 *  than a thrown `DataShapeError`: an unreadable field in one record must not
 *  take the whole screen down. */
function deadline(step: SlaStep, since: string, days: number): Deadline | null {
  const due = addCalendarDays(since, days);
  return due === null ? null : { step: STEP_LABELS[step], due, since };
}

/** The runbook item (`state/phases.ts`) that records the summary as posted. */
export const SUMMARY_ITEM = 'delivered/forum-summary';

/**
 * The step this speaker is currently waiting on, and the day it was due.
 *
 * `null` when no step of the record has an applicable deadline, or when the
 * day its clock would start from is not recorded.
 *
 * The anchors, and why each is the honest one available:
 *
 * - **Board decision** counts from `selection.opened_on`, the day the board
 *   was actually asked. The record holds no separate "lead created" day, and
 *   the window opening is what the board is answerable to.
 * - **Invitation follow-up** counts from `selection.decided_on`. No
 *   invitation-sent day is stored anywhere in the schema, and rather than
 *   invent a field this uses the day the decision was recorded, which is when
 *   sending the invitation becomes due. That is on or before the real sending
 *   day, so the nudge can only ever come early -- the prudent direction for a
 *   reminder, and the reason this proxy is acceptable where a fabricated date
 *   would not be. `''` still yields `null`.
 * - **Forum summary** and **Recording** count from `date`, the day the talk
 *   was delivered, and apply only while the corresponding artefact is missing:
 *   the summary while its runbook item is unticked, the recording while
 *   `youtube_url` is empty. Once either is in, its deadline stops existing
 *   rather than becoming a satisfied one.
 *
 * A delivered speaker can be waiting on both. The earlier due date wins, so a
 * record has exactly one deadline at a time and the screen never stacks two
 * counts against the same card.
 *
 * This reads the *stored* status, not `effectiveStatus`: the wrap-up clock
 * therefore starts when `tools/convener_ops/sweep.py` records the talk as
 * delivered rather than the instant it ends. That is at most a day of slack on
 * a seven-day target, and it keeps this function free of a `now: Date`
 * argument -- which is what keeps a UTC-versus-Paris day from being
 * representable here at all.
 */
export function dueDate(s: Speaker, config: Config): Deadline | null {
  const sla = config.sla_days;

  if (s.status === 'lead') {
    if (!s.selection.opened_on) return null;
    // `vote_window_days`, not an `sla_days` key of its own: the day
    // this step becomes late is the day `tools/convener_ops/sweep.py` parks the
    // lead, and while those were two numbers a config could set one to 20 and
    // have this screen call the board on time the morning the job parked it.
    return deadline('lead_decision', s.selection.opened_on, config.vote_window_days);
  }

  if (s.status === 'invited') {
    if (!s.selection.decided_on) return null;
    return deadline('invitation_follow_up', s.selection.decided_on, sla.invitation_follow_up);
  }

  if (s.status === 'delivered') {
    if (!s.date) return null;
    const open: Deadline[] = [];
    const summary = s.runbook_progress[SUMMARY_ITEM]
      ? null
      : deadline('summary_after_delivery', s.date, sla.summary_after_delivery);
    if (summary) open.push(summary);
    const recording = s.youtube_url
      ? null
      : deadline('recording_after_delivery', s.date, sla.recording_after_delivery);
    if (recording) open.push(recording);
    if (open.length === 0) return null;
    return open.reduce((soonest, d) => (d.due < soonest.due ? d : soonest));
  }

  return null;
}

/**
 * How many calendar days past its deadline this speaker's current step is.
 *
 * `0` both when there is no applicable deadline and when the deadline has not
 * passed -- including on the due day itself, which is still within the target.
 * Never negative: a step cannot be early, only not yet late.
 */
export function overdueDays(s: Speaker, config: Config, today: string): number {
  const d = dueDate(s, config);
  if (!d) return 0;
  const days = calendarDaysBetween(d.due, today);
  return Number.isNaN(days) ? 0 : Math.max(0, days);
}

/**
 * A step's standing, in the shape the screens consume.
 *
 * Three arms, and the `days` count exists on exactly one of them. A caller
 * cannot render a lateness for a step that is not late, because there is no
 * number on the other two arms to render: absent, not guarded.
 */
export type Lateness =
  | { state: 'none' }
  | ({ state: 'due' } & Deadline)
  | ({ state: 'overdue'; days: number } & Deadline);

export type Overdue = Extract<Lateness, { state: 'overdue' }>;

/** `days` is always at least 1 on the `overdue` arm. */
export function lateness(s: Speaker, config: Config, today: string): Lateness {
  const d = dueDate(s, config);
  if (!d) return { state: 'none' };
  const between = calendarDaysBetween(d.due, today);
  // An unreadable `today` cannot make anything late. `notify.overdue` returns
  // `None` for the same input.
  if (Number.isNaN(between)) return { state: 'due', ...d };
  const days = Math.max(0, between);
  return days > 0 ? { state: 'overdue', days, ...d } : { state: 'due', ...d };
}

/**
 * Comparator: the longest-waiting step first, and anything without a deadline
 * last.
 *
 * Both dated arms order by `due` ascending, which is the same ordering as "most
 * overdue first" for the overdue ones and "soonest next" for the rest, without
 * this function needing to know what day it is.
 *
 * The `none` arm sorting *last* is the load-bearing half. Sorting it first --
 * which is what a naive numeric key does, since "no deadline" reads as zero --
 * would fill the top of the inbox with the 7 speakers whose date fields were
 * never filled in and bury everything that is genuinely waiting, making the
 * screen worse than not having it.
 */
export function byUrgency(a: Lateness, b: Lateness): number {
  if (a.state === 'none') return b.state === 'none' ? 0 : 1;
  if (b.state === 'none') return -1;
  if (a.due < b.due) return -1;
  if (a.due > b.due) return 1;
  return 0;
}

/**
 * The sentence a volunteer reads for a step that is late.
 *
 * "Board decision is 3 days overdue" -- a readable phrase about the step, not
 * a code and not a judgement. The subject of the sentence is always the piece
 * of work; there is no grammatical position in it for a person, so no caller
 * can put one there.
 */
export function overdueText(l: Overdue): string {
  return `${l.step} is ${l.days === 1 ? '1 day' : `${l.days} days`} overdue`;
}

/** The second half of the display: the day this step has been waiting since.
 *  Kept as the stored ISO day, which is what the record holds and what every
 *  other date in this app shows. */
export function waitingSince(l: Overdue): string {
  return `waiting since ${l.since}`;
}
