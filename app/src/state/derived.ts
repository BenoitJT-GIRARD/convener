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
 * `tools/convener_ops/maintenance/sweep.py::_paris_today` anchors the unattended job the same
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
  return dateTimeLine(isoDate, STANDING_START_LOCAL);
}

/**
 * The same sentence for an hour that is not the standing one.
 *
 * The negotiation offers evenings with their own start times -- a slot is a
 * day *and* an hour, and `state/dates.ts` says so -- so a draft invitation
 * naming three of them cannot use `dateLine`, which would print the standing
 * 12:30 against every one of them. That is the reference poster's own defect
 * in a second place: a time written from a convention rather than from the
 * record.
 *
 * `parisStandingStart` is still what answers for the zone, and still probed
 * at midday UTC: Europe/Paris changes its clocks in the small hours, so the
 * offset in force at midday is the offset in force at any hour an evening
 * seminar can be offered at.
 */
export function dateTimeLine(isoDate: string, time: string): string {
  const parsed = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!parsed || !time) return '';
  const [, , m, d] = parsed;
  const asUtc = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(asUtc.getTime())) return '';
  const { abbreviation } = parisStandingStart(isoDate);
  const weekday = _WEEKDAYS[asUtc.getUTCDay()];
  const month = _MONTHS[Number(m) - 1];
  return `${weekday}, ${Number(d)} ${month} ${parsed[1]} at ${time} ${abbreviation}`;
}

/**
 * Whether this record has a way into the room on it.
 *
 * **Either source counts, and that is the whole point.** The room is the
 * record's own `zoom_link` *or* the series-wide `instructions` in
 * `instance/data/config.yml`, and an instance is entitled to use one, the
 * other, or both. D-06 is that the chosen platform's account *is* the
 * permanent room, so on such an instance the per-event field is empty by
 * design and the link lives in the series instructions; an instance that
 * opens a room per seminar has it the other way round.
 *
 * This is the same reconciliation `journey/confirmation.py` performs when it
 * composes the message a registrant receives, and `state/artefacts.ts::room`
 * when it draws the volunteer's own panel. It was a rule about *messages*
 * until an edition could be locked without either source set -- at which
 * point the showcase publishes the event, registration opens, and the first
 * person to sign up is told nothing about where to go. Reading it here makes
 * it a precondition instead (`state/dates.ts::lockBlockers`).
 *
 * `config` may be `null`, which is what a screen holds while data loads. That
 * reads as "no series instructions", so a record with its own link still
 * answers true and one without does not -- the same answer the loaded config
 * would give for an instance that has none.
 */
export function roomOnRecord(s: Speaker, config: Config | null): boolean {
  return s.zoom_link.trim() !== '' || (config?.instructions ?? '').trim() !== '';
}

/**
 * How to get into the room, written out: the per-event link and the
 * series-wide instructions, composed the way a message gives them.
 *
 * The rule is `journey/confirmation.py`'s, which is what a registrant
 * actually receives, and it is stated once here so the speaker's own
 * reminder cannot give a different answer from theirs:
 *
 * * the record's own link first, **unless the instructions already contain
 *   it** -- an operator who filled both had registrants reading the same URL
 *   twice under two labels;
 * * then the series instructions, which are where an access code lives.
 *
 * Empty when neither is set, which `roomOnRecord` is the predicate for. No
 * caller should reach a record in that state after `lockBlockers`, and a
 * template that did would render nothing rather than a broken sentence.
 */
export function roomText(s: Speaker, config: Config | null): string {
  const link = s.zoom_link.trim();
  const instructions = (config?.instructions ?? '').trim();
  const lines: string[] = [];
  if (link && !instructions.includes(link)) lines.push(link);
  if (instructions) lines.push(instructions);
  return lines.join('\n');
}

export function hasEnded(s: Speaker, config: Config, now: Date): boolean {
  if (s.status !== 'scheduled' || !s.date) return false;
  if (s.time) {
    // A falsy configured value (0, or unset) falls back to the default,
    // matching tools/convener_ops/maintenance/sweep.py's `or 90` — the two must agree since
    // one displays the transition and the other persists it.
    const duration = (config.seminar_duration_minutes || 90) * 60_000;
    return now.getTime() >= parisWallTimeToEpoch(s.date, s.time) + duration;
  }
  // Legacy rows carry no time: treat them as over the following day.
  return s.date < parisDayOf(now);
}

/**
 * What the user should see, which is not always what is recorded.
 * Persisting this transition is the scheduled job's business (tools/convener_ops/maintenance/sweep.py),
 * so that a single writer owns it and two open tabs cannot race.
 */
export function effectiveStatus(s: Speaker, config: Config, now: Date): SpeakerStatus {
  return hasEnded(s, config, now) ? 'delivered' : s.status;
}

const ONE_DAY_MS = 86_400_000;

/**
 * Whether a volunteer may record this talk as delivered by hand today.
 *
 * From the day before, and for the reason the day before is the answer: the
 * hosts are in the room, the recording has just stopped, and the wrap-up is
 * what they are about to do. Waiting for a scheduled job to notice means the
 * checklist they need is not there while they are still sitting together.
 *
 * **Why there is a hand on this at all.** The clock alone used to be the
 * whole answer, and `effectiveStatus` above is that answer: it reports
 * `delivered` for a talk whose hour has passed. But it is a *display*, and
 * the checklist reads the stored status -- so a record whose evening had gone
 * showed a header saying `Delivered` above the scheduled runbook, and no way
 * anywhere to make the two agree. A header that changes on its own and a page
 * that does not is worse than a header that waits.
 *
 * No arithmetic on days: the comparison is between two instants built from
 * ISO days, so there is no second calendar in this file to disagree with
 * `state/working-days.ts`.
 */
export function deliveryRecordable(s: Speaker, today: string): boolean {
  if (s.status !== 'scheduled' || !s.date) return false;
  const talk = Date.parse(`${s.date}T00:00:00Z`);
  const now = Date.parse(`${today}T00:00:00Z`);
  if (Number.isNaN(talk) || Number.isNaN(now)) return false;
  return now >= talk - ONE_DAY_MS;
}
