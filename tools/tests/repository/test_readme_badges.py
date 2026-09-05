"""The badges at the head of `README.md`, held to what they claim.

A badge is the most-read sentence on a public repository and the least
read by anybody maintaining it. It sits above the first heading, it is
four words long, and nothing anywhere goes red when it stops being true.
Three are in the header, and every one of them got there on one rule:
**a badge has to be checkable from this repository and unable to go
stale.** That rule is what refused a hand-written `Node 24`, which would
have drifted from `.nvmrc` the first time the runtime moved, and a
languages badge, which restates the bar GitHub already draws.

This module is that rule with a reader.

**What the row does not hold, and the judgement behind that.** Nothing here
says *which* three claims the header makes. `test_there_are_badges_to_read`
refuses a row shorter than three and the two pinning sweeps below hold the
licence badge and the accessibility badge to the files that answer for them,
so a badge cannot quietly say something false -- but which claims a front
page makes at all is an editorial decision, and a list of them here would
make the row unchangeable without a test change. What each badge *asserts*
is a control; which assertions are worth three seconds of a stranger's
attention is taste, and taste does not get a gate.

**Where they sit.** Above the first `##`, between the title and the first
section, which is the only place a badge is read at all. Two of these
spent a long time below three screenshots instead, where a reader
scanning a list of repositories never reached them.

**What they may claim.** Two kinds of image, and the difference is who
computes the claim:

* A **static badge**, drawn by `img.shields.io/badge/...` out of text
  somebody typed. Its two halves are read below and held against this
  repository: the licence badge has to carry the identifier `CITATION.cff`
  declares, the accessibility badge has to name the standard
  `site/scripts/check-a11y.mjs` actually hands axe, and no static badge may
  name a toolchain a declaration here pins, because the value on the badge
  and the value in the declaration are then two spellings of one fact with
  nothing holding them together.
* A **generated badge**, drawn by the service whose state it reports --
  the continuous-integration badge `docs/operating/publishing-the-product.md`
  lays at publication is one, and cannot exist before there is a
  repository to name. Nothing here reads its message, because nobody here
  writes it.

**What every badge owes.** A link somewhere a reader can go, and a local
target that is a file this repository tracks. A badge that leads nowhere
asks for trust and offers no way to check it.

The refusals below are proved on invented badges as well as run over the
real page: `test_the_rule_refuses_a_toolchain_badge` and its neighbours
are what say the sweep would fail if the page changed, which a sweep over
one correct page never says on its own.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
from typing import Final
from urllib.parse import unquote

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()
README: Final = ROOT / "README.md"

#: The SPDX identifier this repository ships under. Spelled once here and
#: compared against `CITATION.cff`'s own `license:` by
#: `test_the_licence_badge_and_the_citation_file_name_one_licence`, so this
#: constant cannot become a third spelling of it.
LICENCE_IDENTIFIER: Final = "AGPL-3.0-or-later"

#: The sweep that makes the accessibility claim true, and the workflow that
#: runs it on a push and on a pull request touching what it builds. The badge
#: names a standard and links to the second; both are read below, so a badge
#: outliving either one fails here.
A11Y_CHECKER: Final = ROOT / "site" / "scripts" / "check-a11y.mjs"

#: The array of axe tags that checker runs, and one tag inside it. axe spells
#: a success criterion set `wcag<major><minor?><level>`: `wcag2aa` is WCAG 2.0
#: level AA, `wcag21aa` is 2.1 level AA. The badge has to name the furthest of
#: them, which is what `standard_named_by` computes.
TAG_ARRAY: Final = re.compile(r"WCAG_AA_TAGS\s*=\s*\[([^\]]*)\]")
WCAG_TAG: Final = re.compile(r"wcag(\d)(\d?)(a+)")

#: `[![alt](image)](target)` -- a badge is an image inside a link. An image
#: that links nowhere is not matched here and is refused by
#: `test_every_badge_leads_somewhere` reading the bare-image form as well.
BADGE: Final = re.compile(r"\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)")

#: A Markdown image, linked or not. Used only to find the unlinked ones.
IMAGE: Final = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

#: The host that draws a badge out of text somebody typed, and the path
#: that says the text is the whole of the input.
STATIC_BADGE: Final = "https://img.shields.io/badge/"

#: A single `-` in a shields path, which separates the label from the
#: message from the colour. `--` is shields' own escape for a literal
#: hyphen and does not separate anything, which is why the lookaround is
#: on both sides: `AGPL--3.0--or--later` is one field.
FIELD: Final = re.compile(r"(?<!-)-(?!-)")

#: Toolchains this repository pins in a file, and the file that pins each.
#: A badge naming one of them states a version somebody typed beside a
#: version something reads, and only one of the two is ever updated.
#: Closed and short: a name earns its place by being a thing a declaration
#: here actually holds a value for.
PINNED: Final[dict[str, str]] = {
    "node": ".nvmrc",
    "npm": "app/package.json",
    "python": "tools/pyproject.toml",
    "uv": "tools/uv.lock",
    "vite": "app/package.json",
    "react": "app/package.json",
    "typescript": "app/package.json",
    "eleventy": "site/package.json",
}


def readme() -> str:
    return README.read_text(encoding="utf-8")


def header(text: str) -> str:
    """Everything above the first section heading.

    The badges belong here and the sweeps below say so. `## ` at the start
    of a line is the first section; a page with no section at all is the
    whole of its own header, which is the reading that keeps an empty
    result impossible rather than silent.
    """
    found = re.search(r"^## ", text, re.MULTILINE)
    return text[: found.start()] if found else text


def badges(text: str) -> list[tuple[str, str, str]]:
    """Every `[![alt](image)](target)` in `text`, in the order it reads."""
    return [(m.group(1), m.group(2), m.group(3)) for m in BADGE.finditer(text)]


def static_fields(image: str) -> tuple[str, str] | None:
    """The label and the message of a static badge, unescaped.

    `None` for an image drawn by anything else: a generated badge carries
    no text this repository wrote, so there is nothing here to read.
    """
    if not image.startswith(STATIC_BADGE):
        return None
    parts = FIELD.split(image[len(STATIC_BADGE) :])
    if len(parts) < 2:
        return None
    label, message = parts[0], parts[1]
    return _unescape(label), _unescape(message)


def _unescape(field: str) -> str:
    """Shields' own escaping, undone: `--` is a hyphen, `__` an underscore,
    `_` a space, and the rest is percent-encoded."""
    field = unquote(field)
    field = field.replace("__", "\0").replace("_", " ").replace("\0", "_")
    return field.replace("--", "-")


def toolchains_named(label: str, message: str) -> list[str]:
    """Which pinned toolchains a badge's own text names."""
    said = f"{label} {message}".lower()
    return sorted(name for name in PINNED if re.search(rf"\b{name}\b", said))


def standard_named_by(source: str) -> str:
    """The standard `source` holds axe to, as a badge would spell it.

    Takes the text rather than reading the file, so the refusals below can
    be proved on tag lists this repository does not ship: a checker pinned
    to `wcag22aa` tomorrow has to move the badge with it, and a control
    that only ever saw today's list could not say that.
    """
    declared = TAG_ARRAY.search(source)
    assert declared is not None, (
        "no WCAG_AA_TAGS array in the source given -- the badge's message "
        "is derived from that list and there is nothing here to derive it "
        "from"
    )
    tags = WCAG_TAG.findall(declared.group(1))
    assert tags, "WCAG_AA_TAGS holds no tag this reader recognises"
    major, minor, level = max(
        tags, key=lambda tag: (int(tag[0]), int(tag[1] or 0), len(tag[2]))
    )
    return f"WCAG {major}.{minor or 0} {level.upper()}"


def labelled(label: str) -> list[tuple[str, str]]:
    """Every static badge in the header with this label, as (message, target).

    A list rather than one badge, and the sweeps below assert its length:
    the failure a second licence badge or a second accessibility badge would
    be is a row making one claim twice, which is worth a message of its own
    rather than an index error.
    """
    found: list[tuple[str, str]] = []
    for _alt, image, target in badges(header(readme())):
        fields = static_fields(image)
        if fields is not None and fields[0].lower() == label:
            found.append((fields[1], target))
    return found


def tracked(path: str) -> bool:
    """Whether `path` is a file this repository's index carries."""
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "--error-unmatch", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return listed.returncode == 0


# ------------------------------------------------------------------ #
# The page as it stands.
# ------------------------------------------------------------------ #


def test_there_are_badges_to_read() -> None:
    """Non-vacuity: every sweep below passes over a page with no badge on
    it, and this repository's front page is not one."""
    found = badges(header(readme()))
    assert len(found) >= 3, (
        f"the header of README.md carries {len(found)} badges. Every rule "
        "in this module reads that list, so an empty one is a module that "
        "checks nothing and says nothing about it."
    )


def test_every_badge_sits_in_the_header() -> None:
    """Above the first section, where a badge is actually read.

    Both counts, because either alone passes on the wrong page: the header
    holds badges, and the body below it holds none that the header does
    not.
    """
    text = readme()
    assert badges(header(text)) == badges(text), (
        "README.md carries a badge below its first section heading. A "
        "badge that far down is read by whoever was already convinced; "
        "the header is the whole of what somebody scanning a list of "
        "repositories sees."
    )


def test_every_badge_leads_somewhere() -> None:
    """A badge is an image inside a link, and never a bare image."""
    text = header(readme())
    linked = {image for _, image, _ in badges(text)}
    bare = [alt for alt, image in IMAGE.findall(text) if image not in linked]
    assert bare == [], (
        f"the header of README.md shows {bare} as images with no link. A "
        "badge makes a claim and a reader has to be able to follow it to "
        "the file that answers for it."
    )


def test_every_badge_a_reader_can_follow_points_at_a_tracked_file() -> None:
    unresolved = [
        (alt, target)
        for alt, _, target in badges(header(readme()))
        if "://" not in target and not tracked(target)
    ]
    assert unresolved == [], (
        f"{unresolved} are badge links to paths this repository does not "
        "track. A badge whose link 404s is worse than no badge: it reads "
        "as a claim somebody checked."
    )


def test_the_licence_badge_and_the_citation_file_name_one_licence() -> None:
    """Two published statements of the terms, and they cannot disagree.

    `CITATION.cff` is machine-readable and aggregators read it;
    the badge is what a person reads. `tools/tests/repository/`
    `test_public_repository.py` already holds the file to this identifier,
    so pinning the badge to the same string is what closes the pair.
    """
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert f"license: {LICENCE_IDENTIFIER}" in citation, (
        f"CITATION.cff no longer declares `license: {LICENCE_IDENTIFIER}`, "
        "so the identifier this module compares the badge against is not "
        "the one the repository ships."
    )
    messages = [message for message, _target in labelled("licence")]
    assert messages == [LICENCE_IDENTIFIER], (
        f"the licence badge reads {messages}, and this repository ships "
        f"{LICENCE_IDENTIFIER!r}. A badge naming the wrong terms is read "
        "by everybody who never opens LICENSE."
    )


def test_the_accessibility_badge_names_the_standard_the_sweep_actually_runs() -> None:
    """The badge's message, and the tag list behind it.

    `site/scripts/check-a11y.mjs` hands axe a closed list of success-criterion
    tags and every page of the built showcase is run against it at two
    viewports. The badge is the one-line reading of that list, so the two are
    held together the way the licence badge and `CITATION.cff` are: raise the
    checker to `wcag22aa` and the badge is a claim nobody is making; lower it
    to `wcag2aa` and the badge is a claim nobody is checking.
    """
    expected = standard_named_by(A11Y_CHECKER.read_text(encoding="utf-8"))
    messages = [message for message, _target in labelled("accessibility")]
    assert messages == [expected], (
        f"the accessibility badge reads {messages}, and "
        f"{A11Y_CHECKER.name} holds this repository to {expected!r}. A badge "
        "claiming a standard nothing measures is the one kind of badge this "
        "row exists to refuse."
    )


def test_the_accessibility_badge_leads_to_the_workflow_that_runs_the_sweep() -> None:
    """Where a reader lands, and whether anything is still running there.

    Every other badge here can be checked by opening the file it links to.
    This one claims a *constraint* rather than a state, so the file it links
    to has to be the thing applying it: the workflow that builds the showcase
    and runs the checker over it, on a push and on a pull request. Deleting
    that workflow and leaving the badge is the failure, and it is a failure
    nothing else in this module would see.
    """
    found = labelled("accessibility")
    assert len(found) == 1, (
        f"the header carries {len(found)} badges labelled accessibility"
    )
    _message, target = found[0]
    workflow = (ROOT / target).read_text(encoding="utf-8")
    for expected, why in (
        ("check:a11y", "the sweep the badge is a reading of"),
        ("push:", "so a merged change is checked"),
        ("pull_request:", "so a change is checked before it is merged"),
    ):
        assert expected in workflow, (
            f"{target} carries no {expected!r} -- {why}. The badge links "
            "here because this is what makes its claim true."
        )


def test_no_badge_names_a_toolchain_a_declaration_here_pins() -> None:
    named: list[tuple[str, list[str]]] = []
    for alt, image, _target in badges(header(readme())):
        fields = static_fields(image)
        if fields is None:
            continue
        found = toolchains_named(*fields)
        if found:
            named.append((alt, found))
    assert named == [], (
        f"{named} are badges naming a toolchain this repository pins "
        f"elsewhere ({PINNED}). The badge and the declaration are then two "
        "spellings of one version and only one of them is ever updated: "
        "derive the badge or do not carry it."
    )


# ------------------------------------------------------------------ #
# The rules bite, on badges somebody made up.
# ------------------------------------------------------------------ #


def test_the_fields_of_a_static_badge_are_read_as_shields_writes_them() -> None:
    assert static_fields(f"{STATIC_BADGE}licence-AGPL--3.0--or--later-012765") == (
        "licence",
        "AGPL-3.0-or-later",
    )
    assert static_fields(f"{STATIC_BADGE}cost%20to%20run-%E2%82%AC0-012765") == (
        "cost to run",
        "€0",
    )
    assert static_fields(f"{STATIC_BADGE}accessibility-WCAG%202.1%20AA-012765") == (
        "accessibility",
        "WCAG 2.1 AA",
    )


def test_a_generated_badge_carries_no_text_this_module_reads() -> None:
    """The continuous-integration badge, whose message the service writes."""
    assert (
        static_fields(
            "https://github.com/owner/convener/actions/workflows/quality.yml/badge.svg"
        )
        is None
    )


def test_the_rule_refuses_a_toolchain_badge() -> None:
    """`Node 24`, the badge the criterion was written against."""
    assert toolchains_named("node", "24") == ["node"]
    assert toolchains_named("requires", "Node 24") == ["node"]
    assert toolchains_named("built with", "Vite") == ["vite"]


def test_the_rule_admits_the_badges_this_page_carries() -> None:
    """Narrowness, proved on the three real ones rather than asserted."""
    assert toolchains_named("licence", LICENCE_IDENTIFIER) == []
    assert toolchains_named("cost to run", "€0") == []
    assert toolchains_named("accessibility", "WCAG 2.1 AA") == []


def test_the_standard_is_read_off_the_tags_rather_than_typed_here() -> None:
    """Four tag lists this repository does not ship, and one it does.

    The last of them is the point: a control that only ever computed the
    answer for today's checker would pass unchanged the day somebody
    narrowed it, which is how a check stops being one.
    """
    assert standard_named_by("WCAG_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa']") == (
        "WCAG 2.1 AA"
    )
    assert standard_named_by("WCAG_AA_TAGS = ['wcag2a', 'wcag2aa']") == "WCAG 2.0 AA"
    assert standard_named_by("WCAG_AA_TAGS = ['wcag2a', 'wcag22aa']") == "WCAG 2.2 AA"
    assert standard_named_by("WCAG_AA_TAGS = ['wcag2a']") == "WCAG 2.0 A"


def test_the_header_stops_at_the_first_section() -> None:
    page = "# Title\n\n[![a](i)](t)\n\n## First\n\n[![b](j)](u)\n"
    assert badges(header(page)) == [("a", "i", "t")]
    assert len(badges(page)) == 2


def test_a_page_with_no_section_is_all_header() -> None:
    page = "# Title\n\n[![a](i)](t)\n"
    assert header(page) == page
