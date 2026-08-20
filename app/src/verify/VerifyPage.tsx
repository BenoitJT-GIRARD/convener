import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { verify, NO_MATCHING_KEY } from './verify';
import type { VerifyResult } from './verify';
import { asDisplayCertificate } from './format';
import type { DisplayCertificate } from './format';
import { loadSigningPublicKeys } from './publicKeys';
import { lookupCertificateState, STATE_ISSUED, STATE_REVOKED } from './register';
import type { LookupResult } from './register';

/**
 * Spec S:7's "vérification sans divulgation", made into a page: someone
 * who receives a certificate confirms it holding nothing but the link
 * printed on it (or the 32-character identifier alone, from the printed
 * page -- see `VerifyTokenless` below) -- no account, no request to us for
 * the payload.
 *
 * `#/verify/:identifier?token=…`, not `/verify/…`
 * -------------------------------------------------
 * The fragment is load-bearing for privacy, not only for GitHub Pages
 * routing: everything after `#` is resolved by the browser locally, never
 * sent in an HTTP request, and stripped from `Referer` before this page
 * ever navigates away. `?token=` carries the holder's own **name**
 * (`signing.PAYLOAD_FIELDS`), so switching this application from
 * `HashRouter` to `BrowserRouter` -- a change nothing else in this
 * repository would object to -- would silently start sending every
 * verified participant's name to GitHub's servers in a query string, and
 * to whatever site a link is clicked from after, through `Referer`. See
 * `tools/convener_ops/certificate.py`'s own docstring ("the verification
 * address") and its
 * `test_verification_url_carries_the_token_after_the_fragment_not_before_it`
 * for the Python-side half of this same guarantee.
 *
 * Signature first, register second (ruling 2)
 * -----------------------------------------------
 * `VerifyWithToken` never asks the register anything until a token's
 * signature has already verified -- a malformed or unmatched token never
 * reaches `lookupCertificateState` at all. The register answers "is this
 * currently issued or revoked", not "is this genuine"; asking it the
 * second question, or rendering its unavailability as a verdict on the
 * first, is exactly the confusion ruling 2 exists to prevent -- "a
 * register that cannot be read must say 'I cannot confirm the state',
 * never 'invalid certificate'". `NotVerifiable` below is reachable purely
 * from a signature check, with no register call involved at all.
 *
 * Four answers, four appearances
 * ---------------------------------
 * `valid` / `revoked` / `not verifiable` / `state unknown` -- distinct
 * headings, distinct tones (`primary` / `accent` / `danger` / `info`).
 * `NO_MATCHING_KEY` and `MALFORMED` (see verify.ts) share the one
 * `not verifiable` appearance rather than getting a fifth of their own:
 * this task's own ruling is explicit that a well-formed, unmatched token
 * and a genuinely malformed one both mean the same thing to a stranger
 * standing here -- "I cannot confirm this" -- and naming which of the two
 * happened would risk reading as "prove it harder", not as an honest
 * report. The distinction still exists as data (`verify.ts`'s own return
 * type, tested against the shared fixture's two reason spellings); it is
 * simply not a second visual state.
 *
 * No nominative data leaves this component
 * --------------------------------------------
 * The only name ever rendered here comes from a token the holder's own
 * browser already has, in their own URL -- never logged, never sent
 * anywhere else. Nothing in this file calls `console.*` or touches
 * `localStorage`; the one fetch made when a token is present
 * (`lookupCertificateState`, in register.ts) carries no identifier over
 * the network at all, and the token-less path (`VerifyTokenless`) never
 * runs any cryptography and never renders a name, by construction -- there
 * is no payload in scope for it to read one from.
 */

const CONTACT_EMAIL = 'reading-group@example.test';

type Tone = 'primary' | 'accent' | 'danger' | 'info';

/** Every Tailwind class used below appears here as a complete, literal
 *  string -- Tailwind's build-time scan cannot see a class name assembled
 *  from a template literal (`` `border-${tone}/40` `` would simply never
 *  be generated), so tone is selected by looking up a whole class list,
 *  never by interpolating one. */
const TONE_CLASSES: Record<Tone, { panel: string; title: string }> = {
  primary: { panel: 'border-2 border-primary/40 bg-primary/5', title: 'text-primary-hover' },
  accent: { panel: 'border-2 border-accent/40 bg-accent/5', title: 'text-accent-hover' },
  danger: { panel: 'border-2 border-danger/40 bg-danger/5', title: 'text-danger' },
  info: { panel: 'border-2 border-info/40 bg-info/5', title: 'text-info' },
};

function Panel({ tone, title, children }: { tone: Tone; title: string; children: ReactNode }) {
  const classes = TONE_CLASSES[tone];
  return (
    <div role="alert" className={`${classes.panel} px-5 py-4 text-sm space-y-2`}>
      <p className={`font-display font-bold uppercase tracking-wider text-xs ${classes.title} mb-1`}>
        {title}
      </p>
      {children}
    </div>
  );
}

function Checking() {
  return <p className="text-ink-muted text-sm">Checking…</p>;
}

function IdentifierText({ id }: { id: string }) {
  return <span className="font-mono text-xs">{id}</span>;
}

function CertificateDetails({ cert }: { cert: DisplayCertificate }) {
  return (
    <dl className="mt-2 space-y-1">
      <div>
        <dt className="inline text-ink-muted">Name: </dt>
        <dd className="inline">{cert.name}</dd>
      </div>
      <div>
        <dt className="inline text-ink-muted">Event: </dt>
        <dd className="inline">{cert.event}</dd>
      </div>
      <div>
        <dt className="inline text-ink-muted">Date: </dt>
        <dd className="inline">{cert.date}</dd>
      </div>
      <div>
        <dt className="inline text-ink-muted">Duration: </dt>
        <dd className="inline">{cert.durationHours} hours</dd>
      </div>
      <div>
        <dt className="inline text-ink-muted">Organiser: </dt>
        <dd className="inline">The Example Collective</dd>
      </div>
      <div>
        <dt className="inline text-ink-muted">Certificate identifier: </dt>
        {/* Not <IdentifierText> here: that component wraps its text in a
            <span>, and a <dd> with nothing else in it would carry the
            identical textContent as that span -- ambiguous for a test
            querying by the identifier's own text. Inlined directly instead;
            `IdentifierText` stays reserved for the token-less panels below,
            where it always sits inside a longer sentence, so the
            surrounding element's textContent is never just the
            identifier alone. */}
        <dd className="inline font-mono text-xs">{cert.identifier}</dd>
      </div>
    </dl>
  );
}

function Valid({ cert }: { cert: DisplayCertificate }) {
  return (
    <Panel tone="primary" title="Certificate verified">
      <p>
        This certificate&apos;s signature is genuine, and our register confirms it is
        currently issued.
      </p>
      <CertificateDetails cert={cert} />
    </Panel>
  );
}

function Revoked({ cert }: { cert: DisplayCertificate }) {
  return (
    <Panel tone="accent" title="Certificate revoked">
      <p>
        This certificate&apos;s signature is genuine -- it really was issued to the person
        named below -- but The Example Collective has since revoked it. A revoked certificate
        should not be relied on to attest attendance.
      </p>
      <CertificateDetails cert={cert} />
    </Panel>
  );
}

function NotVerifiable() {
  return (
    <Panel tone="danger" title="We cannot confirm this certificate">
      <p>
        This link&apos;s signature does not check out against any signing key we currently
        publish. This is not proof that anything is wrong: the code may be damaged or
        incomplete, or it may have been issued under a signing key not yet published here. We
        never show a name or any other certificate detail when we cannot confirm a signature.
      </p>
      <p>
        If you believe this certificate is genuine, contact{' '}
        <a className="underline" href={`mailto:${CONTACT_EMAIL}`}>
          {CONTACT_EMAIL}
        </a>
        .
      </p>
    </Panel>
  );
}

function StateUnknown({ cert }: { cert: DisplayCertificate }) {
  return (
    <Panel tone="info" title="We cannot confirm the current state">
      <p>
        This certificate&apos;s signature is genuine -- it was issued to the person named
        below. We could not reach our register just now to confirm whether it is still
        current or has since been revoked. This is not a sign that the certificate is
        invalid -- please try again shortly, or contact{' '}
        <a className="underline" href={`mailto:${CONTACT_EMAIL}`}>
          {CONTACT_EMAIL}
        </a>
        .
      </p>
      <CertificateDetails cert={cert} />
    </Panel>
  );
}

/**
 * The certificate carries a machine-readable code (the token, in the
 * URL); the printed page also carries the 32-character identifier alone,
 * on its own, for someone with only the paper in hand. This is where that
 * open question from task 12 is answered: a visit with no token answers
 * from the register alone, and says plainly that it has confirmed a
 * record, not a document -- never a name, never an implied signature
 * check.
 */
function RecordCaveat() {
  return (
    <p>
      This confirms a record in our register, not the document itself -- we have not checked
      any certificate&apos;s signature or contents this way, and we cannot show a name without
      the full verification link (with its token), usually printed as a QR code on the
      certificate itself.
    </p>
  );
}

function RecordIssued({ identifier }: { identifier: string }) {
  return (
    <Panel tone="primary" title="Recorded as issued">
      <p>
        Our register shows a certificate with identifier <IdentifierText id={identifier} /> was
        issued and has not been revoked.
      </p>
      <RecordCaveat />
    </Panel>
  );
}

function RecordRevoked({ identifier }: { identifier: string }) {
  return (
    <Panel tone="accent" title="Recorded as revoked">
      <p>
        Our register shows a certificate with identifier <IdentifierText id={identifier} /> was
        issued and has since been revoked.
      </p>
      <RecordCaveat />
    </Panel>
  );
}

function RecordNotFound({ identifier }: { identifier: string }) {
  return (
    <Panel tone="danger" title="Not found in our register">
      <p>
        We have no record of a certificate with identifier <IdentifierText id={identifier} />.
        Check the identifier was typed correctly, or use the full verification link if you
        have it.
      </p>
    </Panel>
  );
}

function RecordUnknown({ identifier }: { identifier: string }) {
  return (
    <Panel tone="info" title="We cannot confirm this right now">
      <p>
        We could not reach our register just now to look up identifier{' '}
        <IdentifierText id={identifier} />. This is not a sign that anything is wrong -- please
        try again shortly.
      </p>
    </Panel>
  );
}

function VerifyWithToken({ token }: { token: string }) {
  const [sig, setSig] = useState<'checking' | VerifyResult>('checking');
  const [lookup, setLookup] = useState<'checking' | LookupResult>('checking');

  useEffect(() => {
    let cancelled = false;
    loadSigningPublicKeys()
      .then(keys => verify(token, keys))
      .then(result => {
        if (!cancelled) setSig(result);
      })
      // `verify`/`loadSigningPublicKeys` never reject -- this mirrors the
      // defence-in-depth `.catch` `SignupForm.tsx`'s own key fetch keeps,
      // so a surprise rejection can never leave this stuck at "Checking…".
      .catch(() => {
        if (!cancelled) setSig({ valid: false, reason: NO_MATCHING_KEY });
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Derived at render time, not written into state: a genuinely-signed
  // payload missing its own identifier field is "our bug, never a
  // forger's" (signing.py's own phrase for this shape of surprise), and
  // there is nothing to look up for it -- the render logic below skips the
  // register entirely for that case, going straight to "state unknown"
  // rather than have an effect call `setLookup` for a lookup that was
  // never going to run.
  const identifier =
    sig !== 'checking' && sig.valid && typeof sig.payload.identifier === 'string'
      ? sig.payload.identifier
      : null;

  useEffect(() => {
    if (!identifier) return;
    let cancelled = false;
    lookupCertificateState(identifier).then(result => {
      if (!cancelled) setLookup(result);
    });
    return () => {
      cancelled = true;
    };
  }, [identifier]);

  if (sig === 'checking') return <Checking />;
  if (!sig.valid) return <NotVerifiable />;

  const cert = asDisplayCertificate(sig.payload);
  if (!identifier) return <StateUnknown cert={cert} />;
  if (lookup === 'checking') return <Checking />;
  if (lookup.status === STATE_ISSUED) return <Valid cert={cert} />;
  if (lookup.status === STATE_REVOKED) return <Revoked cert={cert} />;
  // 'not_found' or 'unavailable': the register was either unreachable, or
  // read successfully but does not (yet, or any longer) mention an
  // identifier a signature has just confirmed genuine -- neither is
  // grounds to say "issued" or "revoked", so both land here.
  return <StateUnknown cert={cert} />;
}

function VerifyTokenless({ identifier }: { identifier: string }) {
  const [lookup, setLookup] = useState<'checking' | LookupResult>('checking');

  useEffect(() => {
    let cancelled = false;
    lookupCertificateState(identifier).then(result => {
      if (!cancelled) setLookup(result);
    });
    return () => {
      cancelled = true;
    };
  }, [identifier]);

  if (lookup === 'checking') return <Checking />;
  if (lookup.status === STATE_ISSUED) return <RecordIssued identifier={identifier} />;
  if (lookup.status === STATE_REVOKED) return <RecordRevoked identifier={identifier} />;
  if (lookup.status === 'not_found') return <RecordNotFound identifier={identifier} />;
  return <RecordUnknown identifier={identifier} />;
}

export function VerifyPage() {
  const { identifier } = useParams<{ identifier: string }>();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  return (
    <div className="max-w-content mx-auto px-6 py-12">
      <div className="max-w-xl">
        <h1 className="font-serif text-3xl mb-6">Certificate verification</h1>
        {!identifier ? (
          <Panel tone="danger" title="No certificate identifier">
            <p>This link does not name a certificate to check.</p>
          </Panel>
        ) : token ? (
          <VerifyWithToken token={token} />
        ) : (
          <VerifyTokenless identifier={identifier} />
        )}
      </div>
    </div>
  );
}
