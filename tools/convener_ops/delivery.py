"""Deliver an issued certificate by e-mail -- the only step in the whole
phase that sends a nominative document anywhere at all (spec S:7's
"Remise": "Par courriel. Jamais de document nominatif depose dans un
depot.").

What this module renders, and why HTML with an inline SVG code
------------------------------------------------------------------
`render_certificate` builds a self-contained HTML document, entirely in
memory: the text `docs/toolkit/certificate.md` already describes in
square-bracket placeholders, plus a machine-readable code spec S:7 requires
-- a QR encoding the certificate's own verification address
(`certificate.verification_url`, identifier and signed token both), so a
reader can confirm the document offline, without an account, without
asking us anything. HTML rather than PDF: no binary toolchain to depend on
in a GitHub Actions runner, the document prints from any browser, and a
holder who wants a PDF can produce one themselves with a browser's own
"print to PDF" -- the one feature every browser already ships. An inline
SVG rather than a raster (PNG) code: no image toolchain either, and an SVG
scales cleanly whatever size a reader's screen or printer renders it at.

The QR library: verified against the task's own constraints before it was
added, not assumed
------------------------------------------------------------------------------
`segno` (`tools/pyproject.toml`'s own comment on this dependency has the
checked facts): pure Python, one universal wheel (`py3-none-any`, checked
against the built artefact), no required dependency for this project's
Python floor, BSD-3-Clause (the licence file, not only the PyPI
classifier), and SVG output through `svg_inline()` -- an embeddable
`<svg>...</svg>` fragment -- with no Pillow and no raster step anywhere in
the call path. `_QR_ERROR_LEVEL = "m"` (roughly 15% error correction) was
checked against this project's own realistic worst case, not chosen by
guesswork: `registration._MAX_FIELD_LENGTH` bounds `first_name` and
`surname` at 200 characters each, and a token built from two 200-character
names plus a 300-character event title still encodes at QR version 36 of
40 under "m" (measured as 36, not the 35 an earlier
draft of this comment assumed -- the whole point of this sentence is that
the number was checked rather than assumed, so it has to be the checked
one) -- comfortable headroom, confirmed by generating one and checking
`segno` did not raise, not merely assumed from a capacity table. The
300-character title is no longer only an assumed worst case either:
`certificate.CertificateEvent.__post_init__` enforces it
-- see that constant's own comment for the concrete overflow
this closes (a title long enough on its own, regardless of name length,
made `segno.make` raise `DataOverflowError`, which this module's caller
folded silently into "not sent", forever, since every retry hit the
identical wall).

Never written to disk, never printed -- and why not a build artefact
either
------------------------------------------------------------------------------
`render_certificate` returns a `str`; nothing in this module, and nothing
in `cli.py`'s own callers, ever writes that string to a file anywhere
under the repository, at any point, on any path -- see spec S:1 and S:7
both: "aucune donnee ... dans le depot" is not a rule this module bends
for a *rendered* document just because the document itself is derived
rather than typed by a person. `test_cli.py`'s own
`test_deliver_certificates_never_writes_anything_to_disk` is the test that
would fail the moment a future edit adds exactly that write.

The registration confirmation faced the analogous problem -- an unsent
message -- and answered it differently: writing it to a single,
`.gitignore`d file inside the job's own workspace, uploaded as a 14-day,
access-controlled build artefact. **That pattern was wrong here,
deliberately, not by oversight, from the day this module was written** --
and a review later ruled it wrong for
that confirmation too, once `docs/governance/traitement-donnees.md`
turned out to call that artefact a documented *exception*, when with SMTP
unconfigured (this project's default state) it was the path every
registration took. `confirmation.py`'s own module docstring now carries
that history in full; this module never had the artefact in the first
place, for a reason narrower and stronger than "it should not be the
default path" -- a build artefact is still an Actions surface, retained
and downloadable by anyone with the run's own access, and unlike a
registration confirmation, which carries an address and a matching code
but no cryptographic attestation of anything, what an unsent certificate
document *is* is exactly the nominative, signed document spec S:7 says may
never be "depose dans un depot". No retention window makes that the right
place for it, fourteen days or otherwise.

What makes never keeping a copy safe here is that delivery is *replayable*
(see the next section): the identical document is reproduced from scratch,
on demand, by calling this module's own functions again with the same
inputs. So an undelivered certificate is never stashed anywhere -- it is
*reported* as unsent (`DeliveryResult.sent is False`, no document, no
body, nothing but a boolean) and *replayed*: re-running the same command,
or the whole workflow, regenerates and re-sends the same document, because
nothing about it was ever computed randomly. `DeliveryResult` was already
the shape `confirmation.SendResult` only later adopted, once that type was
narrowed to match -- see that dataclass's own docstring, below.

Replayable, not regenerated -- and bounded by retention (ruling 3)
------------------------------------------------------------------------
`signing.sign` is deterministic (RSA-PKCS1v15, no randomised salt -- see
that module's own docstring for why), and `certificate.issue`'s
fingerprint-keyed lookup reuses an already-registered attendee's existing
`identifier` rather than minting a new one (`certificate.py`'s own module
docstring, "idempotent without being deterministic"). Together, calling
`issue` again for the same attendee -- whether because a delivery failed
and the whole command is re-run, or because the workflow itself is simply
run twice -- reproduces the *exact same* `identifier` and the *exact same*
token, byte for byte, and therefore the exact same rendered document from
this module. A retry is a replay, never a second certificate for the same
person: spec S:8 promises this in words ("une remise echouee se rejoue
sans regenerer"); the mechanism that makes it true lives in
`certificate.py` and `signing.py`, not here -- this module only has to
avoid *breaking* that property, which is exactly what never caching or
regenerating any part of the document from anything but its own
deterministic inputs achieves.

**What "byte-identical" actually covers: the
document and the token, not the envelope.** `_SmtpDeliveryTransport.send`
now sets a `Date` header (`email.utils.formatdate`, current send time) --
spec S:9's own risk table names the spam folder explicitly ("un certificat
dans les indesirables n'existe pas"), and a missing `Date` is a real
spam-scoring signal, so a resend deserves one exactly as much as the first
send did. This does not conflict with the replay guarantee above: a `Date`
header changes the *message* on a retry, never the attachment or its
signature, and nothing this module's own tests pin ever compares the
envelope byte for byte -- only `_sent_attachment_html` and the token it
carries. `confirmation.py`'s own transport had the identical gap
(inherited, not introduced here), deliberately not touched by this round
-- carried item 6 closed it in the phase's final fix wave instead, the
same fix, in the same place in that module's own `_SmtpTransport.send`.

**That replayability is not unconditional forever, and this module does
not claim it is.** `certificate.issue` needs the event's own decrypted
registrations to find the attendee's fingerprint and address at all --
`data/events/<id>/registrations.enc`, together with the event's own
private key. The retention sweep destroys that private key, and with
it every registration it protects, 90 days after the event.
After that, `certificate.issue` (and therefore this module) has no address
left to resolve `CERTIFICATE_ID` against, or to build a fresh delivery
for, at all -- `data/events/<id>/certificates.yml`, the certificate
register, survives that destruction untouched (`certificate.py`'s own
module docstring, "the register survives the data it was derived from"),
so the certificate keeps verifying, forever, exactly as spec S:7 promises
-- but it can never be *sent* again. Replaying a delivery is bounded by
the same 90-day window as the registration it reads; "replayable" in this
module's own docstrings and tests means "replayable while the
registration this certificate was issued from still exists", not
"replayable forever". `test_cli.py`'s own
`test_deliver_certificate_after_the_registration_is_gone_refuses_cleanly`
is the test for this boundary.

Never prints anything, on any path (mirrors confirmation.py exactly)
------------------------------------------------------------------------
Every function here that could ever see a name, an address, a rendered
document or a token never writes any of it to stdout or stderr, on any
path -- sent, unconfigured, or a transport that raised. `deliver` below
catches only `smtplib.SMTPException` and `OSError`, the same narrow pair
`confirmation.deliver` catches, and for the identical reason: it never
inspects or forwards the caught exception's own text anywhere, because
`smtplib` routinely echoes the *recipient address* into an
`SMTPRecipientsRefused` message, and forwarding that string to a caller
that might print it -- or even just format it into a wider message --
would reopen the exact leak `confirmation.py`'s own module docstring
already closed once. `cli.py`'s own callers print only counts, never a
name or an address, on every path including the branch where an attendee
was already on record before this run started (a real defect once found in
`certificate.py` is the reason that branch gets its
own leak-sweep test here too, not only the freshly-issued one).
"""

from __future__ import annotations

import html
import smtplib
from collections.abc import Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate
from typing import Final, Protocol

import segno

from .certificate import ORGANISER, verification_url
from .confirmation import CONTACT_EMAIL, SIGN_OFF, SmtpConfig, smtp_config_from_env
from .registration import Registration

__all__ = [
    "DOCUMENT_INSTRUCTION",
    "Delivery",
    "DeliveryResult",
    "DeliveryTransport",
    "compose",
    "deliver",
    "render_certificate",
]

#: "M" (~15% error correction) -- see the module docstring's own worked
#: worst-case check for why this comfortably fits even a maximal-length
#: name and title, rather than a table lookup taken on faith.
_QR_ERROR_LEVEL: Final = "m"

#: Scale factor `segno` multiplies each QR module by, in the SVG's own
#: coordinate space -- purely a rendering default (the `<style>` block
#: below further constrains the printed size with `width`/`height`), not a
#: value anything else in this module depends on.
_QR_SCALE: Final = 4

#: RFC 8314's implicit-TLS port. Duplicated from `confirmation.py`'s own
#: constant of the same name and value, deliberately, rather than
#: imported: that one is private to its module (leading underscore, not
#: in `confirmation.__all__`), and this is a fixed protocol constant, not
#: project-specific business logic that the two copies could ever drift
#: on.
_IMPLICIT_TLS_PORT: Final = 465


def _format_duration(hours: float) -> str:
    """ "2" for 2.0, "1.5" for 1.5 -- `duration_hours` is always a multiple
    of a quarter hour (`certificate.duration_hours`'s own rounding rule),
    so `:g` never has to fall back to scientific notation for any value
    this module is ever actually handed; a bare "2.0 hours" is not how a
    printed certificate should read."""
    return f"{hours:g}"


def render_certificate(
    *,
    name: str,
    event_title: str,
    event_date: str,
    duration_hours: float,
    identifier: str,
    token: str,
) -> str:
    """The certificate document, as a complete, self-contained HTML page --
    see the module docstring for why HTML with an inline SVG QR, and why
    this is built entirely in memory (never written to disk, from here or
    from any caller).

    `name`, `event_title`, `event_date` and `duration_hours` are exactly
    the fields `certificate._sign_certificate` signed to produce `token` in
    the first place (`certificate.full_name`, `event.title`, `event.date`,
    `certificate.duration_hours`) -- this function does not re-derive or
    decode any of them from `token` itself; the caller (`cli.py`) already
    holds every one of them from the same call that produced `token`, and
    handing them through directly is what keeps this function a plain,
    total, easily tested function of five primitives rather than a second
    place that has to parse a signed envelope. `identifier` and `token`
    together build the verification address
    (`certificate.verification_url`), printed as text and encoded as the
    QR -- the one machine-readable code spec S:7 requires.

    Every value that could contain a free-typed name or title is escaped
    with `html.escape` before it reaches the page: `name` (a participant's
    own registration) and `event_title` (a speaker's own talk title) both
    come from data this project accepts from people it has not otherwise
    sandboxed, and a certificate is exactly the kind of document a browser
    might one day render untrusted.

    **Deliberately not sanitised: bidi overrides (`U+202E` and friends) and
    a bare newline in `name`.** `html.escape` only
    ever handles `<`, `>`, `&` and `"` -- markup, not direction control or
    whitespace -- so a name carrying `U+202E` or `\\n` reaches this page
    exactly as typed. Left alone on purpose, not merely unnoticed: the
    verification page renders the *same* characters, out of the *same*
    signed payload, so the document and the verifier always agree on what
    the name is. Sanitising only here would make them disagree -- a
    document showing one string while the verifier shows another -- which
    is worse than the cosmetic spoofing (a right-to-left override
    reordering how a name displays) it would prevent."""
    url = verification_url(identifier, token)
    qr_svg = segno.make(url, error=_QR_ERROR_LEVEL).svg_inline(scale=_QR_SCALE)
    safe_name = html.escape(name)
    safe_title = html.escape(event_title)
    safe_date = html.escape(event_date)
    safe_identifier = html.escape(identifier)
    safe_url = html.escape(url, quote=True)
    duration_text = html.escape(f"{_format_duration(duration_hours)} hours")
    safe_organiser = html.escape(ORGANISER)
    doc_title = html.escape(
        f"Certificate of attendance — {event_title}"
        if event_title
        else "Certificate of attendance"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{doc_title}</title>
<style>
  body {{
    font-family: Georgia, 'Times New Roman', serif;
    color: #1a1a1a;
    background: #f4f1ea;
    margin: 0;
    padding: 2.5rem 1rem;
  }}
  .certificate {{
    max-width: 40rem;
    margin: 0 auto;
    background: #ffffff;
    border: 1px solid #c9bfa5;
    padding: 3rem 2.5rem;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
  }}
  .organiser {{
    text-transform: uppercase;
    letter-spacing: 0.15em;
    font-size: 0.85rem;
    color: #6b5f45;
    margin: 0 0 0.5rem;
  }}
  h1 {{
    font-size: 1.6rem;
    margin: 0 0 1.5rem;
  }}
  p {{
    line-height: 1.6;
  }}
  .meta {{
    margin-top: 1.5rem;
    font-size: 0.95rem;
  }}
  .meta dt {{
    font-weight: bold;
  }}
  .meta dd {{
    margin: 0 0 0.75rem;
    word-break: break-all;
  }}
  .qr {{
    margin-top: 2rem;
    text-align: center;
  }}
  .qr svg {{
    width: 10rem;
    height: 10rem;
  }}
  @media print {{
    body {{ background: #ffffff; padding: 0; }}
    .certificate {{ box-shadow: none; border: none; }}
  }}
</style>
</head>
<body>
  <article class="certificate">
    <p class="organiser">{safe_organiser}</p>
    <h1>Certificate of attendance</h1>
    <p>This certifies that <strong>{safe_name}</strong> attended
    <strong>{safe_title}</strong>, held on <strong>{safe_date}</strong>,
    for <strong>{duration_text}</strong>.</p>
    <dl class="meta">
      <dt>Identifier</dt>
      <dd>{safe_identifier}</dd>
      <dt>Verify this certificate at</dt>
      <dd><a href="{safe_url}">{safe_url}</a></dd>
    </dl>
    <div class="qr">{qr_svg}</div>
  </article>
</body>
</html>
"""


@dataclass(frozen=True)
class Delivery:
    """One certificate, ready to deliver or to hand to a fake transport in
    a test. `document` is the whole rendered HTML page (`render_certificate`'s
    own return value) -- carried here only for the length of one send, never
    written anywhere by this module or by `cli.py`."""

    to: str
    subject: str
    body: str
    document: str
    document_filename: str


#: The load-bearing half of the body sentence describing the attachment --
#: exported so `test_delivery.py` can pin it against
#: `docs/toolkit/emails/certificate-delivered.md`'s own copy, the same
#: "export the sentence, do not retype it" discipline
#: `confirmation.MATCHING_INSTRUCTION` and `confirmation.UPDATE_WARNING`
#: already use for their own pages. Before this,
#: only the *subject* was pinned (`test_delivery.py`'s own
#: `test_compose_subject_names_the_event`); the body had drifted
#: typographically from the docs copy -- an ASCII "--" here where the docs
#: page has already used an em dash ("—") since this task's own first
#: round, matching `confirmation.compose`'s own subject-line precedent
#: (`f"{subject} — {event.title}"`) -- so this also fixes that drift, not
#: only pins against a future one.
DOCUMENT_INSTRUCTION: Final = (
    "as a self-contained web page you can open in any browser — print it, "
    'or use your browser\'s own "print to PDF" if you would rather keep a '
    "PDF copy."
)


def compose(
    registration: Registration, event_title: str, identifier: str, document: str
) -> Delivery:
    """The e-mail that carries `document` -- see
    `docs/toolkit/emails/certificate-delivered.md` for the copy this
    mirrors, and `DOCUMENT_INSTRUCTION` above for the one sentence pinned
    against it directly. Deterministic in every argument, the same
    property `confirmation.compose` has and for the same reason: a resend
    (`cli.py::deliver_certificate`) reproduces the identical message, not
    merely one carrying the same document."""
    subject = "Your certificate of attendance"
    if event_title:
        subject = f"{subject} — {event_title}"

    what = f" for {event_title}" if event_title else ""
    lines = [
        f"Dear {registration.first_name},",
        "",
        f"Attached is your certificate of attendance{what}, {DOCUMENT_INSTRUCTION}",
        "",
        f"Identifier: {identifier}",
        "",
        "Best regards,",
        SIGN_OFF,
    ]
    return Delivery(
        to=registration.email,
        subject=subject,
        body="\n".join(lines) + "\n",
        document=document,
        document_filename=f"certificate-{identifier}.html",
    )


class DeliveryTransport(Protocol):
    """What `deliver` needs from something that can actually send mail with
    an attachment. Mirrors `confirmation.EmailTransport`'s own shape;
    every test in `test_delivery.py` and `test_cli.py` substitutes a fake,
    which is what keeps this whole suite off the network."""

    def send(self, config: SmtpConfig, delivery: Delivery) -> None: ...


@dataclass(frozen=True)
class _SmtpDeliveryTransport:
    """The only piece of this module that touches the network. Never
    constructed by a test -- `deliver`'s `transport` parameter exists so a
    test never has to. Stdlib `smtplib` and `email.message`, no new
    dependency for the send path itself (only rendering needed one)."""

    timeout: float = 30.0

    def send(self, config: SmtpConfig, delivery: Delivery) -> None:
        email = EmailMessage()
        email["Subject"] = delivery.subject
        email["From"] = config.sender
        email["To"] = delivery.to
        # A real send time, not a fixed or omitted
        # one -- see the module docstring's "what byte-identical actually
        # covers" section for why this does not weaken the replay
        # guarantee (it changes the envelope, never the document or its
        # signature) and why it belongs here at all (spec S:9's own risk
        # table names the spam folder by name).
        email["Date"] = formatdate(localtime=True)
        # Same reasoning as confirmation.py's own transport: "reply to
        # this message" (the compose() body, implicitly, through this
        # header) must be literally true regardless of what CONVENER_SMTP_FROM
        # happens to be.
        email["Reply-To"] = CONTACT_EMAIL
        email.set_content(delivery.body)
        email.add_attachment(
            delivery.document.encode("utf-8"),
            maintype="text",
            subtype="html",
            filename=delivery.document_filename,
        )
        if config.port == _IMPLICIT_TLS_PORT:
            with smtplib.SMTP_SSL(
                config.host, config.port, timeout=self.timeout
            ) as client:
                client.login(config.user, config.password)
                client.send_message(email)
        else:
            with smtplib.SMTP(config.host, config.port, timeout=self.timeout) as client:
                client.starttls()
                client.login(config.user, config.password)
                client.send_message(email)


@dataclass(frozen=True)
class DeliveryResult:
    """The outcome of trying to deliver one certificate document.

    No `document` field, and (since always) no `unsent_body` field either:
    **no way to hold the rendered document here at all**, even
    transiently. See the module docstring's "never written to disk"
    section (ruling 1, ruling 2) for why -- a future caller must never be
    able to "helpfully" write an unsent certificate to a file, an artefact
    included, the way an earlier version of `cli.py::_send_confirmation`
    once wrote `confirmation.SendResult.unsent_body` to
    `unsent-confirmation.eml`. That pattern was already wrong for an
    unsent *confirmation* too, once a review found
    it the default path rather than the documented exception the record
    called it -- `confirmation.py`'s own module docstring carries that
    history -- but it would have been wrong here regardless of what that
    module did: a signed, nominative certificate is exactly what spec S:7
    says may never be "depose dans un depot", an Actions build artefact
    included, and no retention window changes that. `sent` alone is
    everything `cli.py` needs to print a one-line count; the certificate
    itself is never lost by this type refusing to carry a copy, because a
    retry reproduces it byte-identically (see the module docstring's
    "replayable, not regenerated" section) for as long as the
    registration it was built from still exists."""

    sent: bool


def deliver(
    delivery: Delivery,
    env: Mapping[str, str],
    *,
    transport: DeliveryTransport | None = None,
) -> DeliveryResult:
    """Send `delivery`, or report it unsent -- never anywhere in between.
    Mirrors `confirmation.deliver` exactly: two causes collapse to the same
    `DeliveryResult(sent=False)` (no transport configured, and a configured
    transport that raised `smtplib.SMTPException` or `OSError` while
    sending), and the caught exception's own text is never inspected or
    forwarded anywhere -- `smtplib` routinely echoes the recipient address
    into `SMTPRecipientsRefused`, and this function must never be the thing
    that turns that into a leak."""
    config = smtp_config_from_env(env)
    if config is None:
        return DeliveryResult(sent=False)
    active_transport = transport if transport is not None else _SmtpDeliveryTransport()
    try:
        active_transport.send(config, delivery)
    except (smtplib.SMTPException, OSError):
        return DeliveryResult(sent=False)
    return DeliveryResult(sent=True)
