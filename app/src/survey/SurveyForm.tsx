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

type KeyState =
  | { status: 'loading' }
  | { status: 'ready'; publicKeyPem: string }
  | { status: 'unavailable' };

type SubmitState = 'idle' | 'sending' | 'sent' | 'error';

/** Where an event's published public half is fetched from -- identical to
 *  `signup/SignupForm.tsx::eventPublicKeyUrl`: same-origin, the same key an
 *  event's registration was encrypted under (spec S:6, "meme entree que
 *  l'inscription"). Not exported, for the same react-refresh reason
 *  `SignupForm.tsx` gives. */
function eventPublicKeyUrl(eventId: string): string {
  return `${BASE}/keys/events/${encodeURIComponent(eventId)}.pub`;
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
        organiser decrypts them as part of running the event. They are permanently
        destroyed 90 days after the event, at the same time and by the same means as
        your registration.
      </p>
      <p>
        To access, correct or erase your data before that date, write to{' '}
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

export function SurveyForm() {
  const { eventId } = useParams<{ eventId: string }>();
  const [keyState, setKeyState] = useState<KeyState>({ status: 'loading' });
  const [submitState, setSubmitState] = useState<SubmitState>('idle');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const sentPanelRef = useRef<HTMLDivElement>(null);

  const [rating, setRating] = useState<number | ''>('');
  const [recommend, setRecommend] = useState<'' | 'yes' | 'no'>('');
  const [feedback, setFeedback] = useState('');

  useEffect(() => {
    if (!eventId) return;
    let cancelled = false;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), KEY_FETCH_TIMEOUT_MS);
    fetchEventPublicKey(eventId, controller.signal)
      .then(pem => {
        if (cancelled) return;
        setKeyState(pem ? { status: 'ready', publicKeyPem: pem } : { status: 'unavailable' });
      })
      .catch(() => {
        if (!cancelled) setKeyState({ status: 'unavailable' });
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timeout);
    };
  }, [eventId]);

  const effectiveKeyState: KeyState = eventId ? keyState : { status: 'unavailable' };

  useEffect(() => {
    if (submitState === 'sent') sentPanelRef.current?.focus();
  }, [submitState]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    // Defence in depth, not the only guard -- see `SignupForm.tsx::submit`'s
    // identical comment for why this should be unreachable but is checked
    // anyway.
    if (effectiveKeyState.status !== 'ready' || !eventId || rating === '' || recommend === '') {
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
      const envelopeJson = await encryptSurveyResponse(effectiveKeyState.publicKeyPem, fields);
      const url = surveyRelayUrl();
      if (!url) {
        setSubmitState('error');
        setSubmitError('This survey is not open yet. Please try again later.');
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

        {effectiveKeyState.status === 'loading' && (
          <p className="text-ink-muted text-sm">Checking that the survey is available…</p>
        )}

        {effectiveKeyState.status === 'unavailable' && (
          <div className="border-2 border-danger/40 bg-danger/5 px-5 py-4 text-sm">
            <p className="font-display font-bold uppercase tracking-wider text-xs text-danger mb-1">
              This survey is not available right now
            </p>
            <p>
              We could not retrieve the encryption key this event needs before anything can
              be sent. We never send answers unencrypted, so nothing has been sent. Please
              try again later, or contact{' '}
              <a className="underline" href={`mailto:${CONTACT_EMAIL}`}>
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </div>
        )}

        {effectiveKeyState.status === 'ready' && submitState !== 'sent' && (
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
              <textarea
                value={feedback}
                onChange={e => setFeedback(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 text-sm mt-1"
              />
            </label>

            <button
              type="submit"
              disabled={!canSubmit || submitState === 'sending'}
              className="px-4 py-2 bg-primary text-white border-2 border-primary hover:bg-primary-hover disabled:opacity-50 font-display font-bold tracking-widest uppercase text-sm"
            >
              {submitState === 'sending' ? 'Sending…' : 'Submit'}
            </button>

            {submitState === 'error' && submitError && (
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
