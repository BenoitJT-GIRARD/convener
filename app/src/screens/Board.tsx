import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../data/DataContext';
import { LoadError } from '../components/LoadError';
import { Button } from '../components/Button';
import {
  NOMINATION_WINDOW_DAYS,
  declareUnavailability,
  isBoardMember,
  nominationBlocker,
  objectToNomination,
  objectionBlocker,
  openNomination,
  resolveNominations,
  withdrawObjection,
  withdrawalBlocker,
} from '../state/board';
import type { Config, Nomination } from '../data/types';
import { parisToday } from '../state/derived';
import { formatDecision, identifier, type Subject } from '../state/decisions';

const OUTCOME_LABEL: Record<Nomination['outcome'], string> = {
  '': 'Open',
  accepted: 'Joined the board',
  deferred: 'Objected — annual meeting decides',
  waiting: 'Waiting for a seat',
};

/** Which nominations `resolveNominations` would settle today, so the screen
 *  can say what is due before anyone writes it -- and say nothing when
 *  nothing is. Compared by index: `resolveNominations` maps the list
 *  one-to-one and never reorders it. */
function dueOutcomes(config: Config, today: string): Nomination[] {
  const resolved = resolveNominations(config, today);
  return resolved.nominations.filter((n, i) => n.outcome !== config.nominations[i].outcome);
}

export function Board() {
  const { config, speakers, loading, error, saveError, mutateConfig, clearSaveError } = useData();
  const { login } = useAuth();
  const [candidate, setCandidate] = useState('');
  const [until, setUntil] = useState('');
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  if (loading) return <p className="text-ink-muted">Reading the records from GitHub…</p>;
  if (error) return <LoadError message={error} />;
  if (!config || !login) return <p className="text-ink-muted">Nothing to show yet.</p>;

  const today = parisToday();
  const me = login;
  const iAmMember = isBoardMember(config, me, today);
  const due = dueOutcomes(config, today);

  // `board_min` is a target and nothing enforces it -- no rule in
  // `state/board.ts` reads it, and `convener-validate` reports it rather than
  // failing on it. A target nothing states is a decoration, so this is where
  // it is stated, and it is stated in both directions: a line that appears
  // only on bad news never teaches anyone what the board is aiming at.
  const seated = config.board.filter(m => m.status === 'active').length;
  const seats = `${seated} active member${seated === 1 ? '' : 's'}`;
  const compositionNote =
    seated < config.board_min
      ? `${seats}, below the board's target of ${config.board_min}. Nothing is blocked by that: ` +
        'the board still votes and still admits members — the target is what recruiting aims at.'
      : `${seats}. The board aims for ${config.board_min} and seats at most ${config.board_max}.`;

  const nominationReason = nominationBlocker(speakers, config, candidate, me, today);
  // The rule is shown as soon as it is knowable, and the control stays
  // disabled -- a volunteer should never have to submit to find out that
  // the candidate is two webinars short.
  const nominationHint = candidate.trim() === '' ? '' : nominationReason;

  async function write(transform: (current: Config) => Config, message: Subject) {
    setBusy(true);
    try {
      await mutateConfig(transform, message);
    } finally {
      setBusy(false);
    }
  }

  const setAway = () =>
    // `current`, not the `config` this render closed over: another member may
    // have written the file since it was read, and the transform is replayed
    // against whatever is actually there.
    write(
      current => declareUnavailability(current, me, until),
      // Through the grammar, not around it. This writes
      // `unavailable_until`, which `activeBoard` reads and the vote
      // threshold is computed from, so it is a decision and the register
      // records it as one. The day is in the diff; the subject names the
      // record and who acted, like every other line of the register.
      formatDecision({
        kind: 'availability-set',
        entity: identifier(me),
        actor: identifier(me),
        detail: until === '' ? 'back' : 'away',
      }),
    );

  const nominate = async () => {
    const name = candidate.trim();
    await write(
      current => openNomination(speakers, current, name, me, today),
      formatDecision({ kind: 'nomination-open', entity: identifier(name), actor: identifier(me) }),
    );
    setCandidate('');
  };

  const withdraw = (target: string) =>
    write(
      current => withdrawObjection(current, target, me, today),
      formatDecision({
        kind: 'nomination-withdraw-objection',
        entity: identifier(target),
        actor: identifier(me),
      }),
    );

  const object = (target: string) =>
    write(
      current => objectToNomination(current, target, me, reasons[target] ?? '', today),
      formatDecision({
        kind: 'nomination-object',
        entity: identifier(target),
        actor: identifier(me),
      }),
    );

  // One commit per nomination, not one for the batch. G-12 makes board entry
  // a registrable decision, and a single row saying "the nominations were
  // applied" records that something happened to the board without recording
  // who joined it. Each call re-reads `current`, so the seat counting still
  // sees the board the previous one left.
  const applyDue = async () => {
    for (const n of due) {
      await write(
        current => resolveNominations(current, today, n.candidate),
        formatDecision({
          kind: 'nomination-resolve',
          entity: identifier(n.candidate),
          actor: identifier(me),
        }),
      );
    }
  };

  return (
    <div>
      <div className="mb-10">
        <p className="text-xs font-bold tracking-[0.14em] uppercase text-dominant mb-2 flex items-center gap-3">
          <span className="h-0.5 bg-dominant w-8" />
          Who decides
        </p>
        <h1 className="font-display font-extrabold text-3xl uppercase tracking-tight">Board</h1>
      </div>

      {saveError && (
        <div className="mb-6 border border-danger px-4 py-3 text-sm flex items-start gap-4">
          <span className="flex-1">{saveError}</span>
          <button className="text-xs uppercase tracking-wider" onClick={clearSaveError}>
            Dismiss
          </button>
        </div>
      )}

      <section className="mb-10 border-t border-border pt-6">
        <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] mb-4">
          Composition
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wider text-ink-muted text-left">
              <th className="py-2 font-medium">Member</th>
              <th className="py-2 font-medium">Status</th>
              <th className="py-2 font-medium">Availability</th>
              <th className="py-2 font-medium">Joined</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border border-y border-border">
            {config.board.map(m => (
              <tr key={m.login}>
                <td className="py-2 font-mono text-xs">
                  {m.login}
                  {m.login === me && <span className="text-ink-muted"> (you)</span>}
                </td>
                <td className="py-2">{m.status}</td>
                <td className="py-2">
                  {m.status !== 'active'
                    ? '—'
                    : m.unavailable_until === '' || m.unavailable_until < today
                      ? 'available'
                      : `away until ${m.unavailable_until}`}
                </td>
                <td className="py-2 font-mono text-xs text-ink-muted">{m.joined_on || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-sm text-ink-muted mt-3">{compositionNote}</p>
      </section>

      {iAmMember && (
        <section className="mb-10 border-t border-border pt-6">
          <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] mb-2">
            Your availability
          </h2>
          <p className="text-sm text-ink-muted mb-3">
            While you are away you leave the denominator of every vote. The last day away is
            included; you come back on your own, with nothing to write.
          </p>
          <div className="flex items-end gap-3 flex-wrap">
            <label className="block">
              <span className="text-xs uppercase tracking-wider text-ink-muted">Away until</span>
              <input
                type="date"
                aria-label="Away until"
                value={until}
                onChange={e => setUntil(e.target.value)}
                className="mt-1 px-3 py-2 border border-border rounded-md bg-surface text-sm"
              />
            </label>
            <Button onClick={setAway} disabled={busy}>
              {until === '' ? 'Mark me available' : 'Save absence'}
            </Button>
          </div>
        </section>
      )}

      <section className="mb-10 border-t border-border pt-6">
        <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] mb-2">
          Nominations
        </h2>
        <p className="text-sm text-ink-muted mb-4">
          A sponsored candidate joins after {NOMINATION_WINDOW_DAYS} days without an objection. An
          objection does not refuse anyone: it sends the nomination to the annual meeting. While it
          stands, the nomination cannot be opened again — only the member who wrote it can withdraw
          it, and the {NOMINATION_WINDOW_DAYS} days then start again.
        </p>

        {config.nominations.length === 0 ? (
          <p className="text-sm text-ink-muted mb-4">No nomination on record.</p>
        ) : (
          <ul className="divide-y divide-border border-y border-border mb-4">
            {config.nominations.map((n, i) => (
              <li key={`${n.candidate}-${i}`} className="py-3">
                <div className="flex items-baseline gap-3 flex-wrap">
                  <span className="font-mono text-xs">{n.candidate}</span>
                  <span className="text-xs text-ink-muted">
                    sponsored by {n.sponsor} · opened {n.opened_on || '—'}
                  </span>
                  <span className="ml-auto text-xs uppercase tracking-wider text-dominant">
                    {OUTCOME_LABEL[n.outcome]}
                  </span>
                </div>
                {n.objections.length > 0 && (
                  <ul className="mt-2 text-xs text-ink-muted">
                    {n.objections.map(o => (
                      <li key={o.member}>
                        {o.member} ({o.date}): {o.reason}
                      </li>
                    ))}
                  </ul>
                )}
                {iAmMember && n.outcome !== 'accepted' && (
                  <div className="mt-2 flex items-end gap-3 flex-wrap">
                    <label className="block flex-1 min-w-[16rem]">
                      <span className="text-xs uppercase tracking-wider text-ink-muted">
                        Reason for objecting
                      </span>
                      <input
                        type="text"
                        aria-label={`Reason for objecting to ${n.candidate}`}
                        value={reasons[n.candidate] ?? ''}
                        onChange={e =>
                          setReasons(r => ({ ...r, [n.candidate]: e.target.value }))
                        }
                        className="mt-1 w-full px-3 py-2 border border-border rounded-md bg-surface text-sm"
                      />
                    </label>
                    <Button
                      variant="outline"
                      onClick={() => object(n.candidate)}
                      disabled={
                        busy ||
                        objectionBlocker(config, n.candidate, me, reasons[n.candidate] ?? '', today) !==
                          ''
                      }
                    >
                      Object
                    </Button>
                    {withdrawalBlocker(config, n.candidate, me) === '' && (
                      // Offered only to the member whose own objection it is;
                      // `withdrawObjection` refuses anyone else, so the control
                      // and the rule cannot disagree.
                      <Button variant="outline" onClick={() => withdraw(n.candidate)} disabled={busy}>
                        Withdraw my objection
                      </Button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        {iAmMember && due.length > 0 && (
          <div className="mb-4 border border-border p-3 text-sm">
            <p className="mb-2">
              {due.length === 1 ? '1 nomination is' : `${due.length} nominations are`} due:{' '}
              {due.map(n => `${n.candidate} → ${OUTCOME_LABEL[n.outcome]}`).join(', ')}.
            </p>
            <Button onClick={applyDue} disabled={busy}>
              Record the outcome
            </Button>
          </div>
        )}

        {iAmMember && (
          <div className="flex items-end gap-3 flex-wrap">
            <label className="block">
              <span className="text-xs uppercase tracking-wider text-ink-muted">
                Nominate a GitHub username (you sponsor)
              </span>
              <input
                type="text"
                aria-label="Nominate"
                placeholder="github-username"
                value={candidate}
                onChange={e => setCandidate(e.target.value)}
                className="mt-1 px-3 py-2 border border-border rounded-md bg-surface text-sm"
              />
            </label>
            <Button onClick={nominate} disabled={busy || nominationReason !== ''}>
              Open nomination
            </Button>
            {nominationHint !== '' && (
              <p className="text-xs text-ink-muted basis-full">{nominationHint}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
