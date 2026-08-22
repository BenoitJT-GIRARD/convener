from __future__ import annotations

from typing import Any

import pytest
from conftest import speaker

from convener_ops.announce import (
    forum_announcement,
    mailing_list_message,
    network_post,
    recording_announcement,
)
from convener_ops.public_data import to_public

# The literal value `site/src/_data/events.json`'s own MRG-05 fixture
# carries, kept there as "a synthetic room-link-shaped column ... a
# template-regression canary" (`tools/tests/test_site.py`'s own words) --
# reused here rather than a second invented string, so a leak of *this*
# value is provably the same leak that test already guards the site against.
POISONED_ROOM_LINK = (
    "https://us02web.zoom.us/j/9998887771?pwd=SHOULD-NEVER-APPEAR-IN-BUILT-HTML"
)


def _row(**overrides: Any) -> dict[str, Any]:
    """A `to_public`-shaped row, hand-built so each function below can be
    exercised without a full speaker record -- `PUBLIC_FIELD_SOURCES`'s own
    columns, nothing else."""
    base: dict[str, Any] = {
        "id": "MRG-77",
        "title": "On analytical engines",
        "date": "2026-06-11",  # June -- daylight-saving time (CEST)
        "status": "scheduled",
        "abstract": "An abstract about analytical engines.",
        "photo_url": "",
        "bio": "",
        "linkedin": "",
        "seed_questions": "",
        "youtube_url": "",
        "forum_thread": "https://forum.example.org/t/77",
        "speaker_name": "Ada Lovelace",
        "speaker_affiliation": "Analytical Engines Institute",
        "speaker_country": "UK",
    }
    base.update(overrides)
    return base


class TestForumAnnouncement:
    def test_carries_the_real_facts(self) -> None:
        text = forum_announcement(_row())
        assert "Ada Lovelace" in text
        assert "Analytical Engines Institute" in text
        assert "On analytical engines" in text
        assert "An abstract about analytical engines." in text

    def test_points_at_the_event_page_never_the_room(self) -> None:
        text = forum_announcement(_row())
        assert "https://example-instance.github.io/example-showcase/events/mrg-77/" in text

    def test_omits_the_thread_invitation_when_there_is_no_thread_yet(self) -> None:
        text = forum_announcement(_row(forum_thread=""))
        assert "join the discussion after the talk" not in text

    def test_never_carries_a_room_link_even_if_one_reached_the_row(self) -> None:
        # `to_public` never maps a column to `zoom_link`, so a real row never
        # carries this key -- but nothing in this function's own signature
        # stops a caller handing one in anyway, so this proves the function
        # itself never reads or echoes it, not merely that today's data
        # happens not to carry one.
        row = _row(zoom_link=POISONED_ROOM_LINK, registration_link=POISONED_ROOM_LINK)
        text = forum_announcement(row)
        assert POISONED_ROOM_LINK not in text

    def test_states_the_real_paris_offset_summer(self) -> None:
        text = forum_announcement(_row(date="2026-06-11"))
        assert "CEST" in text
        assert "CET" not in text  # "CET" is not a substring of "CEST"

    def test_states_the_real_paris_offset_winter(self) -> None:
        text = forum_announcement(_row(date="2026-03-12"))
        assert "CET" in text
        assert "CEST" not in text


class TestNetworkPost:
    def test_leads_with_the_title(self) -> None:
        text = network_post(_row())
        first_line = text.splitlines()[0]
        assert first_line == "On analytical engines"

    def test_carries_the_registration_link_and_the_real_offset(self) -> None:
        text = network_post(_row(date="2026-09-10"))
        assert "https://example-instance.github.io/example-showcase/events/mrg-77/" in text
        assert "CEST" in text

    def test_never_carries_a_room_link(self) -> None:
        row = _row(zoom_link=POISONED_ROOM_LINK)
        assert POISONED_ROOM_LINK not in network_post(row)


class TestMailingListMessage:
    def test_addresses_a_reader_who_does_not_know_the_series(self) -> None:
        text = mailing_list_message(_row())
        assert "The Example Collective" in text
        assert "forum.example.test" in text

    def test_carries_the_real_facts_and_registration_link(self) -> None:
        text = mailing_list_message(_row())
        assert "Ada Lovelace" in text
        assert "https://example-instance.github.io/example-showcase/events/mrg-77/" in text

    def test_states_the_real_paris_offset_summer(self) -> None:
        assert "CEST" in mailing_list_message(_row(date="2026-04-02"))

    def test_states_the_real_paris_offset_winter(self) -> None:
        assert "CET" in mailing_list_message(_row(date="2026-02-05"))
        assert "CEST" not in mailing_list_message(_row(date="2026-02-05"))

    def test_never_carries_a_room_link(self) -> None:
        row = _row(zoom_link=POISONED_ROOM_LINK)
        assert POISONED_ROOM_LINK not in mailing_list_message(row)


class TestRecordingAnnouncement:
    def test_is_none_when_there_is_nothing_to_announce(self) -> None:
        assert recording_announcement(_row(status="archived", youtube_url="")) is None

    def test_carries_the_video_and_the_biography_when_present(self) -> None:
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            bio="Ada writes the first published computer program.",
        )
        text = recording_announcement(row)
        assert text is not None
        assert "https://youtu.be/analytical-engines" in text
        assert "Ada writes the first published computer program." in text

    def test_omits_the_biography_paragraph_when_there_is_none(self) -> None:
        row = _row(
            status="archived", youtube_url="https://youtu.be/analytical-engines", bio=""
        )
        text = recording_announcement(row)
        assert text is not None
        # No stray blank paragraph or missing-marker left behind either.
        assert "\n\n\n" not in text

    def test_never_carries_a_room_link(self) -> None:
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            zoom_link=POISONED_ROOM_LINK,
        )
        text = recording_announcement(row)
        assert text is not None
        assert POISONED_ROOM_LINK not in text

    def test_omits_the_forum_paragraph_when_there_is_no_thread(self) -> None:
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            forum_thread="",
        )
        text = recording_announcement(row)
        assert text is not None
        assert "forum thread" not in text


class TestRoutedThroughTheRealGate:
    """Integration-level: these four functions are only ever called with
    `public_data.to_public`'s own output in `cli.py::render_announcements`
    (and are documented never to be called any other way), so what actually
    has to hold is that *this* pipeline never leaks a withheld biography or
    an unconsented recording -- not merely that the functions behave once
    handed an already-safe row by hand, which every test above already
    proves on its own terms. This is the one place breaking
    `public_data.to_public`'s own gate would be caught by this module's own
    suite rather than only by `test_public_data.py`."""

    def _archived(self, **overrides: Any) -> dict[str, Any]:
        return speaker(
            status="archived",
            edition_code="MRG-77",
            date="2026-06-11",
            title="On analytical engines",
            abstract="An abstract about analytical engines.",
            bio="Ada writes the first published computer program.",
            youtube_url="https://youtu.be/analytical-engines",
            zoom_link=POISONED_ROOM_LINK,
            forum_thread="https://forum.example.org/t/77",
            **overrides,
        )

    def test_withholds_the_biography_and_the_recording_while_pending(self) -> None:
        entry = self._archived(
            publication={
                "consent": "pending",
                "approved_by": "",
                "approved_on": "",
                "objections": [],
                "outcome": "",
            }
        )
        [row] = to_public([entry])
        # Checked directly on the row, not only through `recording_announcement`
        # returning `None`: that also happens whenever `youtube_url` alone is
        # withheld, which is a separate check in `to_public` from the one that
        # blanks `bio` -- asserting only "no announcement" would not catch a
        # regression that blanked the recording but forgot the biography.
        assert row["bio"] == ""
        assert row["youtube_url"] == ""
        assert recording_announcement(row) is None

    def test_discloses_once_consent_is_granted_and_the_board_has_published(
        self,
    ) -> None:
        entry = self._archived(
            publication={
                "consent": "granted",
                "approved_by": "alice",
                "approved_on": "2026-06-15",
                "objections": [],
                "outcome": "published",
            }
        )
        [row] = to_public([entry])
        text = recording_announcement(row)
        assert text is not None
        assert "Ada writes the first published computer program." in text
        assert "https://youtu.be/analytical-engines" in text

    def test_the_room_link_never_survives_the_real_pipeline_either(self) -> None:
        entry = self._archived(
            publication={
                "consent": "granted",
                "approved_by": "alice",
                "approved_on": "2026-06-15",
                "objections": [],
                "outcome": "published",
            }
        )
        [row] = to_public([entry])
        assert "zoom_link" not in row
        text = recording_announcement(row)
        assert text is not None
        assert POISONED_ROOM_LINK not in text


@pytest.mark.parametrize(
    ("iso_date", "expected"),
    [
        # Three of this project's own five fixture editions
        # (`site/src/_data/events.json`) fall in daylight-saving time -- a
        # test that only checked a winter date would pass against a
        # hard-coded "CET".
        ("2026-04-02", "CEST"),
        ("2026-06-11", "CEST"),
        ("2026-09-10", "CEST"),
        ("2026-02-05", "CET"),
        ("2026-03-12", "CET"),
    ],
)
def test_each_of_the_four_texts_names_the_real_paris_offset(
    iso_date: str, expected: str
) -> None:
    row = _row(date=iso_date, status="scheduled")
    for text in (forum_announcement(row), network_post(row), mailing_list_message(row)):
        assert expected in text
    recording_row = _row(
        date=iso_date, status="archived", youtube_url="https://youtu.be/x"
    )
    recording = recording_announcement(recording_row)
    assert recording is not None
    assert expected in recording
