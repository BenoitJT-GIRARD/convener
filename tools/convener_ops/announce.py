"""The ready-to-publish texts (D-09): a forum announcement, a professional-
network post, a mailing-list message, and the announcement that a recording
has gone up -- drafts an operator reads, adjusts and posts by hand.

Every function below takes exactly one row of `public_data.to_public`'s own
output, never a raw `data/speakers.yml` entry. That is the whole safety
argument: `to_public` has already applied the publication gate --
`PUBLISHABLE_ON_CONSENT` fields blanked unless the speaker's consent and the
board's approval both cleared, the recording additionally blanked outside
`RECORDING_STATUSES`, the room link never mapped to any column at all
(`public_data.PUBLIC_FIELD_SOURCES`'s own comment explains why `zoom_link`
reaches this repository under no name) -- so a row's own shape makes a
withheld biography or a room link structurally unreachable here, the same
way `visual.render_announcement` never re-checks `photo_url`'s consent
because `to_public` already emptied it. See `public_data.py`'s own module
docstring for the argument in full; nothing here re-derives it.

Why prose, not a `{{ }}` template
----------------------------------
`app/src/content/render.ts` already substitutes `docs/toolkit/*.md`'s own
`{{ speaker.… }}`/`{{ public.… }}` placeholders for an operator working
inside the cockpit (`app/`, D-15's "vitrine" vocabulary calls it that) --
that is the surface named in this task's own brief as "where an operator
would copy a text from", and it is not duplicated here. What this module
adds is the same four texts built straight from `data/speakers.yml`, for a
command line or a CI job with no browser and no authenticated session --
`cli.py::render_announcements`'s own docstring says where that matters. So
these functions compose plain English by hand, in Python, rather than
re-reading the Markdown templates: a second templating engine over the same
four files would be a second thing to keep in step with `render.ts`'s own,
for a payoff -- byte-for-byte identical wording on two surfaces nobody reads
side by side -- this project has not asked for. What *is* shared, and
therefore reused rather than restated, is every fact that would otherwise
drift: the real Europe/Paris offset (`visual.date_line`, D-14's own worked
example of exactly this hazard) and the registration address (D-19,
`registration.signup_url`).

No room link, structurally
-----------------------------
Nothing below ever reads a `"zoom_link"` (or any other) key off `row` that
`PUBLIC_FIELD_SOURCES` does not already map -- there is no such key to read,
since `row` is `to_public`'s own output. `registration.signup_url` takes an
event id, never a URL, so the one address every text below points at is
always the event's own public page (D-19), never a room.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from .registration import signup_url
from .visual import date_line

__all__ = [
    "forum_announcement",
    "mailing_list_message",
    "network_post",
    "recording_announcement",
]


def _event_id(row: Mapping[str, Any]) -> str:
    """`row["id"]` is `to_public`'s own rendering of `edition_code`, cased
    exactly as typed in `data/speakers.yml` -- R-5 (`platform.find_speaker`)
    lower-cases it, and this is the one place these functions apply that
    rule, rather than trusting every caller to have done it already."""
    return str(row.get("id", "")).lower()


def _talk_date(row: Mapping[str, Any]) -> date:
    return date.fromisoformat(str(row["date"]))


def _byline(row: Mapping[str, Any]) -> str:
    name = str(row.get("speaker_name", ""))
    affiliation = str(row.get("speaker_affiliation", ""))
    return f"{name} ({affiliation})" if affiliation else name


def forum_announcement(row: Mapping[str, Any]) -> str:
    """The forum announcement: the longest of the four, for readers who
    already know the series and can be given the full abstract and the
    registration address in one place."""
    when = date_line(_talk_date(row))
    signup = signup_url(_event_id(row))
    title = str(row.get("title", ""))
    abstract = str(row.get("abstract", ""))
    thread_note = str(row.get("forum_thread", ""))
    lines = [
        f"Don't miss the next The Example Collective Monthly Reading Group: {title}",
        "",
        f"We are hosting {_byline(row)}, {when}, online and free to attend.",
        "",
        title,
        "",
        abstract,
        "",
        f"Register here: {signup}",
    ]
    if thread_note:
        lines += [
            "",
            "Post your questions ahead of time on this thread, and join the "
            "discussion after the talk.",
        ]
    lines += [
        "",
        "As always, the recording is only published if our speaker later "
        "agrees to it — the talk itself is open to everyone, live.",
    ]
    return "\n".join(lines) + "\n"


def network_post(row: Mapping[str, Any]) -> str:
    """The professional-network post: scanned, not read -- the talk's title
    earns the first line, and everything else is short enough to take in
    without clicking through."""
    when = date_line(_talk_date(row))
    signup = signup_url(_event_id(row))
    title = str(row.get("title", ""))
    lines = [
        f"{title}",
        "",
        f"The Example Collective's next virtual seminar, {when}.",
        "",
        f"{_byline(row)}",
        "",
        f"Free to attend, online, registration required: {signup}",
    ]
    return "\n".join(lines) + "\n"


def mailing_list_message(row: Mapping[str, Any]) -> str:
    """The mailing-list message: plain text, for TEATIME, an institute's own
    newsletter or internal messaging, and the RISC newsletter alike --
    reaching people who did not ask about this particular talk, so nothing
    here assumes they already know the series."""
    when = date_line(_talk_date(row))
    signup = signup_url(_event_id(row))
    title = str(row.get("title", ""))
    abstract = str(row.get("abstract", ""))
    lines = [
        f"Subject: The Example Collective — {title}",
        "",
        "Hello,",
        "",
        f"The Example Collective's next virtual seminar is {when}, online and "
        "free to attend.",
        "",
        f"{_byline(row)} will present:",
        "",
        f'"{title}"',
        "",
        abstract,
        "",
        f"Register here: {signup}",
        "",
        "The Example Collective is a virtual seminar series in behavioural "
        "science, held roughly monthly and open to anyone. Past talks and "
        "recordings are at forum.example.test.",
    ]
    return "\n".join(lines) + "\n"


def recording_announcement(row: Mapping[str, Any]) -> str | None:
    """The recording announcement: for people who missed the talk and for
    people who want to revisit it. `None`, not an empty string, when
    `row["youtube_url"]` is empty -- there is nothing to announce, an
    ordinary state (D-13) for an archived edition whose speaker has not yet
    agreed to publish, and the caller's job to treat it as such rather than
    writing an announcement with a blank where the video should be.

    Includes the speaker's own biography, exactly as `row["bio"]` carries
    it, when `to_public` has left one there -- which, since it shares the
    same gate as the recording (`public_data.py`'s own module docstring:
    "Deliberately the same gate ... not a second, gentler one"), is
    whenever this function has anything to announce in the first place.
    Omitted, not left as an empty paragraph, when there is none.
    """
    youtube_url = str(row.get("youtube_url", ""))
    if not youtube_url:
        return None
    when = date_line(_talk_date(row))
    title = str(row.get("title", ""))
    thread = str(row.get("forum_thread", ""))
    bio = str(row.get("bio", ""))
    lines = [
        f"Now online: {title}",
        "",
        f"The recording of our seminar with {_byline(row)}, {title}, given "
        f"{when}, is now online:",
        "",
        youtube_url,
        "",
        "If you missed it live, this is the whole talk. If you were there, "
        "it is worth another watch, and a good one to send to a colleague "
        "who was not.",
    ]
    if bio:
        lines += ["", bio]
    if thread:
        lines += [
            "",
            "The questions asked before the talk, and the discussion that "
            f"followed, are on the forum thread: {thread}",
        ]
    return "\n".join(lines) + "\n"
