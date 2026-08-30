/**
 * How the programme is composed, over a sliding window (G-13).
 *
 * The series states a preference for early-career speakers and a target of a
 * balanced programme. This module is how the board checks whether it is
 * keeping to that. It is the most sensitive data in the repository -- it is
 * about identifiable researchers -- so the shape of what is computed here is
 * as much a privacy decision as a statistical one, and the choices are
 * written down rather than left to be inferred from the code.
 *
 * **Marginals only, never a cross-tabulation.** Every dimension is counted on
 * its own: how many applicants were postdocs, how many were women, how many
 * came from each country. The intersections are deliberately not offered.
 * With around thirty speakers, "female postdocs in Portugal" is one named
 * person, and a measure that can name someone has stopped being a measure. A
 * caller cannot assemble the cross-tab from what is returned here, because
 * the per-dimension tallies do not carry the identities that would let them
 * be joined. Adding a `by(dimension, dimension)` function would undo that in
 * one line; it is not an oversight that there isn't one.
 *
 * **Counts, never percentages.** `Tally` holds integers. There is no `percent`
 * field anywhere in the types this module exports, and no function that
 * returns one, because a percentage of a denominator this small reads as far
 * more precise than it is: one speaker in a window of eleven moves a
 * percentage by nine points. The only proportion this module will produce is
 * `share`, which returns a count and its denominator so the reader always sees
 * both -- and which refuses to produce even that below
 * `MIN_REPORTING_BASIS`: the misleading form is absent, not guarded.
 *
 * **Only what the speaker told us.** `gender` and `career_stage` are declared
 * values with `undisclosed` as a real, first-class answer. Nothing here
 * guesses at a value from a name, a photograph or a publication record, and
 * `undisclosed` is counted in `total` but excluded from `declared`, which is
 * the only denominator a share of a declared attribute may use. So a window
 * where nobody answered reads as "we do not know", never as a balanced
 * programme. That is the state of the data today: all thirty-one speakers
 * carry `undisclosed` for both.
 *
 * **Affiliation is not a dimension here**, obvious candidate though an
 * institution is. It is free text nobody normalises, so
 * "Univ. of X" and "University of X" are two buckets; and across this many
 * speakers nearly every bucket would hold exactly one person, which makes an
 * "institutional distribution" a re-listing of the speaker table under a
 * heading that says "measure". Country is kept: it is a coarse bucket, and
 * `speaker_country` is already published per row in the public feed, so
 * aggregating it discloses nothing new.
 *
 * Nothing computed here reaches `instance/public-data/`. The public feed is an
 * allowlist in `tools/convener_ops/publication/public_data.py`, `gender` and `career_stage`
 * are not on it, and they must not be: aggregate-only inside the app, a
 * per-speaker attribute becomes individually identifying the moment it is
 * published per row.
 */
import { CAREER_STAGES, GENDERS, isCareerStage, isGender } from '../data/types';
import type { CareerStage, Gender, Speaker, SpeakerStatus } from '../data/types';

/** The bucket for "not told us", shared by every dimension so that a caller
 *  reading `counts.undisclosed` gets the same answer whichever it is reading. */
export const UNDISCLOSED = 'undisclosed';

/**
 * The smallest denominator from which `share` will report a proportion.
 *
 * Below ten, the smallest step a proportion can take is more than ten points,
 * so any share drawn from it says more about the arithmetic than about the
 * programme. The board is not left with nothing in that case -- the counts are
 * still there, and a count of three out of seven is a perfectly honest thing
 * to read. What it is not given is a form that invites a comparison across
 * windows.
 */
export const MIN_REPORTING_BASIS = 10;

/**
 * One dimension counted over one population.
 *
 * `total` is every record in the window, `undisclosed` included: dropping the
 * people who did not answer would shrink the denominator and flatter the
 * result, which is precisely the bias the measure exists to expose. `declared`
 * is `total` minus `undisclosed`, and it is the denominator a share of a
 * declared attribute is taken against -- "two of the five who told us", not
 * "two of thirty".
 */
export interface Tally<K extends string = string> {
  counts: Record<K, number>;
  total: number;
  declared: number;
}

/** The three dimensions, counted independently. See the module note on why
 *  there is no fourth and no cross-tabulation. */
export interface Counts {
  total: number;
  career_stage: Tally<CareerStage>;
  gender: Tally<Gender>;
  country: Tally<string>;
}

/**
 * Applicants and those selected, over one window.
 *
 * `from`/`to` and `undated` are here so the screen can caption the measure
 * with what it actually rests on. `undated` is the number of speakers whose
 * `selection.opened_on` is missing or unreadable: they cannot be placed in
 * time, so they are counted in neither population, and saying so is the
 * difference between a window and a silent omission.
 */
export interface Distribution {
  from: string;
  to: string;
  undated: number;
  applicants: Counts;
  selected: Counts;
}

/**
 * A proportion, in the only two forms this module will produce.
 *
 * There is no arm carrying a percentage, and no arm that hides its
 * denominator. `too-few` is what a share of a basis under
 * `MIN_REPORTING_BASIS` *is* -- not a flag on an otherwise-usable number, so
 * a caller that ignores `kind` renders nothing rather than something
 * misleading.
 */
export type Share =
  | { kind: 'counted'; count: number; of: number }
  | { kind: 'too-few'; count: number; of: number };

/**
 * `count` as a share of the people who actually declared a value.
 *
 * Takes the `Tally` the count came from rather than a bare denominator, so a
 * caller cannot divide by `total` and quietly count the undisclosed as
 * evidence of balance.
 */
export function share(count: number, basis: Pick<Tally, 'declared'>): Share {
  const of = basis.declared;
  return {
    kind: of >= MIN_REPORTING_BASIS ? 'counted' : 'too-few',
    count,
    of,
  };
}

/**
 * Statuses a speaker the board *accepted* holds, whatever happened next.
 *
 * `decline-speaker` is in the list, and that is the point: it is reachable
 * only from `invited`, which is reachable only from `approved`
 * (`transitions.ts`), so a speaker who declined an invitation is one the
 * board selected. Leaving them out would score any group that declines more
 * often as one the board selects less often, which is the opposite of what
 * the measure is for.
 *
 * `parked`, `decline-board` and `lead` are out: a vote that expired, a lead
 * the board turned down, and a vote still open are all "not selected".
 * `vote-reopen` returns a speaker to `lead`, so a cancelled acceptance stops
 * counting as one -- correctly, since it was withdrawn.
 */
const SELECTED_STATUSES: readonly SpeakerStatus[] = [
  'approved',
  'invited',
  'confirmed',
  'scheduled',
  'delivered',
  'archived',
  'decline-speaker',
];

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Days in a Gregorian month, `month` being 1-12. */
function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/**
 * The ISO day `months` calendar months before `day`.
 *
 * Day-of-month is clamped to the length of the target month rather than
 * allowed to roll forward: 31 March less one month is 28 February, not 3
 * March. Rolling forward would shorten the window by a few days at exactly
 * the month ends, which is a difference nobody would ever notice and everyone
 * would inherit.
 *
 * A window of zero months or less collapses to `day` itself -- degenerate,
 * but it counts only what it can honestly place inside it.
 */
export function monthsBefore(day: string, months: number): string {
  const span = Number.isFinite(months) && months > 0 ? Math.trunc(months) : 0;
  const [year, month, date] = day.split('-').map(Number);
  const zeroBased = year * 12 + (month - 1) - span;
  const targetYear = Math.floor(zeroBased / 12);
  const targetMonth = (zeroBased % 12) + 1;
  const clamped = Math.min(date, daysInMonth(targetYear, targetMonth));
  return [
    String(targetYear).padStart(4, '0'),
    String(targetMonth).padStart(2, '0'),
    String(clamped).padStart(2, '0'),
  ].join('-');
}

function stageOf(s: Speaker): CareerStage {
  // `data/validate.ts` has checked this field against the model before the
  // browser saw it, so an unrecognised value no longer reaches here from
  // `instance/data/speakers.yml`. This is kept anyway: it is a
  // total function on its argument, so a caller building a `Speaker` some
  // other way still gets a bucket rather than a new category, and an
  // unrecognised value reads as `undisclosed` -- a typo must not become a
  // career stage the board then reads as a finding.
  return isCareerStage(s.career_stage) ? s.career_stage : UNDISCLOSED;
}

function genderOf(s: Speaker): Gender {
  return isGender(s.gender) ? s.gender : UNDISCLOSED;
}

function countryOf(s: Speaker): string {
  // Free text, so it is trimmed but not otherwise touched; an empty country
  // is an undeclared one and joins the same bucket as an undeclared gender.
  const country = (s.country ?? '').trim();
  return country === '' ? UNDISCLOSED : country;
}

function tallyOf<K extends string>(values: K[], vocabulary?: readonly K[]): Tally<K> {
  const counts = {} as Record<K, number>;
  for (const key of vocabulary ?? []) counts[key] = 0;
  for (const value of values) counts[value] = (counts[value] ?? 0) + 1;
  const undisclosed = counts[UNDISCLOSED as K] ?? 0;
  return { counts, total: values.length, declared: values.length - undisclosed };
}

function countsOf(rows: Speaker[]): Counts {
  return {
    total: rows.length,
    // The fixed vocabularies are passed in so that every bucket exists at
    // zero. A stage nobody in the window holds must show as `0`, not be
    // missing: an absent bucket reads as "not measured", a zero reads as
    // "measured, and nobody" -- which for early-career representation is the
    // whole finding.
    career_stage: tallyOf(rows.map(stageOf), CAREER_STAGES),
    gender: tallyOf(rows.map(genderOf), GENDERS),
    country: tallyOf(rows.map(countryOf)),
  };
}

/**
 * Who applied and who was selected, over the `window` months ending on `on`.
 *
 * Both populations are drawn from the same window and the same date --
 * `selection.opened_on`, the day the lead entered the pipeline -- so the
 * selected are always a subset of the applicants and the two can be read side
 * by side. Dating the selected by their decision instead would let a speaker
 * appear as selected in a window they never applied in, and the ratio of two
 * populations measured over different sets is not a selection rate.
 *
 * Window bounds are inclusive at both ends. `on` is an ISO day from
 * `parisToday()`; nothing here reads a clock.
 */
export function distribution(speakers: Speaker[], window: number, on: string): Distribution {
  const from = monthsBefore(on, window);
  const inWindow: Speaker[] = [];
  let undated = 0;
  for (const s of speakers) {
    const opened = s.selection?.opened_on ?? '';
    if (!ISO_DAY.test(opened)) {
      undated += 1;
      continue;
    }
    if (opened >= from && opened <= on) inWindow.push(s);
  }
  return {
    from,
    to: on,
    undated,
    applicants: countsOf(inWindow),
    selected: countsOf(inWindow.filter(s => SELECTED_STATUSES.includes(s.status))),
  };
}

/** A share that is reportable. Its existence is the only licence a screen has
 *  to print a proportion at all; there is no other way to obtain one. */
export type CountedShare = Extract<Share, { kind: 'counted' }>;

/** One bucket a screen may draw, with the share already proved reportable. */
export interface ReportRow<K extends string> {
  key: K;
  count: number;
  share: CountedShare;
}

/**
 * What a screen is allowed to draw for one dimension.
 *
 * This exists because the guard belongs here rather than in JSX. A component
 * handed a `Tally` has to decide for itself whether the basis holds, and the
 * two ways it can get that wrong -- drawing a `too-few` share as a zero, and
 * dividing `count` by `of` to get a percentage -- are both one line away. So
 * the decision is taken here and the *result* is what crosses the boundary:
 * below the basis there are **no rows at all**, so there is nothing for a
 * screen to render as a zero or an empty bar. The misleading state is absent,
 * not guarded.
 *
 * `too-few` carries `declared` and `total` so the screen can say what is
 * missing -- "none of the twenty-four told us" -- which is a sentence, not a
 * number on a scale. `empty` is a population nobody is in: measuring it would
 * be a category error, not a small sample.
 */
export type DimensionReport<K extends string> =
  | { kind: 'empty' }
  | { kind: 'too-few'; declared: number; total: number }
  | { kind: 'reportable'; total: number; undisclosed: number; rows: ReportRow<K>[] };

/**
 * Turn one `Tally` into the shapes a screen may draw.
 *
 * The threshold is not restated here: every row's share comes from `share`,
 * and one row failing means all of them do, since they share a denominator.
 * `undisclosed` never becomes a row -- its count is not a share of `declared`,
 * which excludes it, so "twenty of four" is unrepresentable rather than
 * merely unlikely. It is returned as a plain count instead, because the
 * number of people who did not answer is the most important thing on the
 * screen and hiding it would flatter the measure.
 */
export function reportOn<K extends string>(tally: Tally<K>): DimensionReport<K> {
  if (tally.total === 0) return { kind: 'empty' };
  // Asked once, of `share` itself, rather than restated here: every bucket in
  // a tally is divided by the same `declared`, so whether one share is
  // reportable is whether all of them are. Asking per bucket instead would
  // report a dimension whose only bucket is `undisclosed` -- country, today --
  // as an empty table rather than as a basis too thin to read.
  const basis = share(tally.declared, tally);
  if (basis.kind !== 'counted') {
    return { kind: 'too-few', declared: tally.declared, total: tally.total };
  }
  const rows: ReportRow<K>[] = [];
  for (const key of Object.keys(tally.counts) as K[]) {
    if (key === UNDISCLOSED) continue;
    const count = tally.counts[key];
    const s = share(count, tally);
    // Narrowing, not a second guard: `basis` above already proved this
    // denominator reportable, and every bucket shares it.
    if (s.kind === 'counted') rows.push({ key, count, share: s });
  }
  return {
    kind: 'reportable',
    total: tally.total,
    undisclosed: tally.counts[UNDISCLOSED as K] ?? 0,
    rows,
  };
}
