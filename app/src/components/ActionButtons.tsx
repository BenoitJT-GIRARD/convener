import { useState } from 'react';
import type { CancelPayload, CancellationReason } from '../state/transitions';
import { CANCELLATION_REASONS, applyTransition, canTransition, type BallotPayload, type LockDatePayload, type OverridePayload, type Role, type Transition } from '../state/transitions';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { activeBoard } from '../state/board';
import { decide, type Outcome } from '../state/governance';
import { deliveryRecordable, parisToday } from '../state/derived';
import { formatDecision, identifier, transitionDecision } from '../state/decisions';
import type { BallotValue, Speaker } from '../data/types';

/** Written out rather than left as "member(s)": a board of one is an
 *  ordinary state on a small series, and the count is read at the moment a
 *  vote is stuck. `state/sla.ts` writes its own day counts the same way. */
function members(n: number): string {
  return n === 1 ? '1 member is' : `${n} members are`;
}

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

  async function fire(
    t: Transition,
    payload?: LockDatePayload | OverridePayload | BallotPayload | CancelPayload,
  ) {
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
              ? `Board vote on hold: only ${members(outcome.eligible)} eligible to vote today.`
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
            Name Host 1 and Host 2 above before sending the invitation.
          </span>,
        );
      } else {
        buttons.push(btn('Mark invitation sent →', 'send-invitation'));
      }
      break;
    }
    case 'invited':
      // The one button of this status. Accepting is not here: it is the
      // click on the evening the speaker agreed to, in the panel above --
      // see `components/DatePanel.tsx`. This is its opposite and covers the
      // whole offer: the speaker cannot come at all.
      buttons.push(btn('Speaker declined', 'invited-decline', 'danger'));
      break;
    case 'scheduled': {
      // Available from the day before, and disabled with the reason beside
      // it until then -- the same shape every other rule on this screen
      // takes. `deliveryRecordable` is the rule; `applyTransition` asks it
      // again at write time.
      const open = deliveryRecordable(speaker, today);
      buttons.push(
        <button
          key="mark-delivered"
          type="button"
          disabled={locked || !open}
          onClick={() => fire('mark-delivered')}
          className={btnCls('primary')}
        >
          Mark it delivered &rarr;
        </button>,
      );
      if (!open) {
        buttons.push(
          <span className="text-sm text-ink-muted" key="msg">
            {speaker.date
              ? `This opens the day before the talk, which is on ${speaker.date}.`
              : 'This opens the day before the talk, and this record carries no date yet.'}
          </span>,
        );
      }
      // The other way out of `scheduled`, and until it existed there was
      // none: a seminar that was announced and did not happen could only
      // leave through Force status, which writes a status and records no act.
      if (role === 'board') {
        buttons.push(
          <CancelForm
            key="cancel-edition"
            disabled={locked}
            onCancel={reason => fire('cancel-edition', { reason })}
          />,
        );
      }
      break;
    }
    case 'parked':
    case 'decline-board':
      if (role === 'board') buttons.push(btn('Reactivate', 'reactivate'));
      break;
    case 'archived':
      // The one control a closed event carries, and it is a door rather than
      // a decision: it puts the record back to `delivered`, where the gate
      // that publishes actually lives. What it is for is said above it by
      // `components/ClosedRecord.tsx`, which is the report this button sits
      // at the foot of.
      if (role === 'board') buttons.push(btn('Reopen the publication decision', 'publication-reopen'));
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
/** The three button shapes this screen uses. A module constant rather than a
 *  closure, because two components in this file draw the same buttons and a
 *  second copy of these strings is how two controls come to look different
 *  for no reason. */
const btnCls = (variant: 'primary' | 'danger' | 'ghost') =>
  variant === 'danger'
    ? 'px-3 py-1.5 text-sm rounded border border-danger text-danger hover:bg-danger hover:text-white disabled:opacity-50'
    : variant === 'ghost'
      ? 'px-3 py-1.5 text-sm rounded border border-border text-ink-muted hover:text-ink disabled:opacity-50'
      : 'px-3 py-1.5 text-sm rounded bg-dominant text-white hover:opacity-90 disabled:opacity-50';

/** Cancelling an announced edition, with the reason the register records.
 *
 *  A select rather than a free text box, and the four values are the same
 *  closed vocabulary `commit_format.py` holds: the reason goes into a commit
 *  subject, which is permanent and unrewritable, and a sentence typed here
 *  could name a person's illness.
 *
 *  Two steps rather than one, like nothing else on this screen. Every other
 *  control here is reversible or reachable again; this one tells everybody
 *  who registered that the talk is off, and there is no putting that back.
 */
function CancelForm({
  disabled,
  onCancel,
}: {
  disabled: boolean;
  onCancel: (reason: CancellationReason) => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<CancellationReason>('speaker-withdrew');

  if (!open) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(true)}
        className={btnCls('ghost')}
      >
        Cancel this edition…
      </button>
    );
  }

  return (
    <div className="w-full space-y-3 border border-danger p-3">
      <p className="text-sm">
        <strong>This tells everyone who registered that the talk is off.</strong> They are
        written to at the address their confirmation went to, and nothing here can be taken
        back. The edition code stays used, and the record moves to the archive.
      </p>
      <label className="block text-sm">
        <span className="text-xs uppercase tracking-wider text-ink-muted">Reason</span>
        <select
          className="mt-1 block w-full px-2 py-1 border border-border bg-surface text-sm"
          value={reason}
          onChange={e => setReason(e.target.value as CancellationReason)}
        >
          {CANCELLATION_REASONS.map(value => (
            <option key={value} value={value}>
              {CANCELLATION_LABELS[value]}
            </option>
          ))}
        </select>
      </label>
      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onCancel(reason)}
          className={btnCls('danger')}
        >
          Cancel the edition and tell the registrants
        </button>
        <button type="button" onClick={() => setOpen(false)} className={btnCls('ghost')}>
          Keep it
        </button>
      </div>
    </div>
  );
}

/** The four reasons, as a person reads them. The values themselves are the
 *  register's words and are never shown: `speaker-withdrew` is a commit
 *  subject, not a sentence. */
const CANCELLATION_LABELS: Record<CancellationReason, string> = {
  'speaker-withdrew': 'The speaker withdrew',
  'board-withdrew': 'The Board withdrew the edition',
  'date-unworkable': 'The date turned out to be unworkable',
  'series-paused': 'The series is paused',
};

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
          ? `Board vote on hold: only ${members(outcome.eligible)} eligible to vote today.`
          : `${outcome.yes} of ${outcome.threshold} yes votes needed · ${members(outcome.eligible)} eligible.`}
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
          className="px-3 py-1.5 text-sm rounded bg-dominant text-white hover:opacity-90 disabled:opacity-50"
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
