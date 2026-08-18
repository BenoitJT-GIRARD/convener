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
import { findOverlaps, nextEditionCode } from '../state/agenda';
import { activeBoard } from '../state/board';
import { decide, type Outcome } from '../state/governance';
import { parisToday } from '../state/derived';
import type { BallotValue, Speaker } from '../data/types';

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
        `data: ${speaker.id} → ${t}`,
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
      break;
    case 'confirmed':
      buttons.push(
        <LockDateForm
          key="lock"
          speaker={speaker}
          disabled={locked}
          onSubmit={(d, e, t) => fire('lock-date', { date: d, edition_code: e, time: t })}
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

function LockDateForm({
  speaker,
  onSubmit,
  disabled,
}: {
  speaker: Speaker;
  onSubmit: (date: string, edition: string, time: string) => void;
  disabled: boolean;
}) {
  const { speakers, config } = useData();
  const [date, setDate] = useState('');
  const [time, setTime] = useState('12:30');
  const [edition, setEdition] = useState('');
  const [err, setErr] = useState<string | null>(null);

  function suggestEdition() {
    if (!config) return;
    setEdition(nextEditionCode(speakers, config.vw_counter));
  }

  function attempt() {
    setErr(null);
    if (!date || !edition || !time || !config) return;
    const hits = findOverlaps(date, speakers, config.overlap_window_days, speaker.id);
    if (hits.length) {
      const h = hits[0];
      setErr(
        `Overlap: ${h.speaker.edition_code || h.speaker.id} is on ${h.speaker.date} (${h.daysApart}d apart). Choose another date.`,
      );
      return;
    }
    onSubmit(date, edition, time);
  }

  const titleMissing = !speaker.title || !speaker.abstract;
  const formIncomplete = !date || !edition || !time;
  const locked = disabled || formIncomplete || titleMissing;

  return (
    <div className="space-y-2 w-full">
      <div className="flex gap-2 items-center flex-wrap">
        <label className="flex items-center gap-1.5">
          <span className="text-xs font-mono uppercase text-ink-muted">Date</span>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="px-2 py-1 text-sm" />
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
        <label className="flex items-center gap-1.5">
          <span className="text-xs font-mono uppercase text-ink-muted">№</span>
          <input
            type="text"
            placeholder="MRG-N"
            value={edition}
            onChange={e => setEdition(e.target.value)}
            className="px-2 py-1 text-sm font-mono w-20"
          />
        </label>
        <button onClick={suggestEdition} className="text-xs text-primary-hover underline" type="button">
          suggest
        </button>
        <button
          disabled={locked}
          onClick={attempt}
          className="px-3 py-1.5 text-sm font-display font-bold tracking-widest uppercase bg-primary text-white border-2 border-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed"
          type="button"
        >
          Lock date →
        </button>
      </div>
      {titleMissing && (
        <p className="text-xs text-danger italic">
          Title and abstract are required before locking the date. Fill them in the checklist above.
        </p>
      )}
      {err && <p className="text-danger text-xs">{err}</p>}
    </div>
  );
}
