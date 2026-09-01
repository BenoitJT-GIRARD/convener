"""Every pairing of type on a ground the cockpit's own chrome sets, read
off its source and measured against every charter this product ships.

Why this is not the accessibility check
----------------------------------------
`site/scripts/check-a11y.mjs` renders the showcase in a real browser and
runs axe over it, which resolves an inherited ground exactly the way a
browser does -- a stronger measurement than anything static. What it
cannot do is reach the cockpit, and that is where the sign-in screen fell
through:

- **It sweeps pages, and the cockpit is not one of them.** That file's own
  `discoverHtmlPages` skips `app/` by name: the operators' cockpit is
  behind a GitHub sign-in and is not a page the public lands on. What it
  does reach of this bundle is the three islands, and the islands are
  drawn by the showcase's own stylesheet rather than by these tokens. So
  no run of that checker has ever measured a cockpit token pairing.
- **It renders one charter -- the one in force.** A duplicate that chose
  `assets/brand/steps/brand.json` builds a cockpit this repository's own gates
  never draw. A pairing that clears AA here and fails there is invisible
  to any check that renders, and `assets/brand/` holds four charters a duplicate
  may choose beside whatever this instance wrote for itself.

The two are complementary and neither replaces the other: axe measures
the real pixels of the pages a visitor reaches, and this measures the
cockpit's own vocabulary against every palette it could ever be drawn in.

What it reads
--------------
The class lists in `app/src`, as string literals. A cockpit component
names its colours in Tailwind utilities (`bg-dominant text-white`), and
`app/tailwind.config.ts` turns each colour key into a custom property this
module knows the charter colour of (`TOKEN_COLOURS`). So the pairings are
*derived from the source* rather than declared in a table beside it: a
button added tomorrow is measured on the commit that adds it, with no
entry to make anywhere -- the same property `brand.shipped` gives the
palettes and `motifs.FAMILIES` gives the drawings.

How a ground is resolved, and what that cannot see
----------------------------------------------------
Within one class list: a foreground utility is measured against the
ground utility in the same list, and against `--paper` -- the ground
`tokens.css` gives `body` -- when that list names none. Variants are
resolved before pairing, so `text-dominant ... hover:bg-dominant
hover:text-white` is measured twice, once at rest (the dominant on paper)
and once hovered (white on the dominant), rather than once as the
nonsense pairing the two words make side by side.

**What it cannot see is a foreground named on a descendant of the element
that set the ground.** That is a real limit, and it is asserted rather
than worked around: resolving it needs the JSX tree, and the tree is not
what this reads. `unresolved_foregrounds` refuses the shape that limit
would hide -- a light foreground in a class list naming no ground of its
own, whose real ground can only be on an ancestor -- so the discipline
"name the ground on the element that names the type" is enforced by the
same sweep rather than left to a habit. Every dark foreground is measured
against the page's ground, which is what every screen in this bundle is
actually drawn on.

`disabled:` is not measured. WCAG 2.1 exempts text that is part of an
inactive user-interface component from 1.4.3 by name, and every
`disabled:` class in this bundle is an `opacity-*` on a control that is
genuinely inert.

Dimming is the other half of the same limit
---------------------------------------------
An element's own `opacity-*` multiplies the contrast of everything it
paints, including type it inherited rather than named. `text-ink-muted`
at `opacity-60` is 2.84 against the page at this instance's charter and
2.85 to 2.98 at the four a duplicate may choose -- a live 1.4.3 failure
this sweep found on its first run, on the agenda's archived cards. So
where a class list names the type it dims, the dimming is composited into
the measurement; and where it dims type it did not name, the class list is
refused outright (`_dimmed_inherited_type`), because the contrast it
reduces belongs to an element this sweep cannot see. What replaces a dim
is a colour that says the same thing and measures: `--ink-faint` for type
that has receded, `--paper-soft` for a whole panel that has.

An unknown word is refused rather than skipped
------------------------------------------------
`text-` and `bg-` carry more than colours -- `text-sm`, `bg-transparent`
-- so a sweep that skipped whatever it did not recognise would also skip
`text-domiant`, and a typo that silently paints the browser's default
black is exactly what a control exists to catch. Every value is either a
colour this module can resolve or a word in `NOT_A_COLOUR`, and anything
else is reported (D-25: a control that cannot fail loudly is not a
control).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .brand import AA_NORMAL_TEXT, colours, contrast_ratio, hex_to_rgb

__all__ = [
    "APP_SRC",
    "BUILT_IN_COLOURS",
    "LITERAL_TOKENS",
    "NOT_A_COLOUR",
    "PAGE_GROUND",
    "SOURCE_SUFFIXES",
    "TOKEN_COLOURS",
    "Pairing",
    "composite",
    "contrast_problems",
    "measure",
    "pairings",
    "scan",
    "sources",
    "token_colours",
    "unresolved_foregrounds",
]

#: Where the cockpit's own source lives, relative to a repository root.
#: Never `app/` whole: `app/scripts/` is the build's own plumbing and
#: `app/tests/` names classes in assertions about markup rather than in
#: markup, and neither is chrome anybody sees.
APP_SRC: Final = Path("app") / "src"

#: The suffixes a class list can be written in. `.ts` as well as `.tsx`,
#: because `components/Button.tsx`'s variants and `screens/Agenda.tsx`'s
#: status colours are plain string tables rather than markup -- a sweep
#: that only read JSX attributes would have missed the one that carries
#: `text-paper` on a filled button.
SOURCE_SUFFIXES: Final = (".tsx", ".ts")

#: Every colour key `app/tailwind.config.ts` declares, and the charter
#: colour behind it. One home for the answer: `generate_brand_css.py`
#: renders `app/src/design/tokens.css`'s generated block from this same
#: table, so the custom property a component reads and the colour this
#: sweep measures it at cannot come to disagree.
#:
#: The names are the showcase's -- `--field` for the saturated ground,
#: `--dominant` for the ink the headlines and the motif are drawn in.
#: The cockpit called them `--primary` and `--accent`, which inverts what
#: either word means: a charter's field is a ground that may never carry
#: text and may never carry white text (every `contrast._forbidden` under
#: `assets/brand/` says so, in those words), while `primary` is the word an
#: author reaches for when filling a button. Twenty-five class lists in
#: fifteen files did one of the two things it invites: eighteen filled a
#: control or a masthead with the field and set white on it, and seven set
#: the field itself as type.
TOKEN_COLOURS: Final[dict[str, str]] = {
    "paper": "white",
    "paper-soft": "band",
    "surface": "white",
    "surface-mute": "field_tint",
    "ink": "ink",
    "ink-muted": "ink_muted",
    "ink-faint": "ink_faint",
    "field": "field",
    "field-text": "field_text",
    "field-tint": "field_tint",
    "dominant": "dominant",
    "dominant-hover": "dominant_hover",
    "dominant-tint": "dominant_tint",
    "border": "rule",
    "border-strong": "rule_strong",
}

#: The two tokens no charter carries -- a rejection colour and a soft
#: informational one, which none of the designer's originals ever had
#: reason to draw. `generate_brand_css.py` owns their values and hands
#: them in, rather than this module keeping a second copy of a constant
#: that already has a home.
LITERAL_TOKENS: Final = ("danger", "info")

#: Tailwind's own palette, which `app/tailwind.config.ts` extends rather
#: than replaces. `text-white` is this white and not `--paper`; the two
#: hold the same value in every charter this product ships, and a sweep
#: measuring the token would be measuring something the browser is not
#: painting.
BUILT_IN_COLOURS: Final[dict[str, str]] = {
    "white": "#ffffff",
    "black": "#000000",
}

#: The ground a foreground sits on when its own class list names none:
#: `tokens.css` gives `body` `background: var(--paper)`, and every screen
#: in this bundle is drawn on it.
PAGE_GROUND: Final = "paper"

#: What `text-` and `bg-` carry when they are not carrying a colour. Held
#: as a list rather than inferred, so that a value in neither this set nor
#: the tables above is a finding rather than a shrug.
NOT_A_COLOUR: Final = frozenset(
    {
        # text-: size, alignment, wrapping, overflow
        "xs",
        "sm",
        "base",
        "lg",
        "xl",
        "2xl",
        "3xl",
        "4xl",
        "5xl",
        "6xl",
        "7xl",
        "8xl",
        "9xl",
        "left",
        "center",
        "right",
        "justify",
        "start",
        "end",
        "wrap",
        "nowrap",
        "balance",
        "pretty",
        "ellipsis",
        "clip",
        # bg-: the keywords, and the attachment/position/repeat/size words
        "transparent",
        "current",
        "inherit",
        "none",
        "auto",
        "cover",
        "contain",
        "fixed",
        "local",
        "scroll",
        "bottom",
        "top",
        "repeat",
        "no-repeat",
        "repeat-x",
        "repeat-y",
        "origin-border",
        "origin-padding",
        "origin-content",
        "clip-border",
        "clip-padding",
        "clip-content",
        "clip-text",
        "blend-normal",
        "blend-multiply",
        "gradient-to-r",
        "gradient-to-l",
        "gradient-to-t",
        "gradient-to-b",
    }
)

#: One utility: an optional chain of variants, `text-` or `bg-`, a value,
#: and an optional `/NN` opacity. `text-[11px]` and every other arbitrary
#: value are not matched at all -- a bracketed value is a length or a
#: literal, never a token name.
_UTILITY: Final = re.compile(
    r"^(?P<variant>(?:[a-z0-9][a-z0-9:-]*:)?)(?P<utility>text|bg)-"
    r"(?P<value>[a-z][a-z0-9-]*)(?:/(?P<alpha>\d{1,3}))?$"
)

#: `opacity-NN`, with the same optional variant chain. An element's own
#: opacity composites what it painted -- ground and type together -- over
#: whatever is behind it, which moves both halves of a pairing toward the
#: page's own ground.
_OPACITY: Final = re.compile(
    r"^(?P<variant>(?:[a-z0-9][a-z0-9:-]*:)?)opacity-(?P<value>\d{1,3})$"
)

#: The variant that means "this control is inert". WCAG 2.1 exempts text
#: in an inactive user-interface component from 1.4.3 by name.
_INERT: Final = "disabled"


#: The foregrounds that can only be meant for a dark ground. One of these
#: in a class list naming no ground is the shape `unresolved_foregrounds`
#: refuses -- see this module's own header.
_LIGHT_FOREGROUNDS: Final = ("white", "paper", "surface")


@dataclass(frozen=True)
class Pairing:
    """One block of type on one ground, as the cockpit's source sets it."""

    path: str
    line: int
    variant: str
    foreground: str
    ground: str
    foreground_alpha: float
    ground_alpha: float
    opacity: float

    @property
    def named(self) -> str:
        """How the pairing is quoted back: the two utilities, as written."""
        state = f" ({self.variant.rstrip(':')})" if self.variant else ""
        return f"text-{self.foreground} on bg-{self.ground}{state}"


def token_colours(charter: dict[str, Any], *, danger: str, info: str) -> dict[str, str]:
    """Every cockpit token, at this charter, as a `#rrggbb` string.

    `danger` and `info` are handed in because no charter carries them:
    `generate_brand_css.py` is where those two live, and this module does
    not keep a second copy of a constant that already has a home.
    """
    named = colours(charter)
    resolved = {token: named[key] for token, key in TOKEN_COLOURS.items()}
    resolved["danger"] = danger
    resolved["info"] = info
    # Tailwind's own two, which the config extends rather than replaces:
    # `text-white` is painted from this white and not from `--paper`.
    resolved.update(BUILT_IN_COLOURS)
    return resolved


def composite(over: str, under: str, alpha: float) -> str:
    """`over` painted on `under` at `alpha`, as a `#rrggbb` string.

    Plain source-over compositing in sRGB, which is what a browser does
    with a `/NN` opacity: `bg-field/10` is not a colour any charter holds,
    and it is a colour somebody reads type on.
    """
    if alpha >= 1:
        return over
    top, bottom = hex_to_rgb(over), hex_to_rgb(under)
    blended = tuple(round(top[i] * alpha + bottom[i] * (1 - alpha)) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*blended)


def sources(root: Path) -> tuple[Path, ...]:
    """Every cockpit source file, root-relative, in path order."""
    found = [
        path
        for path in sorted((root / APP_SRC).rglob("*"))
        if path.suffix in SOURCE_SUFFIXES and path.is_file()
    ]
    return tuple(path.relative_to(root) for path in found)


def _class_lists(text: str, *, first_line: int = 1) -> list[tuple[int, list[str]]]:
    """Every string literal in a source file, with the line it starts on.

    A hand-written scan rather than a regular expression, for two reasons
    a pattern cannot answer. **A comment is not a class list**: this
    module's own header quotes `bg-dominant text-white`, and a sweep that
    read comments would measure the prose that explains it. **A template
    literal holds strings of its own**: `TopTabs`'s active tab and
    `Checklist`'s out-of-window panel are branches of a conditional inside
    a `` ` `` -- `${isActive ? 'border-field-text text-field-text' : ...}`
    -- and a pattern that consumed the backticks whole would swallow both
    branches, which is exactly where two of the pairings this sweep exists
    to measure are written.
    """
    found: list[tuple[int, list[str]]] = []
    line = first_line
    index, end = 0, len(text)
    while index < end:
        char = text[index]
        if char == "\n":
            line += 1
            index += 1
        elif char == "/" and text[index + 1 : index + 2] == "/":
            index = text.find("\n", index)
            if index == -1:
                break
        elif char == "/" and text[index + 1 : index + 2] == "*":
            close = text.find("*/", index + 2)
            close = end if close == -1 else close + 2
            line += text.count("\n", index, close)
            index = close
        elif char in "'\"":
            index, body = _quoted(text, index, char)
            found.extend(_words(body, line))
            line += body.count("\n")
        elif char == "`":
            index, chunks, nested, newlines = _template(text, index)
            for offset, chunk in chunks:
                found.extend(_words(chunk, line + offset))
            for offset, inner in nested:
                found.extend(_class_lists(inner, first_line=line + offset))
            line += newlines
        else:
            index += 1
    return found


def _words(body: str, line: int) -> list[tuple[int, list[str]]]:
    """One literal's lines, each as its words, skipping the empty ones."""
    return [
        (line + offset, chunk.split())
        for offset, chunk in enumerate(body.split("\n"))
        if chunk.split()
    ]


def _quoted(text: str, index: int, quote: str) -> tuple[int, str]:
    """The body of a `'...'` or `"..."` literal, and where it ends."""
    cursor = index + 1
    body: list[str] = []
    while cursor < len(text) and text[cursor] != quote:
        if text[cursor] == "\\":
            cursor += 1
        else:
            body.append(text[cursor])
        cursor += 1
    return cursor + 1, "".join(body)


def _template(
    text: str, index: int
) -> tuple[int, list[tuple[int, str]], list[tuple[int, str]], int]:
    """A `` `...` `` literal, split into what it writes and what it
    interpolates.

    Returns where it ends, its literal chunks with the line offset each
    starts at, the source of each `${...}` with the same offset, and how
    many lines the whole literal spans.
    """
    cursor = index + 1
    chunks: list[tuple[int, str]] = []
    nested: list[tuple[int, str]] = []
    literal: list[str] = []
    offset, start = 0, 0
    while cursor < len(text) and text[cursor] != "`":
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == "\n":
            offset += 1
            literal.append("\n")
            cursor += 1
            continue
        if text[cursor] == "$" and text[cursor + 1 : cursor + 2] == "{":
            chunks.append((start, "".join(literal)))
            literal, start = [], offset
            cursor, inner = _interpolation(text, cursor + 1)
            nested.append((offset, inner))
            offset += inner.count("\n")
            start = offset
            continue
        literal.append(text[cursor])
        cursor += 1
    chunks.append((start, "".join(literal)))
    return cursor + 1, chunks, nested, offset


def _interpolation(text: str, index: int) -> tuple[int, str]:
    """The source inside one `${...}`, brace-counted so a nested object
    literal or a second template does not end it early."""
    depth, cursor = 0, index
    while cursor < len(text):
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
            if depth == 0:
                return cursor + 1, text[index + 1 : cursor]
        cursor += 1
    return cursor, text[index + 1 :]


def _is_a_colour(value: str) -> bool:
    return (
        value in TOKEN_COLOURS or value in BUILT_IN_COLOURS or value in LITERAL_TOKENS
    )


def scan(root: Path) -> tuple[list[Pairing], list[str]]:
    """Every pairing the cockpit's chrome sets, and every class list refused.

    The pairings and the refusals come out of one pass together: a caller
    that measured the first without reporting the second would be
    measuring a sweep that had quietly narrowed itself. Two shapes are
    refused -- a `text-`/`bg-` value this module can neither resolve nor
    recognise, and an `opacity-*` dimming type the same class list does
    not name.
    """
    found: list[Pairing] = []
    unknown: list[str] = []
    for rel in sources(root):
        named = rel.as_posix()
        text = (root / rel).read_text(encoding="utf-8")
        for line, words in _class_lists(text):
            grounds: dict[str, tuple[str, float]] = {}
            foregrounds: dict[str, tuple[str, float]] = {}
            opacities: dict[str, float] = {}
            for word in words:
                inert = _OPACITY.match(word)
                if inert:
                    opacities[inert["variant"]] = int(inert["value"]) / 100
                    continue
                utility = _UTILITY.match(word)
                if not utility:
                    continue
                value = utility["value"]
                if value in NOT_A_COLOUR:
                    continue
                if not _is_a_colour(value):
                    unknown.append(
                        f"{named}:{line}: {word} names neither a colour token "
                        "nor a known non-colour value"
                    )
                    continue
                alpha = 1.0 if utility["alpha"] is None else int(utility["alpha"]) / 100
                target = grounds if utility["utility"] == "bg" else foregrounds
                target[utility["variant"]] = (value, alpha)
            unknown.extend(_dimmed_inherited_type(named, line, foregrounds, opacities))
            found.extend(_resolve(named, line, grounds, foregrounds, opacities))
    return found, unknown


def _dimmed_inherited_type(
    named: str,
    line: int,
    foregrounds: dict[str, tuple[str, float]],
    opacities: dict[str, float],
) -> list[str]:
    """Refuse a class list that dims type it did not name.

    The state matters: `hover:opacity-90` on a list whose base names
    `text-white` dims type that list did name, and is measured. A bare
    `opacity-70` on a list naming no foreground at all dims whatever it
    inherited, which is the ancestor this sweep cannot read.
    """
    return [
        f"{named}:{line}: opacity-{round(value * 100)} dims type this class "
        "list does not name, so what it reduces the contrast of cannot be "
        "measured here. Say it in a colour instead -- ink-faint for type "
        "that has receded, paper-soft for a panel that has."
        for state, value in sorted(opacities.items())
        if _INERT not in state
        and value < 1
        and foregrounds.get(state) is None
        and foregrounds.get("") is None
    ]


def _resolve(
    named: str,
    line: int,
    grounds: dict[str, tuple[str, float]],
    foregrounds: dict[str, tuple[str, float]],
    opacities: dict[str, float],
) -> list[Pairing]:
    """One class list's pairings, one per state the element can be in.

    A state's own ground if it names one, the unvariant ground if it does
    not, the page's ground if neither -- the cascade a browser applies,
    read off one element's own classes.
    """
    resolved: list[Pairing] = []
    for state in sorted({"", *grounds, *foregrounds, *opacities}):
        if _INERT in state:
            continue
        foreground = foregrounds.get(state) or foregrounds.get("")
        if foreground is None:
            continue
        ground = grounds.get(state) or grounds.get("") or (PAGE_GROUND, 1.0)
        resolved.append(
            Pairing(
                path=named,
                line=line,
                variant=state,
                foreground=foreground[0],
                ground=ground[0],
                foreground_alpha=foreground[1],
                ground_alpha=ground[1],
                opacity=opacities.get(state, opacities.get("", 1.0)),
            )
        )
    return resolved


def pairings(root: Path) -> list[Pairing]:
    """Every pairing, for a caller that has already reported the words
    `scan` refused, and for the tests."""
    return scan(root)[0]


def measure(pairing: Pairing, tokens: dict[str, str]) -> float:
    """One pairing's contrast ratio, at one charter's tokens."""
    page = tokens[PAGE_GROUND]
    ground = composite(tokens[pairing.ground], page, pairing.ground_alpha)
    foreground = composite(tokens[pairing.foreground], ground, pairing.foreground_alpha)
    if pairing.opacity < 1:
        ground = composite(ground, page, pairing.opacity)
        foreground = composite(foreground, page, pairing.opacity)
    return contrast_ratio(foreground, ground)


def unresolved_foregrounds(found: list[Pairing]) -> list[str]:
    """Every pairing whose ground this sweep would have had to assume.

    The limit this module's own header states, asserted rather than
    trusted: a foreground light enough to need a dark ground, in a class
    list naming no ground at all, is a pairing whose real ground sits on
    an ancestor -- the one thing a sweep of class lists cannot read. It is
    reported as its own finding rather than measured against the page's
    ground and passed at whatever that happens to give.
    """
    return [
        f"{pairing.path}:{pairing.line}: text-{pairing.foreground} names no "
        "ground in its own class list, so the ground it is drawn on is set "
        "by an ancestor this sweep cannot read. Name the ground on the "
        "element that names the type."
        for pairing in found
        if pairing.ground == PAGE_GROUND
        and pairing.ground_alpha == 1.0
        and pairing.foreground in _LIGHT_FOREGROUNDS
    ]


def contrast_problems(
    found: list[Pairing],
    charter: dict[str, Any],
    *,
    named: str,
    danger: str,
    info: str,
) -> list[str]:
    """Every pairing the cockpit sets that fails AA at this charter."""
    tokens = token_colours(charter, danger=danger, info=info)
    problems: list[str] = []
    for pairing in found:
        ratio = round(measure(pairing, tokens), 2)
        if ratio < AA_NORMAL_TEXT:
            problems.append(
                f"{pairing.path}:{pairing.line}: {pairing.named} is {ratio} "
                f"at {named}, below the {AA_NORMAL_TEXT} WCAG AA needs for "
                "normal text"
            )
    return problems
