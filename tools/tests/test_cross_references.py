"""A cross-reference must name something a reader of this repository can open.

`app/tests/registered-links.test.ts` already refuses a registered page that
links to a page this repository does not publish. This module applies the
identical test to the *other* way a comment points somewhere: not a link, an
identifier or a coordinate. `D-19`, `phase 8, task 3, change E`, `R-27`,
`H4 (2026-08-23 security audit)`, `Minor 2 (fix round 1, task 16)` all read
as citations. Only the first of them resolves.

This is more visible than a commit message. Anybody reading the source meets
it in almost every file, and every one that resolves to nothing costs a
reader the same thing: they go looking, and there is nothing there.

**What resolves, derived rather than listed**
=============================================
Four vocabularies, each read from the repository at run time:

* **`D-NN`** -- the architecture decision records. Derived from the
  filenames under `docs/decisions/`, which is published, registered in
  `app/src/content/registry.ts` and served through the handbook. Adding
  `docs/decisions/d-29-….md` makes `D-29` citable, on its own, with nothing
  here to edit.
* **`T-N`** -- the event journey's countdown, "T minus N days". Not a
  document at all: `app/src/state/phases.ts` establishes the notation in its
  own milestone keys (`scheduled/T-14/zoom-link`), and prose that says
  "around T-6 weeks" is using it. `_countdown_notation_exists` reads those
  keys, so the exemption disappears the day the notation does.
* **`<prefix>-N`** -- an edition code. Derived from the `edition_prefix`
  every tracked `instance/config.json` declares, so `MRG-05` and `MRG-1` resolve
  because two instances in this repository say those prefixes are theirs.
* **`G-NN`** -- a governance rule. Derived from the pages under `docs/`
  that state the rules, each of which *titles* the rule with its number:
  `## Inactivity (G-09)` in `docs/reference/operations.md`, `### The bar
  (G-01)` in `docs/governance/board-rules.md`, `**Declaring an absence
  (G-04)**` opening its own paragraph on that same page. Writing a new
  rule and titling it is what makes its number citable; there is nothing
  here to edit.

And one category that is not this project's at all: a **public standard**
(`UTF-8`, `SHA-256`, `AES-256`, `P-256`, `RFC-822`). Naming one is not a
cross-reference into this repository; a reader looks it up the same way
anybody does. That is why it is a category and not an allowlist of
coordinates -- the rule this module holds is about identifiers *this
project* invents.

**What does not resolve**
=========================
Everything else in the shape `X-NN`, and the phrases below. A phrase is
refused for a reason this module derives too: `published_page_titles` reads
the first heading of every published page under `docs/`, and a coordinate
resolves only if some page bears that name.

That derivation is exactly what separates the two meanings of one word.
`docs/workflow/3-hosting.md` opens `# Phase 3 — Hosting day`, so
"[Phase 3 — Hosting day](../workflow/3-hosting.md)" resolves and stays;
"phase 8, task 3" names a plan this repository never publishes, and goes.
**The limit of that, stated rather than left to be discovered:** the event
journey has four phases, so a *construction* phase numbered 1 to 4 would
pass this check. Five upwards, and every `task N`, `round N`, `wave N`,
`Minor N`, `Critical A` and `change D`, are refused outright, because no
published page bears any of those names.

**A second limit, and this one is a hole rather than a trade.**
`COORDINATE` matches inside a single line. A citation split across a
comment's own line break -- `(task` ending one line, `// 16 ruling 1)`
opening the next -- reads as one citation to a person and as two unrelated
fragments to this sweep. One such split existed in this repository and was
rewritten by hand. Closing the hole means joining a comment's lines before
matching, which makes a candidate of every sentence that happens to end in
a number, so it is left open. It is written here rather than left to be
discovered, because somebody adding a citation should know this check can
miss one.

**A rule is declared where a page titles it, cited everywhere else.**
`G-NN` is the one vocabulary of the four that is not one identifier per
file, per key or per notation: the rules are stated in prose, several of
them on the same page. So the derivation reads the shape a
page uses to *name* a rule -- a heading, or the bold lead that opens a
paragraph or a list item -- ending in `(G-NN)`. An identifier anywhere
else on a published page, in running prose or in a table cell, is a
citation of a rule stated somewhere else, and a citation cannot
authorise itself: without that distinction, a comment's own `G-99` would
become resolvable the moment somebody quoted it in a handbook page.

**A rule nobody publishes has no number, and that is the point.** `G-17`
was cited in ten shipped files and stated on no page a reader can open;
the citations now state the rule instead. The same is true today of the
ballot comment, the absence of a separate quorum rule, and the
British-English check: they are real rules of this project that no
published page states, so nothing here resolves a number for them.

**The prose half**
==================
An identifier is the easy half. The same document gets cited in running
English too -- "the spec's S:4 rights section", "acceptance criterion 8 of
the spec", "see this task's own report" -- and a reader who follows one of
those finds exactly what they find for `R-27`. `WORKING_RECORD_PHRASE`
refuses four phrases, and only four:

* `this task` / `the task's`
* `the brief` / `own brief` / `task brief`
* `the spec` (abbreviated and unqualified)
* `acceptance criterion` / `acceptance criteria`

**What this deliberately does not refuse, and why the list is short.**
A phrase belongs above only if it *can only* mean the working record.
Everything below reads the same way and does not, so refusing it would
buy coverage at the price of an exemption list longer than the rule --
which is the shape this project treats as a failed control, not as a
thorough one:

* **`the plan`.** `plan_queue_drain` computes one and `derivation.py`
  prints one; `validate.py` and `app/src/state/channels.ts` both mean the
  promotion plan a volunteer edits. It is a noun this product owns.
* **`the review`.** `docs/governance/editorial-board.md` says a member
  "reviews edits to the handbook"; `commit_format.py` means "the commits
  under review"; `docs/toolkit/run-of-show.md` means peer review. Ordinary
  English three ways over, in a repository that uses the word 123 times.
* **`the audit`.** `register.py` calls the git history "the audit trail",
  and `test_dependency_audit_workflow.py` means the dependency audit a
  published workflow actually runs.
* **`the report`.** Every guard, checker and sweep in this repository
  prints one, and says so in its own docstring.
* **bare `task`, `phase`, `round`.** `docs/start-here/index.md` is headed
  "Pick a first task", the event journey has four phases, a Markdown
  checklist has tasks, and `yaml.test.ts` has a round-trip. `COORDINATE`
  above already catches the citing use, because that one carries a number.
* **`§N` on its own.** Fourteen of the eighteen this repository carried
  were RFC 5545 sections, and the RFC that governs one is often named a
  sentence earlier rather than beside it -- `ics_reader.py` cites `§3.1`
  and `§3.3.11` in one sentence and names the RFC once. Telling those
  apart needs more context than a sweep has; the four that named this
  project's own documents were rewritten instead.

`this task` is the one entry above that takes the same trade
`SEVERITY_TOKEN` takes: a volunteer-facing page that genuinely meant a
checklist item would fail here and would have to say "this step". That is
a one-word fix, and the alternative was a hundred and twenty citations of
a document nobody can open.
"""

from __future__ import annotations

import ast
import io
import json
import re
import subprocess
import tokenize
from collections.abc import Callable
from functools import cache
from pathlib import Path

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.published import INSTANCE_PATH

ROOT = repo_root()

#: Where the published architecture decision records live, one file per
#: record, `d-NN-<slug>.md`.
DECISIONS_DIR = "docs/decisions"

#: The file whose milestone keys establish the "T minus N" notation.
JOURNEY = Path("app") / "src" / "state" / "phases.ts"

#: Prefixes that name a public standard rather than a document of this
#: project's: character encodings, hash and cipher sizes, a named curve, an
#: RFC. See the module docstring for why this is a category rather than an
#: allowlist.
PUBLIC_STANDARDS = frozenset({"UTF", "SHA", "AES", "RFC", "P"})

#: A published page titling one of its sections with a governance rule's
#: number: `## Inactivity (G-09)`. The number sits at the very end of the
#: heading, which is what separates naming a rule from mentioning one --
#: `**Handover is manual and deliberate, exactly as G-11 provides for:**`
#: in `docs/decisions/d-28-architect-and-board-permissions.md` cites the
#: rule, it does not state it.
RULE_HEADING = re.compile(r"^#{1,6}[ \t]+[^\n]*?\((G-\d{2})\)[ \t]*$", re.MULTILINE)

#: The same act on a page whose rules are paragraphs rather than sections:
#: `**Declaring an absence (G-04)** is something you do for yourself.`, and
#: `- **Diversity (G-13).** A deliberate aim, not an afterthought`. The bold
#: run opens the line -- after a list marker, if there is one -- and closes
#: on the number, so it is a title in everything but markup.
RULE_LEAD = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?\*\*[^*\n]*?\((G-\d{2})\)[.,]?\*\*", re.MULTILINE
)

#: An identifier-shaped citation: one to three capitals, a hyphen, a number.
#: The shape every family this project ever used is written in -- `D-19`,
#: `R-27`, `AF-2`, `P2-9` -- and the shape a new one would be written in.
IDENTIFIER = re.compile(r"(?<![A-Za-z0-9_-])([A-Z]{1,3})-(\d{1,3})(?![A-Za-z0-9_-])")

#: A coordinate into a numbered thing: `phase 8`, `task 3`, `fix round 1`,
#: `ruling 6`, `Minor 2`, `Important 1b`. Resolved against the titles of
#: published pages, which is what lets the event journey's own `Phase 3`
#: through and stops a construction plan's `phase 8`. `ruling` belongs in
#: this list rather than beside the phrases below because a *numbered*
#: ruling is a coordinate and nothing else: "a design ruling", carrying no
#: number, names a settled decision and never matches.
COORDINATE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(phase|task|round|wave|ruling|minor|major|important|critical)"
    r"s?[ \-]+(\d{1,2}[a-z]?)\b",
    re.IGNORECASE,
)

#: The same coordinate, lettered instead of numbered: `change E`,
#: `Critical B`. Case-sensitive on the letter, and stopping at `M`, because
#: `N` and `X` are this repository's placeholders for "any number" -- a
#: comment naming `phase-N-bilan.md` is describing a filename shape, not
#: citing a phase. `change a file` is lower-case and never matches.
LETTERED_COORDINATE = re.compile(r"\b([Cc]hange|Critical|Important|Minor) ([A-M])\b")

#: A section of a document called "spec". No page this repository publishes
#: is called that; the specifications are in the working record.
SPEC_SECTION = re.compile(r"(?i)\bspec(ification)?s?\s*(§|section|S:)\s*\d")

#: The review that produced a fix, cited as its own event. A published page
#: could carry the findings; none does, and `security audit` next to a
#: finding letter was the commonest shape of all. Written as a phrase rather
#: than folded into `COORDINATE` because it carries no number.
SECURITY_AUDIT = re.compile(r"(?i)\bsecurity audit\b")

#: A review finding written as a bare severity: `C4`, `H4`, `M5`, `L3`,
#: `AC8`, `S4`, `P2-9`. This one is **brittle in one direction only, and
#: deliberately left that way** -- the same trade
#: `test_cli.py::test_delete_recording_has_exactly_two_call_sites_both_in_cli`
#: already takes. A comment that genuinely means an HTML heading level will
#: fail here and has to say "heading level 1" instead. That is a cheap,
#: loud, one-line fix; the alternative is leaving the commonest citation
#: shape in this repository's history held by nothing.
SEVERITY_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(C[1-9]|H[1-9]|M[1-9]|L[1-9]|AC\d|S\d|P2-\d{1,2})"
    r"(?![A-Za-z0-9_-])"
)

#: The working record named in words instead of in codes: `this task`, `the
#: brief's step 3`, `the spec's table`, `acceptance criterion 8`. Every one
#: of them points at the same unpublishable documents `SPEC_SECTION` and
#: `SEVERITY_TOKEN` above point at; the only difference is that a reader
#: meets them in running English, so nothing shaped like an identifier
#: catches them.
#:
#: **Deliberately four phrases and not more.** Each is refused because it
#: can only mean the working record -- see the module docstring's "The
#: prose half" for what is left out, and why a longer list would be worse
#: than this one:
#:
#: * `this task` / `the task's`, but never a bare `the task`, which is
#:   ordinary English and this product's own vocabulary besides
#:   (`docs/start-here/index.md` is headed "Pick a first task").
#: * `the brief`, `own brief`, `task brief` -- always the noun. `brief`
#:   alone is left out because it is usually the adjective.
#: * `the spec`, abbreviated and bare. A public standard is always named
#:   where it is cited -- "the CSP specification", "Tally's OpenAPI spec",
#:   "the Fetch spec" -- so an unqualified `the spec` is this project's
#:   own. `the specification` is *not* refused: `docs/reference/
#:   operations.md` uses it four times for CSP.
#: * `acceptance criterion` / `criteria` -- a numbered requirements list.
#:   This product has no such thing of its own to confuse it with.
WORKING_RECORD_PHRASE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])("
    r"this task(?:'s)?"
    r"|the task's"
    r"|(?:the|own|task) brief(?:'s)?"
    r"|the spec(?:'s)?"
    r"|acceptance criteri(?:on|a)"
    r")(?![A-Za-z0-9_-])"
)

_LINE_COMMENT = re.compile(r"^[ \t]*//.*$", re.MULTILINE)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_HASH_COMMENT = re.compile(r"^[ \t]*#(?!!).*$", re.MULTILINE)
_TEMPLATE_COMMENT = re.compile(r"\{#.*?#\}|<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


@cache
def _tracked() -> list[str]:
    """Every file git tracks.

    No directory is held out of this sweep any more. The one that used
    to be -- this project's own working record, which is where every
    coordinate this module refuses came from -- is not in the repository
    at all, so every tracked file is a file somebody can be sent to.
    """
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return listing.splitlines()


def _python_prose(text: str) -> str:
    """A Python file's `#` comments and its docstrings, and nothing else.

    `ast` rather than a regular expression over triple-quoted strings,
    because `visual.py` holds an SVG path in one (`M9 15 V22 …`) and a
    sweep that read it as prose would refuse a `moveto` as a review
    finding. A docstring is a string *statement*, which is a distinction
    only a parser can make.
    """
    parts: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                parts.append(token.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover
        parts.append("")
    try:
        tree = ast.parse(text)
    except SyntaxError:  # pragma: no cover
        return "\n".join(parts)
    carries_a_docstring = (
        ast.Module,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
    )
    for node in ast.walk(tree):
        if isinstance(node, carries_a_docstring):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                parts.append(docstring)
    return "\n".join(parts)


def _json_prose(text: str) -> str:
    """The values of the keys this repository writes prose into.

    JSON carries no comments, so this project puts them in keys of their
    own -- `_comment`, `_roles`, `_why_a_default` -- and in a package's
    `description`. A lockfile has neither, which is what keeps its
    thousands of `MPL-2.0` licence strings out of this sweep.
    """
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:  # pragma: no cover
        return ""
    parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if (
                    isinstance(key, str)
                    and isinstance(value, str)
                    and (key.startswith("_") or key == "description")
                ):
                    parts.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(loaded)
    return "\n".join(parts)


def prose_of(name: str, text: str) -> str:
    """Everything in `name` that is written for a person to read.

    A cross-reference lives in a comment or in prose. Code does not cite
    anything -- and a sweep that read code would refuse `host_1: 'H1'`, a
    fixture's placeholder host name, as a security-audit finding.
    """
    suffix = Path(name).suffix
    if suffix == ".md":
        return text
    if suffix == ".py":
        return _python_prose(text)
    if suffix in {".ts", ".tsx", ".js", ".mjs", ".cjs", ".css"}:
        return "\n".join(_LINE_COMMENT.findall(text) + _BLOCK_COMMENT.findall(text))
    if suffix in {".yml", ".yaml", ".toml"} or Path(name).name == "CODEOWNERS":
        return "\n".join(_HASH_COMMENT.findall(text))
    if suffix in {".njk", ".html"}:
        return "\n".join(_TEMPLATE_COMMENT.findall(text))
    if suffix == ".json":
        return _json_prose(text)
    if Path(name).name in {".gitignore", ".gitattributes"}:
        return "\n".join(_HASH_COMMENT.findall(text))
    return ""


@cache
def published_decision_ids() -> frozenset[str]:
    """`D-NN` for every decision record `docs/decisions/` publishes."""
    ids = set()
    for path in (ROOT / DECISIONS_DIR).glob("d-*.md"):
        match = re.fullmatch(r"d-(\d{2})-.+", path.stem)
        if match:
            ids.add(f"D-{match.group(1)}")
    return frozenset(ids)


@cache
def countdown_notation_exists() -> bool:
    """Whether the event journey still writes its milestones `T-N`."""
    text = (ROOT / JOURNEY).read_text(encoding="utf-8")
    return bool(re.search(r"scheduled/T-\d+/", text))


@cache
def edition_prefixes() -> frozenset[str]:
    """Every prefix an instance in this repository numbers its editions under.

    Read from each tracked copy of `published.INSTANCE_PATH` rather than
    from one: the instance's own declaration is a path `config/boundary.yml`
    hands to the instance, so a derived repository has only the example's.
    The whole path is matched rather than the file name, because
    `config.json` under `instance/` is a name a directory somewhere else
    could carry for something entirely different.
    """
    prefixes = set()
    declaration = INSTANCE_PATH.as_posix()
    for name in _tracked():
        if name != declaration and not name.endswith(f"/{declaration}"):
            continue
        try:
            declared = json.loads((ROOT / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover
            continue
        prefix = declared.get("edition_prefix")
        if isinstance(prefix, str) and prefix:
            prefixes.add(prefix)
    return frozenset(prefixes)


@cache
def _published_pages() -> list[tuple[str, str]]:
    """Every page under `docs/` this repository publishes, with its text.

    What a reader who clones this repository, or opens the handbook the
    app serves from these same files, can actually reach -- which is now
    every page under `docs/`, with nothing held back.
    """
    return [
        (path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "docs").rglob("*.md"))
    ]


def declared_rule_ids(text: str) -> set[str]:
    """Every governance rule one page states as its own.

    Titling, not mentioning: see `RULE_HEADING` and `RULE_LEAD`. The
    distinction is the whole of the derivation's honesty -- a page is free
    to cite a rule stated elsewhere, and doing so must not make the number
    resolve on the strength of the citation alone.
    """
    return set(RULE_HEADING.findall(text)) | set(RULE_LEAD.findall(text))


@cache
def published_governance_rules() -> frozenset[str]:
    """`G-NN` for every rule a published page states."""
    ids: set[str] = set()
    for _, body in _published_pages():
        ids |= declared_rule_ids(body)
    return frozenset(ids)


@cache
def published_page_titles() -> frozenset[str]:
    """The first heading of every published page under `docs/`, lower-cased.

    What a coordinate is resolved against. `docs/workflow/3-hosting.md`
    contributes "phase 3 — hosting day", which is what lets a link to it
    keep saying "Phase 3".
    """
    titles = set()
    for _, body in _published_pages():
        match = _HEADING.search(body)
        if match:
            titles.add(match.group(1).strip().lower())
    return frozenset(titles)


def _coordinate_resolves(word: str, number: str, titles: frozenset[str]) -> bool:
    """Whether some published page is titled `<word> <number>`."""
    opening = f"{word.lower()} {number.lower()}"
    return any(
        title == opening
        or title.startswith(f"{opening} ")
        or title.startswith(f"{opening}—")
        or title.startswith(f"{opening} —")
        for title in titles
    )


#: This module's own path. It is the one file the sweep skips, and the
#: reason is structural rather than convenient: everything above states the
#: rule by naming the shapes it refuses -- `R-27`, `phase 8, task 3`,
#: `Critical A` -- so a module that swept itself would refuse its own
#: source the day it was written. `convener_ops.derivation_guard` already
#: solved the identical problem the other way, by never writing a
#: credential pattern as its own literal; a docstring has no such trick
#: available, because the examples *are* the explanation.
SELF = "tools/tests/test_cross_references.py"


@cache
def _swept() -> list[tuple[str, str]]:
    """Every tracked file that carries prose, with that prose."""
    carried = []
    for name in _tracked():
        if name == SELF:
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        body = prose_of(name, text)
        if body.strip():
            carried.append((name, body))
    return carried


# ------------------------------------------------------------------ #
# The sweep is real: what it reads, and what it derives, both exist.
# ------------------------------------------------------------------ #


def test_the_sweep_reads_prose_from_every_kind_of_file_this_repository_holds() -> None:
    """A guard against a vacuous pass, the same one `registered-links.
    test.ts` puts on its own walk. An extractor that quietly returned
    nothing -- a changed suffix, a regular expression that stopped
    matching -- would make every assertion below pass by reading an empty
    string."""
    suffixes = {Path(name).suffix for name, _ in _swept()}
    for expected in (".py", ".ts", ".yml", ".md", ".json", ".mjs"):
        assert expected in suffixes, (
            f"the sweep found no prose in any {expected} file -- the "
            "extractor has stopped reading a whole kind of file, and every "
            "check in this module is passing over it vacuously"
        )


def test_the_decision_records_this_module_admits_are_the_ones_on_disk() -> None:
    """The allowlist is derived, and derived from something that ships.

    An empty set would make the identifier sweep refuse every `D-NN` in
    the repository, so this fails loudly rather than by an avalanche.
    """
    ids = published_decision_ids()
    assert ids, (
        f"{DECISIONS_DIR}/ holds no `d-NN-<slug>.md` file -- either the "
        "records moved, or their naming changed, and the identifier sweep "
        "below has nothing to resolve `D-NN` against"
    )
    assert "D-19" in ids, (
        "D-19 (the event identifier) is not among the records on disk -- "
        "this module derives its allowlist from those filenames, and this "
        "is the sanity check that the derivation reads what it thinks"
    )


def test_the_rules_this_module_admits_are_the_ones_the_pages_state() -> None:
    """The second derived allowlist, held the same way as the first.

    `G-NN` used to be admitted on trust, because the numbering existed only
    in this project's own framing document and no shipped page carried it.
    The pages carry it now, and this is the check that they still do: an
    empty set would make the sweep refuse every governance citation in the
    repository at once.
    """
    rules = published_governance_rules()
    assert rules, (
        "no published page under docs/ titles a section or a paragraph with "
        "a governance rule's number -- either the rules stopped being "
        "numbered, or the shape they are numbered in changed, and the "
        "identifier sweep below has nothing to resolve `G-NN` against"
    )
    assert "G-01" in rules, (
        "G-01 (the two-thirds bar) is not among the rules the published "
        "pages state -- this module derives its allowlist from those "
        "titles, and this is the sanity check that the derivation reads "
        "what it thinks"
    )


#: What a page does when it *states* a rule, and what it does when it only
#: names one. Both happen on published pages, which is why the difference
#: has to be a shape and not a directory: if a citation counted, quoting a
#: comment's own `G-99` in a handbook page would make `G-99` resolve.
DECLARATION_CASES: tuple[tuple[str, set[str]], ...] = (
    ("## Inactivity (G-09)", {"G-09"}),
    ("**Inactivity (G-09)** is the other half.", {"G-09"}),
    ("- **Diversity (G-13).** A deliberate aim, not an afterthought", {"G-13"}),
    ("| `inactivity_months` | number | ... inactive (G-09). |", set()),
    ("G-11 says the role is transferable; it does not say what a", set()),
    ("- **Handover is manual, exactly as G-11 provides for:** promote", set()),
    ("The second gate (G-10, G-15): what has to be true before a", set()),
)


def test_a_rule_is_declared_by_a_title_and_cited_by_everything_else() -> None:
    """Why the derivation cannot be "the identifier appears on a page".

    The schema reference cites a rule in a table cell, `d-28` cites two in
    its own prose, and neither states one. A page is free to do that; what
    it cannot do is make a number resolve on the strength of the citation.
    """
    for line, declared in DECLARATION_CASES:
        assert declared_rule_ids(line + "\n") == declared, line


def test_the_countdown_notation_is_read_and_not_assumed() -> None:
    """`T-N` is admitted because the journey writes its milestones that
    way. The day it stops, the exemption should go with it."""
    assert countdown_notation_exists(), (
        f"{JOURNEY.as_posix()} declares no `scheduled/T-N/` milestone -- "
        "the countdown notation this module exempts is gone, so the "
        "exemption should go too rather than sit here unearned"
    )


def test_the_edition_prefixes_are_read_from_the_declarations() -> None:
    """At least one instance declares one, or edition codes resolve
    against nothing."""
    prefixes = edition_prefixes()
    assert prefixes, (
        "no tracked `instance/config.json` declares an `edition_prefix` -- an "
        "edition code like `MRG-1` would then read as an unresolvable "
        "citation rather than as this repository's own data"
    )


def test_the_published_page_titles_include_the_event_journey() -> None:
    """The derivation that separates a journey phase from a plan's phase.

    If `docs/workflow/` ever stopped opening its pages with `# Phase N`,
    every link to them would start failing the coordinate sweep -- which
    would be this check's fault, not the links'.
    """
    titles = published_page_titles()
    assert any(title.startswith("phase ") for title in titles), (
        "no published page under docs/ is titled `Phase N` -- the event "
        "journey's own pages are what make a reference to `Phase 3` "
        "resolvable, and without them this module would refuse every link "
        "to them"
    )


# ------------------------------------------------------------------ #
# The rule itself.
# ------------------------------------------------------------------ #


def unresolvable_identifiers(name: str, body: str) -> list[str]:
    """Every `X-NN` in `body` that names nothing this repository publishes."""
    decisions = published_decision_ids()
    rules = published_governance_rules()
    prefixes = edition_prefixes()
    countdown = countdown_notation_exists()
    offenders = []
    for prefix, number in IDENTIFIER.findall(body):
        token = f"{prefix}-{number}"
        if token in decisions:
            continue
        if token in rules:
            continue
        if prefix in prefixes:
            continue
        if prefix in PUBLIC_STANDARDS:
            continue
        if prefix == "T" and countdown:
            continue
        offenders.append(token)
    return offenders


def unresolvable_coordinates(body: str) -> list[str]:
    """Every `phase 8` / `task 3` / `Minor 2` naming no published page."""
    titles = published_page_titles()
    offenders = []
    for word, number in COORDINATE.findall(body):
        if not _coordinate_resolves(word, number, titles):
            offenders.append(f"{word} {number}")
    for word, letter in LETTERED_COORDINATE.findall(body):
        if not _coordinate_resolves(word, letter, titles):
            offenders.append(f"{word} {letter}")
    return offenders


# One sweep per rule rather than one test per file. `registered-links.
# test.ts` generates a case per registered page and there are thirty of
# them; there are five hundred files here, and three cases each would put
# fifteen hundred entries in a suite of three and a half thousand for a
# property that is about the repository rather than about any one file.
# What a person clearing this actually wants is every offender at once,
# so each sweep collects them all and names them in one message.


def _offenders(rule: Callable[[str, str], list[str]]) -> dict[str, list[str]]:
    """`{file: what it cites}` over everything this repository ships."""
    found: dict[str, list[str]] = {}
    for name, body in _swept():
        cited = sorted(set(rule(name, body)))
        if cited:
            found[name] = cited
    return found


def _report(found: dict[str, list[str]]) -> str:
    return "; ".join(f"{name} cites {cited}" for name, cited in found.items())


def test_every_identifier_in_a_comment_names_a_published_document() -> None:
    """`D-19` resolves: `docs/decisions/d-19-event-identifier.md` is a page
    the handbook serves. `R-27` resolved to a reviewer's ruling in a
    document this repository never publishes, and a reader who went
    looking found nothing."""
    found = _offenders(unresolvable_identifiers)
    assert not found, (
        f"{_report(found)}. Nothing this repository publishes declares "
        "them. Cite the thing itself -- the decision record, the function, "
        "the file -- or say what the comment explains rather than where it "
        "was decided. See this module's own docstring."
    )


def test_no_comment_cites_a_phase_or_a_task_that_is_not_published() -> None:
    """`Phase 3 — Hosting day` is a page in the handbook, so a link that
    says "Phase 3" resolves. `phase 8, task 3, change E` named a plan and
    a task inside it, and this repository publishes neither."""
    found = _offenders(lambda name, body: unresolvable_coordinates(body))
    assert not found, (
        f"{_report(found)}. No page this repository publishes is called "
        "that. A comment should say why the code is as it is, never when "
        "it was written."
    )


def working_record_phrases(body: str) -> list[str]:
    """Every phrase in `body` that can only name the working record."""
    return [match.group(1) for match in WORKING_RECORD_PHRASE.finditer(body)]


def test_no_comment_names_the_working_record_in_words() -> None:
    """The same rule as the three sweeps above, for the half of it written
    in English rather than in codes.

    "the spec's S:4 rights section", "acceptance criterion 8 of the spec",
    "see this task's own report" -- a reader who goes looking finds exactly
    what they find for `R-27`. Say what the code guarantees; if a document
    really is the point, name one this repository publishes.
    """
    found = _offenders(lambda name, body: working_record_phrases(body))
    assert not found, (
        f"{_report(found)}. The specifications, the plans and the briefs "
        "are this project's own working record and never ship. State the "
        "guarantee, the measurement or the rule, never the document that "
        "asked for it. See this module's own docstring for the phrases "
        "this sweep deliberately does not refuse."
    )


def _unpublished_sources(name: str, body: str) -> list[str]:
    """A section of an unpublished specification, a review named by its
    date, and a review finding written as a bare severity."""
    cited = sorted({match.group(0) for match in SPEC_SECTION.finditer(body)})
    if SECURITY_AUDIT.search(body):
        cited.append("a security audit")
    cited += sorted({match.group(0) for match in SEVERITY_TOKEN.finditer(body)})
    return cited


def test_no_comment_cites_a_spec_section_or_a_review_finding() -> None:
    """The shapes left after the two sweeps above: `spec S:7`, `security
    audit`, and a finding named by severity alone (`H4`, `M5`, `C4`).

    All three are collected before anything is asserted, rather than
    checked one after another: three assertions in a row stop at the
    first, so a file carrying all three would take three runs to clear.
    """
    found = _offenders(_unpublished_sources)
    assert not found, (
        f"{_report(found)}. The specifications and the reviews are this "
        "project's own working record and never ship: state the rule, not "
        "the document that decided it. If a comment genuinely means an "
        "HTML heading level, write `heading level 1`."
    )


# ------------------------------------------------------------------ #
# The sweep bites: proven against a file written to fail it.
# ------------------------------------------------------------------ #


def test_a_dangling_identifier_is_caught(tmp_path: Path) -> None:
    """Not "the repository is clean today", which a broken sweep also
    reports. A file written to fail, and read through the same
    extractor."""
    probe = tmp_path / "probe.py"
    probe.write_text('"""Refuses a stale payload (R-27, fix round 1)."""\n', "utf-8")
    body = prose_of("probe.py", probe.read_text(encoding="utf-8"))
    assert unresolvable_identifiers("probe.py", body) == ["R-27"]


def test_a_governance_rule_no_page_states_is_caught(tmp_path: Path) -> None:
    """`G-17` was exactly this file: a rule the code enacts, cited by number
    in ten shipped files, and stated on no page a reader can open."""
    probe = tmp_path / "probe.py"
    probe.write_text('"""Assigned by rotation (G-99)."""\n', "utf-8")
    body = prose_of("probe.py", probe.read_text(encoding="utf-8"))
    assert unresolvable_identifiers("probe.py", body) == ["G-99"]


def test_a_published_governance_rule_is_not_caught(tmp_path: Path) -> None:
    """`docs/governance/board-rules.md` titles a section `### The bar
    (G-01)`, so a comment naming the bar by its number resolves."""
    probe = tmp_path / "probe.py"
    probe.write_text('"""The two-thirds bar (G-01)."""\n', "utf-8")
    body = prose_of("probe.py", probe.read_text(encoding="utf-8"))
    assert unresolvable_identifiers("probe.py", body) == []


def test_a_published_decision_record_is_not_caught(tmp_path: Path) -> None:
    """The other half: the sweep must let a real citation through, or it
    would be a rule against citing anything at all."""
    probe = tmp_path / "probe.py"
    probe.write_text('"""The event identifier (D-19)."""\n', "utf-8")
    body = prose_of("probe.py", probe.read_text(encoding="utf-8"))
    assert unresolvable_identifiers("probe.py", body) == []


def test_a_dangling_coordinate_is_caught() -> None:
    """`phase 8` names nothing published; `Phase 3` names a handbook page."""
    assert sorted(unresolvable_coordinates("# Phase 8, task 3, change E")) == [
        "Phase 8",
        "change E",
        "task 3",
    ]
    assert unresolvable_coordinates("see [Phase 3](../workflow/3-hosting.md)") == []
    assert unresolvable_coordinates("change a file, and every phase-N-bilan.md") == []


def test_a_python_svg_path_is_not_read_as_prose() -> None:
    """`visual.py` holds an SVG `moveto` in a triple-quoted string, and a
    sweep that read every triple-quoted string as a docstring would refuse
    `M9` as a review finding. The parser is what keeps that out."""
    source = 'MARK = """<path d="M9 15 V22 H24"/>"""\n'
    assert "M9" not in prose_of("probe.py", source)


#: What the prose sweep must refuse, and what it must let through. The
#: second half is the load-bearing one: every entry there is a real
#: sentence this repository ships today, and each names a thing this
#: product genuinely has -- a plan a command computes, a report a guard
#: prints, an audit a workflow runs, a task a volunteer picks up. A rule
#: that refused those would need an exemption list longer than itself.
PROSE_CASES: tuple[tuple[str, list[str]], ...] = (
    ("acceptance criterion 8 of the spec", ["acceptance criterion", "the spec"]),
    ("the spec's S:4 rights section", ["the spec's"]),
    ("see this task's own report", ["this task's"]),
    ("the brief's own step 1", ["the brief's"]),
    ("this task's own brief warns against", ["this task's", "own brief"]),
    ("the task brief names it verbatim", ["task brief"]),
    ("the acceptance criteria the phase rests on", ["acceptance criteria"]),
    # Left alone, and each is a sentence from a shipped file.
    ("the plan the two imply", []),
    ("the report a person reads, refusals and blind spots alike", []),
    ("the git history is the audit trail", []),
    ("Pick up a task and move it forward", []),
    ("Detection is what the scheduled task operates", []),
    ("the whole of the exception the specification names", []),
    ("checked against Tally's own OpenAPI spec", []),
    ("a plain, dependency-free Node script rather than a spec", []),
    ("the two-trace shape is a design ruling carried into code", []),
    ("a brief note beside the value", []),
)


def test_the_prose_sweep_refuses_a_citation_and_keeps_the_domain_noun() -> None:
    """Both halves, because only the second one can go quietly wrong.

    A sweep that refused `the plan` would be right about
    `tools/tests/journey/test_registration.py` and wrong about
    `convener_ops/derivation.py`, which computes one and prints it -- and
    the way that failure shows up is a maintainer adding an exemption
    rather than a citation being removed.
    """
    for line, refused in PROSE_CASES:
        assert working_record_phrases(line) == refused, line


def test_a_prose_citation_of_the_working_record_is_caught(tmp_path: Path) -> None:
    """Read through the same extractor as everything else, from a file
    written to fail: "the repository is clean today" is also what a broken
    sweep reports."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        '"""Rounds down, per acceptance criterion 8 of the spec."""\n', "utf-8"
    )
    body = prose_of("probe.py", probe.read_text(encoding="utf-8"))
    assert working_record_phrases(body) == ["acceptance criterion", "the spec"]


def test_a_numbered_ruling_is_caught_and_an_unnumbered_one_is_not() -> None:
    """`ruling 6` is a coordinate into a list this repository never
    publishes. "a design ruling", which is how `docs/reference/
    operations.md` and `platform_fcc.py` both name a settled decision,
    carries no number and is not a citation at all."""
    assert unresolvable_coordinates("Ruling 6: inviting people to") == ["Ruling 6"]
    assert unresolvable_coordinates("a settled design ruling about") == []


def test_a_fixture_host_placeholder_is_not_read_as_prose() -> None:
    """`host_1: 'H1'` is a fixture's invented host name, in code. A sweep
    over whole files would refuse it as a security-audit finding, which is
    the sweep being wrong about domain data."""
    source = "const row = { host_1: 'H1', host_2: 'H2' };\n"
    assert "H1" not in prose_of("probe.ts", source)
