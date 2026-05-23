// Stub — replaced in Phase C with the read-only kanban for the unified schema.
import { useData } from '../data/DataContext';

export function Pipeline() {
  const { speakers, loading, error } = useData();
  if (loading) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;
  return (
    <div>
      <h1 className="font-serif text-3xl mb-4">Pipeline</h1>
      <p className="text-ink-muted">{speakers.length} speakers in the data.</p>
    </div>
  );
}
