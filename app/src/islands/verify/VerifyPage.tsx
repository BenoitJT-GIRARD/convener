import type { FormEvent, ReactNode } from 'react';
import { instanceIdentity, showcasePath } from '../../instance';
import { useEffect, useRef, useState } from 'react';
import { verify } from '../../verify/verify';
import type { VerifyResult } from '../../verify/verify';
import { asDisplayCertificate } from '../../verify/format';
import type { DisplayCertificate } from '../../verify/format';
import { loadSigningPublicKeys } from '../../verify/publicKeys';
import { normaliseIdentifier, parsePrintedAddress } from '../../verify/address';
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
 * `tools/convener_ops/journey/certificate.py`'s own module docstring ("the
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
 * browser already has, in their own URL or in what they typed into the
 * form below -- never logged, never sent anywhere else. Nothing in this
 * file calls `console.*` or touches `localStorage`; the one fetch made
 * when a token is present (`lookupCertificateState`, in register.ts)
 * carries no identifier over the network at all, and the token-less path
 * (`VerifyTokenless`) never runs any cryptography and never renders a
 * name, by construction -- there is no payload in scope for it to read
 * one from.
 *
 * Reached with no link at all
 * -----------------------------------------------------------------------
 * This page used to answer a visit carrying no identifier with one panel
 * saying the link named no certificate, and there was no field anywhere
 * on it to do anything about that. Everything a holder needs is printed
 * on their certificate --
 * `tools/convener_ops/journey/delivery.py::render_certificate` puts the
 * identifier on its own line and the whole verification address under it,
 * and encodes that same address as the QR -- so the one thing that page
 * could not survive was its own address changing. A renamed
 * organisation, a moved repository or a custom domain leaves every
 * certificate already issued pointing at nothing, with its holder reading
 * an identifier off the paper and having nowhere to put it, and a
 * relative path cannot help: a QR scanner and a human eye both have no
 * base to resolve one against. `HandEntry` below is the way in, and what
 * it reaches is this same component, from these same modules, as a link
 * reaches.
 *
 * It keeps the property `register.ts` and `certificate.py` are both
 * written around: nothing about *which* certificate is being checked
 * leaves the browser. What was typed stays in this component's own state
 * -- it is never written into `location.hash`, so it reaches no history
 * entry, no address bar and no `Referer` -- `lookupCertificateState`
 * still fetches the whole register rather than one row, and a signature
 * is still checked here against keys this page already holds. The form
 * carries `method="post"` for the reason `SignupForm.tsx`'s own does: if
 * React's delegated submit handler ever failed to attach, a native GET
 * submit would put a token -- which carries the holder's **name** -- into
 * a query string, the browser history and the next page's `Referer`.
 */

// Where a visitor asks us about a certificate: the showcase's data page,
// whose contact section reveals the address only on request
// (`site/src/contact.js`). Linked rather than written out, so this page
// never puts the address where a crawler collecting addresses can read
// it. The showcase's own path comes from `instance/config.json`, carried
// into this bundle by `vite.config.ts`'s own define.
const contactHref = () => `${showcasePath()}data/#contact`;

function ContactUs() {
  return <a href={contactHref()}>contact us</a>;
}

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
      <p>This certificate is genuine and has not been revoked.</p>
      <CertificateDetails cert={cert} />
    </Panel>
  );
}

function Revoked({ cert }: { cert: DisplayCertificate }) {
  return (
    <Panel tone="accent" title="Certificate revoked">
      <p>
        This certificate was issued to the person named below, but{' '}
        {instanceIdentity().organisation} has since revoked it. It no longer attests
        attendance.
      </p>
      <CertificateDetails cert={cert} />
    </Panel>
  );
}

/**
 * `entered` says the code was typed or pasted into `HandEntry` rather
 * than followed as a link, and that difference is the whole reason this
 * component takes a prop. A code that arrived by hand is one a copy could
 * have truncated or a line break could have cut, so the first thing worth
 * doing about it is looking at it again -- offered before the address
 * that is a link's only recourse. Neither wording calls anything forged:
 * `MALFORMED` and `NO_MATCHING_KEY` are the same "we cannot confirm this"
 * to a stranger standing here (see this file's own module comment), and a
 * mistyped character is much the likelier of the two.
 */
function NotVerifiable({ entered }: { entered: boolean }) {
  return (
    <Panel tone="danger" title="We cannot confirm this certificate">
      <p>
        {entered
          ? 'We could not confirm the link you entered.'
          : 'We could not confirm this link.'}{' '}
        It may be incomplete or damaged.
      </p>
      {entered && (
        <p>
          Check that you copied the whole link, including everything after the{' '}
          <code>#</code>, and try again.
        </p>
      )}
      <p>
        If you believe this certificate is genuine, <ContactUs />.
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
        We could not load what we need to check this certificate. Please try again in a
        moment, or <ContactUs /> if it keeps happening.
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
    <Panel tone="info" title="We cannot confirm it is still valid">
      <p>
        This certificate was issued to the person named below.{' '}
        {reason === 'register_unreachable' ? (
          <>
            We could not reach our register to check whether it has been revoked since.
            Please try again in a moment, or <ContactUs />.
          </>
        ) : (
          <>
            It carries no identifier, so we cannot check whether it has been revoked since.
            To confirm it, <ContactUs />.
          </>
        )}
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
    <Panel tone="info" title="Not yet in our register">
      <p>
        This certificate was issued to the person named below, but our register does not
        list it yet. This can happen just after a certificate is issued. If it lasts,{' '}
        <ContactUs />.
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
      This only confirms what our register lists for this identifier, not the document in
      front of you. To check the certificate itself and see the name on it, scan its code
      or paste its full verification link.
    </p>
  );
}

function RecordIssued({ identifier }: { identifier: string }) {
  return (
    <Panel tone="primary" title="Recorded as issued">
      <p>
        Our register lists certificate <IdentifierText id={identifier} /> as issued and not
        revoked.
      </p>
      <RecordCaveat />
    </Panel>
  );
}

function RecordRevoked({ identifier }: { identifier: string }) {
  return (
    <Panel tone="accent" title="Recorded as revoked">
      <p>
        Our register lists certificate <IdentifierText id={identifier} /> as issued and since
        revoked.
      </p>
      <RecordCaveat />
    </Panel>
  );
}

function RecordNotFound({ identifier }: { identifier: string }) {
  return (
    <Panel tone="danger" title="Not found in our register">
      <p>
        Our register has no certificate <IdentifierText id={identifier} />. Check the
        identifier, or scan the code on the certificate.
      </p>
    </Panel>
  );
}

function RecordUnknown({ identifier }: { identifier: string }) {
  return (
    <Panel tone="info" title="We cannot check this right now">
      <p>
        We could not reach our register to look up <IdentifierText id={identifier} />. Please
        try again in a moment.
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
        <IdentifierText id={identifier} /> is not a certificate identifier. An identifier has
        32 characters, using only the digits 0 to 9 and the letters a to f.
      </p>
    </Panel>
  );
}

function VerifyWithToken({ token, entered }: { token: string; entered: boolean }) {
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
  if (!sig.valid) return <NotVerifiable entered={entered} />;

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

/** What this page was given, however it arrived: off the URL, or out of
 *  the form below. `identifier` is the empty string when only a token was
 *  given -- an address may carry one without the other, and a token names
 *  its own certificate inside the payload its signature covers, so
 *  `VerifyWithToken` never reads this field. Neither route ever builds
 *  one of these with both halves empty. */
interface Entry {
  readonly identifier: string;
  readonly token?: string;
}

/** The ids that tie each label, hint and error to its own field. Module
 *  constants rather than `useId()`: `site/src/verify.njk` mounts this
 *  island once per document (`#verify-app`), so there is no second copy
 *  for a fixed id to collide with. */
const IDENTIFIER_FIELD = 'verify-identifier';
const IDENTIFIER_HINT = 'verify-identifier-hint';
const ADDRESS_FIELD = 'verify-address';
const ADDRESS_HINT = 'verify-address-hint';
const ENTRY_ERROR = 'verify-entry-error';

/** Four times the longest address this project has ever printed (885
 *  characters for the shared fixture's own, host and prefix on top), so
 *  that a paste is bounded without any real one being truncated. */
const MAX_ENTRY_LENGTH = 4096;

/**
 * What somebody is told when what they typed is not one of our
 * identifiers, and it is never "not found": the register is not asked at
 * all for a string that could not name a certificate, so the honest
 * complaint is about the shape, and the useful half of it is *which* way
 * the shape is wrong. Length first, because a truncated copy is the
 * common failure and a reader can count; a wrong character otherwise,
 * which is the only thing left once the length is right.
 *
 * It never prints what was typed back. `InvalidIdentifierShape`'s own
 * comment gives the reason -- React escapes it, so this was never an XSS
 * risk, but a page that echoes arbitrary text under its own heading is
 * one nobody should have to think about twice -- and the field still
 * holds what was typed, an inch above the message.
 */
function shapeComplaint(identifier: string): string {
  const shape =
    'An identifier has 32 characters, using only the digits 0 to 9 and the letters a to f';
  return identifier.length === 32
    ? `${shape}. This one has the right length, so one of its characters is not allowed. Check it against the certificate.`
    : `${shape}. This one has ${identifier.length}. Check it against the certificate.`;
}

/**
 * The way in for somebody holding a certificate and no working link.
 *
 * Two fields, one for each thing a certificate has printed on it, and
 * either one is enough: the identifier alone answers from the register,
 * and the address carries the signed token, which is what lets a name be
 * shown. Each has a real label; the identifier's placeholder is an
 * example of its format, never a stand-in for that label. Each hint says
 * where on the certificate to look, through `aria-describedby`, so a
 * screen reader reads it with the field rather than leaving it as an
 * unannounced paragraph nearby.
 *
 * Whichever box an address is pasted into, it is read as one
 * (`parsePrintedAddress` is applied to both), because a person with one
 * long string in the clipboard should not have to work out which of two
 * boxes this page wanted it in.
 *
 * The shape is checked here rather than left to `VerifyTokenless`'s own
 * `InvalidIdentifierShape` panel: an answer beside the field that still
 * holds what was typed is a correction, and the same sentence in a panel
 * that has replaced the form is a dead end.
 */
function HandEntry({
  focusOnMount,
  onEntered,
}: {
  focusOnMount: boolean;
  onEntered: (entry: Entry) => void;
}) {
  const [identifierText, setIdentifierText] = useState('');
  const [addressText, setAddressText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const identifierInput = useRef<HTMLInputElement>(null);

  // Only after `Check another certificate` has taken an answer off the
  // screen -- never on first load, where stealing focus would scroll a
  // reader past the heading that says what this page is.
  useEffect(() => {
    if (focusOnMount) identifierInput.current?.focus();
  }, [focusOnMount]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fromField = parsePrintedAddress(identifierText);
    const fromAddress = parsePrintedAddress(addressText);
    const token = fromField.token ?? fromAddress.token;
    const identifier =
      fromField.identifier ?? fromAddress.identifier ?? normaliseIdentifier(identifierText);

    // A token is checked against its own signed payload, which carries the
    // identifier `VerifyWithToken` actually uses -- so an address that
    // brought one is answerable whatever the identifier field holds, and
    // refusing it over that field's shape would refuse a certificate this
    // page can read.
    if (token) {
      setError(null);
      onEntered({ identifier, token });
      return;
    }
    if (!identifier) {
      setError('Enter the identifier printed on the certificate, or paste its verification link.');
      identifierInput.current?.focus();
      return;
    }
    if (!isValidIdentifierShape(identifier)) {
      setError(shapeComplaint(identifier));
      identifierInput.current?.focus();
      return;
    }
    setError(null);
    onEntered({ identifier });
  }

  return (
    <div className="verify__entry">
      <h2 className="verify__entry-title">Enter the certificate details</h2>
      {/* `method="post"` on a page that would otherwise default to GET.
          Unreachable through React's own delegated submit handler, but if
          that handler ever failed to attach, a native submit would put a
          token -- which carries the holder's name -- into the URL, the
          browser history and the `Referer` of whatever loads next. The
          same closure `SignupForm.tsx` makes for the same reason. */}
      <form method="post" onSubmit={submit} className="verify__form">
        <div className="verify__field">
          <label htmlFor={IDENTIFIER_FIELD}>Certificate identifier</label>
          <p className="verify__hint" id={IDENTIFIER_HINT}>
            Printed on the certificate under &ldquo;Identifier&rdquo;.
          </p>
          <input
            ref={identifierInput}
            id={IDENTIFIER_FIELD}
            type="text"
            placeholder="32 characters, for example 0a1b2c3d4e5f…"
            value={identifierText}
            onChange={e => setIdentifierText(e.target.value)}
            aria-describedby={error ? `${IDENTIFIER_HINT} ${ENTRY_ERROR}` : IDENTIFIER_HINT}
            aria-invalid={error ? true : undefined}
            autoComplete="off"
            spellCheck={false}
            maxLength={MAX_ENTRY_LENGTH}
          />
        </div>
        <div className="verify__field">
          <label htmlFor={ADDRESS_FIELD}>Verification link (optional)</label>
          <p className="verify__hint" id={ADDRESS_HINT}>
            To also see the name on the certificate, paste the full link printed under
            &ldquo;Verify this certificate at&rdquo;.
          </p>
          <textarea
            id={ADDRESS_FIELD}
            rows={3}
            value={addressText}
            onChange={e => setAddressText(e.target.value)}
            aria-describedby={ADDRESS_HINT}
            autoComplete="off"
            spellCheck={false}
            maxLength={MAX_ENTRY_LENGTH}
          />
        </div>
        <button type="submit" className="btn btn--primary">
          Check this certificate
        </button>
        {error && (
          // `role="alert"`, an implicit assertive live region: this text
          // appears purely in response to the button above it, and
          // without this a screen reader user is never told it happened
          // at all. The same discipline `SignupForm.tsx` keeps for its
          // own submit error.
          <p role="alert" id={ENTRY_ERROR} className="verify__error">
            {error}
          </p>
        )}
      </form>
    </div>
  );
}

export function VerifyPage({ identifier, token }: { identifier?: string; token?: string }) {
  const [entry, setEntry] = useState<Entry | null>(null);
  const [returning, setReturning] = useState(false);

  // The URL always wins, and it is read for a token as well as an
  // identifier: an address carrying only a token is still answerable,
  // because the token names its own certificate once its signature holds.
  const fromUrl: Entry | null =
    identifier || token ? { identifier: identifier ?? '', token } : null;
  const given = fromUrl ?? entry;

  if (!given) {
    return (
      <div className="verify">
        <HandEntry focusOnMount={returning} onEntered={setEntry} />
      </div>
    );
  }

  // Keyed for the reason `main.tsx` keys this whole component: a second
  // certificate checked in the same visit must tear the first one's
  // `sig`/`lookup` state down rather than reuse it, or a stale answer
  // briefly describes the previous certificate under the new one's entry.
  const key = `${given.identifier}::${given.token ?? ''}`;
  return (
    <div className="verify">
      {given.token !== undefined ? (
        <VerifyWithToken key={key} token={given.token} entered={fromUrl === null} />
      ) : (
        <VerifyTokenless key={key} identifier={given.identifier} />
      )}
      {fromUrl === null && (
        <p className="verify__again">
          <button
            type="button"
            className="btn"
            onClick={() => {
              setEntry(null);
              setReturning(true);
            }}
          >
            Check another certificate
          </button>
        </p>
      )}
    </div>
  );
}
