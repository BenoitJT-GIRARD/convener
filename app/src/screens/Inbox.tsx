import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { deriveInbox } from '../state/inbox';

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
      <div className="flex items-baseline justify-between mb-6">
        <h1 className="font-serif text-3xl">Inbox</h1>
        <p className="text-sm text-ink-muted">
          {login} · {role}
        </p>
      </div>

      {votes.length > 0 && (
        <section className="mb-8">
          <h2 className="font-serif text-xl mb-3">To vote</h2>
          <div className="space-y-2">
            {votes.map((r, i) => (
              <Link
                key={i}
                to={`/speakers/${r.speaker.id}`}
                className="block bg-surface border border-border rounded-md p-3 hover:shadow-card"
              >
                <p className="font-medium text-sm">{r.label}</p>
                <p className="text-xs text-ink-muted mt-1">
                  {r.speaker.affiliation}
                  {r.speaker.country && ` · ${r.speaker.country}`}
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section className="mb-8">
        <h2 className="font-serif text-xl mb-3">To act on</h2>
        {actions.length === 0 ? (
          <p className="text-ink-muted text-sm">No actions due. Nice.</p>
        ) : (
          <div className="space-y-2">
            {actions.map((r, i) => (
              <Link
                key={i}
                to={`/speakers/${r.speaker.id}`}
                className="block bg-surface border border-border rounded-md p-3 hover:shadow-card"
              >
                <p className="text-xs text-ink-muted font-mono">
                  {r.speaker.edition_code || r.speaker.id} · {r.speaker.name}
                  {r.daysUntil !== undefined && r.daysUntil < 0 && (
                    <span className="text-danger ml-2">past due</span>
                  )}
                </p>
                <p className="font-medium text-sm mt-1">{r.label}</p>
              </Link>
            ))}
          </div>
        )}
      </section>

      {awareness.length > 0 && (
        <section>
          <h2 className="font-serif text-xl mb-3">Awareness</h2>
          <div className="space-y-2">
            {awareness.map((r, i) => (
              <Link
                key={i}
                to={`/speakers/${r.speaker.id}`}
                className="block bg-surface border border-border rounded-md p-3 hover:shadow-card opacity-70"
              >
                <p className="text-xs text-ink-muted font-mono">
                  {r.speaker.edition_code || r.speaker.id}
                </p>
                <p className="text-sm mt-1">{r.label}</p>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
