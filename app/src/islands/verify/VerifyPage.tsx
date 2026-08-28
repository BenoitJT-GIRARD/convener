import type { ReactNode } from 'react';
import { instanceIdentity } from '../../instance';
import { useEffect, useState } from 'react';
import { verify } from '../../verify/verify';
import type { VerifyResult } from '../../verify/verify';
import { asDisplayCertificate } from '../../verify/format';
import type { DisplayCertificate } from '../../verify/format';
import { loadSigningPublicKeys } from '../../verify/publicKeys';
import {
  isValidIdentifierShape,
  lookupCertificateState,
  STATE_ISSUED,
  STATE_REVOKED,
} from '../../verify/register';
import type { LookupResult } from '../../verify/register';

/**
 * Verification without disclosure, made into a page: someone
 * who receives a certificate confirms it holding nothing but the link
 * printed on it (or the 32-character identifier alone, from the printed
 * page -- see `VerifyTokenless` below) -- no account, no request to us for
 * the payload.
 *
 * Extracted from the operators' application package
 * (`app/src/verify/VerifyPage.tsx`, now deleted -- see git history) into
 * an island mounted on its own static page (`site/src/verify.njk`), the
 * identical move registration made. Everything this project
 * promised about verification holds unchanged: `verify.ts`,
 * `register.ts`, `publicKeys.ts` and `format.ts` stay exactly where they
 * were, in `app/src/verify/`, imported here rather than reimplemented
 * -- this file changed, the crypto and the register lookup did not.
 *
 * What changed in the extraction, and why
 * -----------------------------------------
 * - `identifier` and `token` are props, not route params read via
 *   `useParams`/`useSearchParams`: this island has no router at all.
 *   `main.tsx` reads both off `location.hash` itself -- see that file's
 *   own comment for the parsing this replaces `react-router-dom`'s
 *   `HashRouter` with, and for why a `hashchange` listener there gives
 *   this component the same remount discipline `App.tsx`'s old
 *   `VerifyRoute` gave it by keying on a route match.
 * - Class names are plain, semantic strings (`verify__panel`, ...),
 *   reusing `.notice`'s own box shape -- the same reasoning
 *   `SignupForm.tsx`'s own module comment gives for its own conversion
 *   away from Tailwind utilities: this island renders inside a page that
 *   already loads `site/src/style.css`, and pulling in the app's own
 *   Tailwind build here would leak site-wide, not stay scoped to this
 *   component's own subtree.
 *
 * `#/<identifier>?token=…`, not `/verify/<identifier>?token=…`
 * -----------------------------------------------------------------------
 * The fragment is load-bearing for privacy, not only for GitHub Pages
 * routing, and it is the one thing this extraction did *not* change:
 * everything after `#` is resolved by the browser locally, never sent in
 * an HTTP request, and stripped from `Referer` before this page ever
 * navigates away. `?token=` carries the holder's own **name**
 * (`signing.PAYLOAD_FIELDS`), so serving this page from a bare path
 * instead -- the way registration's own address moved -- would
 * silently start sending every verified participant's name to GitHub's
 * servers in a query string, and to whatever site a link is clicked from
 * after, through `Referer`. A router is not what made that safe: a static
 * page reads `location.hash` exactly as well as a `HashRouter` did, which
 * is why this extraction could drop the router and keep the property. See
 * `tools/convener_ops/certificate.py`'s own module docstring ("the
 * verification address") and its
 * `test_verification_url_carries_the_token_after_the_fragment_not_before_it`
 * for the Python-side half of this same guarantee.
 *
 * Signature first, register second
 * --------------------------------
 * `VerifyWithToken` never asks the register anything until a token's
 * signature has already verified -- a malformed or unmatched token never
 * reaches `lookupCertificateState` at all. The register answers "is this
 * currently issued or revoked", not "is this genuine"; asking it the
 * second question, or rendering its unavailability as a verdict on the
 * first, is exactly the confusion this ordering exists to prevent: a
 * register that cannot be read must say "I cannot confirm the state",
 * never "invalid certificate". `NotVerifiable` below is reachable purely
 * from a signature check, with no register call involved at all.
 *
 * Every appearance states only what was actually established
 * ----------------------------------------------------------
 * `valid` / `revoked` / `not verifiable` share their tone with the three
 * intents (`primary` / `accent` / `danger`), but "state unknown" is
 * not one appearance -- it is one *shape* of honesty applied to three
 * different established facts, because "we could not reach our register"
 * and "we read it, and it does not (yet) mention this identifier" and "we
 * could not even load our own signing keys" are three different claims,
 * and the second of each pair is never the holder's fault:
 *
 * - `NotVerifiable` (danger) -- a signing-key manifest was loaded
 *   successfully (even a genuinely empty one) and this token's signature
 *   does not check out against anything in it. `NO_MATCHING_KEY` and
 *   `MALFORMED` (see verify.ts) still share this one appearance rather
 *   than getting one each -- a well-formed, unmatched token and a
 *   genuinely malformed one both mean the same thing to a stranger
 *   standing here, "I cannot confirm this", and naming which of the two
 *   happened would risk reading as "prove it harder". The distinction
 *   still exists as data (verify.ts's own return type, pinned against the
 *   shared fixture's two reason spellings); it is simply not a second
 *   visual state.
 * - `CannotCheckSignature` (info) -- the signing-key manifest itself could
 *   not be loaded at all (`publicKeys.ts::loadSigningPublicKeys` returned
 *   `null`, not `[]`). Nothing has been checked against anything yet, so
 *   this must never read as `NotVerifiable` -- that would paint a
 *   certificate we simply could not check the same shade of "danger" as
 *   one that is genuinely forged.
 * - `StateUnknown` (info) -- the signature *is* genuine, and either the
 *   register could not be reached, or (a distinct, rarer cause) the
 *   confirmed payload carries no `identifier` field to look one up with
 *   at all -- this system's own bug, never a forger's. The body
 *   text names which, so it never claims to have reached a register it
 *   never asked.
 * - `NotInRegister` (info) -- the signature is genuine, the register
 *   *was* read successfully, and it simply does not list this identifier
 *   -- a decisive fact, distinct from "we do not know", and never shown
 *   with `StateUnknown`'s "we could not reach it" wording.
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

// The address a participant writes to about their own data. Declared
// once in `instance/config.json` and carried into this
// bundle by `vite.config.ts`'s own define, because this runs in a
// participant's browser. A duplicate that left this literal here would
// send its own participants' data-protection requests to the previous
// instance's inbox.
const contactEmail = () => instanceIdentity().contact;

type Tone = 'primary' | 'accent' | 'danger' | 'info';

/** `site/src/style.css`'s own class names for the one panel shape every
 *  answer this page gives shares (reusing `.notice`), coloured per tone --
 *  the same lookup-by-tone shape the Tailwind version of this component
 *  used, kept because it is still the right way to pick a whole class list
 *  rather than interpolate one. */
const TONE_CLASSES: Record<Tone, { panel: string; title: string }> = {
  primary: { panel: 'notice verify__panel verify__panel--primary', title: 'verify__eyebrow verify__eyebrow--primary' },
  accent: { panel: 'notice verify__panel verify__panel--accent', title: 'verify__eyebrow verify__eyebrow--accent' },
  danger: { panel: 'notice verify__panel verify__panel--danger', title: 'verify__eyebrow verify__eyebrow--danger' },
  info: { panel: 'notice verify__panel verify__panel--info', title: 'verify__eyebrow verify__eyebrow--info' },
};

function Panel({ tone, title, children }: { tone: Tone; title: string; children: ReactNode }) {
  const classes = TONE_CLASSES[tone];
  return (
    <div role="alert" className={classes.panel}>
      <p className={classes.title}>{title}</p>
      {children}
    </div>
  );
}

function Checking() {
  return <p className="verify__checking">Checking…</p>;
}

function IdentifierText({ id }: { id: string }) {
  return <span className="verify__id">{id}</span>;
}

function CertificateDetails({ cert }: { cert: DisplayCertificate }) {
  return (
    <dl className="verify__details">
      <div>
        <dt>Name: </dt>
        <dd>{cert.name}</dd>
      </div>
      <div>
        <dt>Event: </dt>
        <dd>{cert.event}</dd>
      </div>
      <div>
        <dt>Date: </dt>
        <dd>{cert.date}</dd>
      </div>
      <div>
        <dt>Duration: </dt>
        <dd>{cert.durationHours} hours</dd>
      </div>
      <div>
        <dt>Organiser: </dt>
        <dd>{instanceIdentity().organisation}</dd>
      </div>
      <div>
        <dt>Certificate identifier: </dt>
        {/* Not <IdentifierText> here: that component wraps its text in a
            <span>, and a <dd> with nothing else in it would carry the
            identical textContent as that span -- ambiguous for a test
            querying by the identifier's own text. Inlined directly instead;
            `IdentifierText` stays reserved for the token-less panels below,
            where it always sits inside a longer sentence, so the
            surrounding element's textContent is never just the
            identifier alone. */}
        <dd className="verify__id">{cert.identifier}</dd>
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
        named below -- but {instanceIdentity().organisation} has since revoked it. A revoked
        certificate
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
        <a href={`mailto:${contactEmail()}`}>{contactEmail()}</a>.
      </p>
    </Panel>
  );
}

/**
 * Reachable only when `loadSigningPublicKeys()` returned
 * `null` -- the keys manifest itself could not be fetched or parsed, so
 * nothing has been checked against anything yet. Must never share
 * `NotVerifiable`'s copy or tone: that would tell a stranger a genuine
 * certificate "does not check out against any signing key we currently
 * publish", a claim this page never actually established.
 */
function CannotCheckSignature() {
  return (
    <Panel tone="info" title="We cannot check this certificate right now">
      <p>
        We could not load the signing keys we publish, so we could not check whether this
        certificate&apos;s signature is genuine. This is not a sign that anything is wrong
        with it -- please try again shortly, or contact{' '}
        <a href={`mailto:${contactEmail()}`}>{contactEmail()}</a> if this persists.
      </p>
    </Panel>
  );
}

/**
 * The signature is genuine, and the register either could
 * not be reached (`reason: 'register_unreachable'`) or the confirmed
 * payload carries no `identifier` field to look one up with at all
 * (`reason: 'no_identifier'` -- this system's own bug, never a
 * forger's). Same title and tone either way -- in both cases the honest
 * claim is "we do not know" -- but the body text names which is true,
 * since "we could not reach our register" would be false for the second.
 */
function StateUnknown({
  cert,
  reason,
}: {
  cert: DisplayCertificate;
  reason: 'register_unreachable' | 'no_identifier';
}) {
  return (
    <Panel tone="info" title="We cannot confirm the current state">
      <p>
        This certificate&apos;s signature is genuine -- it was issued to the person named
        below.{' '}
        {reason === 'register_unreachable'
          ? 'We could not reach our register just now to confirm whether it is still current or has since been revoked.'
          : "This certificate does not carry an identifier we can look up, so we cannot confirm whether it is still current or has since been revoked."}{' '}
        This is not a sign that the certificate is invalid -- please try again shortly, or
        contact <a href={`mailto:${contactEmail()}`}>{contactEmail()}</a>.
      </p>
      <CertificateDetails cert={cert} />
    </Panel>
  );
}

/**
 * The signature is genuine *and* the register was read
 * successfully -- unlike `StateUnknown`, this is a decisive fact ("it is
 * not there"), not "we do not know". Kept at tone `info`, not `danger`:
 * the signature already confirms this is genuinely one of ours, so this
 * must never read as an accusation the way the token-less path's
 * `RecordNotFound` (which has no such confirmation) is allowed to.
 */
function NotInRegister({ cert }: { cert: DisplayCertificate }) {
  return (
    <Panel tone="info" title="Not yet reflected in our register">
      <p>
        This certificate&apos;s signature is genuine -- it was issued to the person named
        below. We read our register successfully, but it does not currently list this
        certificate&apos;s identifier. This can happen briefly right after issuance and is not
        a sign that anything is wrong -- if it persists, contact{' '}
        <a href={`mailto:${contactEmail()}`}>{contactEmail()}</a>.
      </p>
      <CertificateDetails cert={cert} />
    </Panel>
  );
}

/**
 * The certificate carries a machine-readable code (the token, in the
 * URL); the printed page also carries the 32-character identifier alone,
 * on its own, for someone with only the paper in hand. This is where that
 * open question is answered: a visit with no token answers
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

/**
 * The token-less flow's only input is the raw identifier this
 * page was given, never confirmed by any signature -- unlike
 * `VerifyWithToken`, below, which always uses the token's own
 * cryptographically-confirmed `identifier` field instead of the given one
 * when both are available. Applying `certificate._CERTIFICATE_ID_RE`'s own
 * shape here closes the one gap that leaves: an identifier that never
 * named one of our certificates at all no longer reads as "not found"
 * (which implies a real, absent identifier) or gets echoed verbatim under
 * this page's own heading.
 */
function InvalidIdentifierShape({ identifier }: { identifier: string }) {
  return (
    <Panel tone="danger" title="Not a certificate identifier">
      <p>
        <IdentifierText id={identifier} /> is not shaped like one of our certificate
        identifiers (32 lowercase hexadecimal characters). Check that you typed or copied it
        correctly, or use the full verification link if you have it.
      </p>
    </Panel>
  );
}

function VerifyWithToken({ token }: { token: string }) {
  const [sig, setSig] = useState<'checking' | 'keys_unavailable' | VerifyResult>('checking');
  const [lookup, setLookup] = useState<'checking' | LookupResult>('checking');

  useEffect(() => {
    let cancelled = false;
    loadSigningPublicKeys()
      .then(keys => {
        if (cancelled) return undefined;
        // `null` means the keys manifest itself could not
        // be loaded -- nothing has been checked against anything yet, so
        // this must never reach `verify()` and read as a signature that
        // genuinely failed. `[]` (a manifest that was read successfully
        // and lists no key) still reaches `verify()` below exactly as
        // before -- it deterministically reports `NO_MATCHING_KEY`, the
        // correct, honest "not verifiable" outcome for that case.
        if (keys === null) {
          setSig('keys_unavailable');
          return undefined;
        }
        return verify(token, keys).then(result => {
          if (!cancelled) setSig(result);
        });
      })
      // `verify`/`loadSigningPublicKeys` never reject -- this mirrors the
      // defence-in-depth `.catch` `SignupForm.tsx`'s own key fetch keeps,
      // so a surprise rejection can never leave this stuck at "Checking…".
      .catch(() => {
        if (!cancelled) setSig('keys_unavailable');
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
    sig !== 'checking' && sig !== 'keys_unavailable' && sig.valid &&
    typeof sig.payload.identifier === 'string'
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
  if (sig === 'keys_unavailable') return <CannotCheckSignature />;
  if (!sig.valid) return <NotVerifiable />;

  const cert = asDisplayCertificate(sig.payload);
  if (!identifier) return <StateUnknown cert={cert} reason="no_identifier" />;
  if (lookup === 'checking') return <Checking />;
  if (lookup.status === STATE_ISSUED) return <Valid cert={cert} />;
  if (lookup.status === STATE_REVOKED) return <Revoked cert={cert} />;
  // 'not_found': the register was read successfully and simply does not
  // (yet, or any longer) mention an identifier a signature has just
  // confirmed genuine -- a decisive fact, distinct from "we do not know"
  // 'unavailable': the register itself could not be
  // reached at all -- genuinely "we do not know".
  if (lookup.status === 'not_found') return <NotInRegister cert={cert} />;
  return <StateUnknown cert={cert} reason="register_unreachable" />;
}

function VerifyTokenless({ identifier }: { identifier: string }) {
  const [lookup, setLookup] = useState<'checking' | LookupResult>('checking');
  const validShape = isValidIdentifierShape(identifier);

  useEffect(() => {
    // An identifier that is not even shaped like one of ours has
    // nothing worth looking up -- never asks the register for it.
    if (!validShape) return;
    let cancelled = false;
    lookupCertificateState(identifier).then(result => {
      if (!cancelled) setLookup(result);
    });
    return () => {
      cancelled = true;
    };
  }, [identifier, validShape]);

  if (!validShape) return <InvalidIdentifierShape identifier={identifier} />;
  if (lookup === 'checking') return <Checking />;
  if (lookup.status === STATE_ISSUED) return <RecordIssued identifier={identifier} />;
  if (lookup.status === STATE_REVOKED) return <RecordRevoked identifier={identifier} />;
  if (lookup.status === 'not_found') return <RecordNotFound identifier={identifier} />;
  return <RecordUnknown identifier={identifier} />;
}

export function VerifyPage({ identifier, token }: { identifier?: string; token?: string }) {
  return (
    <div className="verify">
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
  );
}
