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
 * back.
 */
export function parisToday(): string {
  return parisDayOf(new Date());
}

/** This project's one standing start time, Europe/Paris local. Mirrors
 *  `tools/convener_ops/publication/visual.py::STANDING_START_LOCAL` and
 *  `site/.eleventy.js::STANDING_START_LOCAL`. */
const STANDING_START_LOCAL = '12:30';

const _WEEKDAYS = [
  'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday',
] as const;
const _MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const;

/**
 * Europe/Paris's own UTC offset and abbreviation for `isoDate`, at this
 * project's standing 12:30 local start time -- +01:00/CET from late October
 * to late March, +02:00/CEST the rest of the year.
 *
 * A third independent reading of the identical fact
 * `tools/convener_ops/publication/visual.py::paris_standing_start` and
 * `site/.eleventy.js::parisStandingStart` already compute (D-14: a rule
 * crossing a language boundary is bound by a shared fixture, never moved to
 * one side -- `tools/tests/fixtures` names no site for this one because
 * neither of the other two reads this file either; the five fixture editions
 * in `site/src/_data/events.json`, three of them in daylight-saving time, are
 * what all three implementations are checked against). A hand-typed "CET"
 * regardless of season was the reference poster's own defect,
 * recalled here for a third possible place to reintroduce it:
 * a drafted announcement text.
 *
 * `timeZoneName: 'shortOffset'` is stable across locales ('GMT+1', 'GMT+2');
 * the CET/CEST abbreviation is not -- `en-US`'s own ICU data renders it as
 * this same 'GMT+1'/'GMT+2' string, not the letters, while `en-GB`'s does
 * (`site/.eleventy.js`'s own comment records checking both locally). Rather
 * than pin this project's output to whichever one locale's data happens to
 * spell it out, the offset is the only thing asked of `Intl` here, and the
 * abbreviation is this project's own fixed naming of the one offset Europe/
 * Paris is ever in at this project's own standing hour.
 *
 * Probed at midday UTC on `isoDate`, not at the standing local time itself
 * (computing that would need the offset already known to convert it to UTC
 * first): Europe/Paris's DST transitions always happen in the small hours,
 * well before midday on the transition day, so a midday-UTC probe always
 * resolves the offset actually in effect at 12:30 Paris local time on that
 * same calendar date.
 */
export function parisStandingStart(isoDate: string): { offset: string; abbreviation: string } {
  const probe = new Date(`${isoDate}T12:00:00Z`);
  const part = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/Paris',
    timeZoneName: 'shortOffset',
  })
    .formatToParts(probe)
    .find(p => p.type === 'timeZoneName');
  const match = part ? /^GMT([+-])(\d{1,2})$/.exec(part.value) : null;
  if (!match) {
    throw new Error(`unexpected Europe/Paris UTC offset from Intl for ${isoDate}`);
  }
  const [, sign, hours] = match;
  const offset = `${sign}${hours.padStart(2, '0')}:00`;
  const abbreviation = offset === '+02:00' ? 'CEST' : 'CET';
  return { offset, abbreviation };
}

/**
 * "Thursday, 12 March 2026 at 12:30 CET" -- the one sentence a drafted
 * announcement states an edition's date and time in, computed rather than
 * assembled by hand so the zone label can never be a stale copy-paste.
 * Mirrors `tools/convener_ops/publication/visual.py::date_line` -- fixed English weekday and
 * month names rather than `toLocaleDateString`, for the same reason that
 * module gives: a rendered page's wording must not depend on the locale of
 * whatever machine renders it.
 *
 * `''` for an unparseable or empty `isoDate`, so a record with no date yet
 * shows the ordinary `«missing: …»` marker (`content/render.ts::substitute`)
 * rather than a thrown error surfacing as a broken screen.
 */
export function dateLine(isoDate: string): string {
  const parsed = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!parsed) return '';
  const [, y, m, d] = parsed;
  const asUtc = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(asUtc.getTime())) return '';
  const { abbreviation } = parisStandingStart(isoDate);
  const weekday = _WEEKDAYS[asUtc.getUTCDay()];
  const month = _MONTHS[Number(m) - 1];
  return `${weekday}, ${Number(d)} ${month} ${y} at ${STANDING_START_LOCAL} ${abbreviation}`;
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
