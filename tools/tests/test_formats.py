"""The three named formats, and the print poster's own physical QR size.

`formats.py` names the three concrete sizes task 4 settles on, and computes
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


def test_the_print_qr_module_clears_the_scannable_threshold_for_a_real_id() -> None:
    mm = qr_module_size_mm(PRINT, "mrg-9")
    assert mm == pytest.approx(0.589, abs=0.001)
    assert mm >= SCANNABLE_QR_MODULE_MM


def test_the_print_qr_module_still_clears_the_threshold_for_a_longer_id() -> None:
    """A longer id can bump segno's own version choice (more modules,
    dividing the same physical slot further) -- checked here against an
    id long enough to actually do that (`registration_code_modules` goes
    from 41 to 45 across this boundary), not merely a realistic one, so
    this is the id that stresses the property rather than restating the
    typical case above."""
    long_id = "mrg-999999999"
    assert registration_code_modules(long_id) > registration_code_modules("mrg-9")
    mm = qr_module_size_mm(PRINT, long_id)
    assert mm >= SCANNABLE_QR_MODULE_MM


def test_qr_module_size_mm_raises_for_a_screen_format() -> None:
    """`SQUARE` and `BANNER` have no physical paper size -- a screen pixel
    is not a millimetre, and asking "how wide is this in real life" has no
    answer for either."""
    with pytest.raises(ValueError, match="physical paper size"):
        qr_module_size_mm(SQUARE, "mrg-9")
    with pytest.raises(ValueError, match="physical paper size"):
        qr_module_size_mm(BANNER, "mrg-9")
