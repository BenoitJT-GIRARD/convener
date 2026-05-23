import { useParams, Navigate, Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { ActionButtons } from '../components/ActionButtons';
import { AdminOverride } from '../components/AdminOverride';
import { Checklist } from '../components/Checklist';
import { canFinalize, setField, phaseOf, type FieldKey } from '../state/phases';
import type { Speaker } from '../data/types';

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

  const hasPhase = phaseOf(s.status) !== undefined;

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
        {s.email && ` · ${s.email}`}
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

      {hasPhase && (
        <div className="mt-10">
          <Checklist speaker={s} onToggle={toggle} onField={onField} />
        </div>
      )}

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

      <SpeakerDetails speaker={s} />

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

function SpeakerDetails({ speaker: s }: { speaker: Speaker }) {
  const eventFields: { label: string; value: string }[] = [
    { label: 'Edition', value: s.edition_code },
    { label: 'Date', value: s.date },
    { label: 'Time (Paris)', value: s.time },
    { label: 'Zoom link', value: s.zoom_link },
    { label: 'YouTube URL', value: s.youtube_url },
    { label: 'Forum thread', value: s.forum_thread },
  ].filter(f => f.value);
  const metricFields: { label: string; value: number | null }[] = [
    { label: 'Registrations', value: s.metrics.registrations },
    { label: 'Live peak', value: s.metrics.live_peak },
    { label: 'YouTube views (30d)', value: s.metrics.youtube_views_30d },
    { label: 'Forum replies', value: s.metrics.forum_replies },
  ].filter(f => f.value !== null);
  const hasVotes = s.selection.votes_for.length > 0 || !!s.selection.decided_on;

  return (
    <section className="mt-12 border-t border-border pt-8">
      <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] text-ink mb-6">
        Speaker file
      </h2>

      <DetailBlock title="Talk">
        {s.title ? (
          <>
            <p className="font-medium">{s.title}</p>
            {s.abstract && (
              <p className="text-ink-muted mt-2 whitespace-pre-wrap text-sm">{s.abstract}</p>
            )}
          </>
        ) : (
          <p className="text-ink-faint text-sm italic">No title captured yet.</p>
        )}
      </DetailBlock>

      {eventFields.length > 0 && (
        <DetailBlock title="Event">
          <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-2 text-sm">
            {eventFields.map(f => (
              <DetailLine key={f.label} label={f.label} value={f.value} />
            ))}
          </dl>
        </DetailBlock>
      )}

      {metricFields.length > 0 && (
        <DetailBlock title="Metrics">
          <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-2 text-sm">
            {metricFields.map(f => (
              <DetailLine key={f.label} label={f.label} value={String(f.value)} mono />
            ))}
          </dl>
        </DetailBlock>
      )}

      {hasVotes && (
        <DetailBlock title="Selection vote">
          <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-2 text-sm">
            <DetailLine
              label="Votes for"
              value={s.selection.votes_for.join(', ') || '(none)'}
            />
            {s.selection.decided_on && (
              <DetailLine label="Decided on" value={s.selection.decided_on} mono />
            )}
          </dl>
        </DetailBlock>
      )}

      {s.links.length > 0 && (
        <DetailBlock title="Links">
          <ul className="space-y-1 text-sm">
            {s.links.map(l => (
              <li key={l}>
                <a
                  href={l}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary-hover underline break-all"
                >
                  {l}
                </a>
              </li>
            ))}
          </ul>
        </DetailBlock>
      )}

      {s.notes && (
        <DetailBlock title="Notes">
          <p className="text-ink-muted whitespace-pre-wrap text-sm">{s.notes}</p>
        </DetailBlock>
      )}
    </section>
  );
}

function DetailBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-2">
        {title}
      </p>
      {children}
    </div>
  );
}

function DetailLine({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="text-ink-muted">{label}</dt>
      <dd className={mono ? 'font-mono break-all' : 'break-all'}>{value}</dd>
    </>
  );
}
