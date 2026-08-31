"""What a public repository has to carry, held against what it declares.

`test_notice.py` already pins the terms this software is under and the
notice both interfaces print. This module pins the other four things a
repository somebody else is expected to duplicate has to get right, and
each is pinned against a declaration rather than against a transcription.

1. **The edit list in `README.md` is derived from `config/boundary.yml`,
   not written beside it.** A hand-written list of "the files a duplicate
   edits" is the single most driftable sentence in the entry documentation:
   it is read on day one, it is never read again, and the day a path moves
   nothing tells it. So every path the README names has to be one the
   boundary declaration actually hands to the instance, and every path the
   declaration hands over has to be either named in the README or given a
   reason here for needing no edit. Adding an instance path and forgetting
   the README fails here; naming a product path in the README fails here;
   an exemption for a path that stopped being the instance's fails here
   too.

2. **`CITATION.cff` satisfies the Citation File Format's own required
   set.** The audience is academic, GitHub renders the file as a "Cite this
   repository" button and produces BibTeX from it, and a file missing a
   required key produces nothing at all -- silently, because GitHub simply
   does not draw the button. `REQUIRED_CFF_KEYS` and `CFF_KEYS` are the
   1.2.0 schema's own, and the file is checked against the licence this
   repository actually ships rather than against a string somebody typed
   twice.

3. **`SECURITY.md` keeps a private channel.** Without one, whoever finds a
   hole publishes it or gives up. The check is not that the file exists --
   a file saying "open an issue" would pass that -- but that it names the
   private route and that it still refuses to publish an address, which is
   the property that quietly erodes when somebody finds the private route
   inconvenient.

4. **`CONTRIBUTING.md` states what a contributor certifies, and the
   commit-message check keeps accepting it.** The Developer Certificate of
   Origin is not enforced automatically here, for the reason that file
   gives, so the failure mode is not "an unsigned commit lands" -- it is
   `commit_format` being tightened until a contributor's own
   `Signed-off-by` is refused as an attribution trailer. That is the half
   a test can hold, and it is held below.

And one thing that is not a document at all: **`.github/dependabot.yml`
watches every dependency tree this repository commits**. Six npm manifests
and one Python project are tracked; the file watched two of them, while
every one of the seven already gets an audit in continuous integration. A
manifest committed without an entry there is a tree nothing proposes to
update, and this module derives the answer from `git ls-files` so that the
next one cannot arrive unnoticed.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops.declaration import boundary
from convener_ops.declaration.paths import repo_root
from convener_ops.governance.commit_format import validate_messages

ROOT = repo_root()
README = ROOT / "README.md"
CITATION = ROOT / "CITATION.cff"
SECURITY = ROOT / "SECURITY.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
NOTICE = ROOT / "NOTICE.json"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"

# ------------------------------------------------------------------ #
# 1. The edit list.
# ------------------------------------------------------------------ #

#: The README heading the list sits under, and the fence its table ends at.
#: Named once so that renaming the section fails loudly here rather than
#: silently emptying the sweep below.
EDIT_LIST_HEADING: Final = "## What a duplicate edits"

#: A path the declaration hands to the instance that a duplicate still does
#: not have to edit before its first build, and why. Not an escape hatch:
#: every key has to be a path `config/boundary.yml` actually declares --
#: `test_no_exemption_survives_the_path_it_was_written_for` refuses a stale
#: one -- and the reason sits beside the path rather than in a document
#: nobody reads at the moment it matters. This is `test_second_instance.py`'s
#: `DELIBERATELY_ABSENT` applied to the other question: not "why does the
#: example ship no counterpart" but "why does a duplicate need no edit".
NOT_EDITED: Final[dict[str, str]] = {
    "instance/actions-budget.yml": (
        "Numbers rather than identity: an organisation's Actions allowance "
        "and how busy the series gets. The shipped values are the GitHub "
        "Free plan's own and a ceiling-derived guess at the rest, so they "
        "work on day one and are meant to be re-cut against real "
        "measurements later. The file says so itself."
    ),
    "instance/queue-drain.yml": (
        "One threshold, whose admissible range is derived from the drain's "
        "own cron and from instance/registration-lanes.yml -- so the shipped "
        "value is inside its own bounds by construction, and a duplicate "
        "that never touches it is never wrong."
    ),
    "instance/registration-lanes.yml": (
        "The distance to an event at which a registration stops queueing. "
        "A statement about a series' rhythm, with a working default; "
        "getting it wrong routes a submission to the slower lane and "
        "nothing else."
    ),
    "docs/handbook/governance/register.md": (
        "Declared `regenerated: true`: a total re-rendering of one "
        "repository's own commit history, rewritten in full by a scheduled "
        "job on every push. A duplicate inherits upstream's and its own "
        "next push replaces it, so editing it would be editing a generated "
        "file."
    ),
    "instance/keys/": (
        "Empty of keys in a fresh duplicate and in this repository alike. "
        "Generating an event key or a signing key is an operator's act "
        "performed by a command, never a file anybody types."
    ),
    "instance/public-data/": (
        "Derived from instance/data/ by the product's own commands and committed by "
        ".github/workflows/deploy.yml. Empty in a fresh clone by "
        "construction; a duplicate that authored something here would be "
        "authoring a projection of its own input."
    ),
}

#: The one instance path the README must *not* name, and the reason it is
#: singled out rather than left to `NOT_EDITED`: the product ships a
#: palette and a motif of its own, so a duplicate builds a finished-looking
#: site without providing any design file at all. That is a property of the
#: repository (`brand/convener/brand.json` exists and is the product's), not
#: an opinion, so the two are asserted together below.
CHARTER = "instance/data/brand.json"
PRODUCT_CHARTER = Path("brand") / "convener" / "brand.json"


def _boundary() -> boundary.Boundary:
    return boundary.load(ROOT)


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _unwrapped(path: Path) -> str:
    """One page's text with its line wrapping taken out, so that a
    sentence this module looks for is found whichever column the prose
    happens to break at. Reflowing a paragraph must not be able to turn a
    check off."""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _edit_list_section() -> str:
    """The README section the list lives in, from its heading to the next
    one of the same level. Sliced rather than searched over the whole file:
    a path mentioned in some other section is not a path on the list."""
    text = _readme()
    assert EDIT_LIST_HEADING in text, (
        f"{README.name} no longer carries a {EDIT_LIST_HEADING!r} section, "
        "so nothing here reads the list a duplicate is told to edit"
    )
    after = text.split(EDIT_LIST_HEADING, 1)[1]
    return after.split("\n## ", 1)[0]


def _listed_paths() -> list[str]:
    """The paths in the section's table: the first cell of every row, which
    the README writes in backticks. Read out of the table rather than out
    of the prose, because the prose around it names product paths on
    purpose (the boundary declaration, the example instance) and a sweep
    that could not tell the two apart would be asserting nothing."""
    found = []
    for line in _edit_list_section().splitlines():
        if not line.startswith("| `"):
            continue
        cell = line.split("|")[1].strip()
        match = re.fullmatch(r"`([^`]+)`", cell)
        if match:
            found.append(match.group(1))
    return found


def test_the_readme_actually_lists_something() -> None:
    # The guard against every sweep below passing vacuously because the
    # table was reformatted into prose.
    assert _listed_paths(), (
        f"{README.name}'s {EDIT_LIST_HEADING!r} table names no path, so "
        "every check in this module would pass on an empty list"
    )


def test_every_path_the_readme_tells_a_duplicate_to_edit_is_the_instances() -> None:
    """A README that told a duplicate to edit a product file would be
    telling it to fork: upstream writes that file, and the next merge is a
    conflict. The declaration is the authority, so this asks it rather than
    a reader's memory."""
    declared = _boundary()
    product = [
        path for path in _listed_paths() if declared.owner_of(path) != boundary.INSTANCE
    ]
    assert product == [], (
        f"{README.name} tells a duplicate to edit {product}, which "
        f"{boundary.DECLARATION_PATH.as_posix()} does not hand to the "
        "instance. Either the boundary is wrong or the list is."
    )


def test_every_path_the_boundary_hands_over_is_listed_or_exempt() -> None:
    """The other direction, and the one that actually catches drift: a new
    instance path arriving in the declaration and nobody remembering the
    README. Answered by being on the list, by being covered by something on
    the list (`instance/data/` is answered by `instance/data/config.yml`),
    or by an entry in `NOT_EDITED` carrying its reason."""
    declared = _boundary()
    listed = _listed_paths()
    unanswered = []
    for path in declared.instance_paths:
        if path in listed or path in NOT_EDITED:
            continue
        if path.endswith("/") and any(name.startswith(path) for name in listed):
            continue
        unanswered.append(path)
    assert unanswered == [], (
        f"{boundary.DECLARATION_PATH.as_posix()} hands {unanswered} to the "
        f"instance and {README.name} says nothing about them. Put each on "
        "the list, or state in NOT_EDITED why a duplicate needs no edit "
        "there."
    )


def test_no_exemption_survives_the_path_it_was_written_for() -> None:
    """A reason for a path the declaration no longer hands over is a reason
    for nothing, and it would go on quietly excusing the README from
    mentioning a path that had become the product's."""
    declared = set(_boundary().instance_paths)
    stale = sorted(path for path in NOT_EDITED if path not in declared)
    assert stale == [], (
        f"NOT_EDITED still explains why {stale} needs no edit, and "
        f"{boundary.DECLARATION_PATH.as_posix()} no longer hands it to the "
        "instance"
    )


def test_the_charter_is_not_something_a_duplicate_has_to_write() -> None:
    """The product ships a palette *and* a motif, so a duplicate builds
    without providing a design file. Both halves are asserted: the README
    must not put the charter on the list, and the default it would fall
    back to must exist. Deleting `brand/convener/brand.json` and leaving
    the README alone would otherwise turn a documented convenience into a
    build that fails on a fresh duplicate."""
    assert CHARTER not in _listed_paths(), (
        f"{README.name} now tells a duplicate to write {CHARTER}. The "
        f"product ships {PRODUCT_CHARTER.as_posix()} precisely so that it "
        "does not have to -- see D-16."
    )
    assert (ROOT / PRODUCT_CHARTER).is_file(), (
        f"{PRODUCT_CHARTER.as_posix()} is gone, so an instance that writes "
        f"no {CHARTER} has no palette to fall back to and the README's list "
        "is a file short"
    )


def test_the_list_is_short_enough_to_be_read() -> None:
    """The separation is only real if it is small. Four files or more and
    the honest thing to do is fix the boundary, not lengthen the README:
    "a duplicate edits a short list" stops being true long before anybody
    edits the sentence that says it."""
    listed = _listed_paths()
    assert len(listed) <= 3, (
        f"{README.name} now asks a duplicate to edit {len(listed)} files "
        f"({listed}). Past three, the instance/product separation has "
        "failed and the fix is in config/boundary.yml, not here."
    )


# ------------------------------------------------------------------ #
# 2. The citation.
# ------------------------------------------------------------------ #

#: Citation File Format 1.2.0's own required set, from its published schema
#: (https://github.com/citation-file-format/citation-file-format,
#: `schema.json`). Four keys, and a file missing one produces no "Cite this
#: repository" button at all rather than a broken one.
REQUIRED_CFF_KEYS: Final = frozenset({"authors", "cff-version", "message", "title"})

#: Every key that schema allows at the top level. It declares
#: `additionalProperties: false`, so anything outside this set makes the
#: file invalid -- and invalid here is silent, which is why it is pinned
#: rather than trusted.
CFF_KEYS: Final = frozenset(
    {
        "abstract",
        "authors",
        "cff-version",
        "commit",
        "contact",
        "date-released",
        "doi",
        "identifiers",
        "keywords",
        "license",
        "license-url",
        "message",
        "preferred-citation",
        "references",
        "repository",
        "repository-artifact",
        "repository-code",
        "title",
        "type",
        "url",
        "version",
    }
)

#: The version this file declares. The schema pins it exactly (`^1\\.2\\.0$`),
#: so this is not a floor.
CFF_VERSION: Final = "1.2.0"

#: The SPDX identifier for the terms this repository ships. `LICENSE` is the
#: AGPL version 3 and the notice says "version 3 or later", so the
#: `-or-later` form is the one that matches; `AGPL-3.0-only` would say
#: something the notice does not.
LICENCE_IDENTIFIER: Final = "AGPL-3.0-or-later"


def _citation() -> dict[str, Any]:
    loaded = yaml.safe_load(CITATION.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{CITATION.name} is not a mapping"
    return loaded


def test_the_citation_carries_every_key_the_format_requires() -> None:
    data = _citation()
    missing = sorted(REQUIRED_CFF_KEYS - set(data))
    assert missing == [], (
        f"{CITATION.name} is missing {missing}, which Citation File Format "
        f"{CFF_VERSION} requires. GitHub does not report an invalid file -- "
        "it stops drawing the 'Cite this repository' button, and nothing "
        "else changes."
    )
    assert data["cff-version"] == CFF_VERSION
    for key in ("message", "title"):
        assert isinstance(data[key], str) and data[key].strip(), key


def test_the_citation_carries_no_key_the_format_does_not_know() -> None:
    unknown = sorted(set(_citation()) - CFF_KEYS)
    assert unknown == [], (
        f"{CITATION.name} carries {unknown}, and the schema declares "
        "`additionalProperties: false` -- one unknown key invalidates the "
        "whole file"
    )


def test_the_citation_names_the_copyright_holder_the_notice_names() -> None:
    """Two files state an authorship, and they must not be able to
    disagree: `NOTICE.json`'s copyright line is what both interfaces print
    in their footer, and this is what a citation of the software renders
    to. One name, spelled once, checked against the other."""
    authors = _citation()["authors"]
    assert isinstance(authors, list) and authors, f"{CITATION.name}: no authors"
    named = []
    for author in authors:
        assert isinstance(author, dict)
        given = author.get("given-names", "")
        family = author.get("family-names", "")
        assert given and family, (
            f"{CITATION.name} has an author with no given or family name; "
            "GitHub renders a citation from these two fields"
        )
        named.append(f"{given} {family}")
    copyright_line = json.loads(NOTICE.read_text(encoding="utf-8"))["copyright"]
    unmatched = [name for name in named if name not in copyright_line]
    assert unmatched == [], (
        f"{CITATION.name} credits {unmatched}, and {NOTICE.name}'s "
        f"copyright line reads {copyright_line!r}. A citation that credits "
        "somebody the notice does not is one of the two wrong."
    )


def test_the_citation_declares_the_licence_this_repository_ships() -> None:
    """A citation carrying the wrong licence identifier is worse than one
    carrying none: it is machine-readable, and aggregators read it."""
    assert _citation().get("license") == LICENCE_IDENTIFIER, (
        f"{CITATION.name} must declare `license: {LICENCE_IDENTIFIER}` -- "
        "LICENSE is the GNU Affero General Public License version 3 and "
        "NOTICE.json says 'version 3 or later'"
    )


# ------------------------------------------------------------------ #
# 3. The security channel.
# ------------------------------------------------------------------ #

#: What "a private channel" has to be named as for this file to have one.
#: GitHub's own wording, because that is the button a reporter is looking
#: for; a page that described the idea without naming the control leaves
#: them hunting.
PRIVATE_CHANNEL: Final = ("Report a vulnerability", "advisory")

#: An address-shaped string. `SECURITY.md` deliberately carries none, for
#: the reason `TRADEMARK.md` already gives for its own: the page is
#: published, and a published address is one more thing for a scraper to
#: collect. The private advisory is the address.
_EMAIL_RE: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def test_the_security_page_names_a_private_route() -> None:
    text = _unwrapped(SECURITY)
    for phrase in PRIVATE_CHANNEL:
        assert phrase.lower() in text.lower(), (
            f"{SECURITY.name} no longer names {phrase!r}. Whoever finds a "
            "hole and has nowhere private to put it publishes it or gives "
            "up, and this file exists to make neither necessary."
        )


def test_the_security_page_publishes_no_address() -> None:
    found = sorted(set(_EMAIL_RE.findall(SECURITY.read_text(encoding="utf-8"))))
    assert found == [], (
        f"{SECURITY.name} now publishes {found}. The private advisory is "
        "this page's address, deliberately -- see TRADEMARK.md for the same "
        "decision taken for the same reason."
    )


def test_the_security_page_promises_no_response_time() -> None:
    """The support expectation, on the page where it is load-bearing. A
    published acknowledgement window that one unpaid maintainer cannot
    honour teaches every later reporter that nothing on this page means
    anything."""
    assert "no response time is promised" in _unwrapped(SECURITY).lower(), (
        f"{SECURITY.name} no longer says that no response time is promised. "
        "Either it now promises one and can keep it, or the sentence went "
        "missing."
    )


# ------------------------------------------------------------------ #
# 4. What a contributor certifies.
# ------------------------------------------------------------------ #

#: The certificate itself, and where it is published. Named rather than
#: reproduced: `CONTRIBUTING.md` sends a contributor to the text they are
#: certifying, and a paraphrase kept in this repository would be a second
#: home for somebody else's document.
DCO_URL: Final = "https://developercertificate.org"
SIGN_OFF: Final = "Signed-off-by"


def test_contributing_states_what_a_sign_off_certifies() -> None:
    text = _unwrapped(CONTRIBUTING)
    for needle in (SIGN_OFF, DCO_URL, "Developer Certificate of Origin"):
        assert needle in text, (
            f"{CONTRIBUTING.name} no longer names {needle!r}. A sign-off "
            "nobody can read the terms of certifies nothing."
        )
    for needle in ("no form to sign", "no copyright to assign"):
        assert needle in text, (
            f"{CONTRIBUTING.name} no longer says there is {needle!r}. That "
            "is the half of this which would otherwise cost an academic "
            "contributor a trip to a legal office, and it is what makes "
            "the right asked below proportionate rather than a contributor "
            "licence agreement by another name."
        )


def test_the_separate_licence_is_offered_and_its_condition_is_stated() -> None:
    """Both halves, because either alone is misleading.

    A holder who is the sole author of every line can licence the work
    again, on terms the public licence does not carry, to somebody the
    public licence does not suit. That stops being true the moment part
    of the work belongs to somebody else, and under a certificate of
    origin every contributor keeps their own copyright.

    So `README.md` makes the offer and `CONTRIBUTING.md` states what
    ends it. The offer without the condition would outlive the fact that
    made it possible; the condition without the offer would explain the
    cost of something nobody was told about.
    """
    assert "a separate licence can be negotiated" in _unwrapped(README), (
        f"{README.name} no longer offers a licence other than the public "
        "one. Nobody who needs different terms can tell that asking is a "
        "route rather than an imposition."
    )
    contributing = _unwrapped(CONTRIBUTING)
    for needle, why in (
        (
            "right to license your contribution under terms other than",
            "the grant that keeps the offer possible after a first merge",
        ),
        (
            "non-exclusive",
            "the one word that makes the grant a permission rather than a "
            "surrender of the contributor's own copyright",
        ),
        (
            "the copyright stays yours",
            "that word said again in words a contributor reads without a "
            "lawyer, which is what stops the grant reading as a transfer",
        ),
        (
            "expect to be asked to say so in the pull request",
            "the explicit confirmation a substantial contribution gets, "
            "because a paragraph nobody read is weaker evidence than a "
            "sentence its author wrote",
        ),
    ):
        assert needle in contributing, (
            f"{CONTRIBUTING.name} no longer carries {needle!r} -- {why}."
        )


def test_contributing_states_the_support_expectation() -> None:
    assert "No response is guaranteed" in _unwrapped(CONTRIBUTING), (
        f"{CONTRIBUTING.name} no longer says that no response is "
        "guaranteed. An unanswered issue under a page that implied one is "
        "worse than an unanswered issue under a page that did not."
    )


def test_a_contributors_sign_off_is_not_read_as_an_attribution_trailer() -> None:
    """The half of the Developer Certificate of Origin that a test can
    hold.

    Nothing enforces the sign-off automatically -- `CONTRIBUTING.md` gives
    the reason, and it is that `convener-check-commits` reads every commit
    in a range including the ones a scheduled job wrote, and a certificate
    of origin signed by a job is a false certificate. What that leaves is
    the opposite failure, which is silent: `commit_format` refuses
    `co-authored-by:` and `signed-off-by: claude` on every message, and a
    later tightening of those patterns to a bare `signed-off-by:` would
    reject every contribution this project asks for, in a check nobody
    would think to look at.
    """
    signed = (
        "docs: fix a broken link\n\nSigned-off-by: Jane Developer <jane@example.test>"
    )
    assert validate_messages([signed]) == [], (
        "convener-check-commits now rejects a contributor's own "
        f"{SIGN_OFF} line. CONTRIBUTING.md asks for one on every commit; "
        "the two cannot both be right."
    )


# ------------------------------------------------------------------ #
# 5. Which dependency trees are watched.
# ------------------------------------------------------------------ #

#: How a manifest names its ecosystem in `.github/dependabot.yml`. Only the
#: two this repository actually commits: adding a third language would mean
#: adding it here, which is the point -- a tree in a language nobody
#: enumerated is a tree nothing watches.
ECOSYSTEM_MANIFESTS: Final[dict[str, tuple[str, ...]]] = {
    "npm": ("package.json",),
    "uv": ("pyproject.toml",),
}


def _tracked() -> list[str]:
    listing = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return listing.splitlines()


def _manifest_directories(ecosystem: str) -> set[str]:
    """Every tracked directory holding a manifest of that ecosystem, in the
    leading-slash form `dependabot.yml` writes -- `/` for the root."""
    names = ECOSYSTEM_MANIFESTS[ecosystem]
    found = set()
    for path in _tracked():
        parts = path.rsplit("/", 1)
        if parts[-1] not in names:
            continue
        found.add("/" + parts[0] if len(parts) > 1 else "/")
    return found


def _watched(ecosystem: str) -> set[str]:
    """Every directory `.github/dependabot.yml` watches for that ecosystem,
    reading both spellings the format allows -- `directory:` for one and
    `directories:` for a list."""
    declared = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    assert declared["version"] == 2, f"{DEPENDABOT.name} is not a version 2 config"
    watched: set[str] = set()
    for entry in declared["updates"]:
        if entry.get("package-ecosystem") != ecosystem:
            continue
        single = entry.get("directory")
        if isinstance(single, str):
            watched.add(single)
        many = entry.get("directories")
        if isinstance(many, list):
            watched.update(str(name) for name in many)
    return watched


def test_every_tracked_dependency_tree_is_watched() -> None:
    """Derived from `git ls-files`, so the next manifest committed without
    an entry fails here.

    Every one of these trees already gets an audit on the way in -- `npm
    audit` in `quality.yml` for `app/`, `site/` and the three relays, in
    `visuals.yml` and `visuals-production.yml` for `tools/visuals/`, `pip-audit`
    for `tools/`. An audit that reports a vulnerable package while nothing
    proposes the pull request replacing it is half a control: the finding
    arrives, and then it stays.
    """
    unwatched = {
        ecosystem: sorted(_manifest_directories(ecosystem) - _watched(ecosystem))
        for ecosystem in ECOSYSTEM_MANIFESTS
    }
    unwatched = {key: value for key, value in unwatched.items() if value}
    assert unwatched == {}, (
        f"{DEPENDABOT.name} does not watch {unwatched}. Each of those "
        "directories holds a tracked manifest whose tree continuous "
        "integration already audits, so a vulnerability found there has "
        "nothing to fix it."
    )


def test_nothing_is_watched_that_is_not_there() -> None:
    """The other direction: a directory that stopped holding a manifest.
    Dependabot reports it as a configuration error on the repository's own
    settings page, where nobody looks, and goes on watching the rest."""
    phantom = {
        ecosystem: sorted(_watched(ecosystem) - _manifest_directories(ecosystem))
        for ecosystem in ECOSYSTEM_MANIFESTS
    }
    phantom = {key: value for key, value in phantom.items() if value}
    assert phantom == {}, (
        f"{DEPENDABOT.name} watches {phantom}, where no tracked manifest sits any more"
    )


def test_the_reason_a_duplicate_turns_this_off_is_written_down() -> None:
    """An instance inherits this file, and every manifest it names is the
    product's. A duplicate whose Dependabot bumps a lockfile has edited a
    product file and bought a monthly conflict, so the reason to switch it
    off has to be in the file itself and not in whoever wrote it."""
    text = DEPENDABOT.read_text(encoding="utf-8")
    assert "boundary.yml" in text and "duplicate" in text, (
        f"{DEPENDABOT.name} no longer says what a duplicate does with it. "
        "The file is inherited; the instruction has to be inherited too."
    )
