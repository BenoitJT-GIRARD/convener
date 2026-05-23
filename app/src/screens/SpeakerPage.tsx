import { useParams, Navigate, Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { ActionButtons } from '../components/ActionButtons';
import { AdminOverride } from '../components/AdminOverride';
import { Checklist } from '../components/Checklist';
import { canFinalize, setField, type FieldKey } from '../state/phases';

export function SpeakerPage() {
  const { id } = useParams();
  const { speakers, loading, error, saveSpeakers } = useData();
  const { login } = useAuth();
  const role = useRole();
  if (loading || !role) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;
  const s = speakers.find(sp => sp.id === id);
  if (!s) return <Navigate to="/pipeline" replace />;

  async function toggle(key: string, value: boolean) {
    if (!login || !s) return;
    const next = { ...s, runbook_progress: { ...s.runbook_progress, [key]: value } };
    await saveSpeakers(
      speakers.map(sp => (sp.id === s.id ? next : sp)),
      `data: ${s.id} runbook ${key}=${value}`,
    );
  }

  async function onField(k: FieldKey, v: string) {
    if (!login || !s) return;
    const next = setField(s, k, v);
    await saveSpeakers(
      speakers.map(sp => (sp.id === s.id ? next : sp)),
      `data: ${s.id} set ${k}`,
    );
  }

  async function finalize() {
    if (!login || !s) return;
    const next = { ...s, status: 'archived' as const };
    await saveSpeakers(
      speakers.map(sp => (sp.id === s.id ? next : sp)),
      `data: ${s.id} finalize-and-archive by ${login}`,
    );
  }

  return (
    <div className="max-w-3xl">
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
        {s.time && ` · ${s.time}`}
        {s.host_1 && ` · host 1: ${s.host_1}`}
        {s.host_2 && ` · host 2: ${s.host_2}`}
      </p>
      <p className="text-ink-muted mt-1 text-sm">
        Proposed by <strong>{s.proposed_by || '(unknown)'}</strong> · source: {s.source}
      </p>

      {s.conflicts_of_interest && (
        <div className="mt-4 p-3 border-l-2 border-accent bg-accent-soft">
          <p className="text-xs font-display font-bold uppercase tracking-widest text-accent mb-1">
            Conflicts of interest
          </p>
          <p className="text-sm whitespace-pre-wrap">{s.conflicts_of_interest}</p>
        </div>
      )}

      <div className="mt-6">
        <ActionButtons speaker={s} role={role} />
      </div>

      <div className="mt-10">
        <Checklist speaker={s} onToggle={toggle} onField={onField} />
      </div>

      {s.status === 'delivered' && (
        <div className="mt-8">
          <button
            disabled={!canFinalize(s)}
            onClick={finalize}
            className="font-display font-bold tracking-widest uppercase text-sm bg-primary text-white border-2 border-primary px-5 py-3 hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {canFinalize(s)
              ? 'Finalize and archive ✓'
              : 'Finalize and archive (fill required first)'}
          </button>
        </div>
      )}

      {s.status === 'lead' && (
        <div className="mt-8 text-sm text-ink-muted">
          Votes: {s.selection.votes_for.join(', ') || '(none yet)'}
        </div>
      )}

      {s.links.length > 0 && (
        <div className="mt-8">
          <h2 className="font-serif text-xl mb-2">Links</h2>
          <ul className="space-y-1 text-sm">
            {s.links.map(l => (
              <li key={l}>
                <a href={l} target="_blank" rel="noreferrer" className="text-primary-hover underline">
                  {l}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {s.notes && (
        <div className="mt-8">
          <h2 className="font-serif text-xl mb-2">Notes</h2>
          <p className="text-ink-muted whitespace-pre-wrap text-sm">{s.notes}</p>
        </div>
      )}

      {role === 'board' && (
        <details className="mt-12 border-t border-border pt-6">
          <summary className="cursor-pointer text-sm text-danger">Admin override</summary>
          <AdminOverride speaker={s} />
        </details>
      )}

      <div className="mt-12 pt-6 border-t border-border text-sm">
        <Link to="/pipeline" className="text-primary-hover underline">
          ← back to pipeline
        </Link>
      </div>
    </div>
  );
}
