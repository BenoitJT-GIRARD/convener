/**
 * What an instance threshold may be, computed where somebody types it.
 *
 * Phase 11, task 5. Three of the four files `config/boundary.yml` hands to
 * the instance are numbers a maintainer edits, and every one of those
 * numbers is bounded by something *else* in the repository -- the drain's
 * own cron, the lane threshold next door. A file cannot refuse a value: it
 * takes whatever is typed, and the bound is only discovered later, by a
 * test on somebody's machine or by a scheduled job going red. A form can
 * refuse, and this module is what lets it.
 *
 * The sharp case, and the reason this screen exists at all
 * -------------------------------------------------------
 * `config/queue-drain.yml`'s `alarm_after_hours` is bounded on **both**
 * sides by other declarations. Its floor is twice the drain's period,
 * because `sweep-and-notify.yml`'s own header records that GitHub's
 * scheduled runs "are routinely ten to twenty minutes late and are dropped
 * outright under load" -- an alarm that fires before a healthy drain has
 * had its chance is one people learn to ignore. Its ceiling is
 * `config/registration-lanes.yml`'s `queue_beyond_hours` minus those same
 * two periods, because one period is spent before the clock starts (the age
 * is measured from the first drain that *observed* the entry) and one has
 * to be left after the alarm, or the board hears about a registration as
 * its seminar begins.
 *
 * **With this repository's settings today those two meet exactly at 48**,
 * so there is precisely one legal value, and nothing in the file tells
 * anybody editing it. Raising `queue_beyond_hours` is what buys slack;
 * lowering it towards its own floor takes the ceiling below the floor and
 * makes the pair impossible, which is a finding about the settings rather
 * than a broken check.
 *
 * Two copies of one arithmetic, and why that is allowed here
 * ---------------------------------------------------------
 * `tools/convener_ops/registration_routing.py` and
 * `tools/convener_ops/queue_watch.py` hold the same rules; they have to, because
 * they are what the scheduled jobs enforce and no browser is running when a
 * job runs. D-14's answer to a decision that genuinely lives on both sides
 * of a language boundary is not to move the decision, it is to pin the
 * *answer*: `tools/tests/fixtures/instance-settings.json` holds the cases,
 * `tools/tests/test_instance_settings.py` answers them from Python and
 * `app/tests/settings-bounds.test.ts` answers them from here. A bound this
 * module computed differently from the one the daily job enforces would be
 * worse than no form at all -- a volunteer told a value is fine, and a job
 * that goes red on it the next morning.
 */

/**
 * How many drains in a row every floor here assumes may not happen. Two,
 * not one, mirroring `registration_routing.MISSED_DRAINS_COVERED` -- one is
 * what a floor of "the period itself" would assume, and it is the
 * assumption that loses somebody their seat.
 */
export const MISSED_DRAINS_COVERED = 2;

/** The drain whose cadence every floor below is derived from. */
export const DRAIN_WORKFLOW = '.github/workflows/sweep-and-notify.yml';

export const QUEUE_DRAIN_FILE = 'config/queue-drain.yml';
export const REGISTRATION_LANES_FILE = 'config/registration-lanes.yml';
export const ACTIONS_BUDGET_FILE = 'config/actions-budget.yml';

const HOURS_PER_DAY = 24;

/**
 * The one cron shape this module will put a number on: a fixed minute and a
 * fixed hour, every day. Mirrors `registration_routing._DAILY_CRON_RE`.
 * Anything else -- a step, a list, a day-of-week or day-of-month
 * restriction -- is refused by name rather than approximated, because a
 * floor built on a guessed cadence is a registration that misses its own
 * seminar.
 */
const DAILY_CRON = /^\s*\d+\s+\d+\s+\*\s+\*\s+\*\s*$/;

/** A schedule this module will not put a number on. Its own class, so a
 *  caller can tell "the workflow's schedule is unreadable" -- a finding
 *  about the workflow -- apart from "the value you typed is out of
 *  bounds". */
export class CronShapeRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CronShapeRefused';
  }
}

/**
 * The guaranteed cadence of the drain, from an already-parsed `schedule:`
 * list: the period in hours, and the cron it was read out of.
 *
 * The cron travels with the number because every refusal this module
 * writes names it. A maintainer told "48 hours is the earliest this alarm
 * may fire" can check the arithmetic only if they are also told which
 * schedule the 24 came from -- and that is the difference between a bound
 * somebody trusts and a bound somebody deletes.
 *
 * Only `schedule:` counts, exactly as on the Python side: that workflow
 * also declares `push:` and `workflow_dispatch:`, and both can start the
 * same job -- but neither is a *cadence*, and a floor built on either would
 * be a floor built on somebody's habits.
 *
 * Takes the list rather than the whole workflow document because the two
 * languages disagree about the key it sits under: PyYAML's YAML-1.1
 * resolver turns `on:` into the boolean `True`, while the browser's reader
 * resolves it to the string `"on"`. `drainSchedule` below is where that
 * difference is met, once.
 */
export function drainCadence(schedule: unknown): { hours: number; cron: string } {
  if (!Array.isArray(schedule) || schedule.length === 0) {
    throw new CronShapeRefused(
      `${DRAIN_WORKFLOW} declares no schedule: entry, so nothing guarantees ` +
        'the drain runs at all',
    );
  }
  if (schedule.length !== 1) {
    throw new CronShapeRefused(
      `${DRAIN_WORKFLOW} declares ${schedule.length} cron entries; the ` +
        'worst-case gap between several schedules is not something this ' +
        'arithmetic will guess at',
    );
  }
  const entry: unknown = schedule[0];
  const cron =
    entry !== null && typeof entry === 'object'
      ? (entry as Record<string, unknown>).cron
      : undefined;
  if (typeof cron !== 'string' || !DAILY_CRON.test(cron)) {
    throw new CronShapeRefused(
      `${DRAIN_WORKFLOW} schedules ${JSON.stringify(cron ?? null)}, which is ` +
        'not the fixed-minute, fixed-hour, every-day shape this arithmetic ' +
        'knows how to put a period on',
    );
  }
  return { hours: HOURS_PER_DAY, cron };
}

/**
 * The `schedule:` list out of an already-parsed workflow document.
 *
 * `on:` is the string key here and the boolean `true` under PyYAML; both
 * are read, so a document that came through either reader answers the same
 * -- and neither spelling is a *decision*, which is why this is the one
 * place the difference is allowed to show.
 */
export function drainSchedule(workflow: unknown): unknown {
  if (workflow === null || typeof workflow !== 'object') return undefined;
  const document = workflow as Record<string, unknown>;
  const triggers = document.on ?? document.true;
  if (triggers === null || typeof triggers !== 'object') return undefined;
  return (triggers as Record<string, unknown>).schedule;
}

/** The lowest and the highest `alarm_after_hours` may take. The two can
 *  meet -- today they do -- and they can cross, which says the lane
 *  threshold has been cut so close to the drain's cadence that no alarm can
 *  both wait for a healthy drain and leave anybody time to act. Mirrors
 *  `queue_watch.alarm_bounds`. */
export function alarmBounds(
  periodHours: number,
  queueBeyondHours: number,
): { floor: number; ceiling: number } {
  const margin = MISSED_DRAINS_COVERED * periodHours;
  return { floor: margin, ceiling: queueBeyondHours - margin };
}

/** The lowest `queue_beyond_hours` that is still safe against the drain
 *  that exists. Mirrors `registration_routing.floor_hours`. */
export function laneFloorHours(periodHours: number): number {
  return periodHours * MISSED_DRAINS_COVERED;
}

/** The lowest `config/queue-drain.yml::max_silent_days` may be, in whole
 *  days: the same two drain periods, rounded **up** so a drain running more
 *  often than daily never lowers it below a day. Mirrors
 *  `queue_watch.silence_floor_days`. */
export function silenceFloorDays(periodHours: number): number {
  return Math.max(1, Math.ceil((MISSED_DRAINS_COVERED * periodHours) / HOURS_PER_DAY));
}

/** Everything a bound needs to know about the rest of the repository at the
 *  moment somebody types. Every field is read from a file, never assumed:
 *  `periodHours` from the drain's own cron, the other two from the two
 *  declarations they name. */
export interface Coupling {
  /** The drain's cadence, from `drainPeriodHours`. */
  periodHours: number;
  /** The cron it was derived from, for a message that can be checked. */
  cron: string;
  /** `config/registration-lanes.yml`'s current `queue_beyond_hours`. */
  queueBeyondHours: number;
  /** `config/queue-drain.yml`'s current `alarm_after_hours`. */
  alarmAfterHours: number;
}

/** Which end refused a value. Carried as a field rather than left to be
 *  read out of the sentence, so the fixture can pin it on both sides while
 *  the wording stays free to improve. */
export type BoundName = 'floor' | 'ceiling' | 'coupling';

export interface Refusal {
  bound: BoundName;
  /** One sentence, naming the bound, the number it works out to, and the
   *  declaration it comes from. Never "invalid": a maintainer who is told a
   *  value is invalid edits the file by hand instead. */
  message: string;
}

/** The margin sentence every floor here shares, with the cron it was read
 *  from named so the reader can check it. */
function drainMargin(coupling: Coupling): string {
  return (
    `twice the drain's own period (${MISSED_DRAINS_COVERED} × ` +
    `${coupling.periodHours} hours, from ${DRAIN_WORKFLOW}'s cron ` +
    `'${coupling.cron}')`
  );
}

function alarmRefusal(value: number, coupling: Coupling): Refusal | null {
  const { floor, ceiling } = alarmBounds(coupling.periodHours, coupling.queueBeyondHours);
  const crossed =
    floor > ceiling
      ? ` And these two have crossed: at ${REGISTRATION_LANES_FILE}'s current ` +
        `queue_beyond_hours (${coupling.queueBeyondHours}) no alarm can both wait ` +
        'for a healthy drain and still leave anybody time to act, so it is the ' +
        'lane threshold that has to move, not this one.'
      : '';
  if (value < floor) {
    return {
      bound: 'floor',
      message:
        `${floor} hours is the earliest this alarm may fire: ${drainMargin(coupling)}. ` +
        'An alarm that fires before a healthy drain has had its chance is an ' +
        `alarm people learn to ignore.${crossed}`,
    };
  }
  if (value > ceiling) {
    return {
      bound: 'ceiling',
      message:
        `${ceiling} hours is the latest this alarm may fire: ` +
        `${REGISTRATION_LANES_FILE}'s queue_beyond_hours ` +
        `(${coupling.queueBeyondHours}) minus ${drainMargin(coupling)}. Later ` +
        'than that and the board is told about a registration as its seminar ' +
        `begins.${crossed}`,
    };
  }
  return null;
}

function laneRefusal(value: number, coupling: Coupling): Refusal | null {
  const own = laneFloorHours(coupling.periodHours);
  if (value < own) {
    return {
      bound: 'floor',
      message:
        `${own} hours is the least this threshold may be: ${drainMargin(coupling)}. ` +
        'Below it, a far-lane registrant whose drain was dropped is sent their ' +
        'room link and matching code after their seminar has started.',
    };
  }
  const coupled = coupling.alarmAfterHours + laneFloorHours(coupling.periodHours);
  if (value < coupled) {
    return {
      bound: 'coupling',
      message:
        `${coupled} hours is the least this threshold may be while ` +
        `${QUEUE_DRAIN_FILE} holds alarm_after_hours: ${coupling.alarmAfterHours}. ` +
        "That alarm's ceiling is this value minus " +
        `${drainMargin(coupling)}, so anything lower puts the alarm already ` +
        'written next door out of bounds. Lower that one first, or leave this ' +
        'one where it is.',
    };
  }
  return null;
}

function silenceRefusal(value: number, coupling: Coupling): Refusal | null {
  const floor = silenceFloorDays(coupling.periodHours);
  if (value < floor) {
    return {
      bound: 'floor',
      message:
        `${floor} day${floor === 1 ? '' : 's'} is the least this tolerance may ` +
        `be: the same ${MISSED_DRAINS_COVERED} drain periods the alarm's own ` +
        `floor allows for (${drainMargin(coupling)}), in whole days. A record ` +
        'that must move every day calls a single dropped schedule a dead drain.',
    };
  }
  return null;
}

/** A whole number at or above `least`, or the sentence saying why not. The
 *  minimum each one carries is its own parser's -- `budget_from_data` and
 *  the two beside it refuse below it by name -- so a value this accepted
 *  and that refused would be a file the next scheduled run cannot read. */
function wholeRefusal(value: number, least: number, named: string, file: string): Refusal | null {
  if (!Number.isInteger(value) || value < least) {
    return {
      bound: 'floor',
      message:
        `${named} is a whole number of at least ${least}: ${file}'s own reader ` +
        `refuses anything else by name, so a smaller value here is a file the ` +
        'next scheduled run stops on rather than works from.',
    };
  }
  return null;
}

function shareRefusal(value: number): Refusal | null {
  if (!(value > 0)) {
    return {
      bound: 'floor',
      message:
        `warn_at_share is a share of ${ACTIONS_BUDGET_FILE}'s monthly_minutes, ` +
        'greater than nought: warning at nought is warning always, which is ' +
        'warning never.',
    };
  }
  if (value > 1) {
    return {
      bound: 'ceiling',
      message:
        `warn_at_share is a share of ${ACTIONS_BUDGET_FILE}'s monthly_minutes, ` +
        'so 1 is the most it may be. A warning past the whole allowance is a ' +
        'warning that arrives after the bill.',
    };
  }
  return null;
}

/**
 * Whether one typed value may be written, and why not when it may not.
 *
 * `null` is "write it". Everything else is a `Refusal` naming the end that
 * refused and the declaration the bound is read from -- the whole point
 * being that a maintainer can check the arithmetic rather than take it on
 * trust, and can see *which other file* to move if this one will not go
 * where they want it.
 */
export function checkSetting(
  file: string,
  key: string,
  value: number,
  coupling: Coupling,
): Refusal | null {
  if (!Number.isFinite(value)) {
    return {
      bound: 'floor',
      message: `${key} has to be a number; ${file} holds numbers and nothing else.`,
    };
  }
  if (file === QUEUE_DRAIN_FILE && key === 'alarm_after_hours') {
    return wholeRefusal(value, 1, key, file) ?? alarmRefusal(value, coupling);
  }
  if (file === QUEUE_DRAIN_FILE && key === 'max_silent_days') {
    return wholeRefusal(value, 1, key, file) ?? silenceRefusal(value, coupling);
  }
  if (file === REGISTRATION_LANES_FILE && key === 'queue_beyond_hours') {
    return wholeRefusal(value, 1, key, file) ?? laneRefusal(value, coupling);
  }
  if (file === ACTIONS_BUDGET_FILE && key === 'warn_at_share') {
    return shareRefusal(value);
  }
  if (file === ACTIONS_BUDGET_FILE) {
    return wholeRefusal(value, key === 'max_silent_days' ? 0 : 1, key, file);
  }
  return {
    bound: 'floor',
    message: `${key} is not a setting ${file} declares, so nothing here knows what bounds it.`,
  };
}
