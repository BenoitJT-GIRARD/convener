import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { effectiveStatus } from '../state/derived';
import type { Speaker } from '../data/types';

const STATUS_COLOR: Record<string, string> = {
  scheduled: 'bg-primary/20 border-primary text-ink',
  delivered: 'bg-accent/20 border-accent text-ink',
  wrapped: 'bg-paper border-border text-ink-muted',
  archived: 'bg-paper border-border text-ink-muted opacity-60',
};

export function Agenda() {
  const { speakers, loading, error, config } = useData();
  if (loading) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;
  const now = new Date();

  const dated = speakers
    .filter(s => s.date && ['scheduled', 'delivered', 'wrapped', 'archived'].includes(s.status))
    .sort((a, b) => a.date.localeCompare(b.date));

  const groups: Record<string, Speaker[]> = {};
  for (const s of dated) {
    const key = s.date.slice(0, 7);
    (groups[key] ||= []).push(s);
  }

  return (
    <div>
      <h1 className="font-serif text-3xl mb-2">Agenda</h1>
      <p className="text-ink-muted text-sm mb-6">
        No two webinars within {config?.overlap_window_days ?? 7} days of each other.
      </p>
      {Object.keys(groups).length === 0 ? (
        <p className="text-ink-muted">No dated webinars yet.</p>
      ) : (
        Object.entries(groups).map(([month, items]) => (
          <section key={month} className="mb-6">
            <h2 className="font-mono text-sm text-ink-muted mb-2">{month}</h2>
            <div className="space-y-2">
              {items.map(s => {
                // Display only: what has aired, not necessarily what's
                // recorded yet — the scheduled job (tools/convener_ops/sweep.py)
                // is the single writer for that transition.
                const displayStatus = config ? effectiveStatus(s, config, now) : s.status;
                return (
                  <Link
                    key={s.id}
                    to={`/speakers/${s.id}`}
                    className={`block border rounded p-3 hover:shadow-card ${STATUS_COLOR[displayStatus] || ''}`}
                  >
                    <div className="flex justify-between items-baseline">
                      <p className="font-mono text-xs">
                        {s.edition_code} · {s.date}
                      </p>
                      <p className="text-xs">{displayStatus}</p>
                    </div>
                    <p className="font-medium text-sm mt-1">{s.name}</p>
                    {s.title && <p className="text-xs text-ink-muted">{s.title}</p>}
                  </Link>
                );
              })}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
