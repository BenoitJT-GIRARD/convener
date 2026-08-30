from __future__ import annotations

from typing import Any

import pytest
from conftest import speaker

from convener_ops.declaration import published
from convener_ops.declaration.paths import repo_root
from convener_ops.journey.registration import signup_url
from convener_ops.publication.announce import (
    forum_announcement,
    mailing_list_message,
    network_post,
    recording_announcement,
)
from convener_ops.publication.public_data import to_public

#: Every function below renders the real, committed
#: `docs/toolkit/*.md` page -- the same file `app/src/content/render.ts`
#: substitutes for the cockpit's own copy-to-clipboard button -- rather
#: than a second, hand-typed English composed only in Python. `root=ROOT`
#: is threaded through every call below the same way `visual.render_
#: announcement(..., root=root)` already is: a pure function handed its
#: own inputs, checked against the real checkout, never a fabricated one.
ROOT = repo_root()

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
        text = forum_announcement(_row(), root=ROOT)
        assert "Ada Lovelace" in text
        assert "Analytical Engines Institute" in text
        assert "On analytical engines" in text
        assert "An abstract about analytical engines." in text

    def test_reads_the_real_toolkit_page_not_a_second_copy(self) -> None:
        """The property this exists to prove: a sentence that lives
        only in `docs/toolkit/forum-post-announce.md`, never in this
        module's own prose, must appear in the rendered text -- a
        hand-rolled composition of the same facts could never produce it
        by accident, so this fails the moment this module goes back to
        composing English by hand instead of reading the file."""
        text = forum_announcement(_row(), root=ROOT)
        assert (
            "we host a stellar speaker presenting their work at our "
            "standing time of 12:30 Paris time on a Thursday" in text
        )

    def test_points_at_the_event_page_never_the_room(self) -> None:
        text = forum_announcement(_row(), root=ROOT)
        assert signup_url("mrg-77") in text

    def test_never_carries_a_room_link_even_if_one_reached_the_row(self) -> None:
        # `to_public` never maps a column to `zoom_link`, so a real row never
        # carries this key -- but nothing in this function's own signature
        # stops a caller handing one in anyway, so this proves the function
        # itself never reads or echoes it, not merely that today's data
        # happens not to carry one.
        row = _row(zoom_link=POISONED_ROOM_LINK, registration_link=POISONED_ROOM_LINK)
        text = forum_announcement(row, root=ROOT)
        assert POISONED_ROOM_LINK not in text

    def test_states_the_real_paris_offset_summer(self) -> None:
        text = forum_announcement(_row(date="2026-06-11"), root=ROOT)
        assert "CEST" in text
        assert "CET" not in text  # "CET" is not a substring of "CEST"

    def test_states_the_real_paris_offset_winter(self) -> None:
        text = forum_announcement(_row(date="2026-03-12"), root=ROOT)
        assert "CET" in text
        assert "CEST" not in text


class TestNetworkPost:
    def test_carries_the_real_facts_and_registration_link(self) -> None:
        text = network_post(_row(date="2026-09-10"), root=ROOT)
        assert "Ada Lovelace" in text
        assert "Analytical Engines Institute" in text
        assert "On analytical engines" in text
        assert signup_url("mrg-77") in text
        assert "CEST" in text

    def test_reads_the_real_toolkit_page_not_a_second_copy(self) -> None:
        text = network_post(_row(), root=ROOT)
        assert "There is no LinkedIn robot behind this page and none is planned" in text

    def test_carries_the_forum_thread_link_when_there_is_one(self) -> None:
        # `docs/toolkit/linkedin-post.md` invites readers to the forum
        # thread -- a field the old hand-rolled `network_post` never even
        # read, since it composed its own, shorter English independently
        # of the template.
        text = network_post(
            _row(forum_thread="https://forum.example.org/t/77"), root=ROOT
        )
        assert "https://forum.example.org/t/77" in text
        # The fact is already in the body, so the conditional
        # note in "Notes for the volunteer posting this" must not repeat it.
        assert "none has been opened yet" not in text

    def test_drops_the_forum_thread_line_and_flags_it_as_a_task_when_absent(
        self,
    ) -> None:
        # This template's own "Join the discussion ..." line
        # exists only to carry the link, so an unopened thread must not
        # leave that sentence -- or a marker -- sitting in the post a
        # volunteer is about to paste onto LinkedIn.
        text = network_post(_row(forum_thread=""), root=ROOT)
        assert "Join the discussion" not in text
        assert "«missing: speaker.forum_thread»" not in text
        assert "none has been opened yet, so open one and add its link" in text

    def test_never_carries_a_room_link(self) -> None:
        row = _row(zoom_link=POISONED_ROOM_LINK)
        assert POISONED_ROOM_LINK not in network_post(row, root=ROOT)


class TestMailingListMessage:
    def test_addresses_a_reader_who_does_not_know_the_series(self) -> None:
        # The declared values, never their spelling: this message is
        # rendered for whichever instance runs the repository, and a
        # literal here would pass for one of them and fail for the rest.
        identity = published.load_identity(ROOT)
        text = mailing_list_message(_row(), root=ROOT)
        assert identity.organisation in text
        assert identity.forum_host in text

    def test_reads_the_real_toolkit_page_not_a_second_copy(self) -> None:
        text = mailing_list_message(_row(), root=ROOT)
        assert "who did not ask about this particular talk" in text

    def test_carries_the_real_facts_and_registration_link(self) -> None:
        text = mailing_list_message(_row(), root=ROOT)
        assert "Ada Lovelace" in text
        assert signup_url("mrg-77") in text

    def test_states_the_real_paris_offset_summer(self) -> None:
        assert "CEST" in mailing_list_message(_row(date="2026-04-02"), root=ROOT)

    def test_states_the_real_paris_offset_winter(self) -> None:
        text = mailing_list_message(_row(date="2026-02-05"), root=ROOT)
        assert "CET" in text
        assert "CEST" not in text

    def test_drops_the_forum_thread_sentence_and_flags_it_as_a_task_when_absent(
        self,
    ) -> None:
        # An earlier hand-rolled version showed the ordinary
        # `«missing: …»` marker here -- exactly the bug the optional-field
        # sigil exists for, since this is plain text a volunteer forwards
        # verbatim. An edition with no thread yet now drops the sentence
        # from the body outright and says so, as a task, in "Notes for the
        # volunteer sending this".
        text = mailing_list_message(_row(forum_thread=""), root=ROOT)
        body, _, notes = text.partition("## Notes for the volunteer sending this")
        assert "forum thread" not in body
        assert "«missing: speaker.forum_thread»" not in text
        assert "none has been opened yet, so open one and add its link" in notes

    def test_carries_the_forum_thread_sentence_and_no_note_when_present(self) -> None:
        text = mailing_list_message(
            _row(forum_thread="https://forum.example.org/t/77"), root=ROOT
        )
        assert "on the forum thread: https://forum.example.org/t/77" in text
        assert "none has been opened yet" not in text

    def test_never_carries_a_room_link(self) -> None:
        row = _row(zoom_link=POISONED_ROOM_LINK)
        assert POISONED_ROOM_LINK not in mailing_list_message(row, root=ROOT)


class TestRecordingAnnouncement:
    def test_is_none_when_there_is_nothing_to_announce(self) -> None:
        row = _row(status="archived", youtube_url="")
        assert recording_announcement(row, root=ROOT) is None

    def test_reads_the_real_toolkit_page_not_a_second_copy(self) -> None:
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            bio="Ada writes the first published computer program.",
        )
        text = recording_announcement(row, root=ROOT)
        assert text is not None
        assert "Check the recorded answer before you post" in text

    def test_carries_the_video_and_the_biography_when_present(self) -> None:
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            bio="Ada writes the first published computer program.",
        )
        text = recording_announcement(row, root=ROOT)
        assert text is not None
        assert "https://youtu.be/analytical-engines" in text
        assert "Ada writes the first published computer program." in text
        # The biography is right there in the body, so the
        # conditional "withheld" note in "Notes for the volunteer posting
        # this" must not appear alongside it.
        assert "stays withheld" not in text

    def test_drops_the_biography_paragraph_and_notes_it_was_withheld(self) -> None:
        # This is the finding itself -- `docs/toolkit/
        # recording-announce.md`'s `{{ public.bio }}` used to sit alone as a
        # paragraph and render the bare `«missing: public.bio»` marker
        # straight into the body a volunteer copies and pastes as-is. An
        # unavailable biography now leaves no trace in the body -- no
        # marker, no empty gap where the paragraph used to be -- and is
        # named, as finished business rather than a task, in "Notes for the
        # volunteer posting this".
        row = _row(
            status="archived", youtube_url="https://youtu.be/analytical-engines", bio=""
        )
        text = recording_announcement(row, root=ROOT)
        assert text is not None
        body, _, notes = text.partition("## Notes for the volunteer posting this")
        assert "«missing: public.bio»" not in text
        assert "\n\n\n" not in body  # no empty gap left where the paragraph was
        assert "stays withheld" in notes

    def test_withheld_biography_and_unset_thread_read_differently_in_the_notes(
        self,
    ) -> None:
        # The deeper point the finding raises: consent withheld (nothing to
        # fill in -- and prompting the volunteer to supply one invites them
        # to paste in something the speaker never sent) and not-yet-set (a
        # task the volunteer may be the one to close) must not collapse
        # into the same sentence.
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            bio="",
            forum_thread="",
        )
        text = recording_announcement(row, root=ROOT)
        assert text is not None
        _, _, notes = text.partition("## Notes for the volunteer posting this")
        bio_note = "No biography is included above: it stays withheld"
        thread_note = "No forum thread link is included above: none has been opened yet"
        assert bio_note in notes
        assert thread_note in notes
        assert bio_note != thread_note

    def test_a_required_field_still_shows_the_loud_marker_when_absent(self) -> None:
        # Contrast case: `title` is not one of the two ordinarily-absent
        # fields above -- this project expects a scheduled or archived
        # edition to have one -- so a row missing it is not ready to post
        # and the draft must keep looking exactly that unfinished, the same
        # `«missing: …»` marker every other required field already shows.
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            title="",
        )
        text = recording_announcement(row, root=ROOT)
        assert text is not None
        assert "«missing: public.title»" in text

    def test_never_carries_a_room_link(self) -> None:
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            zoom_link=POISONED_ROOM_LINK,
        )
        text = recording_announcement(row, root=ROOT)
        assert text is not None
        assert POISONED_ROOM_LINK not in text

    def test_drops_the_forum_thread_sentence_and_flags_it_as_a_task(self) -> None:
        # The sentence naming the forum thread exists only to
        # carry that link, so an edition with no thread yet drops the whole
        # sentence from the body -- not merely the address -- and names the
        # gap as a task in "Notes for the volunteer posting this" instead.
        row = _row(
            status="archived",
            youtube_url="https://youtu.be/analytical-engines",
            forum_thread="",
        )
        text = recording_announcement(row, root=ROOT)
        assert text is not None
        body, _, notes = text.partition("## Notes for the volunteer posting this")
        # The whole sentence goes -- not merely the address -- since it
        # exists only to introduce the link.
        assert "The questions asked before the talk" not in body
        assert "on the forum thread" not in body
        assert "«missing: public.forum_thread»" not in text
        assert "none has been opened yet, so open one and add its link" in notes


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
        assert recording_announcement(row, root=ROOT) is None

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
        text = recording_announcement(row, root=ROOT)
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
        text = recording_announcement(row, root=ROOT)
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
    for text in (
        forum_announcement(row, root=ROOT),
        network_post(row, root=ROOT),
        mailing_list_message(row, root=ROOT),
    ):
        assert expected in text
    recording_row = _row(
        date=iso_date, status="archived", youtube_url="https://youtu.be/x"
    )
    recording = recording_announcement(recording_row, root=ROOT)
    assert recording is not None
    assert expected in recording
