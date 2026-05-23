import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';

export function Archive() {
  const { speakers, loading } = useData();
  const [q, setQ] = useState('');
  if (loading) return <p className="text-ink-muted">Loading…</p>;

  const past = speakers
    .filter(s => ['wrapped', 'archived'].includes(s.status))
    .filter(
      s => !q || (s.name + s.title + s.affiliation).toLowerCase().includes(q.toLowerCase()),
    )
    .sort((a, b) => b.date.localeCompare(a.date));

  return (
    <div>
      <h1 className="font-serif text-3xl mb-4">Archive</h1>
      <input
        type="search"
        placeholder="Search…"
        value={q}
        onChange={e => setQ(e.target.value)}
        className="w-full max-w-md px-3 py-2 border border-border rounded mb-6"
      />
      <div className="space-y-2">
        {past.map(s => (
          <Link
            key={s.id}
            to={`/speakers/${s.id}`}
            className="block border border-border bg-surface rounded p-3 hover:shadow-card"
          >
            <p className="font-mono text-xs text-ink-muted">
              {s.edition_code} · {s.date}
            </p>
            <p className="font-medium text-sm mt-1">{s.name}</p>
            {s.title && <p className="text-xs text-ink-muted">{s.title}</p>}
          </Link>
        ))}
        {past.length === 0 && <p className="text-ink-muted text-sm">Nothing here yet.</p>}
      </div>
    </div>
  );
}
