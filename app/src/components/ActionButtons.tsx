import { useState } from 'react';
import {
  canTransition,
  applyTransition,
  type Transition,
  type Role,
  type LockDatePayload,
  type OverridePayload,
  type BallotPayload,
} from '../state/transitions';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { editionCodePrefix, nextEditionCode } from '../state/agenda';
import { DateRejected, answerDate, proposeDates } from '../state/dates';
import { activeBoard } from '../state/board';
import { decide, type Outcome } from '../state/governance';
import { parisToday } from '../state/derived';
import { formatDecision, identifier, transitionDecision } from '../state/decisions';
import type { BallotValue, DateAnswer, Speaker } from '../data/types';

interface Props {
  speaker: Speaker;
  role: Role;
}

export function ActionButtons({ speaker, role }: Props) {
  const { config, mutateSpeakers } = useData();
  const { login } = useAuth();
  const [busy, setBusy] = useState(false);
  // Nothing can be written before config.yml has arrived: every transition
  // reads the board from it, and `fire` would otherwise no-op in silence.
  const locked = busy || !config;

  const today = parisToday();
  // The threshold is never stored: it follows from who is eligible today, so
  // it is recomputed on every render from the board and the ballots cast.
  const board = config ? activeBoard(config, today) : { logins: [], unavailable: [] };
  const outcome = decide({
    board: board.logins,
    unavailable: board.unavailable,
    ballots: speaker.selection.ballots,
  });

  async function fire(t: Transition, payload?: LockDatePayload | OverridePayload | BallotPayload) {
    if (!login || !config || !canTransition(speaker, t, role)) return;
    setBusy(true);
    try {
      // `config` is read from the same load cycle rather than re-read inside the
      // transform: mutate() operates on one path, and the board lives in config.yml
      // while ballots live in speakers.yml. Board composition changes a handful of
      // times a year and a vote runs over two weeks, so a change landing between the
      // read and the write is negligible - and its consequence, a threshold off by
      // one on a single vote, is visible in the decision register and recoverable.
      // What is NOT acceptable is capturing the computed threshold: the decision is
      // recomputed here, from `current`.
      await mutateSpeakers(
        current =>
          current.map(sp =>
            sp.id === speaker.id ? applyTransition(sp, t, login, config, today, payload) : sp,
          ),
        // Not a string: `formatDecision` takes the transition and the very
        // payload it is applied with, so the line cannot disagree with what
        // was written -- see `state/decisions.ts`.
        formatDecision(transitionDecision(t, identifier(speaker.id), identifier(login), payload)),
      );
    } finally {
      setBusy(false);
    }
  }

  const btnCls = (variant: 'primary' | 'danger' | 'ghost') =>
    variant === 'danger'
      ? 'px-3 py-1.5 text-sm rounded border border-danger text-danger hover:bg-danger hover:text-white disabled:opacity-50'
      : variant === 'ghost'
        ? 'px-3 py-1.5 text-sm rounded border border-border text-ink-muted hover:text-ink disabled:opacity-50'
        : 'px-3 py-1.5 text-sm rounded bg-primary text-white hover:opacity-90 disabled:opacity-50';

  function btn(
    label: string,
    t: Transition,
    variant: 'primary' | 'danger' | 'ghost' = 'primary',
  ) {
    if (!canTransition(speaker, t, role)) return null;
    return (
      <button key={label} disabled={locked} onClick={() => fire(t)} className={btnCls(variant)}>
        {label}
      </button>
    );
  }

  const buttons: React.ReactNode[] = [];
  switch (speaker.status) {
    case 'lead':
      if (role === 'board') {
        buttons.push(
          <BallotForm
            key="ballot"
            speaker={speaker}
            login={login}
            outcome={outcome}
            disabled={locked}
            onCast={(value, comment, coiReason) =>
              fire('ballot-cast', { value, comment, coiReason })
            }
            onWithdraw={() => fire('ballot-withdraw')}
          />,
        );
        buttons.push(btn('Park', 'lead-park', 'ghost'));
        buttons.push(btn('Decline', 'lead-decline', 'danger'));
      } else {
        buttons.push(
          <span className="text-sm text-ink-muted" key="msg">
            {outcome.suspended
              ? `Board vote on hold: only ${outcome.eligible} member(s) are eligible to vote today.`
              : `Awaiting board vote (${outcome.yes} / ${outcome.threshold}).`}
          </span>,
        );
      }
      break;
    case 'approved': {
      const hostsSet = !!speaker.host_1 && !!speaker.host_2;
      if (!hostsSet) {
        buttons.push(
          <span className="text-sm text-ink-muted" key="msg">
            Assign Host 1 and Host 2 in the form below before sending the invitation.
          </span>,
        );
      } else {
        buttons.push(btn('Mark invitation sent →', 'send-invitation'));
      }
      break;
    }
    case 'invited':
      buttons.push(btn('Speaker accepted', 'invited-accept'));
      buttons.push(btn('Speaker declined', 'invited-decline', 'danger'));
      // The dates are negotiated while the invitation is out: that is when
      // the speaker replies with the evenings that suit them. Recording the
      // replies here is what gives the lock-in something to choose among.
      buttons.push(
        <CandidateDates
          key="dates"
          speaker={speaker}
          disabled={locked}
          canLock={false}
          onLock={NO_LOCK}
        />,
      );
      break;
    case 'confirmed':
      buttons.push(
        <CandidateDates
          key="dates"
          speaker={speaker}
          disabled={locked}
          canLock
          onLock={(d, e) => fire('lock-date', { date: d, edition_code: e })}
        />,
      );
      break;
    case 'parked':
    case 'decline-board':
      if (role === 'board') buttons.push(btn('Reactivate', 'reactivate'));
      break;
    default:
      break;
  }
  return <div className="flex flex-wrap gap-2 items-center">{buttons}</div>;
}

/** The three ballots the handbook recognises. `abstain` and `recused` are not
 *  decoration: an abstention stays in the denominator (the bar to clear does
 *  not move), while a recusal leaves it (the bar drops, and may suspend the
 *  vote entirely). A board member who can only click "yes" cannot express a
 *  conflict of interest, so all three get a control here. */
const BALLOT_CHOICES: { value: BallotValue; label: string; help: string }[] = [
  { value: 'yes', label: 'Yes', help: 'Approve this speaker.' },
  {
    value: 'abstain',
    label: 'Abstain',
    help: 'No opinion. You still count towards the number of yes votes needed.',
  },
  {
    value: 'recused',
    label: 'Recuse myself',
    help:
      'You have a conflict of interest with this speaker. You leave the count entirely, ' +
      'which lowers the number of yes votes needed.',
  },
];

/**
 * One board member's ballot on one lead.
 *
 * The recusal reason is asked for here, before anything is written:
 * `ballots.castBallot` refuses a recusal without one, and a volunteer should
 * meet that rule as a field to fill in, not as a failed save.
 */
function BallotForm({
  speaker,
  login,
  outcome,
  disabled,
  onCast,
  onWithdraw,
}: {
  speaker: Speaker;
  login: string | null;
  outcome: Outcome;
  disabled: boolean;
  onCast: (value: BallotValue, comment: string, coiReason: string) => void;
  onWithdraw: () => void;
}) {
  const existing = login ? speaker.selection.ballots.find(b => b.voter === login) : undefined;
  const [value, setValue] = useState<BallotValue>(existing?.value ?? 'yes');
  const [comment, setComment] = useState(existing?.comment ?? '');
  const [coiReason, setCoiReason] = useState(existing?.coi_reason ?? '');
  const reasonMissing = value === 'recused' && coiReason.trim() === '';

  return (
    <div className="w-full space-y-3 border border-border p-3">
      <p className="text-sm text-ink-muted">
        {outcome.suspended
          ? `Board vote on hold: only ${outcome.eligible} member(s) are eligible to vote today.`
          : `${outcome.yes} of ${outcome.threshold} yes votes needed · ${outcome.eligible} member(s) eligible.`}
      </p>
      {existing && (
        <p className="text-sm">
          Your ballot: <strong>{existing.value}</strong>. Submitting again replaces it.
        </p>
      )}
      <fieldset className="space-y-1.5">
        <legend className="text-xs uppercase tracking-wider text-ink-muted">Your ballot</legend>
        {BALLOT_CHOICES.map(choice => (
          <label key={choice.value} className="flex gap-2 items-start text-sm">
            <input
              type="radio"
              name={`ballot-${speaker.id}`}
              value={choice.value}
              checked={value === choice.value}
              onChange={() => setValue(choice.value)}
              className="mt-1"
            />
            <span>
              <span className="font-bold">{choice.label}</span>{' '}
              <span className="text-ink-muted">{choice.help}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <label className="block">
        <span className="text-xs uppercase tracking-wider text-ink-muted">Comment (optional)</span>
        <textarea
          value={comment}
          onChange={e => setComment(e.target.value)}
          rows={2}
          className="w-full px-2 py-1 text-sm mt-1"
        />
      </label>
      {value === 'recused' && (
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">
            Reason for the conflict of interest *
          </span>
          <textarea
            value={coiReason}
            onChange={e => setCoiReason(e.target.value)}
            rows={2}
            className="w-full px-2 py-1 text-sm mt-1"
            placeholder="e.g. former co-author, same lab, family tie"
          />
          <span className="block text-xs text-ink-muted mt-1">
            Required: a recusal changes how many yes votes this lead needs, so the register has
            to say why. One line is enough.
          </span>
        </label>
      )}
      <div className="flex gap-2 items-center flex-wrap">
        <button
          type="button"
          disabled={disabled || reasonMissing}
          onClick={() => onCast(value, comment, coiReason)}
          className="px-3 py-1.5 text-sm rounded bg-primary text-white hover:opacity-90 disabled:opacity-50"
        >
          {existing ? 'Update ballot' : 'Submit ballot'}
        </button>
        {existing && (
          <button
            type="button"
            disabled={disabled}
            onClick={onWithdraw}
            className="px-3 py-1.5 text-sm rounded border border-border text-ink-muted hover:text-ink disabled:opacity-50"
          >
            Withdraw ballot
          </button>
        )}
      </div>
    </div>
  );
}

/** Locking is not on offer while the invitation is still out, so the panel
 *  shown there is handed a callback it can never reach. */
const NO_LOCK = () => {};

/**
 * The date negotiation, on screen: the slots offered, the speaker's reply to
 * each, and -- only against a reply that says `accepted` -- the button that
 * freezes one of them.
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
function CandidateDates({
  speaker,
  disabled,
  canLock,
  onLock,
}: {
  speaker: Speaker;
  disabled: boolean;
  canLock: boolean;
  onLock: (date: string, edition: string) => void;
}) {
  const { speakers, config, mutateSpeakers } = useData();
  const { login } = useAuth();
  const [date, setDate] = useState('');
  const [time, setTime] = useState('12:30');
  const [edition, setEdition] = useState('');
  const [busy, setBusy] = useState(false);
  const today = parisToday();
  const locked = disabled || busy || !login || !config;

  const slots = speaker.candidate_dates.map(c => ({ date: c.date, time: c.time }));

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

  async function reply(slotDate: string, answer: DateAnswer) {
    if (locked || !login) return;
    setBusy(true);
    try {
      await mutateSpeakers(
        current =>
          current.map(sp => (sp.id === speaker.id ? answerDate(sp, slotDate, answer).speaker : sp)),
        // `${slotDate}=${answer}` stood here, which published which
        // evenings a named researcher turned down into a subject line
        // nothing can rewrite. `candidate_dates` is NEVER_PUBLISHED for
        // exactly that reason (`state/consent.ts`). The reply is the
        // qualifier; the day is in the diff.
        formatDecision({
          kind: 'date-answer',
          entity: identifier(speaker.id),
          actor: identifier(login),
          detail: answer === '' ? 'cleared' : answer,
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  const titleMissing = !speaker.title || !speaker.abstract;

  return (
    <div className="space-y-2 w-full">
      <p className="text-xs font-mono uppercase text-ink-muted">Dates offered</p>
      {speaker.candidate_dates.length === 0 && (
        <p className="text-xs text-ink-muted italic">
          No dates offered yet. Offer the ones the invitation proposes, then record what the
          speaker replies.
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
                  ? 'text-xs text-primary'
                  : c.answer === 'declined'
                    ? 'text-xs text-danger'
                    : 'text-xs text-ink-muted italic'
              }
            >
              {c.answer === 'accepted'
                ? 'accepted by the speaker'
                : c.answer === 'declined'
                  ? 'declined by the speaker'
                  : 'no reply yet'}
            </span>
            {c.answer !== 'accepted' && (
              <button
                type="button"
                disabled={locked}
                onClick={() => reply(c.date, 'accepted')}
                className="text-xs text-primary-hover underline disabled:opacity-50"
              >
                they accepted
              </button>
            )}
            {c.answer !== 'declined' && (
              <button
                type="button"
                disabled={locked}
                onClick={() => reply(c.date, 'declined')}
                className="text-xs text-danger underline disabled:opacity-50"
              >
                they declined
              </button>
            )}
            {canLock && c.answer === 'accepted' && (
              <button
                type="button"
                disabled={locked || !edition || titleMissing}
                onClick={() => onLock(c.date, edition)}
                className="px-3 py-1 text-xs font-display font-bold tracking-widest uppercase bg-primary text-white border-2 border-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Lock this date &rarr;
              </button>
            )}
          </li>
        ))}
      </ul>

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

      {canLock && (
        <div className="flex gap-2 items-center flex-wrap">
          <label className="flex items-center gap-1.5">
            <span className="text-xs font-mono uppercase text-ink-muted">&#8470;</span>
            <input
              type="text"
              placeholder={`${editionCodePrefix()}N`}
              value={edition}
              onChange={e => setEdition(e.target.value)}
              className="px-2 py-1 text-sm font-mono w-20"
            />
          </label>
          <button
            type="button"
            onClick={() => config && setEdition(nextEditionCode(speakers, config.vw_counter))}
            className="text-xs text-primary-hover underline"
          >
            suggest
          </button>
        </div>
      )}

      {blocker && <p className="text-danger text-xs">{blocker}</p>}
      {canLock && titleMissing && (
        <p className="text-xs text-danger italic">
          Title and abstract are required before locking the date. Fill them in the checklist
          above.
        </p>
      )}
    </div>
  );
}
