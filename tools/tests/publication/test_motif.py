"""The chrome's motif: generated from the registry, and never typed again.

`site/src/_data/motif.json` and `app/src/design/motif.ts` carry the drawing
the showcase's masthead, its home page, its verification page and the
cockpit's sign-in screen set. `tools/scripts/generate_motif.py` writes both
from the family the charter in force names, through
`convener_ops.publication.motifs`.

Three properties, and the third is what the first two exist for.

**The loop is proved, not assumed**, the same way `test_brand.py` proves it
for the design tokens: the tests below read the committed files off disk and
compare them with what today's charter derives. That catches a value
hand-edited without regenerating, and a charter changed without
regenerating.

**The mechanism dispatches.** The path in the fixture is `motifs.path`'s own
output for the family the charter names -- checked for `bracket` as well as
for `ribbon`, so a generator that had hard-coded a second constant under a
name would be caught by the family it was not written for.

**No product-owned template hand-writes an SVG path command.** That is the
defect these files close. Four templates carried the same three cubic-Bezier
paths byte for byte, in two languages, drawing an approximation of one
instance's ribbon on every public page of every duplicate -- geometry with an
owner, in files the identity sweep cannot see, because it compares declared
values and a shape is nobody's declared value. The sweep at the foot of this
module is recursive and reads the index, so a template added in a
subdirectory nobody thought of is under the rule on the commit that adds it.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404
from pathlib import Path
from typing import Final

import pytest
from generate_motif import (
    APP_MODULE_PATH,
    CANVAS,
    COMMAND,
    SITE_DATA_PATH,
    main,
    motif,
    render_app_module,
    render_site_data,
)

from convener_ops.declaration.paths import repo_root
from convener_ops.publication import brand, motifs

ROOT: Final = repo_root()

#: Where a template lives, and what a template is called. Both halves are
#: swept recursively: `site/src/_includes/` is one level down and holds the
#: chrome every public page shares, and `app/src/` is fifteen directories
#: deep in places.
TEMPLATE_ROOTS: Final = (Path("site") / "src", Path("app") / "src")
TEMPLATE_SUFFIXES: Final = (".njk", ".tsx", ".jsx", ".html")

#: A `d` attribute opening on an SVG path command -- every command letter,
#: upper and lower case. The lookbehind is what keeps `id="survey-form"`
#: and `data-id='M...'` out of it: `d` has to be the whole attribute name.
#: A `d` whose value is an expression (`d={MOTIF.path}`) is not matched and
#: is the shape this rule asks for.
_HAND_DRAWN_PATH: Final = re.compile(
    r"""(?<![\w-])d\s*=\s*["'][MmLlHhVvCcSsQqTtAaZz][\s0-9.,+-]"""
)


# --------------------------------------------------------------------------
# The loop: the committed files are what the charter derives
# --------------------------------------------------------------------------


def test_the_committed_site_data_is_what_the_charter_derives() -> None:
    """The showcase's side of the loop, read off disk."""
    assert (ROOT / SITE_DATA_PATH).read_text(encoding="utf-8") == render_site_data(ROOT)


def test_the_committed_app_module_is_what_the_charter_derives() -> None:
    """The cockpit's side of the same loop, from the same call."""
    assert (ROOT / APP_MODULE_PATH).read_text(encoding="utf-8") == render_app_module(
        ROOT
    )


def test_both_files_carry_the_same_drawing() -> None:
    """One derivation, two readers. A path in one and not the other is the
    drift the four hand-kept copies were."""
    site = json.loads((ROOT / SITE_DATA_PATH).read_text(encoding="utf-8"))
    module = (ROOT / APP_MODULE_PATH).read_text(encoding="utf-8")

    assert f"'{site['path']}'" in module
    assert f"'{site['stroke_width']}'" in module
    assert f"'{site['view_box']}'" in module
    assert f"'{site['family']}'" in module


def test_each_generated_file_says_it_is_generated_and_names_the_charter() -> None:
    """A reader who opens either file has to be told not to edit it."""
    site = json.loads((ROOT / SITE_DATA_PATH).read_text(encoding="utf-8"))
    module = (ROOT / APP_MODULE_PATH).read_text(encoding="utf-8")

    assert "generate_motif.py" in site["_generated"]
    assert "Edit the charter, not this file." in site["_generated"]
    assert "generate_motif.py" in module
    assert "Edit\n * the charter, not this file." in module


# --------------------------------------------------------------------------
# The drawing is the registry's, and the registry dispatches
# --------------------------------------------------------------------------


def test_the_fixture_carries_the_registrys_own_output_for_the_charter() -> None:
    """The path is `motifs.path`'s, on the canvas the generator names --
    never a shape this module or a template holds a copy of."""
    site = json.loads((ROOT / SITE_DATA_PATH).read_text(encoding="utf-8"))
    family = brand.motif_family(ROOT)

    assert site["family"] == family
    assert site["path"] == " ".join(motifs.path(family, CANVAS, CANVAS).splitlines())


def test_the_stroke_weight_is_the_charters_ratio_on_that_canvas() -> None:
    """`stroke-width="9"` was hand-written in all four templates and was
    nobody's measurement. The weight scales with the canvas and comes from
    `motif.width_ratio`."""
    site = json.loads((ROOT / SITE_DATA_PATH).read_text(encoding="utf-8"))
    ratio = brand.motif_width_ratio(ROOT)

    assert float(site["stroke_width"]) == pytest.approx(
        motifs.stroke_width(CANVAS, CANVAS, ratio=ratio), abs=0.005
    )


@pytest.mark.parametrize("family", sorted(motifs.FAMILIES))
def test_every_family_draws_its_own_path_through_the_generator(
    family: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mechanism dispatches rather than holding one drawing per name.

    A charter is written into a scratch root naming each family in turn,
    and what comes out is that family's own path. Run for `bracket` and for
    `ribbon`: a generator that had hard-coded a second constant would agree
    with the family it was written for and disagree with the other.
    """
    charter = json.loads((ROOT / brand.DEFAULT_PATH).read_text(encoding="utf-8"))
    charter[brand.MOTIF_KEY][brand.MOTIF_FAMILY] = family
    written = tmp_path / brand.INSTANCE_PATH
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(json.dumps(charter), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    drawn = motif(tmp_path)

    assert drawn.family == family
    assert drawn.path == " ".join(motifs.path(family, CANVAS, CANVAS).splitlines())
    assert drawn.path != " ".join(
        motifs.path(
            next(name for name in motifs.FAMILIES if name != family), CANVAS, CANVAS
        ).splitlines()
    )


def test_an_unknown_family_stops_the_generator_and_names_the_ones_there_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Never a fall back to whichever drawing this product happens to have:
    a duplicate would publish somebody else's mark on every page."""
    charter = json.loads((ROOT / brand.DEFAULT_PATH).read_text(encoding="utf-8"))
    charter[brand.MOTIF_KEY][brand.MOTIF_FAMILY] = "spiral"
    written = tmp_path / brand.INSTANCE_PATH
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(json.dumps(charter), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main([]) == 1
    printed = capsys.readouterr().err
    assert "spiral" in printed
    for name in motifs.FAMILIES:
        assert name in printed


# --------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------


def test_check_passes_on_the_repository_as_committed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same assertion continuous integration runs, here."""
    assert main(["--check"]) == 0
    assert "matches" in capsys.readouterr().out


def test_check_refuses_a_hand_edited_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path edited in the generated file, with the charter untouched --
    one of the two ways a generated file and its source drift apart."""
    for relative in (SITE_DATA_PATH, APP_MODULE_PATH, brand.INSTANCE_PATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            (ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8", newline=""
        )
    hand_edited = tmp_path / SITE_DATA_PATH
    hand_edited.write_text(
        hand_edited.read_text(encoding="utf-8").replace('"M ', '"M 1 1 M ', 1),
        encoding="utf-8",
        newline="",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main(["--check"]) == 1
    printed = capsys.readouterr().err
    assert SITE_DATA_PATH.as_posix() in printed
    assert COMMAND in printed


def test_check_refuses_a_charter_changed_without_regenerating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other way round: the charter moves and the two files do not."""
    for relative in (SITE_DATA_PATH, APP_MODULE_PATH, brand.INSTANCE_PATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            (ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8", newline=""
        )
    charter_path = tmp_path / brand.INSTANCE_PATH
    charter = json.loads(charter_path.read_text(encoding="utf-8"))
    charter[brand.MOTIF_KEY]["width_ratio"] = 0.05
    charter_path.write_text(json.dumps(charter), encoding="utf-8", newline="")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))

    assert main(["--check"]) == 1
    printed = capsys.readouterr().err
    assert SITE_DATA_PATH.as_posix() in printed
    assert APP_MODULE_PATH.as_posix() in printed


# --------------------------------------------------------------------------
# No template draws by hand
# --------------------------------------------------------------------------


def tracked_templates() -> list[str]:
    """Every tracked template under the two source trees, recursively.

    The index rather than a walk: `node_modules/`, `dist/` and `_site/`
    are all on disk in an ordinary working copy and none of them is a
    file this repository holds. Recursive because six sweeps in this
    repository had silently narrowed to one directory, and one of them
    fired again the last time a family was added.
    """
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    return [
        path
        for path in listed
        if path.endswith(TEMPLATE_SUFFIXES)
        and any(path.startswith(root.as_posix() + "/") for root in TEMPLATE_ROOTS)
    ]


def test_the_sweep_reaches_the_templates_it_is_written_for() -> None:
    """A walk that found nothing, or that found one directory's worth,
    would make the rule below pass over an empty list."""
    swept = tracked_templates()

    assert len(swept) > 20, (
        f"the sweep reached {len(swept)} template(s), which is not this "
        "repository -- it is reading the wrong tree, or has narrowed"
    )
    # One from each tree, and one from a subdirectory of each, so a sweep
    # that stopped at the top level fails here rather than passing quietly.
    for named in (
        "site/src/index.njk",
        "site/src/_includes/layout.njk",
        "app/src/App.tsx",
        "app/src/auth/Login.tsx",
    ):
        assert named in swept, f"{named} is a template and the sweep missed it"


def test_no_template_hand_writes_an_svg_path_command() -> None:
    """The rule. Geometry belongs to a family in
    `convener_ops/publication/motifs/`, and reaches a template through
    `site/src/_data/motif.json` or `app/src/design/motif.ts`.

    A `d` attribute typed into markup is a drawing with an owner nothing
    can read: `declarations/boundary.yml` decides ownership per file, the
    identity sweeps compare declared values, and a shape is nobody's
    declared value. Four templates shipped one instance's mark that way,
    on every public page of every duplicate, for as long as they existed.
    """
    offenders: list[str] = []
    for relative in tracked_templates():
        text = (ROOT / relative).read_text(encoding="utf-8")
        found = _HAND_DRAWN_PATH.search(text)
        if found:
            offenders.append(f"{relative}: {text[found.start() : found.start() + 60]}")

    assert not offenders, (
        "a template draws an SVG path by hand, which is geometry nothing "
        "regenerates and no sweep can attribute -- ask "
        "`convener_ops.publication.motifs` for it instead, through "
        f"`{COMMAND}`:\n" + "\n".join(offenders)
    )
