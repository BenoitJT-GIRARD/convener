"""The registration code -- proving it decodes, and proving a room link can
never reach it.

"A code nobody has decoded is a rectangle of noise" (this task's own
brief): every test below that touches an actual QR code decodes it with
`qr_decode.decode_registration_qr` -- an independent decoder, written for
this suite alone (see that module's own docstring) -- and compares the
recovered string against `registration.signup_url`, never merely checking
that some SVG markup was produced.
"""

from __future__ import annotations

import json
import re
from datetime import date

from qr_decode import decode_registration_qr

from convener_ops.paths import repo_root
from convener_ops.registration import signup_url
from convener_ops.registration_code import registration_code_svg
from convener_ops.visual import Announcement, render_announcement

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
    actually *called* with `data/brand.json`'s own black)."""
    svg = registration_code_svg("mrg-4", dark="#123456")
    assert 'stroke="#123456"' in svg


def test_the_registration_code_is_drawn_in_brand_black() -> None:
    """`render_announcement` threads `data/brand.json`'s own "black" into
    the code -- not a hand-typed literal that happens to match today (the
    guard `test_visual.py::
    test_no_brand_colour_hand_typed_outside_root_or_ribbon_stroke` already
    runs against this page; segno renders a doubled hex triple such as
    "#000000" in its own shortened three-digit form, so that guard's
    literal substring search would not have caught a hand-typed value here
    either -- this test checks the actual, expanded colour instead)."""
    brand = json.loads((ROOT / "data" / "brand.json").read_text(encoding="utf-8"))
    black = brand["colour"]["black"].lower()

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
    and extracts only `event_id = entry["id"].lower()` (R-5) to construct
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
    # rather than two (phase 12, task 1). Nothing about it lets a caller
    # choose the address itself, which is the property this test exists
    # for, so the shape rule below is what carries the guard now and the
    # set above is only what makes a reviewer look.
    assert not any(
        word in name.lower()
        for name in parameters
        for word in ("url", "link", "href", "base", "address")
    )
