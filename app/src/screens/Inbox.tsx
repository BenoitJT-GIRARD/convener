import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { deriveInbox, type InboxRow } from '../state/inbox';
import { itemsWaitingFor } from '../state/assignment';
import { parisToday } from '../state/derived';
import { byUrgency, lateness, overdueText, waitingSince, type Lateness } from '../state/sla';
import { LoadError } from '../components/LoadError';
import type { Config } from '../data/types';

/**
 * One row's standing, so the inbox can sort by it and label it.
 *
 * A row with no config loaded, or whose record has no applicable turnaround
 * time, reads as `none` -- which `byUrgency` sorts last. The runbook rows of a
 * scheduled talk are in that group: their T-window is a nudge inside the
 * runbook, not one of the four turnaround times the series commits to, and
 * `deriveInbox` has already ordered them among themselves. `Array.sort` is
 * stable, so that ordering survives underneath this one.
 */
function rowLateness(r: InboxRow, config: Config | null, today: string): Lateness {
  return config ? lateness(r.speaker, config, today) : { state: 'none' };
}

export function Inbox() {
  const { speakers, loading, error, config } = useData();
  const { login } = useAuth();
  const role = useRole();
  if (loading || !role) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <LoadError message={error} />;

  const today = parisToday();
  const rows = deriveInbox(speakers, config, login, role, today)
    .map(r => ({ r, late: rowLateness(r, config, today) }))
    .sort((a, b) => byUrgency(a.late, b.late));
  const votes = rows.filter(x => x.r.kind === 'vote');
  const actions = rows.filter(x => x.r.kind === 'action');
  const awareness = rows.filter(x => x.r.kind === 'awareness');

  // "Where is this event up to" and "what is waiting for me" are two
  // questions, and this screen is the only thing they share. `deriveInbox`
  // keys on `assigned_to` -- who looks after the lead -- while these rows come
  // from the name put against one line of the runbook, read by
  // `state/assignment.ts` from `checklist` and from nothing else. A line
  // nobody is down for produces no row at all, here or anywhere: not naming an
  // owner is the default, not an omission to chase.
  //
  // The rows are shown through the same `Row` as everything else, so a line
  // that is late says it in the words `state/sla.ts` already uses -- "Forum
  // summary is 3 days overdue", "waiting since 2026-08-18" -- about the step,
  // never about whoever is down for it.
  const waiting = itemsWaitingFor(speakers, login).map(w => ({
    r: {
      kind: 'action' as const,
      speaker: w.speaker,
      label: w.item.label,
      itemKey: w.item.key,
      urgency: 0,
    },
    late: config ? lateness(w.speaker, config, today) : ({ state: 'none' } as Lateness),
  }));

  return (
    <div>
      <div className="flex items-baseline justify-between mb-10 flex-wrap gap-2">
        <div>
          <p className="text-xs font-bold tracking-[0.14em] uppercase text-accent mb-2 flex items-center gap-3">
            <span className="h-0.5 bg-accent w-8" />
            What needs you
          </p>
          <h1 className="font-display font-extrabold text-3xl uppercase tracking-tight">Inbox</h1>
        </div>
        <p className="text-xs font-mono text-ink-muted tracking-wider">
          {login} · {role}
        </p>
      </div>

      {votes.length > 0 && <Section num="01" label="To vote" rows={votes} variant="vote" />}

      <Section
        num={votes.length > 0 ? '02' : '01'}
        label="To act on"
        rows={actions}
        variant="action"
        empty="No actions due. Nice."
      />

      {awareness.length > 0 && (
        <Section
          num={String(votes.length > 0 ? 3 : 2).padStart(2, '0')}
          label="Awareness"
          rows={awareness}
          variant="awareness"
        />
      )}

      {waiting.length > 0 && (
        <Section
          num={String(2 + (votes.length > 0 ? 1 : 0) + (awareness.length > 0 ? 1 : 0)).padStart(
            2,
            '0',
          )}
          label="Waiting for you"
          rows={waiting}
          variant="action"
        />
      )}
    </div>
  );
}

interface SectionProps {
  num: string;
  label: string;
  rows: { r: InboxRow; late: Lateness }[];
  variant: 'vote' | 'action' | 'awareness';
  empty?: string;
}

function Section({ num, label, rows, variant, empty }: SectionProps) {
  return (
    <section className="mb-10 border-t border-border pt-6">
      <header className="flex items-baseline gap-3 mb-4">
        <span className="font-mono text-xs text-accent">{num}</span>
        <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] text-ink">
          {label}
        </h2>
        <span className="ml-auto font-mono text-xs text-ink-faint tracking-wider">
          {rows.length} {rows.length === 1 ? 'item' : 'items'}
        </span>
      </header>
      {rows.length === 0 ? (
        <p className="text-ink-muted text-sm pl-7">{empty}</p>
      ) : (
        <ol className="divide-y divide-border border-y border-border">
          {rows.map(({ r, late }, i) => (
            <Row key={i} r={r} late={late} variant={variant} />
          ))}
        </ol>
      )}
    </section>
  );
}

function Row({
  r,
  late,
  variant,
}: {
  r: InboxRow;
  late: Lateness;
  variant: 'vote' | 'action' | 'awareness';
}) {
  const pastDue = r.daysUntil !== undefined && r.daysUntil < 0;
  return (
    <li>
      <Link
        to={`/speakers/${r.speaker.id}`}
        className={`grid grid-cols-[7rem_1fr_auto] gap-4 items-center py-3 px-2 hover:bg-primary-soft transition-colors ${
          variant === 'awareness' ? 'opacity-70' : ''
        }`}
      >
        <span className="font-mono text-xs text-accent uppercase tracking-wider">
          {r.speaker.edition_code || r.speaker.id}
        </span>
        <div className="min-w-0">
          <p className="font-medium text-sm text-ink truncate">{r.label}</p>
          <p className="text-xs text-ink-muted truncate">
            {r.speaker.name}
            {r.speaker.affiliation && ` · ${r.speaker.affiliation}`}
          </p>
          {late.state === 'overdue' && (
            // What is late is the step, and the sentence has no room for
            // anyone's name -- see src/state/sla.ts. The day it has been
            // waiting since is shown alongside so a row that appears at the
            // same moment as twenty others is readable as one shared start.
            <p className="text-xs truncate">
              <span className="font-medium text-danger">{overdueText(late)}</span>
              <span className="text-ink-faint"> · {waitingSince(late)}</span>
            </p>
          )}
        </div>
        <span className="font-mono text-[11px] tracking-wider uppercase text-ink-faint">
          {variant === 'vote' && 'Vote →'}
          {variant === 'action' && (pastDue ? <span className="text-danger">Past due →</span> : 'Open →')}
          {variant === 'awareness' && 'View →'}
        </span>
      </Link>
    </li>
  );
}
