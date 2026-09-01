from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from convener_ops.declaration import published
from convener_ops.journey.confirmation import Confirmation
from convener_ops.journey.registration import Registration
from convener_ops.journey.survey_invite import (
    INVITATIONS_FILE_VERSION,
    NOTICE,
    SURVEY_BASE,
    compose,
    invitations_path,
    registry_from_data,
    registry_to_data,
    survey_url,
)


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


def test_survey_url_names_the_event_on_the_survey_pages_own_address() -> None:
    # A real, bare path -- SURVEY_BASE's own comment
    # explains why this no longer carries a `#` fragment (there was never
    # a Referer-leak property tying it to one in the first place).
    url = survey_url("mrg-042")
    assert url == published.load().under("survey/mrg-042/")


def test_survey_url_quotes_a_hostile_event_id() -> None:
    # This module never receives an unvalidated event id in practice
    # (cli/ always checks `eventkeys.secret_name` first), but survey_url
    # itself takes a bare string -- proving it quotes rather than trusting
    # its argument is cheap insurance against a future caller that skips
    # that check.
    url = survey_url("../escape")
    assert "../" not in url
    assert "%2F" in url or "%2E" in url or "escape" in url


# ------------------------------------------------------------------ #
# `compose`: deterministic, no per-person token, no personal data in the
# subject.
# ------------------------------------------------------------------ #


def test_compose_returns_a_plain_confirmation() -> None:
    message = compose(_registration(), "On analytical engines", "mrg-042")
    assert isinstance(message, Confirmation)
    assert message.to == "ada@example.org"


def test_compose_subject_names_the_event_and_nothing_personal() -> None:
    message = compose(_registration(), "On analytical engines", "mrg-042")
    assert message.subject == "Tell us what you thought — On analytical engines"
    assert "Ada" not in message.subject
    assert "Lovelace" not in message.subject
    assert "ada@example.org" not in message.subject


def test_compose_subject_with_no_title_names_only_the_generic_line() -> None:
    message = compose(_registration(), "", "mrg-042")
    assert message.subject == "Tell us what you thought"


def test_compose_body_greets_the_recipient_by_first_name() -> None:
    message = compose(_registration(first_name="Grace"), "", "mrg-042")
    assert message.body.startswith("Dear Grace,")


def test_compose_body_carries_the_survey_link_and_the_notice() -> None:
    message = compose(_registration(), "On analytical engines", "mrg-042")
    assert survey_url("mrg-042") in message.body
    assert NOTICE in message.body


def test_compose_body_never_carries_the_surname_or_the_institution() -> None:
    """Nothing this module composes should carry more personal
    data than the greeting needs -- a surname or an institution in the
    body would be surplus, never checked or used by anything downstream."""
    message = compose(_registration(), "On analytical engines", "mrg-042")
    assert "Lovelace" not in message.body
    assert "Analytical Engines Institute" not in message.body


def test_compose_is_deterministic() -> None:
    first = compose(_registration(), "On analytical engines", "mrg-042")
    second = compose(_registration(), "On analytical engines", "mrg-042")
    assert first == second


def test_compose_the_same_event_gives_every_recipient_the_identical_link() -> None:
    """No per-person token -- the survey link inside the body is
    a pure function of `event_id` alone, never of the registration."""
    ada = compose(_registration(), "On analytical engines", "mrg-042")
    grace = compose(
        _registration(first_name="Grace", surname="Hopper", email="grace@example.org"),
        "On analytical engines",
        "mrg-042",
    )
    ada_link = re.search(r"https://\S+", ada.body)
    grace_link = re.search(r"https://\S+", grace.body)
    assert ada_link is not None
    assert grace_link is not None
    assert ada_link.group(0) == grace_link.group(0)


# ------------------------------------------------------------------ #
# The invitation registry: `instance/data/survey-invitations.yml`. Mirrors
# `eventkeys.registry_from_data`/`registry_to_data`'s own test coverage
# shape closely, on purpose -- same file family, same closed-shape
# discipline.
# ------------------------------------------------------------------ #


def test_invitations_path_is_relative_to_root(tmp_path: Path) -> None:
    assert (
        invitations_path(tmp_path)
        == tmp_path / "instance" / "data" / "survey-invitations.yml"
    )


def test_registry_from_data_with_none_starts_empty() -> None:
    assert registry_from_data(None) == {}


def test_registry_round_trips() -> None:
    registry = {"mrg-042": date(2026, 8, 20), "mrg-043": date(2026, 9, 1)}
    data = registry_to_data(registry)
    assert data["v"] == INVITATIONS_FILE_VERSION
    assert registry_from_data(data) == registry


def test_registry_to_data_is_sorted_by_event_id() -> None:
    registry = {"mrg-999": date(2026, 1, 1), "mrg-001": date(2026, 1, 1)}
    data = registry_to_data(registry)
    assert [row["event_id"] for row in data["invitations"]] == ["mrg-001", "mrg-999"]


@pytest.mark.parametrize(
    "data",
    [
        {"v": 999, "invitations": []},
        {"v": 1, "invitations": "not-a-list"},
        {"v": 1, "invitations": [{"event_id": "mrg-042"}]},
        {"v": 1, "invitations": [{"event_id": "mrg-042", "invited_on": 42}]},
        {"v": 1, "invitations": [{"event_id": 42, "invited_on": "2026-08-20"}]},
        {"v": 1, "invitations": [{"event_id": "mrg-042", "invited_on": "not-a-date"}]},
        {
            "v": 1,
            "invitations": [
                {"event_id": "mrg-042", "invited_on": "2026-08-20"},
                {"event_id": "mrg-042", "invited_on": "2026-08-21"},
            ],
        },
        "not-a-dict",
    ],
)
def test_registry_from_data_rejects_malformed_input(data: Any) -> None:
    with pytest.raises(ValueError):
        registry_from_data(data)


# ------------------------------------------------------------------ #
# `SURVEY_BASE` used to be bound to `App.tsx`'s own route
# (D-14, "read from both sides") -- that route is gone (see git history).
# `SURVEY_BASE` is now the survey page's own address, one page per event
# (D-19) exactly like `registration.SIGNUP_BASE` -- the shape check below
# mirrors `test_registration.py::test_signup_base_is_the_event_pages_own_
# address`, and `tools/tests/repository/test_workflows.py::
# test_survey_base_matches_the_survey_page_permalink` binds the value
# itself against `site/src/survey.njk`'s own permalink, the D-14
# "read from both sides" discipline moved to that module instead, the
# identical move `test_registration_signup_base_matches_the_event_page_
# permalink` already made for registration.
# ------------------------------------------------------------------ #


def test_survey_base_is_the_survey_pages_own_address() -> None:
    assert SURVEY_BASE.endswith("/survey/")
    assert SURVEY_BASE.startswith(published.load().url)
    assert "#" not in SURVEY_BASE
    assert "/app/" not in SURVEY_BASE


# ------------------------------------------------------------------ #
# `survey_invite.py` and
# `docs/handbook/toolkit/emails/survey-invitation.md:12-14` both claimed this test
# already existed. It did not -- rewording `NOTICE` survived the full
# suite. Same idiom as `test_confirmation.py`'s `_normalised_docs_template`
# and `test_delivery.py`'s own copy of it: collapse the markdown's line
# wrapping to one string and check the composed text is a substring of it.
# ------------------------------------------------------------------ #

_DOCS_TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "handbook"
    / "toolkit"
    / "emails"
    / "survey-invitation.md"
)


def _normalised_docs_template() -> str:
    text = _DOCS_TEMPLATE.read_text(encoding="utf-8")
    return " ".join(text.split())


def test_the_notice_matches_the_documentation_copy() -> None:
    assert NOTICE in _normalised_docs_template()


def test_the_subject_matches_the_documentation_copy() -> None:
    message = compose(_registration(), "[the event's title, when known]", "x")
    assert message.subject in _normalised_docs_template()
