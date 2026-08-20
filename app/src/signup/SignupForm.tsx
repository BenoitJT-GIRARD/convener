import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { encryptRegistration } from './encrypt';
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

async function fetchEventPublicKey(eventId: string): Promise<string | null> {
  let response: Response;
  try {
    response = await fetch(eventPublicKeyUrl(eventId));
  } catch {
    return null;
  }
  if (!response.ok) return null;
  const pem = await response.text();
  return pem.includes('BEGIN PUBLIC KEY') ? pem : null;
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
    fetchEventPublicKey(eventId).then(pem => {
      if (cancelled) return;
      setKeyState(pem ? { status: 'ready', publicKeyPem: pem } : { status: 'unavailable' });
    });
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  const effectiveKeyState: KeyState = eventId ? keyState : { status: 'unavailable' };

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
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ event_id: eventId, ...(envelope as object) }),
      });
      if (!response.ok) {
        setSubmitState('error');
        setSubmitError('Your registration could not be sent. Please try again.');
        return;
      }
      setSubmitState('sent');
    } catch {
      setSubmitState('error');
      setSubmitError('Your registration could not be encrypted. Please try again.');
    }
  }

  const canSubmit = firstName.trim() && surname.trim() && email.trim();

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
          <form onSubmit={submit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
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
              <p className="text-danger text-sm">{submitError}</p>
            )}
          </form>
        )}

        {submitState === 'sent' && (
          <div className="border-2 border-primary/40 bg-primary/5 px-5 py-4 text-sm">
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
