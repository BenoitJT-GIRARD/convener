"""The commands that write what the series shows the world.

The three public-data projections and the calendar feed, the announcement
texts, and the four rendering commands the browser-driven jobs run against
a fixture or against real editions. Nothing here decides what may be
published -- `convener_ops.publication.public_data` does, field by field.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Final

from convener_ops.cli import store
from convener_ops.declaration import published
from convener_ops.declaration.paths import (
    DATA_DIR,
    PUBLIC_DATA_DIR,
    repo_root,
)
from convener_ops.publication import (
    agenda,
    announce,
    brand,
    brand_templates,
    formats,
    motifs,
    typeface,
    visual,
)
from convener_ops.publication.public_data import to_public, to_survey_status


def public_data() -> int:
    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"  - {error}")
        return 1

    rows = to_public(speakers or [])
    out_dir = root / PUBLIC_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "events-public.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} events")
    return 0


def survey_status_public_data() -> int:
    """`convener-survey-status-public-data`: rebuild
    `instance/public-data/survey-status.json` from `instance/data/speakers.yml`'s own
    `survey_enabled` field -- `public_data`'s own
    precedent (above), for a different consumer and a different field: an
    operational fact, not the programme feed `to_public` projects through
    the consent gate.

    Deliberately its own file, its own command, its own step in
    `deploy.yml` -- not folded into `public_data()`'s own
    `events-public.json` -- because the two answer different questions for
    different readers: `events-public.json` is the programme a visitor
    reads, gated on consent; `survey-status.json` is a closed list of ids
    `SurveyForm.tsx` checks membership against before it ever renders a
    question, and it must never require the consent gate to have opened
    for an event that has not even happened yet.
    """
    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"  - {error}")
        return 1

    ids = to_survey_status(speakers or [])
    out_dir = root / PUBLIC_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "survey-status.json").write_text(
        json.dumps(ids, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(ids)} event(s) with the survey open")
    return 0


def agenda_internal() -> int:
    """`convener-agenda-internal`: rebuild
    `instance/public-data/agenda-internal.ics` from
    `instance/data/speakers.yml` and `instance/data/config.yml` --
    `public_data`'s own precedent (above), for a feed that must never reach
    either published bundle: unlike `events-public.json`, nothing in this
    build's own copy scripts ever names this file, and `.gitattributes`
    marks it binary so a checkin never rewrites its own CRLF line endings to
    this repository's own default `eol=lf`. See `agenda.py`'s module
    docstring for the feed in full, and `.github/workflows/deploy.yml`'s own
    "Commit internal agenda" step for where the committed copy comes from.
    """
    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    cfg, cfg_errors = store.load(root / DATA_DIR / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1

    calendar = agenda.build_internal_calendar(speakers or [], cfg or {})
    out_dir = root / PUBLIC_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    # Binary, not text mode: this string already carries real CRLF line
    # endings RFC 5545 requires, and a text-mode write on this project's own
    # Windows checkouts would translate each embedded "\n" to the platform
    # line ending on top of the "\r" already there, corrupting every line to
    # "\r\r\n" (`tools/convener_ops`'s own YAML writers hit the identical trap and
    # guard against it with `newline=""`; binary mode is the same guarantee
    # by a different route).
    (out_dir / "agenda-internal.ics").write_bytes(calendar.encode("utf-8"))
    print(f"wrote {calendar.count('BEGIN:VEVENT')} entrie(s)")
    return 0


def render_visual_fixtures() -> int:
    """`convener-render-visual-fixtures OUTPUT_DIR`: writes the pinned
    render step its input -- one self-contained HTML page per named format
    (`formats.FORMATS`), a `manifest.json` naming each one's format name and
    pixel size, and a copy of the repository's self-hosted `fonts/` beside
    them so a relative `url('fonts/...')` resolves once served.

    The one disk-writing seam between the two halves of that pipeline.
    `visual.render_announcement` and `formats.FORMATS` stay pure -- neither
    touches disk or knows this project builds a Node/Puppeteer step on top
    of what they return -- and the pinned renderer (`tools/visuals/`, a separate
    npm package so only its own CI job ever pays for the Chrome-for-Testing
    download that isolation buys) never re-derives a page's own markup a second
    time in JavaScript: it reads exactly the bytes this command wrote.

    `manifest.json` is the shared *fixture* the two languages agree on
    (D-14's own shape, applied to a boundary this project has not crossed
    before): the pinned renderer reads a format's name and pixel size from
    it rather than a second, hand-typed `{width: 1200, height: 1200}` in
    JavaScript that `formats.py` could silently drift away from.

    Always renders `visual.FIXTURE_ANNOUNCEMENT` -- the one fixed, versioned
    identity the committed reference images are measured against
    (see that constant's own docstring for why it is Ada Lovelace and no
    photograph, never a real, living speaker's name or face). Nothing about
    this command reads `instance/data/speakers.yml`, the clock, or the network: the
    same input always produces the same three pages, which is the entire
    point of a pinned regression fixture.

    **And it renders as the example instance, never as this one.**
    `render_announcement` takes a `root` to read the charter and
    the declaration from; this command used to hand it `repo_root()`, so
    the three committed reference images were a frozen photograph of
    whichever instance ran the repository -- its palette, its ribbon, its
    strapline, its wordmark -- sitting in `tools/visuals/`, which is the
    product's. Two things follow from handing it `examples/the-example-collective/`
    instead, and both are the point rather than a side effect:

    - **the images carry no real instance's identity.** They pin what
      `visual.py` *renders* -- the geometry, the glyph shapes, the QR
      modules, the motif's stroke against its ground. The names and the
      address are the example's, invented and reserved, and the palette
      is the one the example names: `assets/brand/convener/brand.json`,
      the product's own, which is nobody's instance. The designer of this
      instance's charter declined to have it ship with the product; this
      is the byte-level half of honouring that.
    - **the check stops failing for every duplicate.** `visuals.yml` fires
      on the charter's own path, so before this change a duplicate that
      chose its own colours rendered them against images of somebody
      else's and went red on its first push, with nothing wrong.

    `_fixture_root` is what gives `render_announcement` the root it asks
    for. `examples/the-example-collective/` is not one: it holds one file
    per instance path and no `assets/`, so a declaration there naming one
    of the product's charters addresses a directory that is only ever
    above it. The two files that root holds are the example's declaration
    and the charter the example names, which is the same pair a duplicate
    builds from and the same pair `render_poster_fixtures` already lays
    out for every charter it renders.

    The fonts still come from `root / "assets" / "fonts"`: they are the product's,
    self-hosted and served by it (D-17), and `examples/the-example-collective/` holds no
    copy of them precisely because a face is not an identity here.
    """
    if len(sys.argv) != 2:
        print("usage: convener-render-visual-fixtures OUTPUT_DIR", file=sys.stderr)
        return 1
    root = repo_root()
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as scratch:
        # The declaration and the charter the fixture is rendered from --
        # the example instance's, never this repository's own. See the
        # docstring.
        made = _fixture_root(
            Path(scratch) / "example",
            root,
            brand.source(root, published.EXAMPLE_INSTANCE_ROOT),
            published.EXAMPLE_INSTANCE_PATH,
            None,
        )
        for fmt in formats.FORMATS:
            html = visual.render_announcement(
                visual.FIXTURE_ANNOUNCEMENT,
                width=fmt.width,
                height=fmt.height,
                root=made,
            )
            filename = f"{fmt.name}.html"
            (out / filename).write_text(html, encoding="utf-8")
            manifest.append(
                {
                    "name": fmt.name,
                    "width": fmt.width,
                    "height": fmt.height,
                    "file": filename,
                }
            )

    fonts_dest = out / "fonts"
    if fonts_dest.exists():
        shutil.rmtree(fonts_dest)
    shutil.copytree(root / "assets" / "fonts", fonts_dest)

    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(manifest)} visual fixture(s) to {out}")
    return 0


#: The two *instances* this repository holds, under the name their
#: fixtures are written with: the directory each one's own files sit in,
#: and the declaration whose names and address its templates are rendered
#: from.
#:
#: - `instance` -- the instance that happens to run this repository, whose
#:   files are at the root.
#: - `example` -- `examples/the-example-collective/`, the worked example a
#:   duplicate copies, which holds one file for each of the same paths.
#:
#: The charter each is drawn with is not written here. It is
#: `brand.source` below, per instance, because an instance has three ways
#: to answer that question and only one of them is a file of its own: this
#: one writes a charter, the example names one of the product's, and a
#: fresh duplicate does neither. A pair of paths written out here would
#: have been the first answer nailed down as though it were the only one.
_INSTANCES: Final = (
    ("instance", None, published.INSTANCE_PATH),
    (
        "example",
        published.EXAMPLE_INSTANCE_ROOT,
        published.EXAMPLE_INSTANCE_PATH,
    ),
)


def _template_charters(root: Path) -> tuple[tuple[str, Path, Path], ...]:
    """Every charter this repository holds, and the declaration each is
    rendered against.

    The charter in force for each instance above, then one per directory
    under `assets/brand/`, named for that directory: `assets/brand/convener/` is
    the charter a duplicate that has written none of its own is drawn
    with, and every other one is a palette it may choose instead. None of
    the latter has a declaration of its own, because a charter is not an
    identity -- each is rendered against this instance's names, which is
    what a duplicate actually gets the first time it builds.

    An instance that names one of the product's charters therefore appears
    twice, at the same file and against two declarations, and that is the
    sweep working rather than a duplicate entry: what a template has to
    clear is a stroke against a *word*, and the two declarations set
    different words.

    Read off the directory rather than listed, the way `motifs.FAMILIES`
    is read off the directory beside it: a charter added here is measured
    against every family on the commit that adds it, with no entry to
    make in this file, in `templates.yml`'s filter or anywhere else.
    """
    return (
        *(
            (label, brand.source(root, instance), declaration)
            for label, instance, declaration in _INSTANCES
        ),
        *(
            (rel.parent.name, rel, published.INSTANCE_PATH)
            for rel in brand.shipped(root)
        ),
    )


#: The three files `brand_templates` writes, under the name each fixture
#: is written with, and the canvas each is drawn on. The sizes are read off
#: the module that draws them rather than typed again -- `formats.SQUARE`
#: for the square, A4 at ten units a millimetre for the flyer, and the
#: background's own frame -- so a change to any of them moves the fixture
#: with it.
_TEMPLATE_FILES: Final = (
    (
        "announcement",
        brand_templates.render_announcement_template,
        formats.SQUARE.width,
        formats.SQUARE.height,
    ),
    (
        "flyer",
        brand_templates.render_flyer_template,
        formats.PRINT_PAPER_MM[0] * brand_templates.UNITS_PER_MM,
        formats.PRINT_PAPER_MM[1] * brand_templates.UNITS_PER_MM,
    ),
    (
        "background",
        brand_templates.render_video_call_background,
        brand_templates.BACKGROUND_WIDTH,
        brand_templates.BACKGROUND_HEIGHT,
    ),
)


def _fixture_root(
    made: Path, root: Path, charter: Path, declaration: Path, family: str | None
) -> Path:
    """A repository root holding one charter, drawn with one family.

    Two files and nothing else, because that is all a template and a
    poster read: a declaration (the names, the address, the forum the code
    points at) and a charter (the palette and the motif). The charter is
    copied with its `motif.family` replaced, which is how a sweep asks a
    question no committed file asks -- what this charter's own colours and
    this instance's own name look like drawn with *that* family -- without
    inventing a charter and committing it. `None` leaves the family the
    charter itself names, for the caller that renders what is committed
    rather than a cross product.

    **The charter arrives as a file here whichever way the instance it
    came from answers for it**, so a declaration that *names* one has that
    key taken out on the way in. Both together is what `brand.source`
    refuses, and it is right to: in a repository the two would be one
    notion in two files, free to disagree. Here they would be the same
    charter said twice, and the copy is the half that can carry the family
    this fixture is asking about.
    """
    (made / brand.INSTANCE_PATH.parent).mkdir(parents=True, exist_ok=True)
    declared = json.loads((root / declaration).read_text(encoding="utf-8"))
    raw = (root / declaration).read_bytes()
    if published.CHARTER_KEY in declared:
        del declared[published.CHARTER_KEY]
        raw = (json.dumps(declared, indent=2) + "\n").encode("utf-8")
    (made / published.INSTANCE_PATH).write_bytes(raw)
    values = json.loads((root / charter).read_text(encoding="utf-8"))
    if family is not None:
        values["motif"][brand.MOTIF_FAMILY] = family
    (made / brand.INSTANCE_PATH).write_text(
        json.dumps(values, indent=2) + "\n", encoding="utf-8"
    )
    return made


def _template_fixture_root(
    scratch: Path, root: Path, charter: Path, declaration: Path, family: str
) -> Path:
    """One entry of the cross product, in a scratch directory inside
    `scratch`.

    The name carries the family and the charter file's own stem, which is
    `brand` for every charter there is -- so two charters at one family
    are laid out at the same path, one after the other. Each is written
    and then read before the next is laid out, which is what makes that
    safe; a name that told the six apart would be telling apart something
    no caller keeps.
    """
    return _fixture_root(
        scratch / f"{charter.stem}-{family}", root, charter, declaration, family
    )


def render_template_fixtures() -> int:
    """`convener-render-template-fixtures OUTPUT_DIR`: writes the pinned
    clearance check its input -- the three files `brand_templates` writes,
    rendered for every charter this repository holds crossed with every
    family `motifs` draws, plus a `manifest.json` and a copy of `fonts/`.

    The opposite number of `render_visual_fixtures` above in one respect
    and its twin in every other. That command renders one composition at
    three canvases and compares the pixels; this one renders three
    compositions at every charter and every family and measures whether
    any stroke crosses any word. Neither re-derives a page in JavaScript:
    both write the bytes and let `tools/visuals/` read them, which is
    D-14's own shape (the fixture is the boundary).

    **The cross product is the point.** A charter names one family, so a
    sweep over the charters alone would only ever exercise the drawings
    somebody has already chosen -- which is exactly how a family gets
    fitted to one committed layout by hand and nothing notices. Rendering
    every charter with every family asks the question a new family
    actually has to answer: not "does the ribbon still clear the words"
    but "does *this* drawing clear them, at every stroke weight and every
    string length this repository can produce". Neither side of the
    product is a list here: a family added to `motifs.FAMILIES` and a
    charter committed under `assets/brand/` are both swept the moment they
    exist, with no entry to add anywhere.

    Deterministic, and reads nothing an event changes: the templates carry
    `{{speaker.*}}` placeholders rather than a talk, so the same
    declaration and the same charter always produce the same bytes.
    """
    if len(sys.argv) != 2:
        print("usage: convener-render-template-fixtures OUTPUT_DIR", file=sys.stderr)
        return 1
    root = repo_root()
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as scratch:
        for label, charter, declaration in _template_charters(root):
            for family in sorted(motifs.FAMILIES):
                made = _template_fixture_root(
                    Path(scratch), root, charter, declaration, family
                )
                ratio = brand.motif_width_ratio(made)
                for template, render, width, height in _TEMPLATE_FILES:
                    name = f"{label}-{family}-{template}"
                    (out / f"{name}.svg").write_text(render(made), encoding="utf-8")
                    manifest.append(
                        {
                            "name": name,
                            "file": f"{name}.svg",
                            "charter": label,
                            "family": family,
                            "template": template,
                            "width": width,
                            "height": height,
                            "ratio": ratio,
                        }
                    )

    fonts_dest = out / "fonts"
    if fonts_dest.exists():
        shutil.rmtree(fonts_dest)
    shutil.copytree(root / "assets" / "fonts", fonts_dest)

    (out / "advances.json").write_text(
        json.dumps(
            {
                "light": typeface.LIGHT,
                "heavy": typeface.HEAVY,
                "em": {
                    character: {
                        str(weight): typeface.advance_em(character, weight=weight)
                        for weight in (typeface.LIGHT, typeface.HEAVY)
                    }
                    for character in map(chr, range(32, 127))
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(manifest)} template fixture(s) to {out}")
    return 0


def render_poster_fixtures() -> int:
    """`convener-render-poster-fixtures OUTPUT_DIR`: writes the poster
    sweep its input -- the composition `visual.py` generates, at every
    charter this repository holds crossed with every family `motifs` draws
    crossed with every canvas `formats.FORMATS` names.

    The third fixture command, and it exists because the other two each
    answer half of a question and neither answers this one.

    - `render_visual_fixtures` renders **one** charter, the example's, at
      three canvases, and the pinned reference images compare its pixels.
      That is a regression check on the drawing this product happens to
      ship, and it is deliberately blind to a duplicate's own charter --
      `visuals.yml`'s own path filter says so, and
      `test_visuals_workflow.py` holds it there. It could not sweep the
      cross product without either pinning ninety images or comparing
      none.
    - `render_template_fixtures` renders the cross product, of the three
      files a volunteer *downloads*. The poster the cockpit generates is
      not one of them.

    So the composition every duplicate actually publishes -- the one the
    cockpit writes for each event -- was measured at one charter and one
    family. `visual._motif_content_right_margin` pads `.content` (the
    "what to expect" copy and the speaker's photographic plate) with the
    clearance alone rather than with the drawing's own right-hand reach,
    on the argument that the ribbon's right side runs along the canvas
    edge over those rows. That argument is true of the ribbon and of the
    bracket, and it is an argument about two drawings rather than a
    property of any: a family with a deep right-hand drawing would paint
    across the speaker's frame in every duplicate's poster with every gate
    green. Every drawing this product ships is short on the right, and
    until this that was a coincidence rather than a rule.

    Same seam as the other two: this writes the bytes, `tools/visuals/`
    reads them, and neither re-derives a page in the other's language.
    `FIXTURE_ANNOUNCEMENT` is the same fixed, versioned identity the
    reference images use, for the same reason -- an invented speaker, no
    photograph, no clock, no network, so the same input always writes the
    same page.
    """
    if len(sys.argv) != 2:
        print("usage: convener-render-poster-fixtures OUTPUT_DIR", file=sys.stderr)
        return 1
    root = repo_root()
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as scratch:
        for label, charter, declaration in _template_charters(root):
            for family in sorted(motifs.FAMILIES):
                made = _template_fixture_root(
                    Path(scratch), root, charter, declaration, family
                )
                for fmt in formats.FORMATS:
                    name = f"{label}-{family}-{fmt.name}"
                    (out / f"{name}.html").write_text(
                        visual.render_announcement(
                            visual.FIXTURE_ANNOUNCEMENT,
                            width=fmt.width,
                            height=fmt.height,
                            root=made,
                        ),
                        encoding="utf-8",
                    )
                    manifest.append(
                        {
                            "name": name,
                            "charter": label,
                            "family": family,
                            "format": fmt.name,
                            "width": fmt.width,
                            "height": fmt.height,
                            "file": f"{name}.html",
                        }
                    )

    fonts_dest = out / "fonts"
    if fonts_dest.exists():
        shutil.rmtree(fonts_dest)
    shutil.copytree(root / "assets" / "fonts", fonts_dest)

    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(manifest)} poster fixture(s) to {out}")
    return 0


def _scheduled_announcements(rows: list[dict[str, Any]]) -> list[visual.Announcement]:
    """`public_data.to_public`'s own output, turned into the
    `visual.Announcement`s the production render needs -- never a
    second, looser read of the raw speaker record.

    Filtered to `status == "scheduled"`: an edition still being announced,
    the one state "a date locked" (the trigger's own language) describes.
    Routing through `to_public` first is what withholds a portrait under
    the consent gate with no second check written here -- see `visual.py`'s own module
    docstring, "Portrait", for why passing the gated projection through is
    "enough on its own".

    `photo_url` never becomes `portrait_data_uri` here, even on the rare
    row where `to_public` leaves it non-empty. Today that is close to
    unreachable for a *scheduled* row: `public_data.
    personal_disclosure_withheld`'s own docstring records that its gate is
    written to open only once a talk is archived and published, which is
    after the point an announcement is useful -- so a real, ordinarily
    written record never reaches this branch. But nothing stops a
    hand-edited file from setting `publication.outcome: published` on a
    still-`scheduled` row, and `docs/engineering/schema.md` calls
    `photo_url` "a link, not an upload": turning it into something
    `render_announcement` can inline would mean this command reaching onto
    the network for a URL a data file names, which it does not do. A row
    that does carry a consented one prints a visible notice instead of
    silently doing nothing about it (D-25) -- the alternative
    is a gap that looks identical to the common, legitimate case of
    "nothing to embed".
    """
    announcements: list[visual.Announcement] = []
    for row in rows:
        if row.get("status") != "scheduled":
            continue
        event_id = str(row.get("id", "")).lower()
        raw_date = str(row.get("date") or "")
        try:
            talk_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError(
                f"{row.get('id')!r}: scheduled but its date {raw_date!r} is "
                "not a valid YYYY-MM-DD -- instance/data/speakers.yml disagrees "
                "with its own validator"
            ) from exc
        if row.get("photo_url"):
            print(
                f"::notice::{event_id} has a consented photo_url but the "
                "production renderer does not embed a portrait yet -- "
                "rendering the no-portrait variant "
                "(see _scheduled_announcements's own docstring)",
                file=sys.stderr,
            )
        announcements.append(
            visual.Announcement(
                title=str(row.get("title", "")),
                talk_date=talk_date,
                speaker_name=str(row.get("speaker_name", "")),
                speaker_affiliation=str(row.get("speaker_affiliation", "")),
                event_id=event_id,
                portrait_data_uri=None,
            )
        )
    return announcements


def render_visuals() -> int:
    """`convener-render-visuals OUTPUT_DIR`: the disk-writing seam for
    *production* visuals -- real, scheduled editions read from
    `instance/data/speakers.yml`, through the same public gate every other public
    artefact in this project already goes through (`public_data.
    to_public`), never a second, looser read of the raw record.

    The opposite number of `render_visual_fixtures` above: that command
    always renders the one fixed, fictional identity a regression check
    needs and never touches `instance/data/speakers.yml` at all; this one renders
    *only* real, scheduled editions and touches nothing else. Zero
    scheduled editions is a normal, expected state (D-13) -- printed
    plainly, exit 0, an empty `manifest.json` -- not a failure; a
    malformed date on a record that claims to be scheduled is not, and
    fails loudly instead (D-25): `instance/data/speakers.yml` disagreeing with its
    own validator is a data defect this command must never render around
    quietly.

    Same discipline for `formats.qr_module_size_mm`: computed and checked
    here, against every real scheduled edition's own `event_id`, before
    anything is written -- `formats.py`'s own docstring proves the
    function correct but never calls it against real data, and
    `validate.validate_speakers` bounds `edition_code`'s length but only
    in the separate `convener-validate` command, which nothing requires this
    one to run first. An edition whose id is long enough to bump
    `registration_code_modules` past the point where a printed A4 poster's
    QR module drops below `formats.SCANNABLE_QR_MODULE_MM` fails loudly
    (D-25) instead of shipping a poster nobody can scan.

    This is also the "manual command" the trigger requires, independently
    of any workflow: `uv run --frozen --project tools convener-render-visuals
    OUTPUT_DIR` renders the current, real state of `instance/data/speakers.yml` on
    demand, from a plain checkout, no CI needed.

    Only touches the target directory once a valid state has actually been
    computed (mirrors `publish-showcase.yml`'s own "a build that cannot
    replace what it would remove must never be allowed to begin removing
    it"), and then regenerates it whole rather than accumulating into it
    (the same discipline `render_visual_fixtures`'s own `fonts/` handling
    and `register()` already apply): an edition no longer scheduled must
    not leave a stale page sitting next to a manifest that no longer lists
    it.
    """
    if len(sys.argv) != 2:
        print("usage: convener-render-visuals OUTPUT_DIR", file=sys.stderr)
        return 1
    root = repo_root()
    out = Path(sys.argv[1])

    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    try:
        announcements = _scheduled_announcements(to_public(speakers or []))
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    for announcement in announcements:
        module_mm = formats.qr_module_size_mm(formats.PRINT, announcement.event_id)
        if module_mm < formats.SCANNABLE_QR_MODULE_MM:
            print(
                f"::error::{announcement.event_id}: print QR module would be "
                f"{module_mm:.3f}mm, below the {formats.SCANNABLE_QR_MODULE_MM}mm "
                "scannable floor -- edition_code is too long for a printed "
                "A4 poster to stay scannable",
                file=sys.stderr,
            )
            return 1

    out.mkdir(parents=True, exist_ok=True)
    for stale_html in out.glob("*.html"):
        stale_html.unlink()
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()
    fonts_dest = out / "fonts"
    if fonts_dest.exists():
        shutil.rmtree(fonts_dest)

    manifest: list[dict[str, Any]] = []
    if not announcements:
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "no scheduled edition in instance/data/speakers.yml -- nothing to "
            "render (normal until a date is locked)"
        )
        return 0

    for announcement in announcements:
        for fmt in formats.FORMATS:
            html = visual.render_announcement(
                announcement, width=fmt.width, height=fmt.height, root=root
            )
            filename = f"{announcement.event_id}-{fmt.name}.html"
            (out / filename).write_text(html, encoding="utf-8")
            manifest.append(
                {
                    "event_id": announcement.event_id,
                    "name": fmt.name,
                    "width": fmt.width,
                    "height": fmt.height,
                    "file": filename,
                }
            )

    shutil.copytree(root / "assets" / "fonts", fonts_dest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {len(manifest)} production visual page(s) for "
        f"{len(announcements)} scheduled edition(s) to {out}"
    )
    return 0


def render_announcements() -> int:
    """`convener-render-announcements OUTPUT_DIR`: the disk-writing
    seam for the ready-to-publish texts (D-09) -- the forum announcement,
    the professional-network post, the mailing-list message, and the
    recording announcement, one Markdown file each, one subdirectory per
    edition (`OUTPUT_DIR/<event id>/<channel>.md`).

    The app (`app/`, D-15's "cockpit") already offers an authenticated
    operator the same four texts, filled in live from the record they have
    open, through `app/src/content/render.ts`'s gated `{{ public.… }}`
    vocabulary (`app/src/state/consent.ts::toPublicFields`). This command
    is the second, independent route to the identical four texts that
    needs no browser and no authenticated session -- `uv run --frozen --project
    tools convener-render-announcements OUTPUT_DIR` renders the current, real
    state of `instance/data/speakers.yml` on demand, from a plain checkout, exactly
    the same "manual command, independent of any workflow" property
    `render_visuals`'s own docstring states for the visuals.

    This command has a real
    consumer -- `.github/workflows/visuals-production.yml` runs it
    alongside `convener-render-visuals` and uploads both into the identical
    `announcement-visuals` artefact, one subdirectory per edition, so an
    operator downloads the poster and the words for the same talk
    together rather than hunting two separate places for them. The
    per-edition subdirectory (rather than a flat `<event id>-
    <channel>.txt` naming) is what makes that placement work without a
    merge step: `render-production.mjs` already writes each edition's
    images to `OUTPUT_DIR/<event id>/<format>.png` in that same artefact
    directory, so this command's own `<event id>/<channel>.md` lands
    alongside them, never colliding on a filename. `.md`, not `.txt`: the
    text this command now writes is a page's worth of Markdown (headings,
    emphasis, a volunteer's own working notes), not plain prose, because
    it is now `docs/handbook/toolkit/*.md` itself, rendered (`announce.py`'s own
    module docstring) -- the extension names what the file actually is.

    Routed through `public_data.to_public` before either rendering module
    ever sees a row (`announce.py`'s own module docstring) -- never a
    second, looser read of the raw record. A `scheduled` row gets its
    three promotional texts; an `archived` row gets a recording
    announcement only when `announce.recording_announcement` finds a
    `youtube_url` to announce, which is the ordinary, common state (D-13)
    until the speaker agrees and the board's own gate opens.

    Zero renderable editions is a normal state, printed plainly, exit 0 --
    the same "empty is normal" discipline `render_visuals` already
    applies. A malformed date on a record that claims to be scheduled or
    archived is not, and fails loudly instead (D-25).
    """
    if len(sys.argv) != 2:
        print("usage: convener-render-announcements OUTPUT_DIR", file=sys.stderr)
        return 1
    root = repo_root()
    out = Path(sys.argv[1])

    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    rows = to_public(speakers or [])

    out.mkdir(parents=True, exist_ok=True)
    for stale_text in out.glob("*/*.md"):
        stale_text.unlink()
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()

    manifest: list[dict[str, Any]] = []
    try:
        for row in rows:
            event_id = str(row.get("id", "")).lower()
            if not event_id:
                continue
            status = row.get("status")
            texts: dict[str, str] = {}
            if status == "scheduled":
                texts["forum"] = announce.forum_announcement(row, root=root)
                texts["network"] = announce.network_post(row, root=root)
                texts["mailing-list"] = announce.mailing_list_message(row, root=root)
            elif status == "archived":
                recording = announce.recording_announcement(row, root=root)
                if recording is not None:
                    texts["recording"] = recording
            for channel, text in texts.items():
                event_dir = out / event_id
                event_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{channel}.md"
                (event_dir / filename).write_text(text, encoding="utf-8")
                manifest.append(
                    {
                        "event_id": event_id,
                        "channel": channel,
                        "file": f"{event_id}/{filename}",
                    }
                )
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if not manifest:
        print(
            "no scheduled or announceable archived edition in "
            "instance/data/speakers.yml -- nothing to render (normal until a date "
            "is locked or a recording is published)"
        )
        return 0
    print(f"wrote {len(manifest)} announcement text(s) to {out}")
    return 0
