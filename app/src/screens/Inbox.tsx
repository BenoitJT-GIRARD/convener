import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { deriveInbox, type InboxRow } from '../state/inbox';

export function Inbox() {
  const { speakers, loading, error } = useData();
  const { login } = useAuth();
  const role = useRole();
  if (loading || !role) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;

  const today = new Date().toISOString().slice(0, 10);
  const rows = deriveInbox(speakers, login, role, today);
  const votes = rows.filter(r => r.kind === 'vote');
  const actions = rows.filter(r => r.kind === 'action');
  const awareness = rows.filter(r => r.kind === 'awareness');

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
    </div>
  );
}

interface SectionProps {
  num: string;
  label: string;
  rows: InboxRow[];
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
          {rows.map((r, i) => (
            <Row key={i} r={r} variant={variant} />
          ))}
        </ol>
      )}
    </section>
  );
}

function Row({ r, variant }: { r: InboxRow; variant: 'vote' | 'action' | 'awareness' }) {
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
