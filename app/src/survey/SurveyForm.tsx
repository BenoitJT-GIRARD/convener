import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { encryptSurveyResponse, importEventPublicKey } from './encrypt';
import type { SurveyResponse } from './encrypt';

// Same idiom as `signup/SignupForm.tsx`'s own `BASE`: the base the app
// itself is served from, so the fetch below resolves against the deployed
// route rather than wherever the browser happens to be.
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

// The survey shares `services/signup-relay` with registration -- it is a
// second *route* on the same worker (`/survey`, dispatching
// `survey-response-submitted`), not a second deployment -- so it shares
// registration's own relay URL rather than needing a second environment
// variable and a second secret to configure. See
// `services/signup-relay/README.md`, "A second route, not a second worker."
// A missing relay is a normal state (D-13), same as `SignupForm.tsx`.
function surveyRelayUrl(): string | undefined {
  const base = import.meta.env.VITE_SIGNUP_RELAY_URL as string | undefined;
  if (!base) return undefined;
  return `${base.replace(/\/$/, '')}/survey`;
}

const CONTACT_EMAIL = 'reading-group@example.test';

// R-37 (fix round 1): the page-level layer of the switch enforcement.
// `'closed'` means the key loaded fine but this event's survey is not
// enabled -- distinct from `'unavailable'`, a technical failure to fetch
// or validate the public key itself. Both refuse to render the form; they
// are told apart only so the message can be honest about which is true.
type PageState =
  | { status: 'loading' }
  | { status: 'unavailable' }
  | { status: 'closed' }
  | { status: 'ready'; publicKeyPem: string };

type SubmitState = 'idle' | 'sending' | 'sent' | 'error';

/** Where an event's published public half is fetched from -- identical to
 *  `signup/SignupForm.tsx::eventPublicKeyUrl`: same-origin, the same key an
 *  event's registration was encrypted under (spec S:6, "meme entree que
 *  l'inscription"). Not exported, for the same react-refresh reason
 *  `SignupForm.tsx` gives. */
function eventPublicKeyUrl(eventId: string): string {
  return `${BASE}/keys/events/${encodeURIComponent(eventId)}.pub`;
}

/** `scripts/copy-survey-status.mjs`'s own destination -- see that script's
 *  and `survey-status-projection.mjs`'s docstrings for the whole
 *  publish-and-fetch pipeline this closes (R-37): a bare JSON array of
 *  the event ids currently open for the survey, derived from
 *  `data/speakers.yml`'s `survey_enabled` field and published outside the
 *  consent gate entirely, because it is an operational fact rather than
 *  programme data. */
function surveyStatusUrl(): string {
  return `${BASE}/survey-status.json`;
}

// Same reasoning, same values, as `SignupForm.tsx`'s own two timeouts: a
// hung request has no other end, and a page that never says so is silence,
// not the refusal requirement 4 asks for.
const KEY_FETCH_TIMEOUT_MS = 15_000;
const SUBMIT_TIMEOUT_MS = 15_000;

/** Identical in shape to `signup/SignupForm.tsx::fetchEventPublicKey` --
 *  see that function's own docstring for why validating with
 *  `importEventPublicKey` here, rather than a substring sniff, matters. */
async function fetchEventPublicKey(eventId: string, signal: AbortSignal): Promise<string | null> {
  try {
    const response = await fetch(eventPublicKeyUrl(eventId), { signal });
    if (!response.ok) return null;
    const pem = await response.text();
    await importEventPublicKey(pem);
    return pem;
  } catch {
    return null;
  }
}

/**
 * Whether `eventId` currently has the survey switch on, read from the
 * published, build-time-derived `survey-status.json` (R-37).
 *
 * Fails closed on every ambiguity, the same direction
 * `tools/convener_ops/cli.py::_survey_enabled`'s own docstring commits to on
 * the server side: an unreachable file, a non-2xx response, unparsable
 * JSON, or JSON that is not an array all read as "not enabled" here, never
 * as "we could not tell, so allow it". This is a page-level convenience,
 * not the authoritative check -- the relay and the handler both check
 * again, because a client-side check is bypassable by anyone who skips
 * this page entirely and posts to the relay directly.
 */
async function fetchSurveyEnabled(eventId: string, signal: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch(surveyStatusUrl(), { signal });
    if (!response.ok) return false;
    const data: unknown = await response.json();
    return Array.isArray(data) && data.includes(eventId);
  } catch {
    return false;
  }
}

function Notice() {
  return (
    <div className="border-2 border-primary/30 bg-primary/5 px-5 py-4 mb-8 text-sm space-y-2">
      <p className="font-display font-bold uppercase tracking-wider text-xs text-primary-hover mb-1">
        Before you answer
      </p>
      <p>
        This short, optional survey is only sent to people we have recorded as present at
        this event. Three questions, all short.
      </p>
      <p>
        <strong>Your browser encrypts your answers before they are sent</strong>, using
        this event&apos;s own key -- the same key, and the same protection, as your
        registration. Nobody -- including us -- can read your answers until a workshop
        organiser decrypts them as part of running the event.
      </p>
      <p>
        <strong>Your answers are anonymous.</strong> Nothing here -- no name, no address,
        no matching code -- is sent alongside them, and that is deliberate. Because of
        that, we cannot find your own answers to show them to you, correct them or erase
        them individually once sent: there is nothing on file that says which answers are
        yours. Please do not write your name, your email address, or anything else that
        could identify you or anyone else, in the free-text box below.
      </p>
      <p>
        All answers for this event, like your registration, are permanently destroyed
        together with the event&apos;s key 90 days after the event. Questions about this
        survey can be sent to{' '}
        <a className="underline" href={`mailto:${CONTACT_EMAIL}`}>
          {CONTACT_EMAIL}
        </a>
        .
      </p>
    </div>
  );
}

// The five-point scale spelled out as `1..5` rather than typed in the JSX
// below, so the range this page renders can never quietly drift from the
// range `tools/convener_ops/survey.py::_RATING_MIN`/`_RATING_MAX` accepts.
const RATING_VALUES = [1, 2, 3, 4, 5] as const;

// Mirrors `tools/convener_ops/survey.py::_MAX_FEEDBACK_LENGTH` (Important 3,
// fix round 1). Bound here too, not only server-side: before this, a
// 2000-plus-character answer was accepted by this form and by the relay,
// dispatched, and only then discarded by the handler as "could not be
// read" -- a participant who wrote a long, careful answer deserves to see
// the limit before typing past it, not after submitting into a silent
// discard.
const MAX_FEEDBACK_LENGTH = 2000;

export function SurveyForm() {
  const { eventId } = useParams<{ eventId: string }>();
  const [pageState, setPageState] = useState<PageState>({ status: 'loading' });
  const [submitState, setSubmitState] = useState<SubmitState>('idle');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const sentPanelRef = useRef<HTMLDivElement>(null);

  const [rating, setRating] = useState<number | ''>('');
  const [recommend, setRecommend] = useState<'' | 'yes' | 'no'>('');
  const [feedback, setFeedback] = useState('');

  useEffect(() => {
    // Nothing to fetch without an event id -- `effectivePageState` below
    // already reports this as 'unavailable' without an extra render.
    if (!eventId) return;
    let cancelled = false;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), KEY_FETCH_TIMEOUT_MS);
    // The key and the switch are fetched together, under one shared
    // timeout: whichever answer arrives, the other must too before this
    // page can decide anything, so there is no benefit to serialising them.
    Promise.all([
      fetchEventPublicKey(eventId, controller.signal),
      fetchSurveyEnabled(eventId, controller.signal),
    ])
      .then(([pem, enabled]) => {
        if (cancelled) return;
        if (!pem) {
          setPageState({ status: 'unavailable' });
        } else if (!enabled) {
          setPageState({ status: 'closed' });
        } else {
          setPageState({ status: 'ready', publicKeyPem: pem });
        }
      })
      // Both fetch helpers already catch everything and resolve rather
      // than reject -- defence in depth, the same idiom `SignupForm.tsx`
      // uses for its own single fetch.
      .catch(() => {
        if (!cancelled) setPageState({ status: 'unavailable' });
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timeout);
    };
  }, [eventId]);

  const effectivePageState: PageState = eventId ? pageState : { status: 'unavailable' };

  // The success panel replaces the form, which held focus a moment
  // earlier -- see `SignupForm.tsx`'s identical comment for why this
  // moves focus onto the panel rather than letting it fall back to
  // `<body>`.
  useEffect(() => {
    if (submitState === 'sent') sentPanelRef.current?.focus();
  }, [submitState]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    // Defence in depth, not the only guard -- see `SignupForm.tsx::submit`'s
    // identical comment for why this should be unreachable but is checked
    // anyway.
    if (effectivePageState.status !== 'ready' || !eventId || rating === '' || recommend === '') {
      return;
    }

    setSubmitState('sending');
    setSubmitError(null);
    const fields: SurveyResponse = {
      overall_rating: rating,
      recommend: recommend === 'yes',
      feedback: feedback.trim(),
    };

    try {
      const envelopeJson = await encryptSurveyResponse(effectivePageState.publicKeyPem, fields);
      const url = surveyRelayUrl();
      if (!url) {
        // Minor 7 (fix round 1): distinct wording from the 'closed' state
        // above -- this is D-13's ordinary "the relay is not deployed
        // yet" absence, not the survey switch, and a participant whose
        // survey genuinely *is* open must not read this as "try a
        // different event" the way the 'closed' page's own message would
        // otherwise imply.
        setSubmitState('error');
        setSubmitError('Submitting answers is not available yet. Please try again later.');
        return;
      }
      const envelope: unknown = JSON.parse(envelopeJson);
      let response: Response;
      try {
        response = await fetch(url, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ event_id: eventId, ...(envelope as object) }),
          signal: AbortSignal.timeout(SUBMIT_TIMEOUT_MS),
        });
      } catch {
        setSubmitState('error');
        setSubmitError('Your answers could not be sent. Please try again.');
        return;
      }
      if (!response.ok) {
        setSubmitState('error');
        setSubmitError('Your answers could not be sent. Please try again.');
        return;
      }
      // Only on success, the same discipline `SignupForm.tsx` follows: an
      // error must leave the fields exactly as answered, so a retry does
      // not force re-answering.
      setRating('');
      setRecommend('');
      setFeedback('');
      setSubmitState('sent');
    } catch {
      setSubmitState('error');
      setSubmitError('Your answers could not be encrypted. Please try again.');
    }
  }

  const canSubmit = rating !== '' && recommend !== '';

  return (
    <div className="max-w-content mx-auto px-6 py-12">
      <div className="max-w-xl">
        <h1 className="font-serif text-3xl mb-6">
          Quick survey{eventId ? ` for ${eventId}` : ''}
        </h1>

        <Notice />

        {effectivePageState.status === 'loading' && (
          <p className="text-ink-muted text-sm">Checking that the survey is available…</p>
        )}

        {effectivePageState.status === 'unavailable' && (
          <div className="border-2 border-danger/40 bg-danger/5 px-5 py-4 text-sm">
            <p className="font-display font-bold uppercase tracking-wider text-xs text-danger mb-1">
              This survey is not available right now
            </p>
            <p>
              We could not retrieve what this event needs before anything can be sent. We
              never send answers unencrypted, so nothing has been sent. Please try again
              later, or contact{' '}
              <a className="underline" href={`mailto:${CONTACT_EMAIL}`}>
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </div>
        )}

        {effectivePageState.status === 'closed' && (
          <div className="border-2 border-ink-muted/40 bg-ink-muted/5 px-5 py-4 text-sm">
            <p className="font-display font-bold uppercase tracking-wider text-xs text-ink-muted mb-1">
              This survey is not open
            </p>
            <p>There is no survey currently open for this event.</p>
          </div>
        )}

        {effectivePageState.status === 'ready' && submitState !== 'sent' && (
          // `method="post"`, on a page that would otherwise default to GET --
          // the same reasoning `SignupForm.tsx`'s identical attribute gives.
          <form method="post" onSubmit={submit} className="space-y-6">
            <fieldset className="space-y-2">
              <legend className="text-xs uppercase tracking-wider text-ink-muted">
                How would you rate this session overall? *
              </legend>
              <div className="flex gap-3">
                {RATING_VALUES.map(value => (
                  <label key={value} className="flex items-center gap-1 text-sm">
                    <input
                      type="radio"
                      name="overall_rating"
                      value={value}
                      checked={rating === value}
                      onChange={() => setRating(value)}
                      required
                    />
                    {value}
                  </label>
                ))}
              </div>
            </fieldset>

            <fieldset className="space-y-2">
              <legend className="text-xs uppercase tracking-wider text-ink-muted">
                Would you recommend this series to a colleague? *
              </legend>
              <div className="flex gap-4">
                <label className="flex items-center gap-1 text-sm">
                  <input
                    type="radio"
                    name="recommend"
                    value="yes"
                    checked={recommend === 'yes'}
                    onChange={() => setRecommend('yes')}
                    required
                  />
                  Yes
                </label>
                <label className="flex items-center gap-1 text-sm">
                  <input
                    type="radio"
                    name="recommend"
                    value="no"
                    checked={recommend === 'no'}
                    onChange={() => setRecommend('no')}
                  />
                  No
                </label>
              </div>
            </fieldset>

            <label className="block">
              <span className="text-xs uppercase tracking-wider text-ink-muted">
                Anything else you would like to tell us? (optional)
              </span>
              {/* Critical 1 (fix round 1): a warning right where someone is
                  about to type, not only in the notice above the form --
                  the free-text box is the one input that could turn an
                  anonymous store into one that is not. */}
              <p className="text-xs text-ink-muted mt-1 mb-1">
                Please do not include your name, email address, or anything else that
                could identify you or anyone else.
              </p>
              <textarea
                value={feedback}
                onChange={e => setFeedback(e.target.value)}
                rows={4}
                maxLength={MAX_FEEDBACK_LENGTH}
                className="w-full px-3 py-2 text-sm mt-1"
              />
              <span className="block text-right text-xs text-ink-muted mt-1">
                {feedback.length} / {MAX_FEEDBACK_LENGTH}
              </span>
            </label>

            <button
              type="submit"
              disabled={!canSubmit || submitState === 'sending'}
              className="px-4 py-2 bg-primary text-white border-2 border-primary hover:bg-primary-hover disabled:opacity-50 font-display font-bold tracking-widest uppercase text-sm"
            >
              {submitState === 'sending' ? 'Sending…' : 'Submit'}
            </button>

            {submitState === 'error' && submitError && (
              // `role="alert"` (an implicit assertive live region): the
              // message appears purely in response to interaction, after
              // the button that triggered it, and without this a screen
              // reader user is never told it happened at all.
              <p role="alert" className="text-danger text-sm">
                {submitError}
              </p>
            )}
          </form>
        )}

        {submitState === 'sent' && (
          <div
            ref={sentPanelRef}
            role="alert"
            tabIndex={-1}
            className="border-2 border-primary/40 bg-primary/5 px-5 py-4 text-sm outline-none"
          >
            <p className="font-display font-bold uppercase tracking-wider text-xs text-primary-hover mb-1">
              Thank you
            </p>
            <p>Your answers have been sent.</p>
          </div>
        )}
      </div>
    </div>
  );
}
