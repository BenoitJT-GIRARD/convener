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

Fix round 1: one prose, not two
--------------------------------
This module used to compose its own English by hand, deliberately not
reading `docs/toolkit/*.md` -- a second templating engine over the same
four files, its own docstring argued, was a second thing to keep in step
with `render.ts`'s own for a payoff nobody had asked for. That argument
proved wrong the moment it was checked against what an operator actually
copies: `InlineContent.tsx`'s "Copy to clipboard" button copies the whole
substituted page, headers and volunteer notes included, and this module's
hand-typed sentences were a *different*, shorter text under the same four
names -- two independently-authored bodies of prose for one artefact, free
to disagree the moment either one was edited without the other. D-14's own
answer to a rule living on both sides of a language boundary is a shared
fixture read from both sides, not two hand-typed copies; here the shared
artefact is the templates themselves. So every function below now reads
the identical file `render.ts` substitutes -- `docs/toolkit/forum-post-
announce.md`, `linkedin-post.md`, `mailing-list-announce.md`, `recording-
announce.md` -- through `_render`, a second, independent substitution
engine (mechanics may exist twice; the words may not) that resolves the
identical `{{ speaker.… }}`/`{{ public.… }}` vocabulary `render.ts::
substitute` does, including the same `«missing: …»` marker for an unfilled
field. A change to a template's wording now reaches both surfaces because
there is only the one file to change; `tools/tests/test_announce.py`'s own
mutation of a template proves it.

`root` is threaded in by the caller (`cli.py::render_announcements`) rather
than resolved here, the same convention `visual.render_announcement` and
`_load_colours` already hold: a pure function that is handed its own inputs
rather than reading `paths.repo_root()` itself is the one every test in
this module already calls against the real checkout.

No room link, structurally
-----------------------------
Nothing below ever reads a `"zoom_link"` (or any other) key off `row` that
`PUBLIC_FIELD_SOURCES` does not already map -- there is no such key to read,
since `row` is `to_public`'s own output. `registration.signup_url` takes an
event id, never a URL, so the one address every text below points at is
always the event's own public page (D-19), never a room. And no template
below ever declares a `{{ speaker.zoom_link }}`/`{{ public.zoom_link }}`
token in the first place (`tools/tests/test_announce.py`'s own room-link
mutation proves both halves: a token that is not in `row` cannot resolve,
and a token that is not in the template is not there to resolve).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Final

from .registration import signup_url
from .visual import date_line

__all__ = [
    "forum_announcement",
    "mailing_list_message",
    "network_post",
    "recording_announcement",
]

#: Relative to the repository root, the same convention `register.py::
#: REGISTER_PATH` already uses for a `docs/` file -- and the exact
#: directory `app/scripts/copy-handbook.mjs` copies into the cockpit's own
#: `public/handbook/toolkit/`, so this is provably the file an operator's
#: browser fetches too, not a second copy of it.
TOOLKIT_DIR: Final[Path] = Path("docs") / "toolkit"

#: `render.ts`'s own `{{ *.* }}` grammar -- a namespace, a dot, a leaf --
#: reproduced here rather than imported: a `.ts` module cannot be required
#: from Python, and this is the whole of what there is to reproduce.
_PLACEHOLDER = re.compile(r"\{\{\s*([\w]+)\.([\w]+)\s*\}\}")


def _missing(namespace: str, leaf: str) -> str:
    """`render.ts::MISSING`'s own marker, byte-for-byte: a guillemet pair
    around `namespace.leaf`, shown for an empty or absent field exactly as
    the cockpit shows it for the identical reason -- a template reading a
    field this row does not carry is not a bug in the template, it is this
    row not being ready yet (D-13)."""
    return f"«missing: {namespace}.{leaf}»"


def _render(text: str, namespaces: Mapping[str, Mapping[str, str]]) -> str:
    """Resolve every `{{ namespace.leaf }}` token in `text` against
    `namespaces`, exactly the two rules `render.ts::substitute` applies: a
    namespace or leaf this call was not given resolves to the missing
    marker, and so does an empty string -- never a blank line silently
    standing in for a field nobody filled in."""

    def repl(match: re.Match[str]) -> str:
        namespace, leaf = match.group(1), match.group(2)
        value = namespaces.get(namespace, {}).get(leaf, "")
        return value if value else _missing(namespace, leaf)

    return _PLACEHOLDER.sub(repl, text)


def _template(root: Path, name: str) -> str:
    return (root / TOOLKIT_DIR / name).read_text(encoding="utf-8")


def _event_id(row: Mapping[str, Any]) -> str:
    """`row["id"]` is `to_public`'s own rendering of `edition_code`, cased
    exactly as typed in `data/speakers.yml` -- R-5 (`platform.find_speaker`)
    lower-cases it, and this is the one place these functions apply that
    rule, rather than trusting every caller to have done it already."""
    return str(row.get("id", "")).lower()


def _talk_date(row: Mapping[str, Any]) -> date:
    return date.fromisoformat(str(row["date"]))


def _speaker_namespace(row: Mapping[str, Any]) -> dict[str, str]:
    """The `{{ speaker.… }}` fields the forum, professional-network and
    mailing-list templates read -- every one of them `PUBLISHABLE_ALWAYS`
    (`public_data.py`), so reading them straight off `row` needs no further
    gate: agreeing to give a public webinar is agreeing to appear in its
    own programme."""
    return {
        "name": str(row.get("speaker_name", "")),
        "affiliation": str(row.get("speaker_affiliation", "")),
        "title": str(row.get("title", "")),
        "abstract": str(row.get("abstract", "")),
        "edition_code": str(row.get("id", "")),
        "when": date_line(_talk_date(row)),
        "signup_link": signup_url(_event_id(row)),
        "forum_thread": str(row.get("forum_thread", "")),
    }


def _public_namespace(row: Mapping[str, Any]) -> dict[str, str]:
    """The `{{ public.… }}` fields the recording announcement reads --
    `bio` and `youtube_url` are `PUBLISHABLE_ON_CONSENT`, already blanked by
    `to_public` unless the speaker's consent and the board's own approval
    both cleared (`public_data.personal_disclosure_withheld`/
    `recording_withheld`, "deliberately the same gate ... not a second,
    gentler one"). Named `public` rather than `speaker`, mirroring
    `render.ts`'s own two namespaces, even though both read the identical
    `row` here: Python only ever sees `to_public`'s output, so there is no
    second, ungated record for a `speaker.*` token to reach for in this
    module the way TypeScript's raw `Speaker` record still can."""
    return {
        "name": str(row.get("speaker_name", "")),
        "affiliation": str(row.get("speaker_affiliation", "")),
        "title": str(row.get("title", "")),
        "when": date_line(_talk_date(row)),
        "youtube_url": str(row.get("youtube_url", "")),
        "bio": str(row.get("bio", "")),
        "forum_thread": str(row.get("forum_thread", "")),
    }


def forum_announcement(row: Mapping[str, Any], *, root: Path) -> str:
    """`docs/toolkit/forum-post-announce.md`, filled in from `row`."""
    text = _template(root, "forum-post-announce.md")
    return _render(text, {"speaker": _speaker_namespace(row)})


def network_post(row: Mapping[str, Any], *, root: Path) -> str:
    """`docs/toolkit/linkedin-post.md`, filled in from `row`. Named
    `network_post`, not `linkedin_post`: the professional network is the
    channel, LinkedIn is this project's own current choice of one, and the
    template's own filename is the one place that choice is written down
    (`docs/toolkit/linkedin-post.md`'s own module comment)."""
    text = _template(root, "linkedin-post.md")
    return _render(text, {"speaker": _speaker_namespace(row)})


def mailing_list_message(row: Mapping[str, Any], *, root: Path) -> str:
    """`docs/toolkit/mailing-list-announce.md`, filled in from `row`."""
    text = _template(root, "mailing-list-announce.md")
    return _render(text, {"speaker": _speaker_namespace(row)})


def recording_announcement(row: Mapping[str, Any], *, root: Path) -> str | None:
    """`docs/toolkit/recording-announce.md`, filled in from `row` --
    `None`, not a page full of missing markers, when `row["youtube_url"]`
    is empty: there is nothing to announce yet, an ordinary state (D-13)
    for an archived edition whose speaker has not yet agreed to publish,
    and the caller's job to treat it as such."""
    public = _public_namespace(row)
    if not public["youtube_url"]:
        return None
    text = _template(root, "recording-announce.md")
    return _render(text, {"public": public})
