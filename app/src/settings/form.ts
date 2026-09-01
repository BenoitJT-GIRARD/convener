/**
 * What the settings form offers, and -- for each value -- *when* changing
 * it changes anything.
 *
 * The second half of this module is the half that is easy
 * to leave out and expensive to leave out. Saving commits the number and
 * starts `.github/workflows/deploy.yml`; whether that makes the number
 * live depends on which job reads it, and the differences are not
 * cosmetic --
 *
 * - `alarm_after_hours` and the whole of `instance/actions-budget.yml` are
 *   read by *Sweep and notify the board* at the top of each of its runs, so
 *   a change is live at the next one -- tomorrow morning, in the ordinary
 *   case;
 * - `instance/queue-drain.yml`'s `max_silent_days` is read by *Retention
 *   liveness watchdog*, a different schedule;
 * - `queue_beyond_hours` reaches nothing at all until *Deploy app*
 *   regenerates and commits `instance/public-data/registration-routing.json`, which
 *   is what the registration relay actually reads. Saving starts that
 *   workflow, so the new threshold reaches the relay on its next
 *   successful run; until then a registration is still routed on the
 *   threshold already published there.
 *
 * A form that implied any of these took effect on save would be lying in
 * the direction that costs a participant their seat, so every field carries
 * its own answer and the screen prints it beside the field rather than once
 * at the top.
 *
 * The set of keys is closed, and it is closed for a reason that is checked
 * rather than asserted: `queue_watch.thresholds_from_data`,
 * `registration_routing.threshold_from_data` and
 * `actions_usage.budget_from_data` each refuse, by name, any key they do
 * not know. A key this form invented would be a value written into a file
 * the next scheduled run stops on. `tools/tests/fixtures/instance-settings.
 * json` holds the set and `tools/tests/repository/test_instance_settings.py` drives
 * each parser against it, so the two sides cannot drift.
 */
import { ACTIONS_BUDGET_FILE, QUEUE_DRAIN_FILE, REGISTRATION_LANES_FILE } from './bounds';
import { dataDir, keysDir, publicDataDir, registerPath } from '../paths';

/** When a saved value starts being read, and by what. `where` is a path
 *  somebody can open; `when` is a sentence they can act on. */
export interface Effect {
  when: string;
  where: string;
}

const SWEEP: Effect = {
  when: 'at the next run of Sweep and notify the board, which re-reads this file every time it runs.',
  where: '.github/workflows/sweep-and-notify.yml',
};

const WATCHDOG: Effect = {
  when: 'at the next run of Retention liveness watchdog, which is the job that reads this tolerance.',
  where: '.github/workflows/retention-watchdog.yml',
};

const DEPLOY: Effect = {
  when:
    'only once Deploy app has regenerated and committed ' +
    `${publicDataDir()}registration-routing.json, which is what the registration ` +
    'relay reads. Saving starts that workflow, so the new threshold reaches ' +
    'the relay on its next successful run. Until then registrations route ' +
    'on the threshold already published there.',
  where: '.github/workflows/deploy.yml',
};

/** One number the form offers. `kind` decides how it is read back out of
 *  the field; the bounds themselves are `bounds.ts`'s, never restated
 *  here. */
export interface Setting {
  file: string;
  key: string;
  label: string;
  /** What this number decides, in one line, for somebody who has not read
   *  the file's own header. */
  what: string;
  unit: string;
  kind: 'whole' | 'share';
  effect: Effect;
  /** True for the two ends of the coupling, which the screen groups
   *  together: they bound each other, and moving one to make room for the
   *  other is the manoeuvre nothing tells anybody about today. */
  coupled: boolean;
}

export const SETTINGS: readonly Setting[] = [
  {
    file: QUEUE_DRAIN_FILE,
    key: 'alarm_after_hours',
    label: 'Queue alarm',
    what: 'How long a public submission may be known to be waiting before the board is told and the daily job goes red.',
    unit: 'hours',
    kind: 'whole',
    effect: SWEEP,
    coupled: true,
  },
  {
    file: REGISTRATION_LANES_FILE,
    key: 'queue_beyond_hours',
    label: 'Immediate-lane threshold',
    what: 'How close to an event a registration stops waiting for the daily drain and is dispatched straight away.',
    unit: 'hours before the event',
    kind: 'whole',
    effect: DEPLOY,
    coupled: true,
  },
  {
    file: QUEUE_DRAIN_FILE,
    key: 'max_silent_days',
    label: 'Drain silence tolerance',
    what: 'How long instance/data/queue-watch.yml may go without moving before the drain itself is called dead.',
    unit: 'days',
    kind: 'whole',
    effect: WATCHDOG,
    coupled: false,
  },
  {
    file: ACTIONS_BUDGET_FILE,
    key: 'monthly_minutes',
    label: 'Monthly Actions allowance',
    what: "The organisation's free monthly minutes. Shared with its other private repositories, so every figure derived from it is a lower bound on the bill.",
    unit: 'minutes',
    kind: 'whole',
    effect: SWEEP,
    coupled: false,
  },
  {
    file: ACTIONS_BUDGET_FILE,
    key: 'window_days',
    label: 'Usage window',
    what: 'How many days the rolling measurement covers, today included. What has to be visible is a rate, not a monthly total.',
    unit: 'days',
    kind: 'whole',
    effect: SWEEP,
    coupled: false,
  },
  {
    file: ACTIONS_BUDGET_FILE,
    key: 'warn_at_share',
    label: 'Warn at',
    what: 'The share of the monthly allowance at which the projected rate becomes an alarm.',
    unit: 'of the allowance',
    kind: 'share',
    effect: SWEEP,
    coupled: false,
  },
  {
    file: ACTIONS_BUDGET_FILE,
    key: 'submissions_per_day',
    label: 'Burst of submissions',
    what: 'Public submissions in a single day that count as a burst. The only item in the budget whose volume is decided by strangers.',
    unit: 'a day',
    kind: 'whole',
    effect: SWEEP,
    coupled: false,
  },
  {
    file: ACTIONS_BUDGET_FILE,
    key: 'max_runs',
    label: 'Collector ceiling',
    what: 'How many runs the usage collector will read before it gives up and raises its own alarm rather than truncating in silence.',
    unit: 'runs',
    kind: 'whole',
    effect: SWEEP,
    coupled: false,
  },
  {
    file: ACTIONS_BUDGET_FILE,
    key: 'max_silent_days',
    label: 'Measurement silence tolerance',
    what: 'How long instance/data/actions-usage.yml may go without moving before the measurement itself is called dead.',
    unit: 'days',
    kind: 'whole',
    effect: SWEEP,
    coupled: false,
  },
];

/** The files the form writes, in the order the screen shows them. Derived
 *  from `SETTINGS`, so a file cannot appear in one and not the other. */
export function editableFiles(): string[] {
  return [...new Set(SETTINGS.map(setting => setting.file))];
}

/**
 * Why a file the instance owns is nevertheless not offered as a form.
 *
 * Everything `declarations/boundary.yml` hands to the instance and that is *not*
 * in `SETTINGS` gets one of these lines, and none of them is "not
 * implemented yet": each is a reason a form is the wrong instrument.
 * `null` means the path has no entry here, which is itself a finding --
 * `app/tests/settings-screen.test.tsx` refuses one.
 */
export function whyNotAForm(path: string): string | null {
  if (path === dataDir()) {
    return 'Edited here, on the other screens: the board, the pipeline, the agenda and every speaker record are this directory. A second way in would be a second shape for the same records.';
  }
  if (path === keysDir()) {
    return "Cryptographic material. A key is generated by an operator's own command and its private half never touches this repository at all; there is nothing here a field could hold.";
  }
  if (path === publicDataDir()) {
    return 'Derived from instance/data/ by the product\'s own commands and committed by Deploy app. Typing into it would be typing an answer the next run overwrites.';
  }
  if (path === registerPath()) {
    return 'A total re-rendering of this repository\'s own commit history, written by the register workflow on every push and never by hand — convener-register --check fails the build if anybody tries.';
  }
  if (path === 'instance/config.json') {
    return 'Read by the build itself: the address, the identity and the edition prefix are compiled into this bundle and into the showcase, so a change here would take effect at the next deploy and not before — and this screen is running on the old one. The edition prefix is frozen besides: it is in published addresses, on issued certificates and in key filenames, and a series never renumbers editions it has already run.';
  }
  return null;
}
