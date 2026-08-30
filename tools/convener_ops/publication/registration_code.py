"""The codes a scanner reads off this project's own printed work.

Encodes exactly one thing -- `registration.signup_url(event_id)`, the
event's own public page address (D-19) -- and nothing else.
`registration_code_svg` takes an `event_id`, never a URL: there is no
parameter through which a room link, or any other string, could reach the
encoder. That is not an incidental property of this module; it is the
whole reason it exists. This project published a field that used to be
called `registration_link` and actually carried a Zoom room address
(`public_data.py`'s own module docstring has the history); it was removed
from the public feed for exactly that reason, and a workflow guard
(`.github/workflows/preview.yml`) sweeps the built site for it. A poster is
a worse place for that mistake than a web page: it gets printed and pinned
to a wall, and a room link on a wall cannot be withdrawn. Encoding only an
`event_id` -- never accepting a URL, a link, or a whole event/speaker
record this function could reach into -- is what makes that mistake
impossible to repeat here by construction, not merely by convention.
`tools/tests/publication/test_registration_code.py::
test_a_room_link_never_reaches_the_encoded_code` proves it against the
real fixture that already carries one (`site/src/_data/events.json`'s
own `MRG-05` entry).

Two codes, one rule
--------------------
`forum_code_svg` is the second: the code on the video-call background
(`brand_templates.py`), which belongs to the series rather than to any one
edition and points at where the series is discussed. It takes no address
either. Both functions derive their own target from a declaration, and
neither has a parameter an address could arrive through -- that is the
rule this module is, and a second encoder written somewhere else would be
a second place to break it.

The encoder: `segno`, already a dependency, not a new one
----------------------------------------------------------
Writing a QR encoder from scratch would be legitimate work, but it is
also unnecessary here, because `segno` is not a new dependency:
`tools/pyproject.toml` already carries it, checked
against this project's own zero-cost constraints when `delivery.py` first
added it for the certificate's own QR: pure Python, one
universal wheel (`py3-none-any`, checked against the built artefact, not
only the classifier), no required dependency for this project's Python
floor, BSD-3-Clause (the licence file, not only the PyPI classifier), and
SVG output through `svg_inline()` -- no Pillow, no raster step anywhere in
the call path. Writing a second, hand-rolled encoder next to an
already-vetted one would not be caution; it would be exactly the kind of
duplicated logic this project avoids elsewhere for the same reason
(`registration.normalize_email`'s own docstring: "a second, hand-written
definition ... here would risk disagreeing with this one"). What *is*
written from scratch here is the *decoder* that proves the encoder's output
is correct -- `tools/tests/qr_decode.py` -- because nothing in this
project's dependency tree, and no service this project is willing to call
over the network, reads a QR code back. See that module's own docstring.

Why `border` is pinned here rather than left to segno's own default
-----------------------------------------------------------------------
`QR_BORDER` is segno's own current default quiet zone (4 modules) for a
non-Micro QR code, but written down explicitly and imported by
`qr_decode.py` rather than assumed independently in both places: that
decoder turns rendered SVG pixel coordinates back into matrix row/column
indices by subtracting exactly this many modules from each edge, so a
future segno upgrade that changed its own default without this project
noticing would silently break decoding, not merely change the poster's
own whitespace.

Why `omitsize=True`
------------------------
No `width`/`height` attribute on the rendered `<svg>`, only a `viewBox` --
so the code fills whatever box `visual.py`'s own CSS gives it (the
`.registration-code-slot` it is embedded into), the same "the page's CSS
controls layout, not a fixed intrinsic size" discipline every other
element on that page already follows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import segno

from ..declaration import published
from ..journey.registration import signup_url

__all__ = [
    "QR_BORDER",
    "forum_code_svg",
    "forum_code_target",
    "registration_code_modules",
    "registration_code_svg",
]

#: Roughly 15% error correction -- the same choice `delivery.py` makes for
#: the certificate's own QR code, for the same reason: comfortable
#: headroom over a printed poster's realistic wear (a crease, a staple, a
#: light smudge) without inflating the symbol for data this short (a
#: signup URL, never more than a domain plus a short edition id).
_QR_ERROR_LEVEL: Final = "m"

#: Segno's own default quiet zone for a non-Micro QR code, pinned
#: explicitly -- see the module docstring's "Why `border` is pinned"
#: section. `qr_decode.py` imports this constant rather than assuming its
#: own copy of the number.
QR_BORDER: Final = 4


def registration_code_svg(event_id: str, *, dark: str, root: Path | None = None) -> str:
    """The registration QR code for `event_id`, as an embeddable
    `<svg>...</svg>` fragment -- encodes `registration.signup_url(event_id)`
    and nothing else (see the module docstring for why this function's own
    signature, taking an id rather than a URL, makes a room link
    structurally unreachable here, not merely absent by convention).

    `dark` is the single colour the code is drawn in, threaded in by the
    caller (`visual.py`, from `instance/data/brand.json`'s own "black") rather than
    read from the file here -- the same separation `ribbon.py`'s own
    rendering functions keep from `_load_motif` (a caller fetches a brand
    value once and threads it through a pure function, rather than every
    renderer reading the file for itself). Light modules are left
    undrawn (segno's own default): the code is embedded into a white
    `.registration-code-slot` box, so there is nothing a second colour
    would add here that the slot's own background does not already give
    it, and one fewer colour is one fewer place for a value not sourced
    from `instance/data/brand.json` to appear.

    `root` is threaded straight through to `signup_url` and means what
    it means there: which instance's declaration the encoded address is
    built from. The signature still takes an id and never a URL, which
    is the property this module's own docstring rests on -- a root is
    not an address, and no caller can smuggle a room link through one.
    """
    url = signup_url(event_id, root=root)
    qr = segno.make(url, error=_QR_ERROR_LEVEL)
    return qr.svg_inline(
        border=QR_BORDER,
        dark=dark,
        omitsize=True,
        svgclass="registration-qr",
        lineclass="registration-qr__line",
        title=url,
    )


def registration_code_modules(event_id: str, *, root: Path | None = None) -> int:
    """The registration QR's own width, in modules, quiet zone included --
    the one number the print derivation needs to work out the code's
    physical size once printed (`formats.qr_module_size_mm`), and the one
    this function computes the same way `registration_code_svg` itself
    does (same URL, same error level, same `QR_BORDER`) rather than a
    second, independent guess at segno's own version choice: a real event
    id makes a short URL (version 4, 33 data modules) today, but nothing
    stops a longer one bumping the version and, with it, the module count
    a fixed physical slot has to divide the paper's own size by -- see that
    function's own docstring for why this matters at print resolution and
    not on a screen.

    `root` means what it means in `registration_code_svg` above, and is
    here for the same reason the two share an error level and a border:
    they have to measure the same symbol. A root passed to one and not
    the other would put the two back in a position to disagree.
    """
    url = signup_url(event_id, root=root)
    qr = segno.make(url, error=_QR_ERROR_LEVEL)
    modules_across, _ = qr.symbol_size(border=QR_BORDER)
    return int(modules_across)


# --------------------------------------------------------------------------
# The series' own code: the one on the video-call background
# --------------------------------------------------------------------------


def forum_code_target(
    identity: published.Identity, address: published.Published
) -> str:
    """Where the video-call background's code sends a person.

    `identity.forum` -- the address the series discusses at, which every
    poster this project draws already prints in words -- and the published
    showcase when that declaration still carries a placeholder in place of
    an address. The fallback is chosen for degrading to something that
    cannot be absent: an instance with no published address is an instance
    with no site, no event pages and no registration, which is not an
    instance at all.

    **The second branch is not reachable through
    `published.load_identity` today, and that is worth saying rather than
    leaving a reader to discover.** `forum` is in `IDENTITY_FIELDS` and
    not in `DEGRADABLE_FIELDS`, so a declaration carrying a placeholder
    there is refused outright before any renderer sees it -- the rule
    above only ever takes its first branch from a loaded declaration. It
    is written anyway because this is a *code*, not a line of prose: a
    poster that prints `REPLACE` says something obviously unfinished to
    whoever reads it, while a code that encodes it is scanned, resolves to
    nothing, and says nothing to anybody. If `forum` ever earns a place
    beside `proposal_form` in `DEGRADABLE_FIELDS` -- a duplicate running
    webinars with no discussion forum is an ordinary thing to be -- this
    is the one place that already answers for it.

    Not a `Identity` property beside `proposal_form_url`, and not a
    reader of its own: it needs both declarations at once, and
    `Identity` deliberately knows nothing about the published address.
    """
    if published.is_placeholder(identity.forum):
        return address.url
    return identity.forum


def forum_code_svg(*, dark: str, root: Path | None = None) -> str:
    """The video-call background's QR code, as an embeddable `<svg>`.

    Takes no address, exactly as `registration_code_svg` takes no URL, and
    for the same reason: what a code on a shared surface points at is a
    decision this module makes from the declarations, never one a caller
    can pass in. `root` says which repository's declarations, and a root
    is not an address.

    `title` puts the encoded string into the document as text. That is
    what makes the target of a printed code *readable* -- by a person
    opening the file, and by `convener_ops.derivation.derivation_guard`, which sweeps
    every blob for this instance's declared values and can read an SVG
    where it could never read the modules of a rendered code.
    """
    url = forum_code_target(published.load_identity(root), published.load(root))
    qr = segno.make(url, error=_QR_ERROR_LEVEL)
    return qr.svg_inline(
        border=QR_BORDER,
        dark=dark,
        omitsize=True,
        svgclass="forum-qr",
        lineclass="forum-qr__line",
        title=url,
    )
