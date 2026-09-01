import { useEffect, useRef, useState } from 'react';
import { instanceIdentity } from '../../instance';
import { encryptSurveyResponse, importEventPublicKey } from '../../survey/encrypt';
import type { SurveyResponse } from '../../survey/encrypt';
import { surveyStatusUrl } from '../../survey/surveyStatus';

/**
 * Extracted from the operators'
 * application (`app/src/survey/SurveyForm.tsx`, now deleted -- see git
 * history) into an island mounted on the post-event survey's own static
 * page (`site/src/survey.njk`), per D-18 ("static pages, interactivity in
 * islands") -- the identical move registration
 * (`app/src/islands/signup/`) and certificate
 * verification (`app/src/islands/verify/`) each made. `/survey/:eventId`
 * used to live in the same document and the same JavaScript realm as the
 * authenticated cockpit -- a review of this project's web surface
 * named that the one asymmetry left after those two extractions.
 *
 * `encrypt.ts` and `surveyStatus.ts` stay exactly where they were, at
 * `app/src/survey/` -- only the *view* moved, imported from their
 * original location the same way `islands/verify/VerifyPage.tsx` still
 * imports `../../verify/verify`, `../../verify/register`, and the rest of
 * that package unmoved. No second implementation of the encryption --
 * there is exactly one `encryptSurveyResponse`, called from
 * here.
 *
 * What changed in the extraction, and why
 * -----------------------------------------
 * - `eventId` is a prop, not a `useParams` read: this island has no
 *   router -- one static page per event (D-19, the same rule
 *   `site/src/event.njk`'s own permalink already applies), not a route
 *   this script re-parses. `main.tsx` reads it off the mount element's
 *   own `data-event-id` attribute, the identical contract
 *   `islands/signup/main.tsx` already uses.
 * - The data-protection notice (`Notice()`) is gone
 *   from this file. `site/src/survey.njk` now renders that text itself,
 *   as plain static HTML, ahead of this island's own mount point --
 *   D-18's own logic applied literally, the same choice
 *   registration's own notice took: text that needs no interactivity stays
 *   static, so it reads even with JavaScript disabled and never depends
 *   on this bundle loading at all.
 * - Class names are plain, semantic strings (`survey-form__field`, ...)
 *   styled by `site/src/style.css`, not Tailwind utility classes: this
 *   island renders inside a page that already loads that stylesheet, and
 *   pulling in Tailwind's own reset (`@tailwind base`) would apply
 *   site-wide to elements this form does not own -- the same reasoning
 *   `islands/signup/SignupForm.tsx`'s own module comment gives.
 *
 * Everything else this form ever promised holds unchanged: the public key
 * and the survey switch
 * (`survey-status.json`) are fetched under one shared timeout, both
 * fail closed, the free-text field is padded before encryption
 * (`encrypt.ts::padPlaintext`) so its ciphertext length carries no
 * information about what was typed, and nothing about a response --
 * including the relay it posts to -- names who sent it.
 */

// Same idiom as `islands/signup/SignupForm.tsx`'s own `BASE`: the base
// this island is actually served from, so both fetches below resolve
// against the deployed route rather than wherever the browser happens to
// be.
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

// The survey shares `services/signup-relay` with registration -- a second
// *route* on the same worker (`/survey`, dispatching
// `survey-response-submitted`), not a second deployment -- so it shares
// registration's own relay URL rather than needing a second environment
// variable and a second secret to configure. See
// `services/signup-relay/README.md`, "A second route, not a second
// worker." A missing relay is a normal state (D-13), same as
// `SignupForm.tsx`.
function surveyRelayUrl(): string | undefined {
  const base = import.meta.env.VITE_SIGNUP_RELAY_URL as string | undefined;
  if (!base) return undefined;
  return `${base.replace(/\/$/, '')}/survey`;
}

// The address a participant writes to about their own data. Declared
// once in `instance/config.json` and carried into this
// bundle by `vite.config.ts`'s own define, because this runs in a
// participant's browser. A duplicate that left this literal here would
// send its own participants' data-protection requests to the previous
// instance's inbox.
const contactEmail = () => instanceIdentity().contact;

// The page-level layer of the switch
// enforcement. `'closed'` means the key loaded fine but this event's
// survey is not enabled -- distinct from `'unavailable'`, a technical
// failure to fetch or validate the public key itself (which also covers
// an event id nothing was ever published for). Both refuse to render the
// form; they are told apart only so the message can be honest about which
// is true.
type PageState =
  | { status: 'loading' }
  | { status: 'unavailable' }
  | { status: 'closed' }
  | { status: 'ready'; publicKeyPem: string };

type SubmitState = 'idle' | 'sending' | 'sent' | 'error';

/** Where an event's published public half is fetched from -- identical to
 *  `islands/signup/SignupForm.tsx::eventPublicKeyUrl`: same-origin, the
 *  same key an event's registration was encrypted under -- the survey
 *  uses the same entry point as registration. Not exported, for the same
 *  react-refresh reason that sibling function gives. */
function eventPublicKeyUrl(eventId: string): string {
  return `${BASE}/keys/events/${encodeURIComponent(eventId)}.pub`;
}

// Same reasoning, same values, as `islands/signup/SignupForm.tsx`'s own
// two timeouts: a hung request has no other end, and a page that never
// says so is silence, not the refusal requirement 4 asks for.
const KEY_FETCH_TIMEOUT_MS = 15_000;
const SUBMIT_TIMEOUT_MS = 15_000;

/** Identical in shape to `islands/signup/SignupForm.tsx::fetchEventPublicKey`
 *  -- see that function's own docstring for why validating with
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
 * published, build-time-derived `survey-status.json`.
 *
 * Fails closed on every ambiguity, the same direction
 * `tools/convener_ops/cli/journey/event.py::survey_enabled`'s own docstring commits to on
 * the server side: an unreachable file, a non-2xx response, unparsable
 * JSON, or JSON that is not an array all read as "not enabled" here,
 * never as "we could not tell, so allow it". This is a page-level
 * convenience, not the authoritative check -- the relay and the handler
 * both check again, because a client-side check is bypassable by anyone
 * who skips this page entirely and posts to the relay directly.
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

// The five-point scale spelled out as `1..5` rather than typed in the JSX
// below, so the range this page renders can never quietly drift from the
// range `tools/convener_ops/journey/survey.py::_RATING_MIN`/`_RATING_MAX` accepts.
const RATING_VALUES = [1, 2, 3, 4, 5] as const;

// Mirrors `tools/convener_ops/journey/survey.py::_MAX_FEEDBACK_LENGTH`. Bound here too,
// not only server-side: before this, a 2000-plus-character answer was
// accepted by this form and by the relay, dispatched, and only then
// discarded by the handler as "could not be read" -- a participant who
// wrote a long, careful answer deserves to see the limit before typing
// past it, not after submitting into a silent discard.
const MAX_FEEDBACK_LENGTH = 2000;

export function SurveyForm({ eventId }: { eventId?: string }) {
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
      // than reject -- defence in depth, the same idiom
      // `islands/signup/SignupForm.tsx` uses for its own single fetch.
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
  // earlier -- see `islands/signup/SignupForm.tsx`'s identical comment
  // for why this moves focus onto the panel rather than letting it fall
  // back to `<body>`.
  useEffect(() => {
    if (submitState === 'sent') sentPanelRef.current?.focus();
  }, [submitState]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    // Defence in depth, not the only guard -- see
    // `islands/signup/SignupForm.tsx::submit`'s identical comment for why
    // this should be unreachable but is checked anyway.
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
        // Distinct wording from the 'closed' state above -- this is
        // D-13's ordinary "the relay is not deployed yet" absence, not
        // the survey switch, and a participant whose survey genuinely
        // *is* open must not read this as "try a different event" the
        // way the 'closed' page's own message would otherwise imply.
        setSubmitState('error');
        setSubmitError(
          'Submitting answers is not available yet, so nothing you typed has been sent. ' +
            'Please try again later.',
        );
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
      // Only on success, the same discipline `islands/signup/SignupForm.tsx`
      // follows: an error must leave the fields exactly as answered, so a
      // retry does not force re-answering.
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
    <div className="survey-form">
      {effectivePageState.status === 'loading' && (
        <p className="survey-form__status">Checking that the survey is available…</p>
      )}

      {effectivePageState.status === 'unavailable' && (
        <div className="notice survey-form__unavailable">
          <p className="notice__eyebrow">This survey is not available right now</p>
          <p>
            We could not retrieve the encryption key this event needs before anything can
            be sent. We never send answers unencrypted, so nothing has been sent. Please
            try again later, or contact{' '}
            <a href={`mailto:${contactEmail()}`}>{contactEmail()}</a>.
          </p>
        </div>
      )}

      {effectivePageState.status === 'closed' && (
        <div className="notice survey-form__closed">
          <p className="notice__eyebrow">This survey is not open</p>
          <p>There is no survey currently open for this event.</p>
        </div>
      )}

      {effectivePageState.status === 'ready' && submitState !== 'sent' && (
        // `method="post"`, on a page that would otherwise default to GET
        // -- the same reasoning `islands/signup/SignupForm.tsx`'s
        // identical attribute gives.
        <form method="post" onSubmit={submit} className="survey-form__fields">
          <fieldset className="survey-form__fieldset">
            <legend className="survey-form__legend">
              How would you rate this session overall? *
            </legend>
            <div className="survey-form__options">
              {RATING_VALUES.map(value => (
                <label key={value} className="survey-form__option">
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

          <fieldset className="survey-form__fieldset">
            <legend className="survey-form__legend">
              Would you recommend this series to a colleague? *
            </legend>
            <div className="survey-form__options">
              <label className="survey-form__option">
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
              <label className="survey-form__option">
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

          <label className="survey-form__field">
            <span>Anything else you would like to tell us? (optional)</span>
            {/* The one input that could turn an anonymous store into one
                that is not -- a warning right where someone is about to
                type, not only in the page's own static notice above this
                island's mount point. */}
            <p className="survey-form__hint">
              Please do not include your name, email address, or anything else that
              could identify you or anyone else.
            </p>
            <textarea
              value={feedback}
              onChange={e => setFeedback(e.target.value)}
              rows={4}
              maxLength={MAX_FEEDBACK_LENGTH}
              className="survey-form__textarea"
            />
            <span className="survey-form__counter">
              {feedback.length} / {MAX_FEEDBACK_LENGTH}
            </span>
          </label>

          <button
            type="submit"
            disabled={!canSubmit || submitState === 'sending'}
            className="btn btn--primary"
          >
            {submitState === 'sending' ? 'Sending…' : 'Submit'}
          </button>

          {submitState === 'error' && submitError && (
            // `role="alert"` (an implicit assertive live region): the
            // message appears purely in response to interaction, after
            // the button that triggered it, and without this a screen
            // reader user is never told it happened at all.
            <p role="alert" className="survey-form__error">
              {submitError}
            </p>
          )}
        </form>
      )}

      {submitState === 'sent' && (
        <div ref={sentPanelRef} role="alert" tabIndex={-1} className="notice survey-form__sent">
          <p className="notice__eyebrow">Thank you</p>
          <p>Your answers have been sent.</p>
        </div>
      )}
    </div>
  );
}
