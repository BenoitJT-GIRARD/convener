import { useParams, Navigate, Link } from 'react-router-dom';
import { isSafeHref } from '../content/fetch';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { ActionButtons } from '../components/ActionButtons';
import { AdminOverride } from '../components/AdminOverride';
import { ClosedRecord } from '../components/ClosedRecord';
import { DatePanel } from '../components/DatePanel';
import { RegistrationCount } from '../components/RegistrationCount';
import { PublicationGate } from '../components/PublicationGate';
import { Checklist } from '../components/Checklist';
import { InlineContent } from '../content/InlineContent';
import { setField, phaseOf, type FieldKey } from '../state/phases';
import { assignItem } from '../state/assignment';
import { dataEdit, identifier, itemKey } from '../state/decisions';
import { effectiveStatus, parisToday, roomText } from '../state/derived';
import { LoadError } from '../components/LoadError';
import type { Config, Speaker } from '../data/types';

export function SpeakerPage() {
  const { id } = useParams();
  const { speakers, loading, error, config, mutateSpeakers } = useData();
  const { login } = useAuth();
  const role = useRole();
  if (loading || !role) return <p className="text-ink-muted">Reading the records from GitHub…</p>;
  if (error) return <LoadError message={error} />;
  const s = speakers.find(sp => sp.id === id);
  if (!s) return <Navigate to="/pipeline" replace />;
  // What the clock says, against what the record says. The header shows the
  // *record*: a header that moved on its own while the checklist below it did
  // not is exactly the mismatch R40 records, and a status nobody wrote is not
  // a status this page should assert. Where the two differ, the difference is
  // said out loud and the control that closes it is at the end of the
  // checklist. `tools/convener_ops/maintenance/sweep.py` is still the
  // unattended writer, and now it is not the only way through.
  const clockSays = config ? effectiveStatus(s, config, new Date()) : s.status;
  const timePassed = clockSays !== s.status;

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

  /**
   * What fills the journey's `button-group` lines on this record.
   *
   * Keyed by journey key rather than chosen here: `state/phases.ts` says
   * where the date negotiation and the closing buttons sit inside each
   * status, and this map only says what they are. Only the current phase's
   * keys are ever read, so the three date panels and the one set of buttons
   * listed here render one at a time.
   *
   * The order that comes out of it is the correction: what you need to know,
   * then what you do, then how you record that you did it. The buttons used
   * to sit above the whole checklist, which put *Mark invitation sent* in
   * front of the dates the invitation names.
   */
  const slots: Record<string, React.ReactNode> = {
    'approved/offer-dates': <DatePanel speaker={s} role={role} mode="offer" />,
    'invited/replies': <DatePanel speaker={s} role={role} mode="reply" />,
    'confirmed/lock-date': <DatePanel speaker={s} role={role} mode="lock" />,
    'lead/board-vote': <ActionButtons speaker={s} role={role} />,
    'approved/send-invitation': <ActionButtons speaker={s} role={role} />,
    'invited/decline': <ActionButtons speaker={s} role={role} />,
    'scheduled/mark-delivered': <ActionButtons speaker={s} role={role} />,
    'delivered/count-registrations': (
      <RegistrationCount speaker={s} onCounted={n => onField('registrations', String(n))} />
    ),
  };

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
      {timePassed && (
        <p className="text-sm text-dominant mt-1">
          This talk&apos;s time has passed. Record it as delivered at the end of the runbook
          below, and the wrap-up opens.
        </p>
      )}
      <p className="text-ink-muted mt-1 text-sm">
        Proposed by <strong>{s.proposed_by || '(unknown)'}</strong> · source: {s.source}
        {s.email && ` · ${s.email}`}
      </p>

      {s.conflicts_of_interest && (
        <div className="mt-4 p-3 border-l-2 border-dominant bg-dominant-tint">
          <p className="text-xs font-display font-bold uppercase tracking-widest text-dominant mb-1">
            Conflicts of interest
          </p>
          <p className="text-sm whitespace-pre-wrap">{s.conflicts_of_interest}</p>
        </div>
      )}

      {/* A status with no journey of its own -- parked, declined, archived.
          What it needs is a report rather than a checklist: why it is
          closed, when, and what could reopen it. The control that does the
          reopening follows it, in the order every other status is laid out
          in -- what you need to know, then what you do. */}
      {!hasPhase && (
        <div className="mt-6 space-y-4">
          <ClosedRecord speaker={s} config={config} />
          <ActionButtons speaker={s} role={role} />
          {/* The message that says the video is up, filled in from this
              record. This page is the only place it is ever reachable
              filled in: publishing writes `archived` in the same gesture,
              so no delivered record ever carries it, and
              `screens/Templates.tsx` renders every template blank. It came
              here with the gate and stays after it, because it is a text to
              copy and not a control over the record. */}
          {s.status === 'archived' && s.publication.outcome === 'published' && (
            <div className="border-t border-border pt-4">
              <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-2">
                Tell people it is up
              </p>
              <InlineContent
                contentKey="toolkit/recording-announce"
                ctx={{ speaker: s, host: s.host_1, today: parisToday() }}
              />
            </div>
          )}
        </div>
      )}

      {hasPhase && (
        <div className="mt-10">
          <Checklist
            speaker={s}
            onToggle={toggle}
            onField={onField}
            onAssign={assign}
            people={people}
            config={config}
            slots={slots}
          />
        </div>
      )}

      {/* Archiving publishes a named researcher's recording, so it is no
          longer a bare button here: it lives behind the second gate (G-07,
          G-08), which asks for the speaker's permission and the board's
          separately.

          `delivered` and nowhere else. It used to be drawn on an archived
          record too, on the argument that a speaker may withdraw their
          permission afterwards and that has to stay actionable. The need is
          real and the place was wrong: it left an event whose whole meaning
          is that the question is settled asking it again, in radio buttons.
          A withdrawal is recorded where speakers are asked (`screens/
          Consent.tsx`), and the board's own half reopens the record first --
          `ClosedRecord` above says so, and `ActionButtons` draws the door. */}
      {s.status === 'delivered' && <PublicationGate speaker={s} role={role} />}

      <SpeakerDetails speaker={s} config={config} />

      {role === 'board' && (
        <details className="mt-12 border-t border-border pt-6">
          <summary className="cursor-pointer text-sm text-danger">Admin override</summary>
          <AdminOverride speaker={s} />
        </details>
      )}

      <div className="mt-12 pt-6 border-t border-border text-sm">
        <Link to="/pipeline" className="text-field-text underline">
          ← back to pipeline
        </Link>
      </div>
    </div>
  );
}

function SpeakerDetails({ speaker: s, config }: { speaker: Speaker; config: Config | null }) {
  const eventFields: { label: string; value: string }[] = [
    { label: 'Edition', value: s.edition_code },
    { label: 'Date', value: s.date },
    { label: 'Time (Paris)', value: s.time },
    // The way into the room, from whichever source has it. This read
    // `s.zoom_link` alone, so on an instance whose account is one permanent
    // room -- where that field is empty by design (D-06) -- the panel a
    // volunteer checks before the seminar showed no room at all, while every
    // registrant was being sent one. The record and the message now answer
    // from the same composition (`state/derived.ts::roomText`).
    //
    // Safe to draw here because this cockpit is private (D-15), and
    // `publish-showcase.yml` refuses to publish a build carrying a room.
    { label: 'Room', value: roomText(s, config) },
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
                    className="text-field-text underline break-all"
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
