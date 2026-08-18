import type { Config, Speaker, SpeakerStatus } from '../data/types';

/**
 * Convert a wall-clock time in Europe/Paris to a UTC epoch, DST included.
 * Moved here from DataContext: it is pure, so it belongs with the other
 * derivations and can finally be tested.
 */
export function parisWallTimeToEpoch(dateStr: string, timeStr: string): number {
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
  return s.date < now.toISOString().slice(0, 10);
}

/**
 * What the user should see, which is not always what is recorded.
 * Persisting this transition is the scheduled job's business (tools/convener_ops/sweep.py),
 * so that a single writer owns it and two open tabs cannot race.
 */
export function effectiveStatus(s: Speaker, config: Config, now: Date): SpeakerStatus {
  return hasEnded(s, config, now) ? 'delivered' : s.status;
}
