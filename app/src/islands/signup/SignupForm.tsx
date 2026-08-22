import { useEffect, useRef, useState } from 'react';
import { encryptRegistration, importEventPublicKey } from '../../signup/encrypt';
import type { Registration } from '../../signup/encrypt';

/**
 * Task 6: extracted from the operators' application package
 * (`app/src/signup/SignupForm.tsx`, now deleted -- see git history) into
 * an island mounted on the public event page (`site/src/event.njk`), per
 * D-18 ("static pages, interactivity in islands") and P-2 ("islands are
 * built in the cockpit"). Before this, a visitor who wanted to register
 * downloaded the whole operators' cockpit -- its routing, its
 * authentication, every screen -- to fill in four fields.
 *
 * Everything phase 4 established about this form holds unchanged: the
 * public key comes from the same origin the island itself is served from,
 * encryption happens in the browser under `encrypt.ts` -- shared, never
 * reimplemented (the rule this whole file exists to honour) -- there are
 * abort timeouts on both requests, and the component remounts on a
 * changed event id (`main.tsx`'s own `key={eventId}`, the exact discipline
 * `App.tsx`'s `SignupRoute` used to give it).
 *
 * What changed in the extraction, and why
 * -----------------------------------------
 * - `eventId` is a prop, not a route param: this island has no router --
 *   one static page per event (D-19), not a fragment this script
 *   re-parses. `main.tsx` reads it off the mount element's own
 *   `data-event-id` attribute.
 * - The data-protection notice (`Notice()`, phase 4 spec §4) is gone from
 *   this file. `site/src/event.njk` now renders that text itself, as
 *   plain static HTML, ahead of this island's own mount point -- D-18's
 *   own logic applied literally: text that needs no interactivity stays
 *   static, so it reads even with JavaScript disabled and never depends
 *   on this bundle loading at all. Rendering it a second time from here
 *   would put two copies of the same legal notice on one page. See
 *   `tools/tests/test_site.py::test_the_notice_precedes_the_reserved_
 *   place_for_the_registration_form`, already checking the static copy.
 * - `AttendanceBoundaries()` (spec S:5's two matching boundaries) stays:
 *   `event.njk` never carries that text, so nothing is duplicated by
 *   keeping it here.
 * - Class names are plain, semantic strings (`signup-form__field`, ...)
 *   styled by `site/src/style.css`, not Tailwind utility classes: this
 *   island renders inside a page that already loads that stylesheet, and
 *   pulling in Tailwind's own reset (`@tailwind base`) would apply
 *   site-wide to elements this form does not own -- headings, the
 *   masthead -- not merely inside this component's own subtree.
 */

// `public/keys/events/<id>.pub` is still populated at build time by
// `app/scripts/copy-event-keys.mjs` from this repository's own
// `keys/events/`, and still ships inside the app's own build output --
// see that script's own comment for why a missing file here is a normal
// state, not a build failure. `base` for this island's own Vite build
// (`app/vite.config.ts`, `mode === 'island-signup'`) is
// `/example-showcase/app/`, the same value the main app build uses -- Fix round
// 4 correction: this used to read `/app/`, deliberately distinct, on the
// reasoning that this bundle runs on a page served by the *site*, whose
// own templates already addressed the app's assets root-relative to the
// site's own root. That reasoning assumed the site's own root-relative
// links already landed at wherever GitHub Pages resolves this project's
// published root to; they did not, since there is no CNAME and no custom
// domain, so that root is one path segment (`/example-showcase/`) below the
// domain root a bare `/foo` actually addresses -- see
// `app/vite.config.ts`'s own comment on `islandSignupConfig` for the fix
// this island shares with every template in `site/`.
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

// A missing relay is a normal state (D-13), the same idiom `auth/strategy.ts`
// uses for `VITE_AUTH_PROXY_URL`: the relay in `services/signup-relay/` is
// built and deployed separately, so this form must work -- refusing to send,
// calmly -- before that exists. Unlike a missing event key, a missing relay
// is never the "must not fall back to plain text" exception: nothing has
// been read from the participant yet when this is checked. Read inside
// `submit`, like `authEnv()` reads its own variables at call time, rather
// than cached at module scope -- so a test can change it with `vi.stubEnv`.
function relayUrl(): string | undefined {
  return import.meta.env.VITE_SIGNUP_RELAY_URL as string | undefined;
}

const CONTACT_EMAIL = 'reading-group@example.test';

// Mirrors `tools/convener_ops/registration.py::_MAX_FIELD_LENGTH` (Important 1,
// branch review). Bound here too, not only server-side: before this, a
// 201-character field was accepted by this form and by the relay,
// encrypted, shown as sent, and only then dropped by `to_registration` as
// "could not be read" -- `convener-handle-registration` exits non-zero, no
// registration is stored, and no confirmation is sent, with nothing on
// this page ever telling the participant.
// `test_confirmation.py::test_signup_form_max_field_length_matches_the_
// python_constant` binds this number against the Python constant (D-14),
// so the two cannot drift apart the way `SurveyForm.tsx`'s own
// `MAX_FEEDBACK_LENGTH` still can.
const MAX_FIELD_LENGTH = 200;

type KeyState =
  | { status: 'loading' }
  | { status: 'ready'; publicKeyPem: string }
  | { status: 'unavailable' };

type SubmitState = 'idle' | 'sending' | 'sent' | 'error';

/** Where an event's published public half is fetched from -- same-origin,
 *  never the private repository directly. Not exported: this file exports
 *  the one component only (react-refresh/only-export-components), and a
 *  test can check the fetched URL through the stubbed `fetch` call it
 *  already has to make instead. */
function eventPublicKeyUrl(eventId: string): string {
  return `${BASE}/keys/events/${encodeURIComponent(eventId)}.pub`;
}

// A hung request has no other end: there is no server-side timeout on a
// static-file fetch, and without one a flaky connection -- this page's
// typical audience -- would leave the participant looking at "Checking
// that registration is available…" forever, which is silence, not the
// refusal requirement 4 asks for.
const KEY_FETCH_TIMEOUT_MS = 15_000;

// Same reasoning as KEY_FETCH_TIMEOUT_MS, applied to the submit POST beside
// it: a relay that never answers -- rather than answering with an error --
// would otherwise leave the button reading "Sending…" forever, which is
// exactly the silence requirement 4 refuses to allow for the key fetch and
// no more acceptable here.
const SUBMIT_TIMEOUT_MS = 15_000;

/**
 * Fetches an event's published public half and confirms it is actually
 * usable, in one step: `response.text()` and the validity check both sit
 * inside the same `try` as the fetch itself, so a body-read failure is
 * refused exactly like a network failure, not left to reject unhandled.
 *
 * "Usable" means `importEventPublicKey` accepts it -- not a
 * `BEGIN PUBLIC KEY` substring sniff, which a truncated body or a
 * perfectly well-formed non-RSA key (an EC public key carries the
 * identical label) both pass. Either of those would have rendered the
 * form, let the participant fill it in, and only failed at submit with a
 * message that can never be fixed by retrying -- validating here instead
 * means every malformed-key case is refused before anyone starts typing.
 */
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

// Two boundaries `tools/convener_ops/attendance.py` draws and spec S:5 asks to be
// written "on the event page, in the same place as 'present without having
// registered'" -- not only in `docs/reference/operations.md`, which a
// participant never reads. Neither is a matching weakness to keep
// improving; both are stated here exactly as the matching cascade actually
// behaves, not softened into "we will do our best". `event.njk` carries no
// copy of this text, so keeping it here duplicates nothing.
function AttendanceBoundaries() {
  return (
    <div className="notice signup-form__boundaries">
      <p className="notice__eyebrow">About your certificate</p>
      <p>
        <strong>Turning up without registering does not make you eligible.</strong> We only
        recognise people we can match to a registration -- register first if you want a
        certificate.
      </p>
      <p>
        <strong>Joining by telephone cannot be matched.</strong> The meeting platform gives
        us no address and no display name for a phone connection, so we cannot match you by
        your email address or by your name that way. If you want a certificate, join with
        the room link instead and put your matching code in your display name.
      </p>
    </div>
  );
}

export function SignupForm({ eventId }: { eventId?: string }) {
  const [keyState, setKeyState] = useState<KeyState>({ status: 'loading' });
  const [submitState, setSubmitState] = useState<SubmitState>('idle');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const sentPanelRef = useRef<HTMLDivElement>(null);
  const submitButtonRef = useRef<HTMLButtonElement>(null);

  const [firstName, setFirstName] = useState('');
  const [surname, setSurname] = useState('');
  const [email, setEmail] = useState('');
  const [institution, setInstitution] = useState('');
  // G-18: the announce-list opt-in. Unticked by default -- nothing in this
  // component, or in `Registration`'s construction below, ever flips this on
  // behalf of a participant.
  const [membershipOptIn, setMembershipOptIn] = useState(false);

  useEffect(() => {
    // Nothing to fetch without an event id -- `effectiveKeyState` below
    // already reports this as 'unavailable' without an extra render, the
    // same way `DataContext`'s `visible` folds "nothing to load yet" into
    // its state at read time rather than writing it from inside an effect.
    if (!eventId) return;
    let cancelled = false;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), KEY_FETCH_TIMEOUT_MS);
    fetchEventPublicKey(eventId, controller.signal)
      .then(pem => {
        if (cancelled) return;
        setKeyState(pem ? { status: 'ready', publicKeyPem: pem } : { status: 'unavailable' });
      })
      // `fetchEventPublicKey` already catches everything itself and
      // resolves to `null` rather than rejecting -- this mirrors
      // `AuthContext.tsx`'s own `.catch` after a `.then` that "never
      // rejects": defence in depth, not the only place a failure is
      // handled, so a hang or a rejection can never leave `keyState`
      // stuck at 'loading' with nothing said.
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

  // The success panel replaces the form -- which held focus, on the submit
  // button, a moment earlier -- rather than appearing alongside it, so
  // focus would otherwise silently fall back to `<body>`. Moving it onto
  // the panel keeps a keyboard or screen reader user oriented on the
  // sentence that just replaced what they were looking at.
  useEffect(() => {
    if (submitState === 'sent') sentPanelRef.current?.focus();
  }, [submitState]);

  // Fix round 1 (task 11's manual pass, "how error messages are
  // announced" -- flagged, not fixed, there; fixed here). Setting
  // `submitState` to `'sending'` disables the button that still held
  // focus a moment earlier -- a disabled element cannot hold focus, so
  // the browser drops it to `<body>` immediately, before this component
  // ever gets to render anything about what happened (confirmed against
  // real Chrome in task 11's report). The `role="alert"` below already
  // gets a screen-reader user this sentence read aloud the instant it is
  // inserted, live-region delivery needs no focus to move at all -- but a
  // keyboard user with no screen reader is left at `<body>` with no
  // signal anything happened, and Tab restarts the whole page from the
  // top to find out.
  //
  // Restoring focus to the button itself, not to the alert, on purpose:
  // the button is the control the participant was actually operating,
  // its own accessible name has not changed ("Register" again, once
  // re-enabled), and it sits immediately before the alert in reading
  // order, so a Tab press from here reaches it next. Moving focus onto
  // the alert instead, the way the success panel moves onto itself,
  // would very likely read twice to a screen-reader user: once from the
  // live region firing as the paragraph is inserted, a second time from
  // the browser's own "now focused: <accessible name>" announcement on
  // arrival -- the success panel has no such double-announcement risk,
  // because nothing there is also a live region competing with the
  // focus-change announcement.
  useEffect(() => {
    if (submitState === 'error') submitButtonRef.current?.focus();
  }, [submitState]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    // Defence in depth, not the only guard: the fields below only render at
    // all once `effectiveKeyState.status === 'ready'` (see the JSX), so this
    // should be unreachable -- but a function that trusts its own render
    // tree to keep it safe is one refactor away from not being safe.
    if (effectiveKeyState.status !== 'ready' || !eventId) return;

    setSubmitState('sending');
    setSubmitError(null);
    const fields: Registration = {
      first_name: firstName.trim(),
      surname: surname.trim(),
      email: email.trim(),
      institution: institution.trim(),
      membership_opt_in: membershipOptIn,
    };

    try {
      const envelopeJson = await encryptRegistration(effectiveKeyState.publicKeyPem, fields);
      const url = relayUrl();
      if (!url) {
        // Ordinary D-13 absence: the relay is not deployed yet. Nothing
        // about the participant's data has left this function, encrypted or
        // otherwise -- there is simply nowhere to send it to.
        setSubmitState('error');
        setSubmitError('Registration is not open for this event yet. Please try again later.');
        return;
      }
      const envelope: unknown = JSON.parse(envelopeJson);
      let response: Response;
      try {
        // A timeout here is a network-layer failure, not an encryption
        // one -- it has its own try/catch, and its own message below,
        // rather than falling into the outer catch's "could not be
        // encrypted", which would blame the wrong half of this function
        // for a relay that simply never answered.
        response = await fetch(url, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ event_id: eventId, ...(envelope as object) }),
          signal: AbortSignal.timeout(SUBMIT_TIMEOUT_MS),
        });
      } catch {
        setSubmitState('error');
        setSubmitError('Your registration could not be sent. Please try again.');
        return;
      }
      if (!response.ok) {
        setSubmitState('error');
        setSubmitError('Your registration could not be sent. Please try again.');
        return;
      }
      // Only on success: an error must leave the fields exactly as typed,
      // so a retry does not force retyping. Once sent, though, "the
      // browser must not be able to read back what it just sent" is not
      // only about the network -- the plaintext has no reason to keep
      // sitting in this component's own state for the rest of the tab's
      // life, so it does not.
      setFirstName('');
      setSurname('');
      setEmail('');
      setInstitution('');
      setMembershipOptIn(false);
      setSubmitState('sent');
    } catch {
      setSubmitState('error');
      setSubmitError('Your registration could not be encrypted. Please try again.');
    }
  }

  const canSubmit = Boolean(firstName.trim() && surname.trim() && email.trim());

  return (
    <div className="signup-form">
      <AttendanceBoundaries />

      {effectiveKeyState.status === 'loading' && (
        <p className="signup-form__status">Checking that registration is available…</p>
      )}

      {effectiveKeyState.status === 'unavailable' && (
        <div className="notice signup-form__unavailable">
          <p className="notice__eyebrow">Registration is not available right now</p>
          <p>
            We could not retrieve the encryption key this event needs before anything can
            be sent. We never send registration details unencrypted, so nothing has been
            sent. Please try again later, or contact{' '}
            <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
          </p>
        </div>
      )}

      {effectiveKeyState.status === 'ready' && submitState !== 'sent' && (
        // `method="post"`, on a page that would otherwise default to GET:
        // not reachable through React's own delegated submit handler, but
        // if that handler ever failed to attach, a native submit would put
        // a name and an email address into the URL, the browser history
        // and the `Referer` header of whatever loads next -- the one page
        // on this site where that failure mode is worth closing outright.
        <form method="post" onSubmit={submit} className="signup-form__fields">
          <div className="signup-form__row">
            <label className="signup-form__field">
              <span>First name *</span>
              <input
                type="text"
                value={firstName}
                onChange={e => setFirstName(e.target.value)}
                required
                maxLength={MAX_FIELD_LENGTH}
                autoComplete="given-name"
              />
            </label>
            <label className="signup-form__field">
              <span>Surname *</span>
              <input
                type="text"
                value={surname}
                onChange={e => setSurname(e.target.value)}
                required
                maxLength={MAX_FIELD_LENGTH}
                autoComplete="family-name"
              />
            </label>
          </div>

          <label className="signup-form__field">
            <span>Email address *</span>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              maxLength={MAX_FIELD_LENGTH}
              autoComplete="email"
            />
          </label>

          <label className="signup-form__field">
            <span>Institution (optional)</span>
            <input
              type="text"
              value={institution}
              onChange={e => setInstitution(e.target.value)}
              maxLength={MAX_FIELD_LENGTH}
              autoComplete="organization"
            />
          </label>

          <label className="signup-form__checkbox">
            <input
              type="checkbox"
              checked={membershipOptIn}
              onChange={e => setMembershipOptIn(e.target.checked)}
            />
            <span>
              Also subscribe me to the announce list for future events. I can unsubscribe
              with one click from any email, and I will be asked to reconfirm every year.
            </span>
          </label>

          <button
            ref={submitButtonRef}
            type="submit"
            disabled={!canSubmit || submitState === 'sending'}
            className="btn btn--primary"
          >
            {submitState === 'sending' ? 'Sending…' : 'Register'}
          </button>

          {submitState === 'error' && submitError && (
            // `role="alert"` (an implicit assertive live region): the
            // message appears purely in response to interaction, after
            // the button that triggered it, and without this a screen
            // reader user is never told it happened at all.
            <p role="alert" className="signup-form__error">
              {submitError}
            </p>
          )}
        </form>
      )}

      {submitState === 'sent' && (
        <div ref={sentPanelRef} role="alert" tabIndex={-1} className="notice signup-form__sent">
          <p className="notice__eyebrow">Registration sent</p>
          <p>
            A confirmation email carrying the room link and your matching code is on its
            way.
          </p>
        </div>
      )}
    </div>
  );
}
