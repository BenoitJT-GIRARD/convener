"""The codes this project prints -- proving they decode, and proving an
address can never be handed to one.

A code nobody has decoded is a rectangle of noise, so every test below
that touches an actual QR code decodes it with
`qr_decode.decode_registration_qr` -- an independent decoder, written for
this suite alone (see that module's own docstring) -- and compares the
recovered string against `registration.signup_url`, never merely checking
that some SVG markup was produced.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date

import pytest
from helpers.qr_decode import decode_registration_qr

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.published import (
    DEGRADABLE_FIELDS,
    IDENTITY_FIELDS,
    INSTANCE_PATH,
    PLACEHOLDER_MARKER,
    Identity,
    Published,
    identity_from_data,
    load_identity,
)
from convener_ops.journey.registration import signup_url
from convener_ops.publication import brand
from convener_ops.publication.registration_code import (
    forum_code_svg,
    forum_code_target,
    registration_code_svg,
)
from convener_ops.publication.visual import Announcement, render_announcement

ROOT = repo_root()
_W, _H = 1200.0, 1200.0


def _extract_registration_svg(doc: str) -> str:
    """The `<svg>...</svg>` fragment inside the rendered page's own
    `data-registration-code-slot` div -- decoded exactly as embedded, not
    regenerated from the `Announcement` that produced the page, so a bug
    in how `render_announcement` threads its own arguments through would
    not have anywhere to hide."""
    match = re.search(
        r'<div class="registration-code-slot" data-registration-code-slot>'
        r"(.*?)</div>",
        doc,
        re.DOTALL,
    )
    assert match, "no registration-code-slot found in the rendered page"
    return match.group(1)


# ---------------------------------------------------------------------------
# The code round-trips: decode(encode(event_id)) == signup_url(event_id).
# ---------------------------------------------------------------------------


def test_registration_code_svg_decodes_to_the_signup_url() -> None:
    svg = registration_code_svg("mrg-4", dark="#000000")
    assert decode_registration_qr(svg) == signup_url("mrg-4")


def test_registration_code_svg_decodes_correctly_for_several_edition_ids() -> None:
    """Not just one id: a short one, a zero-padded one, and a long one
    (edition ids grow arbitrarily -- D-19 names nothing else as an
    identifier, so nothing here assumes a fixed length)."""
    for event_id in ("mrg-1", "mrg-007", "mrg-2026-summer-special-edition"):
        svg = registration_code_svg(event_id, dark="#000000")
        assert decode_registration_qr(svg) == signup_url(event_id)


def test_the_rendered_page_carries_a_code_that_decodes_to_the_signup_url() -> None:
    """Not the isolated function in a vacuum -- the actual composed page,
    the artefact a Chrome render turns into the poster's own pixels."""
    announcement = Announcement(
        title="On analytical engines",
        talk_date=date(2026, 3, 12),
        speaker_name="Ada Lovelace",
        speaker_affiliation="Analytical Engines Institute",
        event_id="mrg-9",
    )
    doc = render_announcement(announcement, width=_W, height=_H, root=ROOT)
    svg = _extract_registration_svg(doc)
    assert decode_registration_qr(svg) == signup_url("mrg-9")


def test_registration_code_svg_draws_in_the_given_colour() -> None:
    """`dark` reaches the rendered stroke -- proof that the colour is a
    parameter threaded through, not a value baked into this module (see
    `test_the_registration_code_is_drawn_in_brand_black` for proof it is
    actually *called* with `instance/data/brand.json`'s own black)."""
    svg = registration_code_svg("mrg-4", dark="#123456")
    assert 'stroke="#123456"' in svg


def test_the_registration_code_is_drawn_in_brand_black() -> None:
    """`render_announcement` threads `instance/data/brand.json`'s own "black" into
    the code -- not a hand-typed literal that happens to match today (the
    guard `test_visual.py::
    test_no_brand_colour_hand_typed_outside_root_or_motif_stroke` already
    runs against this page; segno renders a doubled hex triple such as
    "#000000" in its own shortened three-digit form, so that guard's
    literal substring search would not have caught a hand-typed value here
    either -- this test checks the actual, expanded colour instead)."""
    charter = json.loads((ROOT / brand.source(ROOT)).read_text(encoding="utf-8"))
    black = charter["colour"]["black"].lower()

    doc = render_announcement(
        Announcement(
            title="t",
            talk_date=date(2026, 1, 1),
            speaker_name="n",
            speaker_affiliation="a",
            event_id="mrg-1",
        ),
        width=_W,
        height=_H,
        root=ROOT,
    )
    svg = _extract_registration_svg(doc)
    stroke = re.search(r'stroke="(#[0-9a-fA-F]+)"', svg)
    assert stroke, "no stroke colour found on the registration code"
    value = stroke.group(1).lower()
    if len(value) == 4:  # segno's own shortened "#rgb" form
        value = "#" + "".join(ch * 2 for ch in value[1:])
    assert value == black


# ---------------------------------------------------------------------------
# A room link can never reach the code -- structurally, not by convention.
# `Announcement.event_id` is the only thing `_registration_slot_html` ever
# reads to build it; there is no field anywhere on this dataclass, or on
# `registration_code_svg`'s own signature, through which a URL could
# substitute for an id.
# ---------------------------------------------------------------------------


def test_a_room_link_never_reaches_the_encoded_code() -> None:
    """`site/src/_data/events.json`'s own `MRG-05` entry is this project's
    real, already-committed fixture for exactly this shape of mistake: it
    carries `registration_link`, a Zoom room address, marked
    "SHOULD-NEVER-APPEAR-IN-BUILT-HTML" -- the same string
    `.github/workflows/preview.yml`'s own guard sweeps the built site for.
    A caller building this edition's poster has that whole record in hand
    and extracts only `event_id = entry["id"].lower()` to construct
    an `Announcement` -- there is no parameter here the room link could
    travel through even if a future caller tried to pass the record
    itself, because `Announcement` and `registration_code_svg` both take
    an id, never a URL, never a whole record (see `registration_code.
    registration_code_svg`'s own docstring)."""
    events = json.loads(
        (ROOT / "site" / "src" / "_data" / "events.json").read_text(encoding="utf-8")
    )
    entry = next(e for e in events if e["id"] == "MRG-05")
    assert "SHOULD-NEVER-APPEAR-IN-BUILT-HTML" in entry["registration_link"]

    event_id = entry["id"].lower()
    announcement = Announcement(
        title=entry["title"],
        talk_date=date.fromisoformat(entry["date"]),
        speaker_name=entry["speaker_name"],
        speaker_affiliation=entry["speaker_affiliation"],
        event_id=event_id,
    )
    doc = render_announcement(announcement, width=_W, height=_H, root=ROOT)

    assert "SHOULD-NEVER-APPEAR-IN-BUILT-HTML" not in doc
    assert "zoom.us" not in doc
    assert entry["registration_link"] not in doc

    svg = _extract_registration_svg(doc)
    decoded = decode_registration_qr(svg)
    assert decoded == signup_url(event_id)
    assert "zoom" not in decoded.lower()


def test_registration_code_svg_signature_has_no_url_or_link_parameter() -> None:
    """A structural guard against the trap ever being reopened: the only
    way to influence what the code encodes is `event_id` -- if a future
    edit ever added a second parameter shaped like a URL or a link, this
    is the test that should force a reviewer to ask why."""
    import inspect

    parameters = inspect.signature(registration_code_svg).parameters
    assert set(parameters) == {"event_id", "dark", "root"}
    # `root` is a directory, not an address. It says which instance's
    # declaration the URL is *derived* from -- the same root
    # `visual.render_announcement` already takes for the charter, so that a
    # poster's colours and the address inside its QR come from one instance
    # rather than two. Nothing about it lets a caller
    # choose the address itself, which is the property this test exists
    # for, so the shape rule below is what carries the guard now and the
    # set above is only what makes a reviewer look.
    assert not any(
        word in name.lower()
        for name in parameters
        for word in ("url", "link", "href", "base", "address")
    )


# ---------------------------------------------------------------------------
# The series' own code: the one on the video-call background
# ---------------------------------------------------------------------------


def _identity(**overrides: str) -> Identity:
    """This instance's identity with one or two fields replaced, so a rule
    can be exercised against a declaration this repository does not have."""
    declared = load_identity(ROOT)
    return replace(declared, **overrides)


def test_the_background_code_points_at_the_declared_forum() -> None:
    """The first branch, and the only one a loaded declaration reaches --
    see `forum_code_target`'s own docstring for why the second is written
    anyway."""
    identity = _identity(forum="https://forum.example.org")
    address = Published(url="https://example-instance.github.io/example-showcase/")
    assert forum_code_target(identity, address) == "https://forum.example.org"


def test_the_background_code_falls_back_to_the_published_showcase() -> None:
    """The second branch. A code is not prose: a poster printing `REPLACE`
    says something obviously unfinished, while a code encoding it is
    scanned, resolves to nothing, and says nothing at all -- so the rule
    degrades to the one address an instance cannot be without."""
    identity = _identity(forum=f"https://{PLACEHOLDER_MARKER}")
    address = Published(url="https://example-instance.github.io/example-showcase/")
    assert forum_code_target(identity, address) == address.url


def test_the_declaration_cannot_reach_that_second_branch_today() -> None:
    """What makes the branch above unreachable, pinned where it is decided
    rather than left for a reader to work out.

    `forum` is required and is not degradable, so `identity_from_data`
    refuses a placeholder there before any renderer sees the declaration.
    This is not an argument for deleting the fallback -- it is the line
    that would have to change first, named so that whoever changes it
    finds the code that already answers for it.
    """
    assert "forum" in IDENTITY_FIELDS
    assert "forum" not in DEGRADABLE_FIELDS

    declaration = json.loads((ROOT / INSTANCE_PATH).read_text(encoding="utf-8"))
    declaration["identity"] = {
        **declaration["identity"],
        "forum": f"https://{PLACEHOLDER_MARKER}",
    }
    with pytest.raises(ValueError, match="forum"):
        identity_from_data(declaration)


def test_the_background_code_decodes_to_the_forum_this_instance_declares() -> None:
    """Decoded, not merely produced -- the same standard every other code
    in this module is held to."""
    svg = forum_code_svg(dark="#000000", root=ROOT)
    assert decode_registration_qr(svg) == load_identity(ROOT).forum


def test_the_background_code_encodes_no_edition_at_all() -> None:
    """What the hand-drawn background it replaces got wrong. Its code
    pointed at one forum thread for one 2024 edition, so a background
    reused at every session since sent every scanner to a talk that had
    already happened -- and nothing could see it, because nothing in this
    repository reads an image. The series' code carries the series and
    nothing an edition changes.
    """
    decoded = decode_registration_qr(forum_code_svg(dark="#000000", root=ROOT))
    assert decoded == load_identity(ROOT).forum
    assert signup_url("mrg-1", root=ROOT) not in decoded
    assert not re.search(r"/t/|/events/", decoded)


def test_forum_code_svg_signature_has_no_url_or_link_parameter() -> None:
    """The same structural guard `registration_code_svg` carries, on the
    second encoder: an address is derived from a declaration here, never
    handed in."""
    import inspect

    parameters = inspect.signature(forum_code_svg).parameters
    assert set(parameters) == {"dark", "root"}
    assert not any(
        word in name.lower()
        for name in parameters
        for word in ("url", "link", "href", "base", "address")
    )
