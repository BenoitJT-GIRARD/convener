import { useParams, Navigate, Link } from 'react-router-dom';
import { isSafeHref } from '../content/fetch';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { ActionButtons } from '../components/ActionButtons';
import { AdminOverride } from '../components/AdminOverride';
import { PublicationGate } from '../components/PublicationGate';
import { Checklist } from '../components/Checklist';
import { setField, phaseOf, type FieldKey } from '../state/phases';
import { assignItem } from '../state/assignment';
import { dataEdit, identifier, itemKey } from '../state/decisions';
import { effectiveStatus } from '../state/derived';
import { LoadError } from '../components/LoadError';
import type { Speaker } from '../data/types';

export function SpeakerPage() {
  const { id } = useParams();
  const { speakers, loading, error, config, mutateSpeakers } = useData();
  const { login } = useAuth();
  const role = useRole();
  if (loading || !role) return <p className="text-ink-muted">Reading the records from GitHub…</p>;
  if (error) return <LoadError message={error} />;
  const s = speakers.find(sp => sp.id === id);
  if (!s) return <Navigate to="/pipeline" replace />;
  // Display only: what has aired, not necessarily what's recorded yet — the
  // scheduled job (tools/convener_ops/maintenance/sweep.py) is the single writer for that.
  const displayStatus = config ? effectiveStatus(s, config, new Date()) : s.status;

  async function toggle(key: string, value: boolean) {
    if (!login || !id) return;
    await mutateSpeakers(
      current =>
        current.map(sp =>
          sp.id === id
            ? { ...sp, runbook_progress: { ...sp.runbook_progress, [key]: value } }
            : sp,
        ),
      // A box ticked on the runbook is the record catching up with work
      // already done, not an act of the register. The key is the journey's
      // own, from `state/phases.ts`, and names no one.
      dataEdit(identifier(id), { part: 'runbook-box', key: itemKey(key), ticked: value }),
    );
  }

  async function onField(k: FieldKey, v: string) {
    if (!login || !id) return;
    await mutateSpeakers(
      current => current.map(sp => (sp.id === id ? setField(sp, k, v) : sp)),
      // A talk detail typed in. `k` is a field name, never its value: the
      // value is in the diff, where the consent classification governs it.
      // `Edit` is what holds that -- `part: 'field'` carries a `FieldKey`
      // and has nowhere to put `v` -- rather than the care of whoever edits
      // this line next.
      dataEdit(identifier(id), { part: 'field', key: k }),
    );
  }

  // Who can be put down for a line: the board, plus whichever hosts this
  // record already names. Hosts are here because a host is who a runbook line
  // usually belongs to and is not necessarily a board member; the record's own
  // `host_1`/`host_2` are read as the *candidates offered*, never as an
  // answer -- an unassigned line stays unassigned until somebody chooses.
  const people = Array.from(
    new Set([...(config?.board ?? []).map(m => m.login), s.host_1, s.host_2].filter(Boolean)),
  );

  async function assign(key: string, who: string) {
    if (!login || !id) return;
    await mutateSpeakers(
      current => assignItem(current, id, key, who, config),
      // Who owes a line is not a decision of the register, and the login
      // put down is deliberately left out of the subject -- the line is
      // named, the person is not.
      dataEdit(identifier(id), { part: 'owner', key: itemKey(key), cleared: who === '' }),
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
        Status: <strong>{displayStatus}</strong>
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
          <Checklist
            speaker={s}
            onToggle={toggle}
            onField={onField}
            onAssign={assign}
            people={people}
            config={config}
          />
        </div>
      )}

      {/* Archiving publishes a named researcher's recording, so it is no
          longer a bare button here: it lives behind the second gate (G-10,
          G-15), which asks for the speaker's permission and the board's
          separately. Still shown once archived, because a speaker may
          withdraw their permission afterwards and that has to be actionable. */}
      {(s.status === 'delivered' || s.status === 'archived') && (
        <PublicationGate speaker={s} role={role} />
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
  const hasVotes =
    s.selection.ballots.length > 0 || !!s.selection.opened_on || !!s.selection.decided_on;

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
            {s.selection.opened_on && (
              <DetailLine label="Opened on" value={s.selection.opened_on} mono />
            )}
            {s.selection.ballots.length === 0 && (
              <DetailLine label="Ballots" value="(none cast yet)" />
            )}
            {/* One line per ballot rather than a list of names: a recusal is
                only meaningful next to the reason given for it, and the
                comments are what makes the decision readable years later. */}
            {s.selection.ballots.map(b => (
              <DetailLine
                key={b.voter}
                label={b.voter}
                value={[b.value, b.coi_reason, b.comment].filter(Boolean).join(' — ')}
              />
            ))}
            {s.selection.decided_on && (
              <DetailLine label="Decided on" value={s.selection.decided_on} mono />
            )}
          </dl>
        </DetailBlock>
      )}

      {s.links.length > 0 && (
        <DetailBlock title="Links">
          <ul className="space-y-1 text-sm">
            {/* `links` comes from the public, unreviewed proposal intake
                (tools/convener_ops/journey/proposal.py) with no scheme check of its
                own -- a candidate submitting `javascript:...` as a
                "link" reaches this render unfiltered. `isSafeHref`
                (content/fetch.ts, the same allowlist `handbookUrl`
                already applies to handbook markdown) is the guard: an
                unsafe scheme still shows the board what was submitted,
                just never as a clickable href a board member's own
                click could execute. */}
            {s.links.map(l => (
              <li key={l}>
                {isSafeHref(l) ? (
                  <a
                    href={l}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary-hover underline break-all"
                  >
                    {l}
                  </a>
                ) : (
                  <span className="break-all">{l}</span>
                )}
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
