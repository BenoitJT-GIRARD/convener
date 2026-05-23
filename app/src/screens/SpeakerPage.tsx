// Stub — replaced in Phase C with the action-driven speaker workspace.
import { useParams, Navigate } from 'react-router-dom';
import { useData } from '../data/DataContext';

export function SpeakerPage() {
  const { id } = useParams();
  const { speakers, loading } = useData();
  if (loading) return <p className="text-ink-muted">Loading…</p>;
  const s = speakers.find(sp => sp.id === id);
  if (!s) return <Navigate to="/pipeline" replace />;
  return (
    <div>
      <p className="text-xs text-ink-muted font-mono mb-1">
        {s.id}
        {s.edition_code && ` · ${s.edition_code}`}
      </p>
      <h1 className="font-serif text-3xl">{s.name}</h1>
      <p className="text-ink-muted mt-1">
        {s.affiliation}
        {s.country && ` · ${s.country}`}
      </p>
      <p className="text-ink-muted mt-1">
        Status: <strong>{s.status}</strong>
        {s.date && ` · ${s.date}`}
      </p>
      {s.title && (
        <div className="mt-6">
          <h2 className="font-serif text-xl mb-2">Talk</h2>
          <p className="font-medium">{s.title}</p>
          {s.abstract && <p className="text-ink-muted mt-2 whitespace-pre-wrap">{s.abstract}</p>}
        </div>
      )}
    </div>
  );
}
