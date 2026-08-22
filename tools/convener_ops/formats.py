"""The three real derivations of one template (task 4).

`visual.render_announcement` stays a single function, taking a plain
`width`/`height` in pixels and knowing nothing about "the square" or "the
print poster" as concepts of its own -- see that module's own docstring for
why one composition, read against its own two numbers, is the whole point.
This module is only where the three concrete choices F-03's seven channels
actually collapse into are written down once, each under a name, so a
future caller (task 5's pinned render, a future publishing command) reads
`formats.BANNER` instead of a bare `1200, 630` repeated at every call site
that needs it.

The three names
----------------
- `SQUARE` (1200x1200) -- the forum, the social pages, the institutes' own
  newsletters and internal messaging. What tasks 1-3 already built and this
  project has reviewed.
- `BANNER` (1200x630) -- the share preview: 1200x630 is the size several
  major platforms already expect for a link-preview image (a wide,
  roughly-1.91:1 crop), and it is also what becomes the `og:image` phase 5
  deliberately left absent (that phase's own task 10, and its acceptance
  criterion 6). Wiring the actual `<meta property="og:image">` tag is not
  this module's job, or this task's -- see `visual.py`'s own docstring for
  why: phase 5 left the tag out rather than pointing it at a file that did
  not exist yet, and one still does not exist until task 5's pinned render
  and task 6's publishing trigger produce one at a stable, real address.
  This module only makes sure the *composition* that will fill that file is
  a correct, tested derivation, ready for whichever later task wires it in.
- `PRINT` -- F-03's seventh channel: a poster actually printed and pinned up
  in an institute, not a hypothetical. See `_a4_dimensions_px`'s own
  docstring for the size and resolution this settles on, and why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .registration_code import registration_code_modules
from .visual import REGISTRATION_SLOT_PADDING_VMIN, REGISTRATION_SLOT_VMIN

__all__ = [
    "BANNER",
    "FORMATS",
    "PRINT",
    "PRINT_PAPER_MM",
    "SCANNABLE_QR_MODULE_MM",
    "SQUARE",
    "Format",
    "qr_module_size_mm",
]


@dataclass(frozen=True)
class Format:
    """One named canvas size. `dpi` and `paper_mm` are set only for a
    format that is actually printed on paper -- `SQUARE` and `BANNER` are
    screen formats, where a pixel is not a physical measurement and asking
    "how many millimetres wide is this" has no answer worth computing."""

    name: str
    width: float
    height: float
    dpi: float | None = None
    paper_mm: tuple[float, float] | None = None


SQUARE: Final = Format(name="square", width=1200.0, height=1200.0)

#: The share preview. 1200x630 -- a roughly 1.91:1 crop -- is the size
#: several major link-preview consumers already expect for an `og:image`;
#: matching it is what keeps a shared link's own preview un-cropped rather
#: than centre-cropped to whatever *this* project happened to pick. See the
#: module docstring for why this is also, eventually, phase 5's own missing
#: `og:image`.
BANNER: Final = Format(name="banner", width=1200.0, height=630.0)

#: A4 portrait (210mm x 297mm), the paper size a standard office printer
#: already handles without special equipment -- the same "no dependency on
#: a collaborator's own equipment" reasoning this project's global
#: constraints already apply to accounts and services extends naturally to
#: paper size: A3 reads as more of a "real poster" at a glance, but not
#: every institute's own printer takes A3 stock, and every one of them
#: takes A4. F-03 names this channel "affiches imprimées et posées dans les
#: instituts" -- printed and pinned up -- not "professionally printed",
#: and this project has already turned down machinery nobody would actually
#: run (the revalidation's own reasoning for not building a container image
#: nobody would ever exercise applies here too, one level down).
PRINT_PAPER_MM: Final = (210.0, 297.0)

#: 300 dpi, not 150. `_A4_150DPI_PX` below is what 150 dpi would give:
#: 1240x1754, half the linear resolution -- the task brief's own "thin for
#: print" example, and correctly so: a 150dpi print holds up passably at
#: arm's length but a printed line at that resolution visibly softens up
#: close, exactly the distance someone reads an institute noticeboard from.
#: 300 dpi costs real, measurable things in return, both reported (not
#: assumed) once this task actually rendered the print state: roughly 4x
#: the pixels (2480x3508 against 1240x1754) means roughly 4x the PNG bytes
#: and a render several times slower -- acceptable for a file generated
#: once per edition by a CI job with no visitor waiting on it, the same
#: trade this project already made for the certificate's own QR resolution
#: (`delivery.py`). A visitor's own render (`SQUARE`, `BANNER`) never pays
#: this cost; only the one format meant to leave the screen at all does.
_PRINT_DPI: Final = 300.0


def _mm_to_px(mm: float, dpi: float) -> int:
    """A physical length, in millimetres, as a whole pixel count at `dpi`."""
    return round(mm / 25.4 * dpi)


PRINT: Final = Format(
    name="print",
    width=_mm_to_px(PRINT_PAPER_MM[0], _PRINT_DPI),
    height=_mm_to_px(PRINT_PAPER_MM[1], _PRINT_DPI),
    dpi=_PRINT_DPI,
    paper_mm=PRINT_PAPER_MM,
)

FORMATS: Final = (SQUARE, BANNER, PRINT)

#: The task brief's own stated reliability floor: a QR module below roughly
#: this size is unreliable under an ordinary phone camera. Not this
#: project's own measurement -- a physical constraint of the scanning
#: hardware, stated as given -- but the one number `qr_module_size_mm`'s
#: own result has to clear for `PRINT` to be a real, usable channel rather
#: than a poster nobody can actually register from.
SCANNABLE_QR_MODULE_MM: Final = 0.4


def qr_module_size_mm(fmt: Format, event_id: str) -> float:
    """The physical size of one QR module, in millimetres, when `fmt` is
    printed at its own real paper size.

    Deliberately independent of `fmt.dpi`: a module's physical footprint is
    governed by the *paper's* own size and the fraction of its shorter side
    `visual.py`'s own `.registration-code-slot` reserves for the code
    (`REGISTRATION_SLOT_VMIN`, less two lots of
    `REGISTRATION_SLOT_PADDING_VMIN` for the slot's own inner padding on
    each side, both imported from there rather than re-typed here -- see
    that module's own docstring for why), divided across however many
    modules `registration_code_modules` says the real, rendered code for
    this `event_id` actually needs. Doubling the resolution (150dpi to
    300dpi) doubles the pixels each module occupies and so its own
    on-screen crispness, but not the millimetres it occupies on paper --
    which is the only thing a phone camera's own optics ever has to
    resolve. Raises if `fmt` carries no `paper_mm` (a screen format: the
    question "how many millimetres" has no answer for one).
    """
    if fmt.paper_mm is None:
        raise ValueError(f"{fmt.name!r} has no physical paper size to measure")
    modules = registration_code_modules(event_id)
    short_side_mm = min(fmt.paper_mm)
    slot_inner_vmin = REGISTRATION_SLOT_VMIN - 2 * REGISTRATION_SLOT_PADDING_VMIN
    slot_fraction = slot_inner_vmin / 100.0
    return slot_fraction * short_side_mm / modules
