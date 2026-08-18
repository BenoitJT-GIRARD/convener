import type { Config, Speaker, SpeakerStatus } from '../data/types';

/**
 * Convert a wall-clock time in Europe/Paris to a UTC epoch, DST included.
 * Moved here from DataContext: it is pure, so it belongs with the other
 * derivations and can finally be tested.
 */
export function parisWallTimeToEpoch(dateStr: string, timeStr: string): number {
  // Single-probe DST correction: this reads the UTC offset at the wall time
  // *treated as if it were already UTC*, which is off by one probe iteration
  // right at a DST transition. For wall times in [00:00, 03:00) on the day
  // the clock changes, that can land the probe on the wrong side of the
  // transition and produce an answer up to an hour off. Unreachable in
  // practice here: seminars run at 12:30 (see the `time` default in
  // src/data/demo.ts and src/components/ActionButtons.tsx), never in that
  // window. Left as a known, accepted limitation rather than complicated
  // away for a scenario this data can never hit.
  const probe = new Date(`${dateStr}T${timeStr}:00Z`);
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/Paris',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
  const map: Record<string, string> = {};
  for (const part of fmt.formatToParts(probe)) {
    if (part.type !== 'literal') map[part.type] = part.value;
  }
  const hour = map.hour === '24' ? '00' : map.hour;
  const parisIso = `${map.year}-${map.month}-${map.day}T${hour}:${map.minute}:${map.second}Z`;
  return probe.getTime() - (Date.parse(parisIso) - probe.getTime());
}

/**
 * The ISO `YYYY-MM-DD` calendar day an instant falls on in Europe/Paris.
 *
 * `Intl` is asked for the Paris wall date directly rather than an offset being
 * applied by hand, so DST is the platform's problem and not ours. `en-CA`
 * formats dates as `YYYY-MM-DD`, which is the shape every date in the data
 * files and every comparison in this app already uses.
 */
const PARIS_DAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Paris',
  year: 'numeric', month: '2-digit', day: '2-digit',
});

export function parisDayOf(instant: Date): string {
  return PARIS_DAY.format(instant);
}

/**
 * Today, in Europe/Paris.
 *
 * The one way this app is allowed to ask what day it is. `new Date()
 * .toISOString().slice(0, 10)` is a *UTC* day, and between midnight and 01:00
 * (02:00 in summer) Paris it is still yesterday's -- which matters because
 * several callers do not merely compare this value, they persist it:
 * `opened_on`, `joined_on`, `decided_on`, and every working-day deadline
 * derived from them. A volunteer acting late in the evening would stamp the
 * record with the wrong day and every later comparison would inherit it.
 * `tools/convener_ops/sweep.py::_paris_today` anchors the unattended job the same
 * way; an ESLint rule in `eslint.config.js` keeps the UTC form from coming
 * back (P2-9).
 */
export function parisToday(): string {
  return parisDayOf(new Date());
}

export function hasEnded(s: Speaker, config: Config, now: Date): boolean {
  if (s.status !== 'scheduled' || !s.date) return false;
  if (s.time) {
    // A falsy configured value (0, or unset) falls back to the default,
    // matching tools/convener_ops/sweep.py's `or 90` — the two must agree since
    // one displays the transition and the other persists it.
    const duration = (config.seminar_duration_minutes || 90) * 60_000;
    return now.getTime() >= parisWallTimeToEpoch(s.date, s.time) + duration;
  }
  // Legacy rows carry no time: treat them as over the following day.
  return s.date < parisDayOf(now);
}

/**
 * What the user should see, which is not always what is recorded.
 * Persisting this transition is the scheduled job's business (tools/convener_ops/sweep.py),
 * so that a single writer owns it and two open tabs cannot race.
 */
export function effectiveStatus(s: Speaker, config: Config, now: Date): SpeakerStatus {
  return hasEnded(s, config, now) ? 'delivered' : s.status;
}
