import { useParams, Navigate, Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { ActionButtons } from '../components/ActionButtons';
import { Checklist } from '../components/Checklist';
import { phaseOf, gatesComplete } from '../state/phases';

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
    const nextProgress = { ...s.runbook_progress, [key]: value };
    let next = { ...s, runbook_progress: nextProgress };
    const phase = phaseOf(s.status);
    if (phase?.autoAdvance && gatesComplete(phase, nextProgress)) {
      next = { ...next, status: phase.autoAdvance };
    }
    await saveSpeakers(
      speakers.map(sp => (sp.id === s.id ? next : sp)),
      `data: ${s.id} runbook ${key}=${value}`,
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
        {s.host && ` · host: ${s.host}`}
        {s.co_hosts.length > 0 && ` · co-hosts: ${s.co_hosts.join(', ')}`}
      </p>

      <div className="mt-6">
        <ActionButtons speaker={s} role={role} />
      </div>

      <div className="mt-10">
        <Checklist speaker={s} onToggle={toggle} />
      </div>

      {s.title && (
        <div className="mt-10">
          <h2 className="font-serif text-xl mb-2">Talk</h2>
          <p className="font-medium">{s.title}</p>
          {s.abstract && (
            <p className="text-ink-muted mt-2 whitespace-pre-wrap text-sm">{s.abstract}</p>
          )}
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
                <a href={l} target="_blank" rel="noreferrer" className="text-primary underline">
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

      <div className="mt-12 pt-6 border-t border-border text-sm">
        <Link to="/pipeline" className="text-primary underline">
          ← back to pipeline
        </Link>
      </div>
    </div>
  );
}
