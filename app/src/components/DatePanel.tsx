import { useState } from 'react';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { editionCodePrefix, nextEditionCode, raisedEditionCounter } from '../state/agenda';
import { DateRejected, answerDate, lockBlockers, proposeDates } from '../state/dates';
import { parisToday } from '../state/derived';
import {
  dataEdit,
  formatDecision,
  identifier,
  transitionDecision,
} from '../state/decisions';
import {
  applyTransition,
  canTransition,
  type LockDatePayload,
  type Role,
} from '../state/transitions';
import type { Speaker } from '../data/types';

/**
 * The date negotiation, on screen: the evenings put to the speaker, the reply
 * to each, and -- once one is agreed -- the control that freezes it.
 *
 * **What the three modes are, and why the panel has modes at all.** The same
 * list of dates means three different things at three points of the journey,
 * and each point offers exactly the controls that make sense there:
 *
 * - `offer`, on an approved record. Nobody has been asked yet, so there is
 *   nothing to reply to: the list is what the invitation is going to say, and
 *   the only control adds another evening to it. This panel did not exist
 *   here at all, which is the defect: a volunteer had to mark the invitation
 *   sent before the app would let them choose the dates the invitation names.
 * - `reply`, on an invited record. Each evening is now a control: clicking it
 *   is both "they said yes" and "this is the evening", one gesture where
 *   there used to be two. A quieter control beside it records an evening they
 *   cannot make -- kept, because the ordinary case is a speaker who can make
 *   none of the three and proposes a fourth, and offering the fourth is only
 *   sensible next to a record of the three refusals.
 * - `lock`, on a confirmed record. The edition number is typed here and
 *   nowhere else, and the accepted evening is frozen.
 *
 * There is no field to type a date into and lock. The lock-in takes a date
 * out of this list or it does not happen, because `state/dates.ts` hands out
 * an `AcceptedDate` for nothing else; the volunteer is never in a position to
 * commit an outside researcher to an evening the record does not show them
 * agreeing to.
 *
 * The clash check runs on the offer, before the button is enabled, and its
 * sentence is the one `proposeDates` would throw with -- asked of the rule
 * rather than written a second time here.
 */
export type DateMode = 'offer' | 'reply' | 'lock';

interface Props {
  speaker: Speaker;
  role: Role;
  mode: DateMode;
}

export function DatePanel({ speaker, role, mode }: Props) {
  const { speakers, config, mutateSpeakers, mutateConfig } = useData();
  const { login } = useAuth();
  const [date, setDate] = useState('');
  const [time, setTime] = useState('12:30');
  const [edition, setEdition] = useState('');
  // Whether what is in the box came from `Suggest the next code` and has not
  // been typed over since. A suggestion is a *reading* of the agenda and goes
  // stale the moment anybody else locks a date; a code somebody typed is a
  // decision, and is written exactly as given. See `fire`.
  const [suggested, setSuggested] = useState(false);
  // The room for *this* edition, which starts as whatever the record already
  // carries -- empty, on an instance whose series instructions hold the
  // address for every session. It is written with the lock-in rather than on
  // its own, because it is what satisfies that write's own precondition.
  const [room, setRoom] = useState(speaker.zoom_link);
  const [busy, setBusy] = useState(false);
  const today = parisToday();
  const locked = busy || !login || !config;

  const slots = speaker.candidate_dates.map(c => ({ date: c.date, time: c.time }));
  // The joining instructions the whole series uses, when this instance has
  // any. One value for every session, never per event -- D-06 makes the
  // account itself the permanent room, and `journey/platform.py` spends a
  // paragraph on why putting it on a record would invite writing different
  // instructions for a room that is the same room every time.
  const seriesRoom = (config?.instructions ?? '').trim();

  // Asked of the rule, not restated: `proposeDates` is pure, so the offer
  // about to be made is tried here on the values on screen and its refusal
  // becomes the disabled reason. A volunteer reads why the date will not do
  // before clicking, never after a failed save.
  let blocker: string | null = null;
  if (config && date) {
    try {
      proposeDates(speaker, [...slots, { date, time }], speakers, config.overlap_window_days, today);
    } catch (e) {
      if (!(e instanceof DateRejected)) throw e;
      blocker = e.message;
    }
  }

  async function offer() {
    if (locked || !config || !login || !date || blocker) return;
    setBusy(true);
    try {
      // Everything the transformation writes is read from `current`: the
      // slots already offered come from the record as freshly read, not from
      // the copy this component rendered, so a date offered from another
      // browser in the meantime survives instead of being overwritten. Only
      // the one new slot comes from the form -- it is what the volunteer has
      // just typed and exists nowhere else.
      await mutateSpeakers(
        current =>
          current.map(sp =>
            sp.id === speaker.id
              ? proposeDates(
                  sp,
                  [...sp.candidate_dates.map(c => ({ date: c.date, time: c.time })), { date, time }],
                  current,
                  config.overlap_window_days,
                  today,
                )
              : sp,
          ),
        // The act, not the day. Which evenings a researcher was offered is
        // their availability rather than the programme, and the diff already
        // carries it -- the same division `lock-date` and `availability-set`
        // make.
        formatDecision({
          kind: 'date-propose',
          entity: identifier(speaker.id),
          actor: identifier(login),
        }),
      );
      setDate('');
    } finally {
      setBusy(false);
    }
  }

  /** One transition, applied against freshly-read data. The accepted evening
   *  and the lock-in both come through here, so neither can be recorded from
   *  a copy of the record this component rendered with. */
  async function fire(transition: 'invited-accept' | 'lock-date', payload: LockDatePayload) {
    if (locked || !config || !login || !canTransition(speaker, transition, role)) return;
    setBusy(true);
    try {
      // What the winning attempt actually assigned. `mutateSpeakers` replays
      // its transformation against freshly-read data and hands back only
      // whether it wrote, so the code is captured here as the transform runs.
      // A replay overwrites it, which is the point: the attempt that lands is
      // the last one to run, so this holds what the commit contains.
      let assigned = payload.edition_code;

      const wrote = await mutateSpeakers(
        current => {
          // **Decided here, not on screen.** `Suggest the next code` reads
          // the agenda as it was when the button was pressed, and a
          // suggestion is stale the moment anybody else locks a date --
          // `nextEditionCode` skips codes already in use, but only among the
          // records it is shown. Two volunteers locking at the same moment
          // were both handed the same next code, and both wrote it: a
          // duplicate `edition_code` that nothing refuses until
          // `validate-data.yml` fails on the commit that is already pushed.
          // Recomputing inside the transformation puts that reading on the
          // same freshly-read list the write lands on.
          //
          // A code the volunteer typed is never recomputed. Typing one is a
          // decision -- renumbering a series, matching a poster already
          // printed -- and second-guessing it here would silently write
          // something other than what the screen said.
          assigned = suggested
            ? nextEditionCode(current, config.next_edition_number)
            : payload.edition_code;
          return current.map(sp =>
            sp.id === speaker.id
              ? applyTransition(sp, transition, login, config, today, {
                  ...payload,
                  edition_code: assigned,
                })
              : sp,
          );
        },
        formatDecision(
          transitionDecision(transition, identifier(speaker.id), identifier(login), payload),
        ),
      );

      // The record is the act; the counter is the bookkeeping, and it follows
      // rather than leads. If this second write fails the mark lags -- loud in
      // `sh gates.sh`, and harmless while the record stands, because
      // `nextEditionCode` skips codes already in use. Raising it first and
      // failing on the record would leave a number burnt with no record
      // carrying it, and this pair is two files with no transaction between
      // them, so one of the two orders has to be chosen and defended.
      //
      // Raised from `assigned`, never from `payload.edition_code`: after a
      // replay those differ, and the mark has to pass the code that was
      // written rather than the one the screen offered.
      if (wrote && transition === 'lock-date' && assigned) {
        await raiseEditionCounter(assigned);
      }
    } finally {
      setBusy(false);
    }
  }

  /** Raise `next_edition_number` past the code just assigned.
   *
   *  Nothing did this: the counter appeared in three files of the cockpit and
   *  two of the tooling, and every one of them read it. So it stayed at 1
   *  while editions were assigned, and the first instance to schedule an
   *  edition met a red gate over a value no screen exposes.
   *
   *  A separate write from the record's, because they are separate files and
   *  this application has no two-file transaction. The transform is a
   *  maximum, so a replay against fresher data -- somebody else locking in at
   *  the same moment -- cannot lower it.
   */
  async function raiseEditionCounter(editionCode: string) {
    await mutateConfig(
      current => ({
        ...current,
        next_edition_number: raisedEditionCounter(current.next_edition_number, editionCode),
      }),
      dataEdit(identifier(speaker.id), { part: 'edition-counter' }),
    );
  }

  /** An evening the speaker cannot make. Not a transition: the record stays
   *  where it is, and what changes is one answer in the offer. The day is not
   *  in the subject -- `candidate_dates` is `NEVER_PUBLISHED`
   *  (`state/consent.ts`), and a commit subject is the one place in this
   *  repository nothing can be taken back from. */
  async function declineDate(slotDate: string) {
    if (locked || !login) return;
    setBusy(true);
    try {
      await mutateSpeakers(
        current =>
          current.map(sp =>
            sp.id === speaker.id ? answerDate(sp, slotDate, 'declined').speaker : sp,
          ),
        formatDecision({
          kind: 'date-answer',
          entity: identifier(speaker.id),
          actor: identifier(login),
          detail: 'declined',
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  // Read against the values on screen, so the star clears as the volunteer
  // fills the box rather than after a refused save. `zoom_link` is the one
  // this panel now owns; `config` carries the series instructions, which
  // satisfy the same requirement on an instance that has them.
  const missing = lockBlockers({ ...speaker, zoom_link: room }, edition, config);
  const canOffer = mode !== 'lock';

  return (
    <div className="space-y-2 w-full">
      <p className="text-xs font-mono uppercase text-ink-muted">Dates offered</p>
      {speaker.candidate_dates.length === 0 && (
        <p className="text-xs text-ink-muted italic">
          No dates offered yet. Offer the ones the invitation proposes; the draft below fills
          itself in as you add them.
        </p>
      )}
      <ul className="space-y-1">
        {speaker.candidate_dates.map(c => (
          <li key={c.date} className="flex gap-2 items-center flex-wrap text-sm">
            <span className="font-mono">
              {c.date} {c.time}
            </span>
            <span
              className={
                c.answer === 'accepted'
                  ? 'text-xs text-field-text'
                  : c.answer === 'declined'
                    ? 'text-xs text-danger'
                    : 'text-xs text-ink-muted italic'
              }
            >
              {c.answer === 'accepted'
                ? 'accepted by the speaker'
                : c.answer === 'declined'
                  ? 'declined by the speaker'
                  : mode === 'offer'
                    ? 'in the invitation'
                    : 'no reply yet'}
            </span>
            {mode === 'reply' && c.answer !== 'accepted' && (
              <button
                type="button"
                disabled={locked}
                onClick={() =>
                  fire('invited-accept', { date: c.date, edition_code: '', zoom_link: '' })
                }
                className="px-3 py-1 text-xs font-display font-bold tracking-widest uppercase bg-dominant text-white border-2 border-dominant hover:bg-dominant-hover disabled:opacity-50"
              >
                They can make this one &rarr;
              </button>
            )}
            {mode === 'reply' && c.answer !== 'declined' && (
              <button
                type="button"
                disabled={locked}
                onClick={() => declineDate(c.date)}
                className="text-xs text-danger underline disabled:opacity-50"
              >
                not this one
              </button>
            )}
            {mode === 'lock' && c.answer === 'accepted' && (
              <button
                type="button"
                disabled={locked || missing.length > 0}
                onClick={() =>
                  fire('lock-date', { date: c.date, edition_code: edition, zoom_link: room })
                }
                className="px-3 py-1 text-xs font-display font-bold tracking-widest uppercase bg-dominant text-white border-2 border-dominant hover:bg-dominant-hover disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Lock this date &rarr;
              </button>
            )}
          </li>
        ))}
      </ul>

      {canOffer && (
        <div className="flex gap-2 items-center flex-wrap">
          <label className="flex items-center gap-1.5">
            <span className="text-xs font-mono uppercase text-ink-muted">Offer date</span>
            <input
              type="date"
              value={date}
              onChange={e => setDate(e.target.value)}
              className="px-2 py-1 text-sm"
            />
          </label>
          <label className="flex items-center gap-1.5">
            <span className="text-xs font-mono uppercase text-ink-muted">Time (Paris)</span>
            <input
              type="time"
              value={time}
              onChange={e => setTime(e.target.value)}
              className="px-2 py-1 text-sm font-mono w-24"
            />
          </label>
          <button
            type="button"
            disabled={locked || !date || !time || !!blocker}
            onClick={offer}
            className="px-3 py-1.5 text-sm rounded border border-border text-ink-muted hover:text-ink disabled:opacity-50"
          >
            Offer this date
          </button>
        </div>
      )}

      {mode === 'lock' && (
        <div className="flex gap-2 items-center flex-wrap">
          <label className="flex items-center gap-1.5">
            <span className="text-xs font-mono uppercase text-ink-muted">
              Edition
              {/* The one star this screen owns: the title and the abstract
                  are lines of the checklist and are marked there, while the
                  edition number is typed here and nowhere else. It is also
                  the one the maintainer hunted for. */}
              {!edition && <span className="text-danger ml-1">*</span>}
            </span>
            <input
              type="text"
              placeholder={`${editionCodePrefix()}N`}
              value={edition}
              onChange={e => {
                setEdition(e.target.value);
                setSuggested(false);
              }}
              className="px-2 py-1 text-sm font-mono w-20"
            />
          </label>
          <button
            type="button"
            onClick={() => {
              if (!config) return;
              setEdition(nextEditionCode(speakers, config.next_edition_number));
              setSuggested(true);
            }}
            className="text-xs text-field-text underline"
          >
            Suggest the next code
          </button>
        </div>
      )}

      {mode === 'lock' && (
        <div className="flex flex-col gap-1">
          <label className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-mono uppercase text-ink-muted">
              Room
              {/* Starred only when nothing else answers for it. On an
                  instance whose series instructions carry the address, this
                  box is an override and leaving it empty is the ordinary
                  case -- so a star here would mark a field nobody needs to
                  fill. */}
              {!seriesRoom && !room && <span className="text-danger ml-1">*</span>}
            </span>
            <input
              type="text"
              placeholder={seriesRoom ? 'only if this edition uses a different room' : 'https://…'}
              value={room}
              onChange={e => setRoom(e.target.value)}
              className="px-2 py-1 text-sm font-mono flex-1 min-w-48"
            />
          </label>
          {/* What the registrants will be told when the box is left empty.
              Shown rather than assumed: the address lives in
              `instance/data/config.yml` and no screen exposed it, so a
              volunteer locking a date could not see what the person signing
              up an hour later would receive. */}
          {seriesRoom && !room && (
            <p className="text-xs text-ink-muted">
              Registrants are sent the series room:{' '}
              <span className="font-mono whitespace-pre-line">{seriesRoom}</span>
            </p>
          )}
        </div>
      )}

      {blocker && <p className="text-danger text-xs">{blocker}</p>}
      {mode === 'lock' && missing.length > 0 && (
        <p className="text-xs text-danger italic">
          <span aria-hidden="true">*</span> {missing.join(', ')} — still to fill in before this
          date can be locked.
        </p>
      )}
    </div>
  );
}
