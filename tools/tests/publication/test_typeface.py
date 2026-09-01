"""How wide a line is reckoned to be, before a glyph is drawn.

The measurement itself is not this module's to make -- the tables are read
off the committed font file in the pinned engine, and
`tools/visuals/check-templates.mjs` re-measures every entry on every run.
What is held here is everything about them that can be true or false
without a browser: that the tables describe the same character set, that a
weight between the two measured ones is never charged less than either,
that an accented letter is charged as the letter it is built on, and that
the estimate is an over-estimate rather than an under-estimate wherever the
two can be told apart.
"""

from __future__ import annotations

import pytest

from convener_ops.publication import typeface


def test_both_tables_describe_the_same_characters() -> None:
    """One table naming a character the other does not would make a line's
    width depend on which weight it happens to be set in, in a way that is
    a gap in the measurement rather than a property of the face."""
    light = {
        character for _em, characters in typeface._LIGHT_EM for character in characters
    }
    heavy = {
        character for _em, characters in typeface._HEAVY_EM for character in characters
    }
    assert light == heavy


def test_every_printable_ascii_character_is_measured() -> None:
    """The set is not "the characters this instance happens to use": a
    declaration is a duplicate's own words, and a character nobody measured
    would be charged the widest advance in the table and shrink a line that
    did not need shrinking."""
    printable = {chr(code) for code in range(32, 127)}
    measured = {
        character for _em, characters in typeface._HEAVY_EM for character in characters
    }
    assert measured == printable


def test_no_character_is_named_twice_in_one_table() -> None:
    """Two entries for one character would make the table's meaning depend
    on the order it is read in."""
    for table in (typeface._LIGHT_EM, typeface._HEAVY_EM):
        seen = "".join(characters for _em, characters in table)
        assert len(seen) == len(set(seen))


def test_a_weight_between_the_two_is_never_charged_less_than_either() -> None:
    """The reason `advance_em` takes a maximum rather than the heavier
    table: a space is *wider* at 400 than at 900 in this face, so charging
    every in-between weight the heavy table alone would undercharge every
    space on the page."""
    for code in range(32, 127):
        character = chr(code)
        light = typeface.advance_em(character, weight=typeface.LIGHT)
        heavy = typeface.advance_em(character, weight=typeface.HEAVY)
        middle = typeface.advance_em(character, weight=700)
        assert middle >= light
        assert middle >= heavy


def test_the_space_is_the_character_that_makes_that_rule_necessary() -> None:
    """Named rather than left implicit: if this ever stops being true the
    rule above becomes a control that cannot fail, and somebody should be
    told why it is still there."""
    assert typeface.advance_em(" ", weight=typeface.LIGHT) > typeface.advance_em(
        " ", weight=typeface.HEAVY
    )


def test_an_accented_letter_is_charged_as_the_letter_it_is_built_on() -> None:
    """Exact for this face -- an acute over a capital A does not make the A
    wider -- and the alternative charges every accented name the widest
    advance in the table, which is how a duplicate writing French gets a
    poster set two sizes smaller than it needed."""
    for accented, base in (("É", "E"), ("è", "e"), ("Ç", "C")):
        assert typeface.advance_em(accented, weight=typeface.HEAVY) == (
            typeface.advance_em(base, weight=typeface.HEAVY)
        )


def test_a_character_no_table_names_is_charged_the_widest_one_they_do() -> None:
    """A glyph outside the measurement is never charged less than a
    measured one: the direction that sets a line smaller than it had to be
    rather than one that puts it through the drawing."""
    assert typeface.advance_em("中", weight=typeface.HEAVY) == (
        typeface.WIDEST_ADVANCE_EM
    )


def test_width_scales_with_the_size_it_is_given() -> None:
    line = "READING ROOM"
    assert typeface.width(line, size=100.0, weight=900) == pytest.approx(
        10 * typeface.width(line, size=10.0, weight=900)
    )


def test_letter_spacing_is_charged_once_per_character() -> None:
    """Including after the last one, which is what SVG's own
    `letter-spacing` does."""
    line = "ABC"
    bare = typeface.width(line, size=50.0, weight=900)
    spaced = typeface.width(line, size=50.0, weight=900, letter_spacing=3.0)
    assert spaced - bare == pytest.approx(9.0)


def test_an_empty_line_measures_nothing() -> None:
    assert typeface.width("", size=50.0, weight=900) == 0.0


def test_a_size_that_is_not_a_length_is_refused() -> None:
    with pytest.raises(ValueError, match="positive length"):
        typeface.width("A", size=0.0, weight=900)


def test_the_lines_these_templates_actually_set_are_over_estimated() -> None:
    """The estimate has to sit above what the engine measured, or a block
    placed against it runs into the drawing. These four are the widths
    `tools/visuals/check-templates.mjs` reported for the lines that
    decide a size on each of the two pages, in the face the charter names.

    They are here rather than only in the browser because a browser is not
    always in the room: this is the arithmetic half of the same claim, and
    it fails on a table edited without re-measuring even when nobody runs
    the pinned engine.

    **Every line here is the example instance's**, and that is a
    requirement rather than a preference. Two of them were the identity of
    whichever instance runs this repository, and a fixture of that shape
    cannot survive the derivation: `convener-derive` rewrites a declared
    value wherever it appears, and a substitution converts a *string* and
    not the width somebody measured beside it -- the same argument
    `repository.regenerate` makes for a stylesheet's contrast figures. The
    derived repository either shipped this instance's name in a public
    product test or failed this assertion, depending only on whether the
    rewrite table had heard of the spelling. Neither is a state to leave a
    fixture in. `instances/example/` is the product's, so its lines are
    rewritten by nothing and measure the same on both sides.

    The first two are the same line at the two sizes the two pages set it
    at, which is what "the line that decides a size on each page" means
    here: both pages head with the series' name.
    """
    for line, size, weight, spacing, measured in (
        ("MONTHLY READING GROUP", 50.0, 900, 1.0, 768.4),
        ("MONTHLY READING GROUP", 86.0, 900, 2.0, 1327.4),
        ("Join the discussion before and after the talk at", 31.0, 400, 0.0, 623.0),
        ("THE EXAMPLE COLLECTIVE", 105.56, 900, 0.0, 1584.9),
    ):
        estimated = typeface.width(
            line, size=size, weight=weight, letter_spacing=spacing
        )
        assert estimated >= measured, f"{line!r} is estimated narrower than it sets"
        assert estimated <= measured * 1.1, (
            f"{line!r} is estimated more than a tenth wider than it sets, which "
            "costs a page size for nothing"
        )
