/**
 * Asking the speakers whose recordings are still unpublished (G-15).
 *
 * Phase 2 built a gate that cannot publish a recording without a recorded
 * `granted`, and left thirty-one real researchers on the other side of it,
 * none of them ever asked. This screen is the means to ask. It does not ask
 * on anybody's behalf -- a person writes to a person -- and it is built so
 * that a volunteer who has heard nothing back cannot leave a mark saying
 * otherwise.
 *
 * Three things it deliberately cannot do:
 *
 * 1. **Record an answer nobody gave.** The only write on this screen is the
 *    existing `consent-set` transition, whose payload type is
 *    `ConsentDecision` -- `granted | refused`, with no third member. There is
 *    no "assume", no "no answer yet", and nothing that acts on more than one
 *    record at a time: a control that wrote thirty-one answers at once would
 *    be a control for recording thirty-one conversations nobody had.
 * 2. **Keep a list.** Who still owes an answer is `awaitingAnswer` over the
 *    records themselves, recomputed on every render. A stored list of people
 *    to contact would be a second source of truth, and the first thing it
 *    would do is disagree with the data -- always in the direction of a
 *    speaker ticked off without being written to.
 * 3. **Make a refusal feel like a failure.** The two answers sit side by
 *    side, in the same type, in the same colour, behind the same button. A
 *    screen that paints "they refused" in red is a screen that quietly pays a
 *    volunteer to come back with a yes.
 *
 * The message itself is a template like every other (`content/InlineContent`),
 * and the sentence in it saying what would be published is composed from the
 * field classification in `state/consent.ts`. Nobody has to remember to keep
 * the two in step, because nobody wrote the sentence.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useRole } from '../auth/useRole';
import { useData } from '../data/DataContext';
import { InlineContent } from '../content/InlineContent';
import { LoadError } from '../components/LoadError';
import { answeredList, awaitingAnswerList } from '../state/consent';
import { formatDecision, identifier, transitionDecision } from '../state/decisions';
import { parisToday } from '../state/derived';
import { applyTransition, canTransition, type Role } from '../state/transitions';
import type { ConsentDecision, Speaker } from '../data/types';

const MESSAGE_KEY = 'toolkit/emails/consent-request';

/**
 * The two answers, in the order a speaker might give either.
 *
 * Same shape, same length of explanation, same weight on the page. The
 * refusal's help text says what actually happens next, and what does not:
 * nothing about the talk, the series or a future invitation changes. That is
 * not reassurance for the speaker -- they will never see this screen -- it is
 * for the volunteer, who is about to record a "no" and should not feel they
 * are recording a loss.
 */
const ANSWERS: { value: ConsentDecision; label: string; help: string }[] = [
  {
    value: 'granted',
    label: 'They agreed',
    help: 'They told us, in writing, that the recording may be published. It still goes through the board and the objection window before it goes online.',
  },
  {
    value: 'refused',
    label: 'They would rather we did not',
    help: 'A complete answer, and an ordinary one. The recording stays offline and any copy already published comes out of the feed. Nothing about their talk, their place in the series or a future invitation changes.',
  },
];

export function Consent() {
  const { speakers, loading, error } = useData();
  const role = useRole();

  if (loading || !role) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <LoadError message={error} />;

  const waiting = awaitingAnswerList(speakers);
  const answered = answeredList(speakers);

  return (
    <div>
      <div className="mb-8">
        <p className="text-xs font-bold tracking-[0.14em] uppercase text-accent mb-2 flex items-center gap-3">
          <span className="h-0.5 bg-accent w-8" />
          Permissions
        </p>
        <h1 className="font-display font-extrabold text-3xl uppercase tracking-tight">
          Recording consent
        </h1>
        <p className="text-sm text-ink-muted mt-3 max-w-prose">
          A recording is published only when the speaker has told us it may be. This page says who
          is still to be written to, offers the message to send them, and records what they answer
          &mdash; nothing more. It writes to nobody on your behalf.
        </p>
      </div>

      <section className="mb-10">
        <header className="flex items-baseline gap-3 mb-4">
          <span className="font-mono text-xs text-accent">01</span>
          <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] text-ink">
            Still to be asked
          </h2>
          <span className="text-xs text-ink-muted italic">
            Every talk given whose speaker has not answered
          </span>
          <span className="ml-auto font-mono text-xs text-ink-faint tracking-wider">
            {waiting.length} {waiting.length === 1 ? 'speaker' : 'speakers'}
          </span>
        </header>

        {waiting.length === 0 ? (
          <p className="text-ink-muted text-sm pl-7 italic">
            Everyone who has given a talk has answered.
          </p>
        ) : (
          <>
            <p className="text-sm text-ink-muted max-w-prose mb-4 pl-7">
              Nobody on this list has said no. Nobody on it has said yes either &mdash; they have
              not been asked, and until one of them answers there is nothing to record here. If a
              speaker never replies, leave their record exactly as it is: waiting is not an
              agreement, and no length of waiting turns it into one.
            </p>
            <ol className="divide-y divide-border border-y border-border">
              {waiting.map(s => (
                <AwaitingRow key={s.id} speaker={s} role={role} />
              ))}
            </ol>
          </>
        )}
      </section>

      <section className="mb-10">
        <header className="flex items-baseline gap-3 mb-4">
          <span className="font-mono text-xs text-accent">02</span>
          <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] text-ink">
            Answered
          </h2>
          <span className="text-xs text-ink-muted italic">
            Both answers are outcomes; neither is a failure
          </span>
          <span className="ml-auto font-mono text-xs text-ink-faint tracking-wider">
            {answered.length} {answered.length === 1 ? 'answer' : 'answers'}
          </span>
        </header>
        {answered.length === 0 ? (
          <p className="text-ink-muted text-sm pl-7 italic">Nobody has answered yet.</p>
        ) : (
          <ol className="divide-y divide-border border-y border-border">
            {answered.map(s => (
              <li
                key={s.id}
                className="grid grid-cols-[7rem_1fr_auto] gap-4 items-center py-3 px-2"
              >
                <Link
                  to={`/speakers/${s.id}`}
                  className="font-mono text-xs text-accent uppercase tracking-wider truncate no-underline"
                >
                  {s.edition_code || s.id}
                </Link>
                <p className="text-sm text-ink truncate">
                  <strong className="font-semibold">{s.name}</strong>
                  {s.affiliation && <span className="text-ink-muted"> · {s.affiliation}</span>}
                </p>
                <span className="font-mono text-xs text-ink-muted">
                  {s.publication.consent === 'granted' ? 'agreed' : 'would rather we did not'}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

/** One speaker still to be written to: who they are, the message to send, and
 *  the place to put what they answer. */
function AwaitingRow({ speaker, role }: { speaker: Speaker; role: Role }) {
  const [showMessage, setShowMessage] = useState(false);
  return (
    <li>
      <div className="grid grid-cols-[7rem_1fr_auto] gap-4 items-center py-3 px-2">
        <Link
          to={`/speakers/${speaker.id}`}
          className="font-mono text-xs text-accent uppercase tracking-wider truncate no-underline"
        >
          {speaker.edition_code || speaker.id}
        </Link>
        <div className="min-w-0">
          <p className="font-medium text-sm text-ink truncate">{speaker.title || speaker.name}</p>
          <p className="text-xs text-ink-muted truncate">
            <strong className="font-semibold">{speaker.name}</strong>
            {speaker.affiliation && ` · ${speaker.affiliation}`}
            {speaker.date && ` · ${speaker.date}`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowMessage(!showMessage)}
          className="font-display font-bold text-[10px] tracking-widest uppercase text-primary-hover border border-border px-2 py-0.5 hover:bg-primary-soft"
        >
          {showMessage ? 'Hide the message' : 'Show the message'}
        </button>
      </div>

      {showMessage && (
        <div className="ml-[7.25rem] mr-2 mb-3 p-3 bg-surface border border-border">
          <InlineContent
            contentKey={MESSAGE_KEY}
            ctx={{ speaker, today: parisToday() }}
            variant="inline"
          />
        </div>
      )}

      <RecordAnswer speaker={speaker} role={role} />
    </li>
  );
}

/**
 * Recording what one speaker replied.
 *
 * Nothing is pre-selected, so the button cannot be pressed by reflex: a
 * volunteer has to say which of the two things happened before there is
 * anything to submit. The rule a volunteer cannot satisfy -- only the board
 * records consent -- removes the control and prints the reason, rather than
 * offering it and failing on save.
 */
function RecordAnswer({ speaker, role }: { speaker: Speaker; role: Role }) {
  const { config, mutateSpeakers } = useData();
  const { login } = useAuth();
  const [choice, setChoice] = useState<ConsentDecision | ''>('');
  const [busy, setBusy] = useState(false);

  if (!canTransition(speaker, 'consent-set', role)) {
    return (
      <p className="ml-[7.25rem] mr-2 mb-3 text-xs text-ink-muted">
        A board member records what the speaker answers. Anybody can send the message.
      </p>
    );
  }

  async function record(consent: ConsentDecision) {
    if (!login || !config) return;
    setBusy(true);
    try {
      const today = parisToday();
      // The transformation reads `current`, never the `speaker` this row
      // rendered with: a speaker may have written to somebody else in the
      // meantime, and the answer that lands is the one applied to the row as
      // it stands on the remote.
      await mutateSpeakers(
        current =>
          current.map(sp =>
            sp.id === speaker.id
              ? applyTransition(sp, 'consent-set', login, config, today, { consent })
              : sp,
          ),
        formatDecision(
          transitionDecision('consent-set', identifier(speaker.id), identifier(login), {
            consent,
          }),
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ml-[7.25rem] mr-2 mb-3 space-y-2">
      <fieldset className="space-y-1.5">
        <legend className="text-xs uppercase tracking-wider text-ink-muted">
          What {speaker.name || 'the speaker'} answered
        </legend>
        {ANSWERS.map(a => (
          <label key={a.value} className="flex gap-2 items-start text-sm">
            <input
              type="radio"
              name={`consent-answer-${speaker.id}`}
              value={a.value}
              checked={choice === a.value}
              onChange={() => setChoice(a.value)}
              className="mt-1"
            />
            <span>
              <span className="font-bold">{a.label}</span>{' '}
              <span className="text-ink-muted">{a.help}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <button
        type="button"
        disabled={busy || !config || choice === ''}
        onClick={() => choice !== '' && record(choice)}
        className="px-3 py-1.5 text-sm rounded bg-primary text-white hover:opacity-90 disabled:opacity-50"
      >
        Record their answer
      </button>
    </div>
  );
}
