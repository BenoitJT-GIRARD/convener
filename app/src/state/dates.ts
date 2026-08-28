/**
 * The negotiation of a webinar date, from the slots put to the speaker to the
 * one that is finally locked.
 *
 * The invitation has always offered several dates and the speaker has always
 * replied with the ones that suit them; only the conclusion was ever written
 * down, because the model held a single `date`. `Speaker.candidate_dates`
 * holds the offer and the replies, and this module is the behaviour around
 * it.
 *
 * What is being protected here is not bookkeeping. Locking a date commits an
 * unpaid outside researcher to a specific evening, in their own time zone,
 * around their own teaching and family. Doing that on a date they never
 * accepted is the failure this module is built against, so the wrong call is
 * made **unwritable** rather than checked: `lockDate` does not take a date,
 * it takes an `AcceptedDate`, and the only way to hold one is to have read it
 * out of the record with `acceptedDates`. A string a volunteer typed into a
 * box has no route to that type, and the compiler says so at the call site --
 * the same shape the `Identifier` brand takes in `state/decisions.ts`.
 *
 * **A slot is identified by its day.** Not by the pair (day, hour): the
 * question put to the speaker is "would the 12th suit you?", the reply is
 * recorded against the day, `AcceptedDate` is a day, and the hour of the
 * evening finally locked is read off the slot that day names. `proposeDates`
 * refuses to offer one day twice for that reason, and both file readers --
 * `data/validate.ts` here and `tools/convener_ops/validate.py` there -- now refuse
 * a record that holds two hours on one day, so a file edited by hand cannot
 * present this module with two answers to one question.
 * `candidate_date_cases` in `tools/tests/fixtures/governance-cases.json` is
 * the pair's shared statement of that.
 *
 * Pure throughout: no clock, no state, no side effects. Today's date and the
 * rest of the agenda are parameters, so every function here can run inside a
 * `mutate` transformation replayed against a freshly-read value.
 */
import type { CandidateDate, DateAnswer, Speaker } from '../data/types';
import { findOverlaps } from './agenda';

declare const acceptedBrand: unique symbol;

/**
 * A date this speaker's record says the speaker accepted.
 *
 * The brand is what makes the wrong lock-in unconstructible rather than
 * merely detected: `lockDate` has no `string` slot for a date, so no typed
 * value, form field or URL parameter can reach it without passing through
 * `acceptedDates` below -- which reads the stored answers and hands back
 * nothing else.
 */
export type AcceptedDate = string & { readonly [acceptedBrand]: true };

/** A date that cannot be offered, answered or locked as asked. The message is
 *  a plain sentence saying what to do instead -- it reaches a volunteer's
 *  screen as-is, relayed by `github/errors.ts`. */
export class DateRejected extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DateRejected';
  }
}

/** One slot as it goes out in the invitation: a day and a start time, with no
 *  answer yet because nobody has been asked. */
export interface ProposedSlot {
  date: string;
  time: string;
}

/** What `answerDate` gives back: the updated record, and -- only when the
 *  answer recorded was `accepted` -- that date as an `AcceptedDate`, so the
 *  caller that has just recorded an acceptance can lock it in the same
 *  transformation without going looking for it again. */
export interface AnsweredDate {
  speaker: Speaker;
  accepted: AcceptedDate | null;
}

/** The single point in the codebase where the brand is applied. Private on
 *  purpose: everything that produces an `AcceptedDate` goes through
 *  `acceptedDates`, which only ever calls it on an entry whose stored answer
 *  is `accepted`. */
function brand(date: string): AcceptedDate {
  return date as AcceptedDate;
}

/**
 * The dates this record says the speaker accepted, in the order they were
 * offered.
 *
 * A reader, not a constructor: it cannot invent an acceptance, it can only
 * report one that `answerDate` (or the speaker's reply as recorded in
 * `instance/data/speakers.yml`) already wrote down. Everything that needs an
 * `AcceptedDate` gets it from here, so "did the speaker agree to this
 * evening?" is answered by the record and never by the caller.
 */
export function acceptedDates(speaker: Speaker): AcceptedDate[] {
  return speaker.candidate_dates.filter(c => c.answer === 'accepted').map(c => brand(c.date));
}

/**
 * Put a set of slots to the speaker.
 *
 * The clash check lives here rather than at the lock-in. Two events a few
 * days apart split the same small audience, and a volunteer who discovers
 * that at the lock-in has already sent the speaker a date to hold: the person
 * to disappoint has already been chosen. Checking at proposal time means a
 * clashing date is never offered in the first place, so `findOverlaps` runs
 * once per candidate here and the answer is a sentence naming the event in
 * the way.
 *
 * `today` is a parameter (`parisToday()` at the call site) rather than a
 * clock read: a slot in the past is not an offer, and a pure function is one
 * that can be replayed inside `mutate`.
 *
 * Re-proposing a date already in the list keeps the answer already recorded
 * against it -- re-sending an invitation must not quietly erase a refusal --
 * while a date dropped from the list leaves with its answer, because it is no
 * longer on offer.
 */
export function proposeDates(
  current: Speaker,
  slots: ProposedSlot[],
  agenda: Speaker[],
  windowDays: number,
  today: string,
): Speaker {
  if (slots.length === 0) {
    throw new DateRejected(
      'An invitation has to offer at least one date. Add a slot before sending it.',
    );
  }

  const seen = new Set<string>();
  const candidate_dates: CandidateDate[] = [];

  for (const slot of slots) {
    if (!slot.date) {
      throw new DateRejected('One of the slots has no date. Fill it in or remove the row.');
    }
    if (!slot.time) {
      throw new DateRejected(
        `${slot.date} has no start time. The speaker is being asked to hold an evening, so ` +
          'the offer has to say which hours.',
      );
    }
    if (seen.has(slot.date)) {
      throw new DateRejected(
        `${slot.date} is offered twice. Offer each date once, so the speaker's reply cannot ` +
          'be ambiguous.',
      );
    }
    seen.add(slot.date);

    if (slot.date < today) {
      throw new DateRejected(
        `${slot.date} has already passed. Offer dates from ${today} onwards.`,
      );
    }

    const hits = findOverlaps(slot.date, agenda, windowDays, current.id);
    if (hits.length > 0) {
      const hit = hits[0];
      const other = hit.speaker.edition_code || hit.speaker.id;
      throw new DateRejected(
        `${slot.date} clashes with ${other}, which is on ${hit.speaker.date}, ` +
          `${hit.daysApart} day(s) away. The series keeps ${windowDays} days between events, ` +
          'so offer a date further from that one.',
      );
    }

    const known = current.candidate_dates.find(c => c.date === slot.date);
    candidate_dates.push({
      date: slot.date,
      time: slot.time,
      answer: known ? known.answer : '',
    });
  }

  return { ...current, candidate_dates };
}

/**
 * Record the speaker's reply about one slot.
 *
 * Only a slot that was actually offered can be answered: an answer about a
 * date nobody proposed is a note about a conversation that did not happen,
 * and it would be the one way an acceptance could appear in the record
 * without anyone having asked.
 *
 * There is no third answer to record. `DATE_ANSWERS` holds `accepted`,
 * `declined` and the empty string and nothing else, so "probably fine" is not
 * expressible -- see the note on the type. An answer may be changed (a
 * speaker's term dates move) and the new one replaces the old in place, which
 * keeps `instance/data/speakers.yml` readable as a diff.
 */
export function answerDate(current: Speaker, date: string, answer: DateAnswer): AnsweredDate {
  const known = current.candidate_dates.find(c => c.date === date);
  if (!known) {
    throw new DateRejected(
      `${date} was never put to this speaker, so there is no reply to record against it. ` +
        'Offer the date first, then record what they said.',
    );
  }

  const speaker: Speaker = {
    ...current,
    candidate_dates: current.candidate_dates.map(c => (c.date === date ? { ...c, answer } : c)),
  };

  return { speaker, accepted: acceptedDates(speaker).find(d => d === date) ?? null };
}

/**
 * Freeze the negotiated slot: the record moves to `scheduled` and
 * `Speaker.date` / `Speaker.time` finally hold one evening.
 *
 * `accepted` is an `AcceptedDate`, so a date the speaker never accepted
 * cannot be passed here at all -- that is the guarantee, and it is the
 * compiler's, not a test's. The check below is a backstop for the one case
 * the type cannot see: a brand read before a concurrent write and used after
 * it, where the record no longer says what it said. `mutate` replays this
 * transformation against freshly-read data, so the answer is re-read from
 * `current` rather than trusted from the value in hand.
 *
 * The time is taken from the slot the speaker accepted, never from a separate
 * field: a lock-in that could name an hour other than the one offered is a
 * contradiction the caller should not be able to write.
 */
export function lockDate(current: Speaker, accepted: AcceptedDate, editionCode: string): Speaker {
  const slot = current.candidate_dates.find(c => c.date === accepted && c.answer === 'accepted');
  if (!slot) {
    throw new DateRejected(
      `${accepted} is not a date this speaker has accepted. Record their reply first -- ` +
        'locking a date commits them to that evening.',
    );
  }
  if (!editionCode) {
    throw new DateRejected(
      'The edition number is missing. Use "suggest" to take the next one in the series.',
    );
  }

  return {
    ...current,
    status: 'scheduled',
    date: slot.date,
    time: slot.time,
    edition_code: editionCode,
  };
}
