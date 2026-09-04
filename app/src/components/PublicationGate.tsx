import { useState } from 'react';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { InlineContent } from '../content/InlineContent';
import { parisToday } from '../state/derived';
import { formatDecision, identifier, transitionDecision } from '../state/decisions';
import { canArchive, objectionWindowCloses, standingObjections } from '../state/governance';
import { blockers } from '../state/phases';
import {
  applyTransition,
  canTransition,
  type ConsentPayload,
  type ObjectionPayload,
  type ResolutionPayload,
  type Role,
  type Transition,
} from '../state/transitions';
import type { ConsentDecision, ObjectionResolution, Speaker } from '../data/types';

/**
 * The second gate (G-07, G-08): what has to be true before a seminar
 * recording goes online.
 *
 * Two permissions, from two parties, kept visibly apart on the screen
 * because they are kept apart in the rule. The speaker's block asks a
 * question and records an answer; the board's block records an approval and
 * counts a window. Neither block ever fills in the other's field, and no
 * control here writes `outcome: 'published'` -- only the archiving button
 * does, and only when `canArchive` allows it.
 *
 * Every rule the volunteer cannot satisfy leaves the control disabled with
 * the reason beside it, rather than failing on submit.
 */
export function PublicationGate({ speaker, role }: { speaker: Speaker; role: Role }) {
  const { config, mutateSpeakers } = useData();
  const { login } = useAuth();
  const [busy, setBusy] = useState(false);
  const locked = busy || !config;
  const today = parisToday();

  const p = speaker.publication;
  const gate = config
    ? canArchive(speaker, config, today)
    : { allowed: false, reason: 'Waiting for the configuration to load.' };
  const standing = standingObjections(p);
  const published = p.outcome === 'published';

  async function fire(t: Transition, payload?: ConsentPayload | ObjectionPayload | ResolutionPayload) {
    if (!login || !config || !canTransition(speaker, t, role)) return;
    setBusy(true);
    try {
      // The transformation reads `current`, never the `speaker` prop this
      // component rendered with: between the read and the write another
      // member may have objected, or the speaker may have withdrawn their
      // consent. Re-running `applyTransition` -- and with it `canArchive` --
      // against the freshly-read row is what makes that objection count.
      await mutateSpeakers(
        current =>
          current.map(sp =>
            sp.id === speaker.id ? applyTransition(sp, t, login, config, today, payload) : sp,
          ),
        formatDecision(transitionDecision(t, identifier(speaker.id), identifier(login), payload)),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-8 border border-border p-4 space-y-6">
      <div>
        <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] text-ink">
          Publishing the recording
        </h2>
        <p className="text-sm text-ink-muted mt-1">
          Two separate permissions are needed: the speaker&apos;s, and the board&apos;s.
        </p>
      </div>

      {published && !gate.allowed && (
        <p className="p-3 border-l-2 border-danger bg-danger/5 text-sm text-danger">
          <strong>This recording is online and should not be.</strong> {gate.reason} Take the
          recording down, then resolve this below.
        </p>
      )}

      <ConsentBlock speaker={speaker} role={role} disabled={locked} onSet={c => fire('consent-set', { consent: c })} />

      <BoardBlock
        speaker={speaker}
        role={role}
        disabled={locked}
        windowCloses={config && p.approved_on ? objectionWindowCloses(p, config) : ''}
        onApprove={() => fire('publication-approve')}
        onObject={reason => fire('publication-object', { reason })}
        onResolve={(resolution, note) => fire('publication-resolve', { resolution, note })}
      />

      {standing.length > 0 && (
        <div>
          <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-1">
            Objections standing
          </p>
          <ul className="text-sm space-y-1">
            {standing.map(o => (
              <li key={`${o.member}-${o.date}`}>
                <strong>{o.member}</strong> on {o.date}: {o.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ArchiveBlock
        speaker={speaker}
        role={role}
        disabled={locked}
        reason={gate.reason}
        allowed={gate.allowed}
        onArchive={() => fire('finalize-archive')}
        onArchiveOnly={() => fire('archive-unpublished')}
      />

      {published && (
        <div className="border-t border-border pt-4">
          <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-2">
            Tell people it is up
          </p>
          <InlineContent
            contentKey="toolkit/recording-announce"
            ctx={{ speaker, host: speaker.host_1, today }}
          />
        </div>
      )}
    </section>
  );
}

const CONSENT_CHOICES: { value: ConsentDecision; label: string; help: string }[] = [
  {
    value: 'granted',
    label: 'They agreed',
    help: 'The speaker told you, in writing, that the recording may be published.',
  },
  {
    value: 'refused',
    label: 'They refused, or withdrew their agreement',
    help: 'The recording must not be published, and any copy already online has to come down.',
  },
];

/**
 * The speaker's permission (G-07).
 *
 * There is no control here for "no answer yet", and that is deliberate:
 * `pending` is where the record starts, and leaving it alone is exactly what
 * a volunteer who has not heard back should do. A button that wrote it back
 * would be a button for turning a silence into a record of a silence -- one
 * step from a record of an agreement.
 */
function ConsentBlock({
  speaker,
  role,
  disabled,
  onSet,
}: {
  speaker: Speaker;
  role: Role;
  disabled: boolean;
  onSet: (consent: ConsentDecision) => void;
}) {
  const p = speaker.publication;
  const [choice, setChoice] = useState<ConsentDecision | ''>('');
  const editable = role === 'board' && canTransition(speaker, 'consent-set', role);

  return (
    <div>
      <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-1">
        The speaker&apos;s permission
      </p>
      <p className="text-sm">
        Recorded answer: <strong>{p.consent === '' ? 'not asked' : p.consent}</strong>
      </p>
      {!editable ? null : (
        <div className="mt-2 space-y-2">
          <fieldset className="space-y-1.5">
            <legend className="text-xs uppercase tracking-wider text-ink-muted">
              Record what the speaker told you
            </legend>
            {CONSENT_CHOICES.map(c => (
              <label key={c.value} className="flex gap-2 items-start text-sm">
                <input
                  type="radio"
                  name={`consent-${speaker.id}`}
                  value={c.value}
                  checked={choice === c.value}
                  onChange={() => setChoice(c.value)}
                  className="mt-1"
                />
                <span>
                  <span className="font-bold">{c.label}</span>{' '}
                  <span className="text-ink-muted">{c.help}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <p className="text-xs text-ink-muted">
            If they have not answered, leave this alone. Not hearing back is not an agreement, and
            no amount of waiting turns it into one.
          </p>
          <button
            type="button"
            disabled={disabled || choice === ''}
            onClick={() => choice !== '' && onSet(choice)}
            className="px-3 py-1.5 text-sm rounded bg-dominant text-white hover:opacity-90 disabled:opacity-50"
          >
            Record the speaker&apos;s answer
          </button>
        </div>
      )}
    </div>
  );
}

const RESOLUTION_CHOICES: { value: ObjectionResolution; label: string; help: string }[] = [
  {
    value: 'lift',
    label: 'Lift the objection',
    help: 'The concern was addressed. The recording goes back to the gate; it is not published by this.',
  },
  {
    value: 'withhold',
    label: 'Withhold the recording',
    help: 'The board decides not to publish. This can be lifted later, by a board member.',
  },
];

/** The board's half: an approval, an objection window counted in working
 *  days, and the objections themselves. */
function BoardBlock({
  speaker,
  role,
  disabled,
  windowCloses,
  onApprove,
  onObject,
  onResolve,
}: {
  speaker: Speaker;
  role: Role;
  disabled: boolean;
  windowCloses: string;
  onApprove: () => void;
  onObject: (reason: string) => void;
  onResolve: (resolution: ObjectionResolution, note: string) => void;
}) {
  const p = speaker.publication;
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [resolution, setResolution] = useState<ObjectionResolution>('lift');
  const canApprove = canTransition(speaker, 'publication-approve', role);
  const canObject = canTransition(speaker, 'publication-object', role);
  const canResolve = canTransition(speaker, 'publication-resolve', role);

  return (
    <div className="space-y-3">
      <p className="font-display font-bold uppercase tracking-widest text-[11px] text-ink-muted mb-1">
        The board&apos;s approval
      </p>
      <p className="text-sm">
        {p.approved_on ? (
          <>
            Approved by <strong>{p.approved_by}</strong> on {p.approved_on}
            {windowCloses && ` · objection window closes ${windowCloses}`}
          </>
        ) : (
          'Not approved yet.'
        )}
      </p>

      {canApprove && (
        <button
          type="button"
          disabled={disabled}
          onClick={onApprove}
          className="px-3 py-1.5 text-sm rounded bg-dominant text-white hover:opacity-90 disabled:opacity-50"
        >
          {p.approved_on ? 'Approve again (restarts the window)' : 'Approve for publication'}
        </button>
      )}

      {canObject && (
        <div className="space-y-1.5">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-ink-muted">
              Reason for objecting to publishing this recording
            </span>
            <textarea
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={2}
              className="w-full px-2 py-1 text-sm mt-1"
            />
          </label>
          <button
            type="button"
            disabled={disabled || reason.trim() === ''}
            onClick={() => onObject(reason)}
            className="px-3 py-1.5 text-sm rounded border border-danger text-danger hover:bg-danger hover:text-white disabled:opacity-50"
          >
            Object
          </button>
          <span className="block text-xs text-ink-muted">
            Required: an objection stops a named researcher&apos;s talk being published, so the
            register has to say why.
          </span>
        </div>
      )}

      {canResolve && (
        <div className="space-y-1.5 border-t border-border pt-3">
          <fieldset className="space-y-1.5">
            <legend className="text-xs uppercase tracking-wider text-ink-muted">
              Resolve the objections
            </legend>
            {RESOLUTION_CHOICES.map(c => (
              <label key={c.value} className="flex gap-2 items-start text-sm">
                <input
                  type="radio"
                  name={`resolution-${speaker.id}`}
                  value={c.value}
                  checked={resolution === c.value}
                  onChange={() => setResolution(c.value)}
                  className="mt-1"
                />
                <span>
                  <span className="font-bold">{c.label}</span>{' '}
                  <span className="text-ink-muted">{c.help}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-ink-muted">
              What was decided
            </span>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={2}
              className="w-full px-2 py-1 text-sm mt-1"
            />
          </label>
          <button
            type="button"
            disabled={disabled || note.trim() === ''}
            onClick={() => onResolve(resolution, note)}
            className="px-3 py-1.5 text-sm rounded bg-dominant text-white hover:opacity-90 disabled:opacity-50"
          >
            Resolve
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Closing the record -- with the recording, or without it.
 *
 * **Publishing and archiving are two things** (R43). They used to be one
 * button, which meant a recording nobody may publish was a record nobody
 * could close: a speaker who says no, or a board that resolves to withhold,
 * left the event sitting in `delivered` for ever with a disabled button and
 * a sentence explaining why it would stay disabled. Everything else about
 * the wrap-up was finished and there was nothing left to do but wait for a
 * permission that was never coming.
 *
 * So the control is one of two, and which one is not a choice a volunteer
 * makes -- it is a fact about the record:
 *
 * - somebody has *refused* (`publicationRefused`): the button archives, and
 *   says only that. It cannot publish; `applyTransition` refuses to write a
 *   published outcome on this path at all.
 * - otherwise: the button is the one that publishes, exactly as before,
 *   behind the gate. An unanswered consent and an objection window still
 *   running are waits, not refusals, and a wait must not offer a way to
 *   close the record around it.
 *
 * Both are disabled with the reason beside them whenever the delivered-phase
 * checklist is still incomplete -- the wrap-up is owed either way -- so a
 * volunteer meets that rule as a sentence to read, never as a failed save.
 */
function ArchiveBlock({
  speaker,
  role,
  disabled,
  allowed,
  reason,
  onArchive,
  onArchiveOnly,
}: {
  speaker: Speaker;
  role: Role;
  disabled: boolean;
  allowed: boolean;
  reason: string;
  onArchive: () => void;
  onArchiveOnly: () => void;
}) {
  const refused = canTransition(speaker, 'archive-unpublished', role);
  if (!refused && !canTransition(speaker, 'finalize-archive', role)) return null;
  // Naming what is in the way, rather than pointing at the checklist above:
  // one of the things that can be in the way is not in the checklist above.
  // The registration check sits two weeks before the talk, and a volunteer
  // told to fill in the delivered fields would have gone looking for a field
  // that is already filled in.
  const outstanding = speaker.status === 'delivered' ? blockers(speaker) : [];
  const wrapUp = outstanding.map(b => b.why).join(' ');
  const blocked = refused ? outstanding.length > 0 : !allowed || outstanding.length > 0;
  const message = refused ? wrapUp : !allowed ? reason : wrapUp;

  const label = refused
    ? 'Archive without publishing'
    : speaker.publication.outcome === 'published'
      ? 'Publish the recording again'
      : 'Publish the recording and archive';

  return (
    <div className="border-t border-border pt-4 space-y-2">
      {refused && (
        <p className="text-sm text-ink-muted">
          {reason} The rest of the record is still worth closing, so this archives it and
          publishes nothing.
        </p>
      )}
      <button
        type="button"
        disabled={disabled || blocked}
        onClick={refused ? onArchiveOnly : onArchive}
        className="font-display font-bold tracking-widest uppercase text-sm bg-dominant text-white border-2 border-dominant px-5 py-3 hover:bg-dominant-hover disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {label}
      </button>
      {blocked && <p className="text-sm text-danger">{message}</p>}
    </div>
  );
}
