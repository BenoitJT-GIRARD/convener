"""The three named formats, and the print poster's own physical QR size.

`formats.py` names the three concrete sizes this project settles on, and computes
the one number that turns "the print poster" from a hopeful label into a
checked property: how many millimetres wide one QR module actually is once
`PRINT` is printed at its own real paper size -- the number a phone camera's
own optics have to resolve, not a screen concern at all (see that module's
own docstring for the reasoning, and `visual.py`'s for why the CSS slot's
own size lives there and is threaded in rather than retyped).
"""

from __future__ import annotations

import pytest

from convener_ops.formats import (
    BANNER,
    FORMATS,
    PRINT,
    PRINT_PAPER_MM,
    SCANNABLE_QR_MODULE_MM,
    SQUARE,
    qr_module_size_mm,
)
from convener_ops.registration_code import registration_code_modules
from convener_ops.visual import is_wide


def test_formats_tuple_names_exactly_the_square_banner_and_print() -> None:
    assert FORMATS == (SQUARE, BANNER, PRINT)
    assert {fmt.name for fmt in FORMATS} == {"square", "banner", "print"}


def test_square_and_banner_are_the_seven_channels_own_first_two_shapes() -> None:
    assert (SQUARE.width, SQUARE.height) == (1200.0, 1200.0)
    assert (BANNER.width, BANNER.height) == (1200.0, 630.0)
    assert SQUARE.dpi is None
    assert BANNER.dpi is None
    assert SQUARE.paper_mm is None
    assert BANNER.paper_mm is None


def test_print_is_a4_portrait_at_300dpi_in_real_pixels() -> None:
    """The deliberate choice this task's own brief asks to state and
    justify: A4 (210mm x 297mm -- every office printer's own default, not
    just a wide-format one), at 300dpi. `_mm_to_px` turns that into the
    same whole-pixel figures the print industry already uses for "A4 at
    300dpi" (2480x3508) -- not an approximation this test invents
    independently, a property of the millimetre-to-pixel arithmetic
    itself."""
    assert PRINT.paper_mm == PRINT_PAPER_MM == (210.0, 297.0)
    assert PRINT.dpi == 300.0
    assert (PRINT.width, PRINT.height) == (2480, 3508)


def test_print_is_the_only_named_format_that_is_wide() -> None:
    # PRINT itself is not wide (a tall portrait poster) -- restated here,
    # against the actual named constant rather than a hand-typed pair of
    # numbers, alongside the other two, so the three stay mutually
    # exclusive: exactly one format (the banner) is ever wide.
    assert [is_wide(fmt.width, fmt.height) for fmt in FORMATS] == [
        False,
        True,
        False,
    ]


# ---------------------------------------------------------------------------
# The print QR's own physical module size -- the number that makes "a
# poster actually pinned to a wall" a checked property rather than a hope.
# ---------------------------------------------------------------------------


#: The slot the printed code actually occupies on A4, in millimetres --
#: `visual.py`'s own `.registration-code-slot` fraction of the paper's
#: shorter side, less its inner padding. Pinned as a number because that is
#: the regression this section is really guarding: a change to the slot's
#: own size, or to the paper, moves every figure below at once.
#:
#: The module size itself used to be pinned here instead
#: (0.589mm), and it was a statement about *this* instance's published
#: address rather than about the poster. `registration_code_modules` encodes
#: `registration.signup_url(event_id)`, so the module count -- and with it
#: every millimetre figure -- moves with the length of the address the
#: instance publishes at. A duplicate with a longer one failed this test for
#: a reason it could not fix, while the property the test exists for (the
#: printed code stays scannable) still held. The slot's width does not move;
#: what the address can move is how finely it is divided.
PRINT_QR_SLOT_MM = 24.15


def test_the_print_qr_slot_is_the_same_width_whatever_address_it_carries() -> None:
    """The geometry, held on its own: however many modules the encoded
    address needs, they divide this one physical width."""
    for event_id in ("mrg-9", "mrg-999999999"):
        modules = registration_code_modules(event_id)
        actual = qr_module_size_mm(PRINT, event_id) * modules
        assert actual == pytest.approx(PRINT_QR_SLOT_MM, abs=0.01)


def test_the_print_qr_module_clears_the_scannable_threshold_for_a_real_id() -> None:
    """The property, which is what "a poster actually pinned to a wall"
    means: one module is wide enough for a phone camera to resolve."""
    assert qr_module_size_mm(PRINT, "mrg-9") >= SCANNABLE_QR_MODULE_MM


def test_the_print_qr_module_still_clears_the_threshold_for_a_longer_id() -> None:
    """A longer id can bump segno's own version choice (more modules,
    dividing the same physical slot further), and the id that does it is
    *found* rather than typed: where that boundary falls depends on how
    long the published address already is, which is the instance's own
    business. Searching for the first id that actually crosses it keeps
    this a test of the property under stress rather than a restatement of
    one organisation's address length."""
    baseline = registration_code_modules("mrg-9")
    longer = next(
        (
            candidate
            for candidate in ("mrg-" + "9" * n for n in range(1, 80))
            if registration_code_modules(candidate) > baseline
        ),
        None,
    )
    assert longer is not None, (
        "no event id under 80 characters needs a larger QR version than "
        "'mrg-9' -- this test would otherwise pass without ever crossing the "
        "boundary it exists to cross"
    )
    assert qr_module_size_mm(PRINT, longer) >= SCANNABLE_QR_MODULE_MM


def test_qr_module_size_mm_raises_for_a_screen_format() -> None:
    """`SQUARE` and `BANNER` have no physical paper size -- a screen pixel
    is not a millimetre, and asking "how wide is this in real life" has no
    answer for either."""
    with pytest.raises(ValueError, match="physical paper size"):
        qr_module_size_mm(SQUARE, "mrg-9")
    with pytest.raises(ValueError, match="physical paper size"):
        qr_module_size_mm(BANNER, "mrg-9")
