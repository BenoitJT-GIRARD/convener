import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { encryptRegistration, importEventPublicKey } from './encrypt';
import type { Registration } from './encrypt';

// Same idiom as `content/fetch.ts`: the base the app itself is served from,
// so a fetch resolves against the deployed route rather than wherever the
// browser happens to be. `public/keys/events/<id>.pub` is populated at
// build time by `scripts/copy-event-keys.mjs` from the repository's own
// `keys/events/` -- see that script for why a missing file here is a
// normal state, not a build failure.
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

function Notice() {
  return (
    <div className="border-2 border-primary/30 bg-primary/5 px-5 py-4 mb-8 text-sm space-y-2">
      <p className="font-display font-bold uppercase tracking-wider text-xs text-primary-hover mb-1">
        Before you register
      </p>
      <p>
        We collect your first name, surname and email address to register you for this
        event and to issue your attendance certificate afterwards. Institution is optional.
        Nothing else is asked for.
      </p>
      <p>
        <strong>Your browser encrypts this information before it is sent</strong>, using
        this event&apos;s own key. Nobody -- including us -- can read it until a workshop
        organiser decrypts it as part of running the event. The event&apos;s data,
        encrypted form included, is permanently destroyed 90 days after the event by
        destroying the key that could ever read it again.
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

export function SignupForm() {
  const { eventId } = useParams<{ eventId: string }>();
  const [keyState, setKeyState] = useState<KeyState>({ status: 'loading' });
  const [submitState, setSubmitState] = useState<SubmitState>('idle');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const sentPanelRef = useRef<HTMLDivElement>(null);

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
    <div className="max-w-content mx-auto px-6 py-12">
      <div className="max-w-xl">
        <h1 className="font-serif text-3xl mb-6">
          Register{eventId ? ` for ${eventId}` : ''}
        </h1>

        {/* The notice comes before the form, not after: a notice below a
            submit button informs nobody. */}
        <Notice />

        {effectiveKeyState.status === 'loading' && (
          <p className="text-ink-muted text-sm">Checking that registration is available…</p>
        )}

        {effectiveKeyState.status === 'unavailable' && (
          <div className="border-2 border-danger/40 bg-danger/5 px-5 py-4 text-sm">
            <p className="font-display font-bold uppercase tracking-wider text-xs text-danger mb-1">
              Registration is not available right now
            </p>
            <p>
              We could not retrieve the encryption key this event needs before anything can
              be sent. We never send registration details unencrypted, so nothing has been
              sent. Please try again later, or contact{' '}
              <a className="underline" href={`mailto:${CONTACT_EMAIL}`}>
                {CONTACT_EMAIL}
              </a>
              .
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
          <form method="post" onSubmit={submit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="block">
                <span className="text-xs uppercase tracking-wider text-ink-muted">
                  First name *
                </span>
                <input
                  type="text"
                  value={firstName}
                  onChange={e => setFirstName(e.target.value)}
                  required
                  className="w-full px-3 py-2 text-sm mt-1"
                  autoComplete="given-name"
                />
              </label>
              <label className="block">
                <span className="text-xs uppercase tracking-wider text-ink-muted">
                  Surname *
                </span>
                <input
                  type="text"
                  value={surname}
                  onChange={e => setSurname(e.target.value)}
                  required
                  className="w-full px-3 py-2 text-sm mt-1"
                  autoComplete="family-name"
                />
              </label>
            </div>

            <label className="block">
              <span className="text-xs uppercase tracking-wider text-ink-muted">
                Email address *
              </span>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2 text-sm mt-1"
                autoComplete="email"
              />
            </label>

            <label className="block">
              <span className="text-xs uppercase tracking-wider text-ink-muted">
                Institution (optional)
              </span>
              <input
                type="text"
                value={institution}
                onChange={e => setInstitution(e.target.value)}
                className="w-full px-3 py-2 text-sm mt-1"
                autoComplete="organization"
              />
            </label>

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={membershipOptIn}
                onChange={e => setMembershipOptIn(e.target.checked)}
                className="mt-1"
              />
              <span>
                Also subscribe me to the announce list for future events. I can unsubscribe
                with one click from any email, and I will be asked to reconfirm every year.
              </span>
            </label>

            <button
              type="submit"
              disabled={!canSubmit || submitState === 'sending'}
              className="px-4 py-2 bg-primary text-white border-2 border-primary hover:bg-primary-hover disabled:opacity-50 font-display font-bold tracking-widest uppercase text-sm"
            >
              {submitState === 'sending' ? 'Sending…' : 'Register'}
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
              Registration sent
            </p>
            <p>
              A confirmation email carrying the room link and your matching code is on its
              way.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
