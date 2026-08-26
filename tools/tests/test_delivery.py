from __future__ import annotations

import html
import re
import smtplib
from pathlib import Path
from typing import Any, ClassVar

import pytest
import segno

from convener_ops.certificate import ORGANISER, verification_url
from convener_ops.confirmation import CONTACT_EMAIL, SmtpConfig
from convener_ops.delivery import (
    DOCUMENT_INSTRUCTION,
    Delivery,
    DeliveryResult,
    compose,
    deliver,
    render_certificate,
)
from convener_ops.registration import Registration

_TOKEN = "a-fake-token-not-a-real-signature"
_IDENTIFIER = "f" * 32


def _registration(**overrides: Any) -> Registration:
    base: dict[str, Any] = {
        "first_name": "Ada",
        "surname": "Lovelace",
        "email": "ada@example.org",
        "institution": "Analytical Engines Institute",
        "membership_opt_in": True,
    }
    base.update(overrides)
    return Registration(**base)


def _document(**overrides: Any) -> str:
    fields: dict[str, Any] = {
        "name": "Ada Lovelace",
        "event_title": "On analytical engines",
        "event_date": "2026-09-01",
        "duration_hours": 1.5,
        "identifier": _IDENTIFIER,
        "token": _TOKEN,
    }
    fields.update(overrides)
    return render_certificate(**fields)


class FakeTransport:
    """Records every call; never touches a socket. `raises`, when set, is
    raised instead of recording -- mirrors `test_confirmation.py`'s own
    `FakeTransport` exactly, for the same two exceptions `deliver` is
    documented to catch, and for one it must not."""

    def __init__(self, raises: BaseException | None = None) -> None:
        self.raises = raises
        self.calls: list[tuple[SmtpConfig, Delivery]] = []

    def send(self, config: SmtpConfig, delivery: Delivery) -> None:
        if self.raises is not None:
            raise self.raises
        self.calls.append((config, delivery))


_CONFIG_ENV = {
    "CONVENER_SMTP_HOST": "smtp.example.org",
    "CONVENER_SMTP_PORT": "587",
    "CONVENER_SMTP_USER": "convener-certificates@example.org",
    "CONVENER_SMTP_PASSWORD": "shh",
    "CONVENER_SMTP_FROM": "convener-certificates@example.org",
}


# ------------------------------------------------------------------ #
# render_certificate(): a self-contained HTML document, built in memory
# ------------------------------------------------------------------ #


def test_render_certificate_carries_every_printed_field() -> None:
    doc = _document()
    assert "Ada Lovelace" in doc
    assert "On analytical engines" in doc
    assert "2026-09-01" in doc
    assert "1.5 hours" in doc
    assert _IDENTIFIER in doc
    assert ORGANISER in doc


def test_render_certificate_prints_a_whole_number_duration_without_a_decimal() -> None:
    doc = _document(duration_hours=2.0)
    assert "2 hours" in doc
    assert "2.0" not in doc


def test_render_certificate_carries_the_verification_url_as_text_and_as_a_qr() -> None:
    """The original version of this test proved
    the URL appears as text and that *some* `<svg class="qr">` exists,
    with nothing linking the two -- a QR encoding anything at all would
    still pass. `segno.make(url, ...)` -> `segno.make(identifier, ...)`
    survived 330 tests against the original test; this pins the embedded
    SVG to a byte-identical re-encoding of the verification URL, the same
    way it was first proved by hand."""
    doc = _document()
    url = verification_url(_IDENTIFIER, _TOKEN)
    assert url in doc
    assert 'class="qr"' in doc

    expected_svg = segno.make(url, error="m").svg_inline(scale=4)
    assert expected_svg in doc, (
        "the embedded QR is not a byte-identical encoding of the printed "
        "verification URL -- it could be encoding anything at all and "
        "this test would not know"
    )


def test_render_certificate_qr_decodes_to_the_same_url_as_the_printed_text() -> None:
    """Belt and braces on the property above, pinned a different way: pull
    the `<a href>` straight out of the rendered document (what a reader's
    browser would actually follow) and confirm *that* is what the QR
    encodes, rather than relying on both sides independently agreeing to
    call `verification_url` the same way."""
    doc = _document()
    [href] = re.findall(r'<a href="([^"]+)">', doc)
    href = html.unescape(href)
    assert href == verification_url(_IDENTIFIER, _TOKEN)
    assert segno.make(href, error="m").svg_inline(scale=4) in doc


def test_render_certificate_is_a_complete_self_contained_html_document() -> None:
    """No external stylesheet, script or image reference -- the document
    must render identically whether or not the reader is online, which is
    why the QR is drawn inline rather than referenced."""
    doc = _document()
    assert doc.startswith("<!doctype html>")
    assert "<style>" in doc
    assert "<script" not in doc
    assert "http://" not in doc.replace(verification_url(_IDENTIFIER, _TOKEN), "")


def test_render_certificate_escapes_a_hostile_name() -> None:
    """A registered name is free-typed by the participant, never sanitised
    upstream -- see the module docstring's own reasoning for why this must
    be escaped here, not trusted from the caller."""
    doc = _document(name="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;" in doc


def test_render_certificate_escapes_a_hostile_event_title() -> None:
    doc = _document(event_title='"><img src=x>')
    assert '"><img src=x>' not in doc


def test_render_certificate_with_no_event_title_has_a_sensible_title_tag() -> None:
    doc = _document(event_title="")
    assert "<title>Certificate of attendance</title>" in doc


def test_render_certificate_is_deterministic() -> None:
    """Same inputs, same bytes -- the property `cli.py`'s replay depends
    on: a retried delivery must reproduce the identical
    document, not merely one carrying the same facts."""
    assert _document() == _document()


def test_render_certificate_a_different_token_produces_a_different_document() -> None:
    assert _document(token=_TOKEN) != _document(token=_TOKEN + "x")


def test_render_certificate_never_writes_anything_to_disk(tmp_path: Path) -> None:
    """Nothing this function does may place a rendered certificate under
    version control, or under any directory at
    all -- it only ever returns a string."""
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    _document()
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert before == after == []


# ------------------------------------------------------------------ #
# compose(): the e-mail that carries the document
# ------------------------------------------------------------------ #


def test_compose_addresses_the_registrant() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    assert message.to == "ada@example.org"


def test_compose_subject_names_the_event_when_known() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    assert message.subject == "Your certificate of attendance — On analytical engines"


def test_compose_subject_is_still_sensible_with_no_event_title() -> None:
    message = compose(_registration(), "", _IDENTIFIER, "<html/>")
    assert message.subject == "Your certificate of attendance"


def test_compose_carries_the_identifier_in_the_body() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    assert _IDENTIFIER in message.body


def test_compose_carries_the_document_and_a_filename_naming_the_identifier() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    assert message.document == "<html/>"
    assert message.document_filename == f"certificate-{_IDENTIFIER}.html"


def test_compose_is_deterministic_so_a_resend_reproduces_it_exactly() -> None:
    a = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    b = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    assert a == b


# ------------------------------------------------------------------ #
# deliver(): the transport, and D-13's absent-integration shape -- no
# test opens a socket; the real transport is only ever reached through a
# fake. `DeliveryResult` carries only `sent`, never the document -- see
# the module docstring. `confirmation.SendResult` was narrowed to the
# identical shape on review; this module never had
# the wider one in the first place -- see the module docstring's "never
# written to disk" section for why.
# ------------------------------------------------------------------ #


def test_deliver_with_no_transport_configured_reports_unsent() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    assert deliver(message, {}) == DeliveryResult(sent=False)


def test_deliver_sends_through_the_configured_transport() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    transport = FakeTransport()

    result = deliver(message, _CONFIG_ENV, transport=transport)

    assert result == DeliveryResult(sent=True)
    assert len(transport.calls) == 1
    config, sent_message = transport.calls[0]
    assert config.host == "smtp.example.org"
    assert sent_message == message


def test_deliver_reports_unsent_when_the_transport_raises_smtp_exception() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    transport = FakeTransport(raises=smtplib.SMTPRecipientsRefused({}))

    assert deliver(message, _CONFIG_ENV, transport=transport) == DeliveryResult(
        sent=False
    )


def test_deliver_reports_unsent_when_the_transport_raises_os_error() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    transport = FakeTransport(raises=OSError("connection refused"))

    assert deliver(message, _CONFIG_ENV, transport=transport) == DeliveryResult(
        sent=False
    )


def test_deliver_does_not_swallow_an_unrelated_exception() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    transport = FakeTransport(raises=ValueError("not a transport failure"))

    with pytest.raises(ValueError, match="not a transport failure"):
        deliver(message, _CONFIG_ENV, transport=transport)


def test_deliver_never_prints_anything_on_any_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")

    deliver(message, {})
    deliver(message, _CONFIG_ENV, transport=FakeTransport())
    deliver(message, _CONFIG_ENV, transport=FakeTransport(raises=OSError("x")))

    assert capsys.readouterr() == ("", "")


def test_delivery_result_has_no_document_or_body_field() -> None:
    """The design choice the module docstring argues for at length: a
    caller cannot write the rendered certificate to a file through this
    type, because the type has nowhere to carry it -- see
    `DeliveryResult`'s own docstring."""
    fields = DeliveryResult(sent=False).__dataclass_fields__
    assert set(fields) == {"sent"}


# ------------------------------------------------------------------ #
# The real transport's own branching (implicit TLS vs STARTTLS) and the
# attachment it builds -- exercised with smtplib's own classes replaced,
# still no socket opened. Mirrors test_confirmation.py's own
# _FakeSmtpClient.
# ------------------------------------------------------------------ #


class _FakeSmtpClient:
    instances: ClassVar[list[_FakeSmtpClient]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_called = False
        self.login_calls: list[tuple[str, str]] = []
        self.sent: list[Any] = []
        _FakeSmtpClient.instances.append(self)

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, user: str, password: str) -> None:
        self.login_calls.append((user, password))

    def send_message(self, message: Any) -> None:
        self.sent.append(message)

    def __enter__(self) -> _FakeSmtpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_smtp_delivery_transport_uses_starttls_on_an_ordinary_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from convener_ops.delivery import _SmtpDeliveryTransport

    _FakeSmtpClient.instances = []
    monkeypatch.setattr("convener_ops.delivery.smtplib.SMTP", _FakeSmtpClient)
    config = SmtpConfig(
        host="smtp.example.org", port=587, user="u", password="p", sender="from@x"
    )
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")

    _SmtpDeliveryTransport().send(config, message)

    assert len(_FakeSmtpClient.instances) == 1
    client = _FakeSmtpClient.instances[0]
    assert client.port == 587
    assert client.starttls_called is True
    assert client.login_calls == [("u", "p")]
    assert len(client.sent) == 1
    sent_email = client.sent[0]
    assert sent_email["Reply-To"] == CONTACT_EMAIL
    # A real Date header -- the spam folder is a named risk
    # here, and a missing Date is a real
    # scoring signal. Present, and not empty -- not asserting an exact
    # value, since the real transport uses the actual send time.
    assert sent_email["Date"] is not None
    assert str(sent_email["Date"]).strip() != ""
    # The certificate document is attached, not inlined into the body.
    attachments = list(sent_email.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == f"certificate-{_IDENTIFIER}.html"
    assert attachments[0].get_content() == "<html/>"


def test_smtp_delivery_transport_uses_implicit_tls_on_port_465(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from convener_ops.delivery import _SmtpDeliveryTransport

    _FakeSmtpClient.instances = []
    monkeypatch.setattr("convener_ops.delivery.smtplib.SMTP_SSL", _FakeSmtpClient)
    config = SmtpConfig(
        host="smtp.example.org", port=465, user="u", password="p", sender="from@x"
    )
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")

    _SmtpDeliveryTransport().send(config, message)

    assert len(_FakeSmtpClient.instances) == 1
    client = _FakeSmtpClient.instances[0]
    assert client.port == 465
    assert client.starttls_called is False
    assert client.login_calls == [("u", "p")]


# ------------------------------------------------------------------ #
# D-14: the documentation copy a board member reads must not quietly say
# something different from what this module actually sends.
# ------------------------------------------------------------------ #

_DOCS_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "toolkit"
    / "emails"
    / "certificate-delivered.md"
)


def _normalised_docs_template() -> str:
    text = _DOCS_TEMPLATE.read_text(encoding="utf-8")
    return " ".join(text.split())


def test_the_subject_matches_the_documentation_copy() -> None:
    message = compose(
        _registration(), "[the event's title, when known]", "x", "<html/>"
    )
    assert message.subject in _normalised_docs_template()


def test_the_document_instruction_matches_the_documentation_copy() -> None:
    """Only the subject used to be pinned --
    the body had already drifted typographically from the docs copy (an
    ASCII "--" where both the docs page and `compose`'s own subject line
    already used an em dash). `DOCUMENT_INSTRUCTION` is exported so this
    test, and `compose` itself, can never quietly diverge from
    `docs/toolkit/emails/certificate-delivered.md` again -- the same
    "export the sentence" discipline `test_confirmation.py` already
    applies to `MATCHING_INSTRUCTION` and `UPDATE_WARNING`."""
    assert DOCUMENT_INSTRUCTION in _normalised_docs_template()


def test_compose_body_carries_the_document_instruction_verbatim() -> None:
    message = compose(_registration(), "On analytical engines", _IDENTIFIER, "<html/>")
    assert DOCUMENT_INSTRUCTION in message.body
