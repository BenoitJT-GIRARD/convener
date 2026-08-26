from __future__ import annotations

import json
import re
import smtplib
from pathlib import Path
from typing import Any, ClassVar

import pytest

from convener_ops import published, registration
from convener_ops.confirmation import (
    CONTACT_EMAIL,
    FIELD_LABELS,
    MATCHING_INSTRUCTION,
    SMTP_ENV_VARS,
    UPDATE_WARNING,
    Confirmation,
    EventDetails,
    EventNotFoundError,
    SendResult,
    SmtpConfig,
    _join_labels,
    changed_fields,
    compose,
    deliver,
    event_details,
    smtp_config_from_env,
)
from convener_ops.platform import ManualPlatform, Room
from convener_ops.registration import Registration

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


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


def _speaker(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "edition_code": "MRG-901",
        "zoom_link": "https://meet.example.org/permanent-room",
        "youtube_url": "",
        "title": "On analytical engines",
        "date": "2026-09-01",
    }
    base.update(overrides)
    return base


_ROOM = Room(
    join_url="https://meet.example.org/permanent-room",
    instructions="Wait to be let in.",
)
_EVENT = EventDetails(title="On analytical engines", date="2026-09-01", room=_ROOM)
_BLANK_EVENT = EventDetails(title="", date="", room=Room(join_url="", instructions=""))


class FakeTransport:
    """Records every call; never touches a socket. `raises`, when set, is
    raised instead of recording -- for the two exceptions `deliver` is
    documented to catch, and for one it must not."""

    def __init__(self, raises: BaseException | None = None) -> None:
        self.raises = raises
        self.calls: list[tuple[SmtpConfig, Confirmation]] = []

    def send(self, config: SmtpConfig, message: Confirmation) -> None:
        if self.raises is not None:
            raise self.raises
        self.calls.append((config, message))


_CONFIG_ENV = {
    "CONVENER_SMTP_HOST": "smtp.example.org",
    "CONVENER_SMTP_PORT": "587",
    "CONVENER_SMTP_USER": "convener-registration@example.org",
    "CONVENER_SMTP_PASSWORD": "shh",
    "CONVENER_SMTP_FROM": "convener-registration@example.org",
}


# ------------------------------------------------------------------ #
# changed_fields(): what an update names, never what it quotes
# ------------------------------------------------------------------ #


def test_changed_fields_is_empty_when_nothing_differs() -> None:
    assert changed_fields(_registration(), _registration()) == ()


def test_changed_fields_names_the_one_field_that_differs() -> None:
    old = _registration(institution="Somewhere Else")
    new = _registration()
    assert changed_fields(old, new) == ("institution",)


def test_changed_fields_names_several_fields_in_a_fixed_order() -> None:
    old = _registration(first_name="Augusta", membership_opt_in=False)
    new = _registration()
    # FIELD_LABELS's own order: first_name before membership_opt_in.
    assert changed_fields(old, new) == ("first name", "announce-list subscription")


def test_changed_fields_never_names_a_value_it_saw_change() -> None:
    """The property directly: a diff that leaks the old or the
    new institution name would defeat the point of naming fields instead of
    quoting them."""
    old = _registration(institution="Old Institute")
    new = _registration(institution="New Institute")
    for label in changed_fields(old, new):
        assert "Institute" not in label


def test_changed_fields_covers_every_registration_field() -> None:
    """`FIELD_LABELS` must name all five `Registration` fields, or a real
    change to one would go unreported -- pins the set directly rather than
    trusting the dict literal never falls behind the dataclass."""
    assert set(FIELD_LABELS) == {
        "first_name",
        "surname",
        "email",
        "institution",
        "membership_opt_in",
    }


def test_join_labels_forms() -> None:
    assert _join_labels([]) == ""
    assert _join_labels(["a"]) == "a"
    assert _join_labels(["a", "b"]) == "a and b"
    assert _join_labels(["a", "b", "c"]) == "a, b and c"


# ------------------------------------------------------------------ #
# event_details(): the room through Platform, title/date off the record
# ------------------------------------------------------------------ #


def test_event_details_reads_title_date_and_room() -> None:
    platform = ManualPlatform(speakers=[_speaker(edition_code="MRG-901")])

    details = event_details([_speaker(edition_code="MRG-901")], "mrg-901", platform)

    assert details.title == "On analytical engines"
    assert details.date == "2026-09-01"
    assert details.room.join_url == "https://meet.example.org/permanent-room"


def test_event_details_raises_for_an_unknown_event() -> None:
    platform = ManualPlatform(speakers=[])
    with pytest.raises(EventNotFoundError, match="mrg-999"):
        event_details([], "mrg-999", platform)


def test_event_details_blank_title_and_date_read_as_empty_strings() -> None:
    speakers = [_speaker(edition_code="MRG-901", title="", date="")]
    platform = ManualPlatform(speakers=speakers)

    details = event_details(speakers, "mrg-901", platform)

    assert details.title == ""
    assert details.date == ""


# ------------------------------------------------------------------ #
# compose(): the four required contents, and the update notice
# ------------------------------------------------------------------ #


def test_compose_addresses_the_registrant() -> None:
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    assert message.to == "ada@example.org"


def test_compose_subject_names_the_event_when_known() -> None:
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    assert "On analytical engines" in message.subject


def test_compose_subject_is_still_sensible_with_no_event_title() -> None:
    message = compose(_registration(), _BLANK_EVENT, "WXYZ-2345")
    assert message.subject == "Your registration is confirmed"


def test_compose_carries_the_room_link() -> None:
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    assert _ROOM.join_url in message.body


def test_compose_carries_the_room_instructions_when_present() -> None:
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    assert "Wait to be let in." in message.body


def test_compose_says_something_sensible_with_no_room_link_yet() -> None:
    message = compose(_registration(), _BLANK_EVENT, "WXYZ-2345")
    assert "has not been set yet" in message.body


def test_compose_carries_the_matching_code_and_its_exact_instruction() -> None:
    """The load-bearing content (spec S:3, S:5): both the instruction
    sentence and the live code itself must be in the message, verbatim --
    this is the test the task's own mutation exercise is built to kill by
    dropping the code from `compose`."""
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    assert MATCHING_INSTRUCTION in message.body
    assert "WXYZ-2345" in message.body
    assert f"{MATCHING_INSTRUCTION}: WXYZ-2345" in message.body


def test_compose_gives_a_worked_example_built_from_the_registrants_name() -> None:
    """The instruction alone leaves open
    whether the hyphen is part of the code and whether the participant's
    own name stays in the field. The worked example answers both."""
    message = compose(
        Registration("Ada", "Lovelace", "ada@example.org", "", False),
        _EVENT,
        "WXYZ-2345",
    )
    assert "So your display name should read exactly: Ada Lovelace WXYZ-2345" in (
        message.body
    )


def test_compose_names_the_fallback_cascade_with_no_code() -> None:
    """Spec S:5's documented fallback when `CONVENER_MATCHING_SALT` is unset
    (an ordinary D-13 absence, `registration.matching_code`'s own
    docstring) -- the message must still say *something* about how
    attendance will be matched, not simply omit the sentence."""
    message = compose(_registration(), _EVENT, None)
    assert MATCHING_INSTRUCTION not in message.body
    assert "match your attendance" in message.body


def test_compose_carries_the_data_protection_notice_and_the_rights_notice() -> None:
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    assert "Data protection." in message.body
    assert "90 days" in message.body
    assert "reply to this message" in message.body
    assert CONTACT_EMAIL in message.body


def test_compose_says_nothing_about_an_update_when_nothing_changed() -> None:
    message = compose(_registration(), _EVENT, "WXYZ-2345", changed=())
    assert "This confirms an update" not in message.body
    assert UPDATE_WARNING not in message.body


def test_compose_names_what_changed_and_warns_when_something_did() -> None:
    """The only detection channel for a silent overwrite has to name
    the change and tell the reader what to do if it was not them.

    Asserts the whole sentence, not a bare substring:
    "institution" also appears in `_DATA_PROTECTION`, which
    every message ever composed carries, so a mutant naming the *wrong*
    changed field would still satisfy a check for that word alone."""
    message = compose(_registration(), _EVENT, "WXYZ-2345", changed=("institution",))
    assert (
        "This confirms an update to an earlier registration for this "
        "event: we changed the institution."
    ) in message.body
    assert UPDATE_WARNING in message.body


def test_compose_joins_several_changed_fields_in_one_sentence() -> None:
    message = compose(
        _registration(),
        _EVENT,
        "WXYZ-2345",
        changed=("first name", "institution"),
    )
    assert "first name and institution" in message.body


def test_compose_never_quotes_the_institution_value_in_an_update_notice() -> None:
    """The property `changed_fields` names but does not quote has to
    survive into the composed message too, not only into the field list."""
    message = compose(
        _registration(institution="Analytical Engines Institute"),
        _EVENT,
        "WXYZ-2345",
        changed=("institution",),
    )
    assert "Analytical Engines Institute" not in message.body


def test_compose_is_deterministic_so_a_resend_reproduces_it_exactly() -> None:
    """The property a manual resend depends on directly: composing twice
    from the same inputs, including the same code, must give byte-identical
    output -- this is the test the task's own mutation exercise is built to
    kill by making a resend derive a different code."""
    first = compose(_registration(), _EVENT, "WXYZ-2345")
    second = compose(_registration(), _EVENT, "WXYZ-2345")
    assert first == second


# ------------------------------------------------------------------ #
# smtp_config_from_env(): D-13, all five secrets or none
# ------------------------------------------------------------------ #


def test_smtp_env_vars_names_exactly_the_five_keys_of_config_env() -> None:
    """`SMTP_ENV_VARS` exists so a second module
    (`delivery.py`) and a test deriving what a function reads from its
    own source (`test_workflows.py`'s `_env_vars_read`) can name "every
    email_transport secret" without retyping five strings a second time
    -- pinned here against the same env mapping every `smtp_config_from_env`
    test in this file already uses, so the exported set and the actual
    keys `smtp_config_from_env` reads can never quietly drift apart."""
    assert set(_CONFIG_ENV) == SMTP_ENV_VARS


def test_smtp_config_from_env_with_all_five_secrets() -> None:
    config = smtp_config_from_env(_CONFIG_ENV)
    assert config == SmtpConfig(
        host="smtp.example.org",
        port=587,
        user="convener-registration@example.org",
        password="shh",
        sender="convener-registration@example.org",
    )


def test_smtp_config_from_env_with_nothing_set_is_none() -> None:
    assert smtp_config_from_env({}) is None


@pytest.mark.parametrize(
    "missing",
    [
        "CONVENER_SMTP_HOST",
        "CONVENER_SMTP_PORT",
        "CONVENER_SMTP_USER",
        "CONVENER_SMTP_PASSWORD",
        "CONVENER_SMTP_FROM",
    ],
)
def test_smtp_config_from_env_is_none_when_any_one_secret_is_missing(
    missing: str,
) -> None:
    env = dict(_CONFIG_ENV)
    del env[missing]
    assert smtp_config_from_env(env) is None


def test_smtp_config_from_env_treats_a_blank_secret_as_absent() -> None:
    env = dict(_CONFIG_ENV)
    env["CONVENER_SMTP_HOST"] = "   "
    assert smtp_config_from_env(env) is None


@pytest.mark.parametrize("port", ["not-a-number", "0", "-1", "65536", "587.0"])
def test_smtp_config_from_env_rejects_an_unusable_port(port: str) -> None:
    env = dict(_CONFIG_ENV)
    env["CONVENER_SMTP_PORT"] = port
    assert smtp_config_from_env(env) is None


def test_smtp_config_from_env_accepts_the_implicit_tls_port() -> None:
    env = dict(_CONFIG_ENV)
    env["CONVENER_SMTP_PORT"] = "465"
    config = smtp_config_from_env(env)
    assert config is not None
    assert config.port == 465


# ------------------------------------------------------------------ #
# deliver(): the transport, and D-13's log fallback -- no test opens a
# socket; the real transport is only ever reached through a fake.
# ------------------------------------------------------------------ #


def test_deliver_with_no_transport_returns_unsent() -> None:
    """`SendResult` carries only `sent` --
    no `unsent_body`, the same narrow shape `delivery.DeliveryResult`
    already used. Nothing here holds the composed message on the unsent
    path any more, so there is nothing left to inspect but the boolean."""
    message = compose(_registration(), _EVENT, "WXYZ-2345")

    result = deliver(message, {})

    assert result == SendResult(sent=False)


def test_deliver_sends_through_the_configured_transport() -> None:
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    transport = FakeTransport()

    result = deliver(message, _CONFIG_ENV, transport=transport)

    assert result == SendResult(sent=True)
    assert len(transport.calls) == 1
    config, sent_message = transport.calls[0]
    assert config.host == "smtp.example.org"
    assert sent_message == message


def test_deliver_falls_back_to_unsent_when_the_transport_raises_smtp_exception() -> (
    None
):
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    transport = FakeTransport(raises=smtplib.SMTPRecipientsRefused({}))

    result = deliver(message, _CONFIG_ENV, transport=transport)

    assert result == SendResult(sent=False)


def test_deliver_falls_back_to_unsent_when_the_transport_raises_os_error() -> None:
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    transport = FakeTransport(raises=OSError("connection refused"))

    result = deliver(message, _CONFIG_ENV, transport=transport)

    assert result == SendResult(sent=False)


def test_deliver_does_not_swallow_an_unrelated_exception() -> None:
    """Only a real transport failure is caught -- a programming mistake in
    a fake (or a future real transport) must still surface as itself."""
    message = compose(_registration(), _EVENT, "WXYZ-2345")
    transport = FakeTransport(raises=ValueError("not a transport failure"))

    with pytest.raises(ValueError, match="not a transport failure"):
        deliver(message, _CONFIG_ENV, transport=transport)


def test_deliver_never_prints_anything_on_any_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The property the module docstring's whole transport section exists
    for: this module must never be the thing that puts an address or a
    code into stdout, on any of the three paths -- unconfigured, sent, or a
    failed send."""
    message = compose(_registration(), _EVENT, "WXYZ-2345")

    deliver(message, {})
    deliver(message, _CONFIG_ENV, transport=FakeTransport())
    deliver(message, _CONFIG_ENV, transport=FakeTransport(raises=OSError("x")))

    assert capsys.readouterr() == ("", "")


# ------------------------------------------------------------------ #
# The real transport's own branching (implicit TLS vs STARTTLS), exercised
# with smtplib's own classes replaced -- still no socket opened.
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


def test_smtp_transport_uses_starttls_on_an_ordinary_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from convener_ops.confirmation import _SmtpTransport

    _FakeSmtpClient.instances = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP", _FakeSmtpClient)
    config = SmtpConfig(
        host="smtp.example.org", port=587, user="u", password="p", sender="from@x"
    )
    message = compose(_registration(), _EVENT, "WXYZ-2345")

    _SmtpTransport().send(config, message)

    assert len(_FakeSmtpClient.instances) == 1
    client = _FakeSmtpClient.instances[0]
    assert client.port == 587
    assert client.starttls_called is True
    assert client.login_calls == [("u", "p")]
    assert len(client.sent) == 1
    # "reply to this message" must be true
    # regardless of what `config.sender` (CONVENER_SMTP_FROM) happens to be.
    assert client.sent[0]["Reply-To"] == CONTACT_EMAIL
    # The same `Date` header
    # `delivery.py::_SmtpDeliveryTransport.send` already carries
    # -- the spam folder is a real risk here, and a missing `Date` is a
    # real scoring signal. Present, and
    # not empty -- not asserting an exact value, since the real transport
    # uses the actual send time.
    assert client.sent[0]["Date"] is not None
    assert str(client.sent[0]["Date"]).strip() != ""


def test_smtp_transport_uses_implicit_tls_on_port_465(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from convener_ops.confirmation import _SmtpTransport

    _FakeSmtpClient.instances = []
    monkeypatch.setattr("convener_ops.confirmation.smtplib.SMTP_SSL", _FakeSmtpClient)
    config = SmtpConfig(
        host="smtp.example.org", port=465, user="u", password="p", sender="from@x"
    )
    message = compose(_registration(), _EVENT, "WXYZ-2345")

    _SmtpTransport().send(config, message)

    assert len(_FakeSmtpClient.instances) == 1
    client = _FakeSmtpClient.instances[0]
    assert client.port == 465
    # Implicit TLS: never calls starttls, since the connection is already
    # encrypted from the first byte.
    assert client.starttls_called is False
    assert client.login_calls == [("u", "p")]


# ------------------------------------------------------------------ #
# Confirmation.__eq__ / SendResult -- plain dataclasses, pinned so a field
# added later without updating a caller is at least visible in a diff.
# ------------------------------------------------------------------ #


def test_confirmation_is_a_plain_comparable_value() -> None:
    a = Confirmation(to="x@example.org", subject="s", body="b")
    b = Confirmation(to="x@example.org", subject="s", body="b")
    assert a == b


# ------------------------------------------------------------------ #
# D-14: the two load-bearing sentences (the matching-code instruction and
# the update warning) are pinned against the documentation copy a board
# member reads, so the two cannot quietly say different things -- the same
# discipline `tools/tests/fixtures/governance-cases.json` applies across
# Python and TypeScript, applied here across code and documentation
# instead.
# ------------------------------------------------------------------ #

_DOCS_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "toolkit"
    / "emails"
    / "registration-confirmed.md"
)


def _normalised_docs_template() -> str:
    """The docs page's prose with line wrapping collapsed -- a soft-wrapped
    sentence in the markdown source is one sentence, not two, and a plain
    substring check must see it that way too."""
    text = _DOCS_TEMPLATE.read_text(encoding="utf-8")
    return " ".join(text.split())


def test_the_matching_instruction_matches_the_documentation_copy() -> None:
    assert MATCHING_INSTRUCTION in _normalised_docs_template()


def test_the_update_warning_matches_the_documentation_copy() -> None:
    assert UPDATE_WARNING in _normalised_docs_template()


# ------------------------------------------------------------------ #
# Two more unbound copies a review found: the contact address and
# the retention window, both restated in `SignupForm.tsx` (the page a
# participant reads *before* registering) rather than read from one place.
# Pinned the same D-14 way, across a third file this time.
# ------------------------------------------------------------------ #

#: The form itself moved from `app/src/signup/SignupForm.tsx`
#: (the operators' application) to `app/src/islands/signup/SignupForm.tsx`
#: (the island mounted on the public event page) -- see git history for
#: the file this replaced. `encrypt.ts`, which these tests never read,
#: stayed exactly where it was: shared, not moved, not forked.
_SIGNUP_FORM = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "src"
    / "islands"
    / "signup"
    / "SignupForm.tsx"
)


def test_the_contact_email_matches_the_signup_pages_own_notice() -> None:
    """`SignupForm.tsx` names a concrete address for "access, correct or
    erase your data" before anyone registers; the confirmation e-mail's
    own rights notice names the same one.

    Both sides used to hold the literal and this test bound
    them to each other -- which could say the two copies still agreed,
    never that there was one. Both now read `config/instance.json`, so
    what is asserted here is that neither has gone back to writing it out:
    the registration form reads the identity, and no e-mail address
    appears in its source at all.
    """
    source = _SIGNUP_FORM.read_text(encoding="utf-8")
    assert "instanceIdentity().contact" in source, (
        "SignupForm.tsx no longer reads the contact address from the "
        "instance's own declaration"
    )
    literals = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", source)
    assert literals == [], (
        f"SignupForm.tsx writes an e-mail address out again: {literals}"
    )
    assert published.load_identity().contact == CONTACT_EMAIL


def test_the_retention_window_is_the_same_number_everywhere() -> None:
    """The paragraph with legal weight: "90 days" is
    restated in `confirmation.py`, the docs copy, and `eventkeys.py`'s own
    citation of the same number (`RSA_KEY_BITS`'s docstring: "this
    project's retention window, 90 days"). Nothing
    here reads a shared constant -- none exists -- so this test is what
    keeps the prose
    copies from drifting apart until one does.

    There is a fourth restatement, `site/src/event.njk`'s own
    notice -- at first quoted from `SignupForm.tsx`'s own copy as a
    stopgap (that template's own comment said so), before the registration
    island was mounted. Mounting it removed the in-component
    copy: the notice is not interactive, so D-18 keeps it as
    plain static HTML on the event page and the island renders none of it
    itself -- rendering it from both places would put two copies of the
    same legal notice on one page. `event.njk` is therefore the *only*
    place this window is restated in either front end; `SignupForm.tsx` no
    longer carries "90 days" at all, so it is dropped from this binding
    rather than kept and left permanently unable to match.
    """
    from convener_ops.confirmation import _DATA_PROTECTION

    eventkeys_source = (
        Path(__file__).resolve().parents[2] / "tools" / "convener_ops" / "eventkeys.py"
    ).read_text(encoding="utf-8")
    event_page_source = (
        Path(__file__).resolve().parents[2] / "site" / "src" / "event.njk"
    ).read_text(encoding="utf-8")

    def _days(text: str) -> str:
        match = re.search(r"(\d+) days", text)
        assert match is not None, f"no '<N> days' found in: {text[:200]!r}"
        return match.group(1)

    code = _days(_DATA_PROTECTION)
    docs = _days(_normalised_docs_template())
    eventkeys = _days(eventkeys_source)
    event_page = _days(event_page_source)

    assert code == docs == eventkeys == event_page == "90"

    # Belt and braces for the removal itself: a regression that pasted the
    # notice back into the island would put two copies on one built page,
    # exactly the defect this restructuring exists to prevent.
    signup_source = _SIGNUP_FORM.read_text(encoding="utf-8")
    assert "90 days" not in signup_source, (
        "SignupForm.tsx restates the retention window again -- that text "
        "now lives only on site/src/event.njk; rendering it from the "
        "island too would show it twice on the built event page"
    )


def test_signup_form_max_field_length_matches_the_python_constant() -> None:
    """`registration._MAX_FIELD_LENGTH`
    mutated from 200 to 5000 survived every Python test, and `SignupForm.tsx`
    had no `maxLength` counterpart at all -- a 201-character field was
    accepted by the browser and the relay, shown as sent, and only then
    dropped by `to_registration` as "could not be read". Bound here the
    same D-14 way `test_the_contact_email_matches_the_signup_pages_own_
    notice` already binds `CONTACT_EMAIL`, across the identical language
    boundary: a hand-typed `200` on each side that could drift apart
    exactly the way `SurveyForm.tsx`'s own `MAX_FEEDBACK_LENGTH` still
    can, unbound, from `survey._MAX_FEEDBACK_LENGTH`."""
    from convener_ops.registration import _MAX_FIELD_LENGTH

    source = _SIGNUP_FORM.read_text(encoding="utf-8")
    match = re.search(r"MAX_FIELD_LENGTH = (\d+)", source)
    assert match is not None, "SignupForm.tsx no longer declares MAX_FIELD_LENGTH"
    assert int(match.group(1)) == _MAX_FIELD_LENGTH


# ------------------------------------------------------------------ #
# This page's own pinned claim -- "the room
# is a permanent account, its link is not otherwise published" -- is only
# checkable if something actually checks the "otherwise" against every
# public template, not merely against this one page's own prose. Before
# the fix, both `forum-post-announce.md` and `linkedin-post.md` published
# `{{ speaker.zoom_link }}` under the word "Registration", contradicting
# the claim below. Pinned here, beside the claim itself, so the
# contradiction cannot come back through either template without a test
# failing on this exact page.
# ------------------------------------------------------------------ #

_ROOM_LINK_CLAIM = "The room link only ever reaches a participant here"
_TOOLKIT_DIR = Path(__file__).resolve().parents[2] / "docs" / "toolkit"
_PUBLIC_ANNOUNCEMENT_TEMPLATES = (
    _TOOLKIT_DIR / "forum-post-announce.md",
    _TOOLKIT_DIR / "linkedin-post.md",
    # The mailing-list message: the same "announces something
    # upcoming, points at the event page" shape as the two above, so it
    # carries the same signup-link claim and is checked against the same
    # room-link literal. `recording-announce.md`, the fourth text,
    # is not here -- it announces something already delivered and has no
    # registration to send anyone to, so it is checked on its own below.
    _TOOLKIT_DIR / "mailing-list-announce.md",
)

#: The recording announcement, checked for the room-link leak this
#: whole section exists to catch, but not folded into
#: `_PUBLIC_ANNOUNCEMENT_TEMPLATES`: that tuple's second test requires
#: every member to publish `{{ speaker.signup_link }}`, and this page
#: never registers anyone -- the talk it announces has already happened.
_RECORDING_ANNOUNCEMENT_TEMPLATE = _TOOLKIT_DIR / "recording-announce.md"


def test_the_room_link_claim_is_still_on_the_page() -> None:
    """The claim this whole section pins the templates against -- if this
    sentence is ever reworded away, the tests below are pinning nothing."""
    assert _ROOM_LINK_CLAIM in _normalised_docs_template()


def test_no_public_announcement_template_publishes_the_room_link() -> None:
    for path in _PUBLIC_ANNOUNCEMENT_TEMPLATES:
        text = path.read_text(encoding="utf-8")
        assert "zoom_link" not in text, (
            f"{path.name} publishes {{{{ speaker.zoom_link }}}} -- the room "
            "link -- contradicting registration-confirmed.md's own pinned "
            "claim that it 'is not otherwise published'"
        )


def test_the_recording_announcement_never_publishes_the_room_link_either() -> None:
    text = _RECORDING_ANNOUNCEMENT_TEMPLATE.read_text(encoding="utf-8")
    assert "zoom_link" not in text, (
        f"{_RECORDING_ANNOUNCEMENT_TEMPLATE.name} publishes "
        "{{ speaker.zoom_link }} -- the room link -- contradicting "
        "registration-confirmed.md's own pinned claim that it 'is not "
        "otherwise published'"
    )


def test_every_public_announcement_template_publishes_the_signup_link_instead() -> None:
    """A correction: `registration.SIGNUP_BASE` used to be published
    as a literal, with the event id left for a volunteer to type in
    by hand -- exactly the "depends on somebody remembering, and getting it
    right" shape this project refuses everywhere else. Both templates now
    carry `{{ speaker.signup_link }}`, a value `render.ts` computes from the
    Speaker record's own `edition_code`, so nothing about the
    address is ever hand-filled."""
    for path in _PUBLIC_ANNOUNCEMENT_TEMPLATES:
        text = path.read_text(encoding="utf-8")
        assert "{{ speaker.signup_link }}" in text, (
            f"{path.name} does not publish {{{{ speaker.signup_link }}}} -- "
            "nothing on this page tells a participant where to register"
        )
        assert "event id" not in text.lower(), (
            f"{path.name} still asks a volunteer to fill in the event id by "
            "hand -- the link is computed now, not typed"
        )


# ------------------------------------------------------------------ #
# The mapping (event_id is edition_code,
# lower-cased -- platform.py::find_speaker) does exist, contrary to an
# earlier claim. `registration.signup_url` and `render.ts`'s own
# `signup_link` derivation must compute the identical address for the
# identical Speaker record; bound here by the shared, worked fixture
# (D-14) rather than by two constants trusted to agree. `edition_code` is
# deliberately mixed-case in the fixture -- lower-casing IS the rule.
# ------------------------------------------------------------------ #

_SIGNUP_LINK_FIXTURE = Path(__file__).parent / "fixtures" / "signup-link.json"


def _signup_link_cases() -> dict[str, Any]:
    cases = json.loads(_SIGNUP_LINK_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(cases, dict), (
        f"{_SIGNUP_LINK_FIXTURE.name} is a {type(cases).__name__}, not the "
        "JSON object of worked cases this module and `render.ts` both read"
    )
    return cases


def test_signup_base_matches_the_shared_fixture() -> None:
    """The fixture states the *path* the product
    publishes an event page under; the root both sides prepend is
    `config/instance.json`'s, read here through `published.load()` and on
    the TypeScript side through `import.meta.env.VITE_PUBLISHED_URL`. The
    fixture used to hold the whole address, which made it a copy of that
    root rather than a binding between two implementations."""
    cases = _signup_link_cases()
    assert published.load().under(cases["signup_path"]) == registration.SIGNUP_BASE


@pytest.mark.parametrize(
    "case", _signup_link_cases()["cases"], ids=lambda c: c["edition_code"]
)
def test_signup_url_matches_the_shared_fixtures_worked_examples(
    case: dict[str, str],
) -> None:
    # The fixture's own event_id pins the rule: lower-casing edition_code
    # IS the rule, not merely an assumption the case was built under.
    assert case["event_id"] == case["edition_code"].lower()
    assert registration.signup_url(case["event_id"]) == published.load().under(
        case["signup_url_path"]
    )
