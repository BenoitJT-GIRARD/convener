import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { voteState } from '../data/voting';
import { Button } from './Button';
import type { Speaker } from '../data/types';

const BOARD_SIZE = 6;

export function VotePanel({ speaker, onVote }: {
  speaker: Speaker;
  onVote: (votes: string[]) => Promise<void>;
}) {
  const { login } = useAuth();
  const votes = speaker.selection.votes_for;
  const state = voteState(votes, BOARD_SIZE);
  const youVoted = !!login && votes.includes(login);
  const [busy, setBusy] = useState(false);

  async function castVote() {
    if (!login || youVoted) return;
    setBusy(true);
    try { await onVote([...votes, login]); }
    finally { setBusy(false); }
  }

  return (
    <div className="my-6 p-4 rounded-md bg-paper border border-border">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="font-serif text-xl">Selection vote</h2>
        <div className="text-sm">
          <span className="font-mono">{state.count} / {state.threshold}</span>
          <span className={`ml-3 text-xs uppercase tracking-wider ${state.state === 'passed' ? 'text-primary' : 'text-ink-muted'}`}>
            {state.state}
          </span>
        </div>
      </div>
      <p className="text-sm text-ink-muted mb-3">
        Two-thirds of the Editorial Board ({BOARD_SIZE} members) must say yes.
        {votes.length > 0 && <> Voted: {votes.join(', ')}.</>}
      </p>
      {youVoted
        ? <p className="text-primary text-sm">✓ You voted.</p>
        : <Button onClick={castVote} disabled={busy}>{busy ? 'Voting…' : 'Vote yes'}</Button>
      }
    </div>
  );
}
