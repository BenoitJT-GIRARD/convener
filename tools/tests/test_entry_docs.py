"""`README.md` and `docs/architecture.md` are the entry documentation a
newcomer reads first (phase 5 spec Section 8, task 14). Properties are
pinned here rather than trusted by inspection:

1. Every relative Markdown link the two files carry resolves to a real
   file in this repository -- and, if the target sits under `docs/`, to a
   page `app/src/content/registry.ts` actually publishes, or to one of the
   two pages that file's own tests already name as deliberately
   unregistered (`app/tests/copy-handbook.test.ts`). README.md and
   docs/architecture.md are not registered pages themselves, so nothing
   already checks their own outbound links the way
   `app/tests/registered-links.test.ts` checks a registered page's.
2. `docs/reference/operations.md` -- documents every secret this project
   uses and is deliberately excluded from the app's public bundle -- is
   named by these two files *in prose, never as a clickable link*, this
   repository's own convention for a path a reader should not be led to
   follow. `INFORMATION-ARCHITECTURE.md` and `site/README.md` already use
   this same convention; this test holds the pair to it too.
3. The published architecture decision records
   (`docs/decisions/index.md`) are a real link from at least one of the
   two files, not merely named -- the working register they were edited
   from stays under `docs/superpowers/`, which never ships, but the edited
   records do, so a reader must be able to click through to them.

Every check is a sweep over the two files' own text, not a fixed list of
links transcribed by hand: a link added later that breaks any rule fails
here on its own.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
from pathlib import Path

from convener_ops.paths import repo_root

ROOT = repo_root()
README = ROOT / "README.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"
REGISTRY_TS = ROOT / "app" / "src" / "content" / "registry.ts"
DOCS = ROOT / "docs"

#: `docs/index.md` and `docs/README.md` are real, deliberately unregistered
#: pages meant for a reader browsing the repository itself, not the app --
#: see `app/tests/copy-handbook.test.ts`'s own test naming them.
#: `docs/architecture.md`, this same task's own second file, joins them for
#: the identical reason (and lets README.md link to it). Anything else
#: under `docs/` must be in the registry to be a safe link target.
UNREGISTERED_BUT_SAFE = {"index.md", "README.md", "architecture.md"}

#: The path this repository's own convention names in prose rather than as
#: a link -- see `INFORMATION-ARCHITECTURE.md` and `site/README.md` for the
#: precedent.
OPERATIONS_REFERENCE = "docs/reference/operations.md"

#: The published form of the decision register -- see
#: `docs/decisions/index.md` itself, and `docs/superpowers/mise-en-ligne.md`
#: Section 1 for why an edited copy exists at all.
DECISIONS_INDEX = "docs/decisions/index.md"

_LINK_RE = re.compile(r"\]\(([^)]+)\)")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)


def _local_links(text: str) -> list[str]:
    """Markdown links in `text` that stay inside this repository: no URL
    scheme (so not `https:` or `mailto:`) and not a same-page `#anchor`."""
    links = []
    for href in _LINK_RE.findall(text):
        if _SCHEME_RE.match(href):
            continue
        if href.startswith("#"):
            continue
        links.append(href)
    return links


def _target(from_file: Path, href: str) -> tuple[Path, str | None]:
    """Where `href`, written inside `from_file`, points: the file, and the
    `#anchor` fragment if it carries one."""
    path_part, _, anchor = href.partition("#")
    target = (from_file.parent / path_part).resolve()
    return target, (anchor or None)


def _slugify(heading: str) -> str:
    """GitHub's own heading-to-anchor rule, the part of it that matters for
    the plain ASCII headings this project writes: lower-case, spaces to
    hyphens, everything but a word character or a hyphen dropped."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    return re.sub(r"[\s]+", "-", slug)


def _headings(text: str) -> set[str]:
    return {
        _slugify(m.group(1))
        for m in re.finditer(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)
    }


def _registered_docs_files() -> set[str]:
    """Every `file:` this project's own content registry names -- the same
    text `registry.ts` itself is read as by `app/scripts/handbook-registry.mjs`."""
    text = REGISTRY_TS.read_text(encoding="utf-8")
    return set(re.findall(r"file:\s*'([^']+)'", text))


def test_the_two_files_actually_contain_at_least_one_local_link() -> None:
    # A guard against the sweep below passing vacuously because nobody
    # wrote a link at all -- the same shape `registered-links.test.ts`
    # puts on its own sweep.
    total = sum(
        len(_local_links(p.read_text(encoding="utf-8"))) for p in (README, ARCHITECTURE)
    )
    assert total > 0


def test_every_local_link_resolves_to_a_real_file() -> None:
    broken = []
    for source in (README, ARCHITECTURE):
        text = source.read_text(encoding="utf-8")
        for href in _local_links(text):
            target, _ = _target(source, href)
            if not target.is_file():
                broken.append(f"{source.name} -> {href}")
    assert broken == []


def test_every_local_anchor_names_a_real_heading() -> None:
    broken = []
    for source in (README, ARCHITECTURE):
        text = source.read_text(encoding="utf-8")
        for href in _local_links(text):
            target, anchor = _target(source, href)
            if anchor is None:
                continue
            heading_text = (
                target.read_text(encoding="utf-8") if target.is_file() else ""
            )
            if anchor not in _headings(heading_text):
                broken.append(f"{source.name} -> {href}")
    assert broken == []


def test_a_docs_link_targets_a_published_page_or_a_known_safe_one() -> None:
    registered = _registered_docs_files()
    broken = []
    for source in (README, ARCHITECTURE):
        text = source.read_text(encoding="utf-8")
        for href in _local_links(text):
            target, _ = _target(source, href)
            try:
                rel = target.relative_to(DOCS).as_posix()
            except ValueError:
                continue  # not under docs/ at all -- a different check covers it
            if rel in UNREGISTERED_BUT_SAFE:
                continue
            if rel not in registered:
                broken.append(f"{source.name} -> {href}")
    assert broken == []


def test_the_entry_docs_link_to_the_decisions_index() -> None:
    # mise-en-ligne.md Section 2: once the architecture decision records
    # exist in their published form, README.md and docs/architecture.md
    # must *link* to them, not merely name the private working register
    # they were edited from -- naming without a link was only ever right
    # while nothing published existed yet to point at.
    target = (ROOT / DECISIONS_INDEX).resolve()
    linked = False
    for source in (README, ARCHITECTURE):
        text = source.read_text(encoding="utf-8")
        for href in _local_links(text):
            candidate, _ = _target(source, href)
            if candidate == target:
                linked = True
    assert linked
    assert (ROOT / DECISIONS_INDEX).is_file()


def test_the_operations_reference_is_named_not_linked_and_real() -> None:
    # docs/reference/operations.md documents every secret this project
    # uses and is deliberately excluded from the app's public bundle
    # (app/tests/copy-handbook.test.ts) -- named, never linked, the same
    # convention as the decision register above.
    combined = README.read_text(encoding="utf-8") + ARCHITECTURE.read_text(
        encoding="utf-8"
    )
    assert OPERATIONS_REFERENCE in combined
    assert f"]({OPERATIONS_REFERENCE})" not in combined
    assert (ROOT / OPERATIONS_REFERENCE).is_file()


def test_the_diagram_carries_the_personal_data_lifecycle() -> None:
    # Spec Section 8's own acceptance test: "a reader must see in one
    # image where an address lives and when it disappears." This does not
    # execute the mermaid renderer (that would be a network call to fetch
    # one, on every test run, for a static diagram) -- it was rendered and
    # visually checked once by hand instead (task 14's own report records
    # that). What is pinned here is the regression a silent future edit
    # could actually cause: exactly one fenced mermaid block, that closes,
    # and that still names the two repositories, the encrypted store, the
    # per-event key, and the 90-day window -- the parts of the diagram
    # this criterion is actually about.
    # Exactly one mermaid block -- the file also carries ordinary ```bash
    # fences (the Contributing section), so counting every ``` fence in
    # the file would not tell this apart from those.
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert text.count("```mermaid") == 1
    block = text.split("```mermaid", 1)[1].split("```", 1)[0]
    for label in (
        "example-cockpit",
        "example-showcase",
        "registrations.enc",
        "CONVENER_EVENT_KEY_",
        "90 days after the event",
        "nothing can decrypt it",
    ):
        assert label in block, label


#: The two prefixes that name this project's own working record: the
#: tracked half (specifications, plans, phase reviews, the inventory) and
#: the untracked half (`.gitignore` keeps it out of every clone). Neither
#: exists for a reader who did not write them -- one because
#: `convener_ops.derivation_guard.KEPT_BACK` never lets it leave, the
#: other because it was never in a clone at all.
WORKING_RECORD = ("docs/superpowers/", ".superpowers/")


def _shipping_markdown() -> list[Path]:
    """Every tracked Markdown page except the working record itself."""
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [
        ROOT / name
        for name in listed
        if not name.startswith("docs/superpowers/") and (ROOT / name).is_file()
    ]


def test_no_shipping_page_names_this_project_s_own_working_record() -> None:
    """Phase 12, task 6.

    `app/tests/decisions-records.test.ts` already holds this of
    `docs/decisions/`: a published record may not send a reader into
    `docs/superpowers/`, because that directory never leaves this
    repository. The same sentence is true of every other page that ships,
    and nothing held them to it -- so `README.md` and `docs/README.md`
    both pointed a public reader at a design specification that will not
    exist in the derived repository, `site/README.md` at a decision whose
    published form sits in `docs/decisions/`, and
    `docs/reference/operations.md` at four such paths plus one under
    `.superpowers/`, which `.gitignore` keeps out of *every* clone and
    which was therefore already unfollowable here.

    Prose or link makes no difference: none of those five was a link, and
    every one of them was a dead end for the reader who met it.
    """
    offending = {
        path.relative_to(ROOT).as_posix(): prefix
        for path in _shipping_markdown()
        for prefix in WORKING_RECORD
        if prefix in path.read_text(encoding="utf-8")
    }
    assert not offending, (
        f"{sorted(offending)} name this project's own working record, which "
        "no reader of the published repository has. Say the fact, or point "
        "at the published form of it under docs/decisions/."
    )
