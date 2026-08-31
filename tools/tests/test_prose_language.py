"""This product ships in British English, and so do the comments in it.

`cspell.json` already declares `en-GB` and already gates the prose a reader
opens: the handbook under `docs/`, the two pages at the repository root,
each service's and each instance's own README, the showcase's templates and
the workflows. What it never looked at is the *source*, because `tools/**`
is in `ignorePaths` outright and `app/**` was never in `files` at all. So
French prose sat in shipped comments and docstrings for as long as the
repository has existed, in three shapes:

* a **quotation** of this project's own working record, dropped into
  English prose -- "les cles publiques anterieures restent publiees, pour
  que la rotation n'invalide jamais un certificat deja emis" stood in two
  modules, and a reader who wanted the rest of the sentence had nowhere to
  go, because the document it came from is not in this repository and
  never will be;
* a **false attribution** -- `D-26` cited, in quotation marks, saying
  something in French, when
  `docs/engineering/decisions/d-26-verify-deployed-shape.md` is published
  in English and says "Verify the shape that will actually be deployed,
  never a convenient local one";
* a whole **docstring** in French, and written without its accents at
  that, so that even as French it was degraded.

The first two are the same defect `test_cross_references.py` refuses one
step earlier: prose pointing at a document nobody can open. This module
refuses the language rather than the coordinate, because a quotation
carries no coordinate to catch.

**Why this is a test and not more `cspell`.**
=============================================
Pointing `cspell` at `tools/**` and `app/**` is the obvious move and the
wrong one. Those trees are mostly identifiers -- `hexdigest`,
`monkeypatch`, `namedtuples`, `unregistrable`, `workerd` -- and the
dictionary needed to quiet them would end up longer than the rule it
serves, which is the shape this project treats as a failed control rather
than a thorough one. What matters here is a much narrower surface: the
sentences a person wrote for another person. `test_cross_references.py`
already extracts exactly that surface, and this module reads it through
the same `prose_of`, so there is one extractor in this repository and not
two. Everything that extractor is careful about is inherited whole: `ast`
and `tokenize` for Python, so a docstring is a string *statement* and an
SVG path held in a triple-quoted string is not prose; comment syntax per
language for the rest.

**Fixture data is content, and is never read.**
===============================================
That inheritance is what keeps this rule off the data. A value is not a
comment, so `tools/tests/fixtures/config-from-app.yml`'s `label: Affiches
imprimees dans les instituts` and `speakers-from-app.yml`'s
`seed_questions` are invisible here -- and they must be, because they
exist to prove accented text survives a round trip through this
repository's own readers and writers. The same is true of every value
under `instance/data/`, `instances/` and `instance/public-data/`. The rule is about the
language a *maintainer* writes in, never the language an event runs in.

**Function words, not accents.**
================================
Accents are the tempting signal and the wrong one, twice over. Half the
sites this module was written for carried none: "les donnees deviennent
definitivement illisibles", "meme entree que l'inscription", "une remise
echouee se rejoue sans regenerer" were all typed without them, so an
accent sweep would have found half the defect and reported the repository
clean. And accents appear in this repository's English legitimately --
`Bezier`, and a person's name -- so the signal is noisy in both
directions.

`FRENCH` below is a closed list of French function words that are not
English words, plus one shape: the elision an English word never takes,
a single letter or `qu` against an apostrophe and a lower-case word
(`l'inscription`, `n'existe`, `qu'un`). English contractions are safe
from it -- `it's` and `don't` have letters on both sides of the
apostrophe, `o'clock` opens on a letter the list does not hold.

**Two markers, in a window of two lines.** Two rather than three because
a quotation of five or six words is the commonest shape here and often
carries no more; two lines rather than one because this repository wraps
its prose at about seventy-six characters, so a quoted sentence routinely
straddles a line break -- the same hole `test_cross_references.py` records
for its own single-line match, closed here because a language is a
property of a whole sentence rather than of one token in it.

**What this deliberately does not catch, and why the list stops here**
======================================================================
* **A French phrase carrying fewer than two of those words.** Four shapes
  in this repository were exactly that, and every one was rewritten by
  hand rather than by widening the rule: a two-word label
  ("Verification sans divulgation"), a rule named without grammar
  ("reconnue presente"), a single French noun dropped into an English
  sentence ("gabarits", "remise"), and a bare list of nouns
  ("donnees, finalite, base legale, destinataires, duree, mesures").
  Catching those needs a French *dictionary*, which is the control this
  module exists instead of.
* **`de`, `est` and `par`, the three commonest words held out.** `de` is
  the commonest word in French and also the commonest French word inside
  English prose (`de facto`, a surname, a journal title). `est` and `par`
  are worse than that: they are ordinary English abbreviations and idiom,
  and `Est. 2019, and on par with the rest of the sector` carries both,
  which is a whole English sentence this rule would have refused. All
  three cost nothing to leave out -- measured against every French site
  this repository actually carried, each was still caught by two of the
  words that remain.
* **Any language that is not French.** The defect this repository had was
  French, the project's own working language; a rule against "not
  English" would need a dictionary of English, which is `cspell`, which
  is the control this module exists instead of.
* **String literals, fixtures and instance data**, per the section above.
* **A citation of something unpublishable that happens to be in English.**
  That is `test_cross_references.py`'s rule, not this one, and the two
  sweep the same surface for that reason.

**The spell check's own reach**
===============================
Two decisions about `cspell.json`'s `files` list are made here rather than
left to whoever reads the list next:

* **`TRADEMARK.md` is gated.** It is this project's own prose, at the
  repository root, beside two pages that were already in the list. Nothing
  distinguished it but an oversight.
* **`LICENSE` is not, and must not be.** It is the Free Software
  Foundation's text, reproduced verbatim, American spellings and all;
  `test_notice.py::AGPL_SHA256` pins it byte for byte against the
  published file. A British-English spell check over it would report
  "license", "authorize" and "defense" as errors that must not be fixed,
  and the only way to quiet them would be to teach the dictionary
  American spellings this product does not use anywhere else.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from test_cross_references import _tracked, prose_of

from convener_ops.declaration.paths import repo_root

ROOT = repo_root()

#: The spell check's own declaration, read rather than restated.
CSPELL = "cspell.json"

#: French function words with no English homograph, and none of them a
#: plausible identifier. `sans` is here and never fires on `sans-serif`,
#: because the boundary below refuses a hyphen on either side. `de`,
#: `est`, `par`, `la`, `le`, `en` and `on` are deliberately absent -- see
#: the module docstring's "what this deliberately does not catch".
FRENCH_WORDS = frozenset(
    {
        "aucun",
        "aucune",
        "aux",
        "avec",
        "cette",
        "ces",
        "chaque",
        "dans",
        "depuis",
        "des",
        "doit",
        "donc",
        "dont",
        "du",
        "elle",
        "elles",
        "etaient",
        "etait",
        "ils",
        "jamais",
        "les",
        "leur",
        "leurs",
        "lorsque",
        "mais",
        "meme",
        "ne",
        "nous",
        "parce",
        "pas",
        "peut",
        "plutot",
        "pour",
        "quand",
        "que",
        "qui",
        "sans",
        "sera",
        "seront",
        "ses",
        "soit",
        "sont",
        "sous",
        "sur",
        "toujours",
        "tous",
        "tout",
        "toute",
        "toutes",
        "une",
        "vous",
    }
)

#: One of those words, or a French elision -- a single letter, or `qu`,
#: against an apostrophe and a lower-case word. Accents are not part of
#: the signal at all; see the module docstring for why.
FRENCH = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    + "|".join(sorted(FRENCH_WORDS, key=len, reverse=True))
    + r"|(?:qu|[cdjlmnst])'[a-zà-ÿ]{2,}"
    + r")(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)

#: How many distinct markers make a window French, and how many lines a
#: window spans. See the module docstring's "two markers, in a window of
#: two lines" for both numbers.
MARKERS_REQUIRED = 2
WINDOW_LINES = 2

#: This module's own path, and the one file the sweep skips. The reason is
#: the same structural one `test_cross_references.py` gives for skipping
#: itself: everything above states the rule by quoting the French it
#: refuses, so a module that swept itself would refuse its own source the
#: day it was written. The examples *are* the explanation.
SELF = "tools/tests/test_prose_language.py"


def french_windows(body: str) -> list[str]:
    """Every window of `body` carrying `MARKERS_REQUIRED` French markers.

    Reported as the markers found rather than as the sentence, so a
    failure names what to look for without reprinting a paragraph of
    somebody's docstring into a pytest report.
    """
    lines = body.splitlines()
    found: list[str] = []
    for start in range(len(lines)):
        window = " ".join(lines[start : start + WINDOW_LINES])
        markers = {match.group(0).lower() for match in FRENCH.finditer(window)}
        if len(markers) >= MARKERS_REQUIRED:
            found.append(" ".join(sorted(markers)))
    return found


def swept() -> list[tuple[str, str]]:
    """Every tracked file that carries prose, with that prose.

    Read through `test_cross_references.prose_of`, so comments and
    docstrings and nothing else -- see the module docstring's "fixture
    data is content".
    """
    carried: list[tuple[str, str]] = []
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
# The sweep is real: it reads prose, and it reads it from every kind of
# file this repository holds.
# ------------------------------------------------------------------ #


def test_the_sweep_reads_prose_from_every_kind_of_file_this_repository_holds() -> None:
    """The same guard against a vacuous pass `test_cross_references.py`
    puts on its own walk: an extractor that quietly returned nothing would
    make every assertion below pass by reading an empty string."""
    suffixes = {Path(name).suffix for name, _ in swept()}
    for expected in (".py", ".ts", ".tsx", ".yml", ".md", ".json", ".mjs", ".css"):
        assert expected in suffixes, (
            f"the sweep found no prose in any {expected} file -- the "
            "extractor has stopped reading a whole kind of file, and the "
            "check below is passing over it vacuously"
        )


# ------------------------------------------------------------------ #
# The rule itself.
# ------------------------------------------------------------------ #


def test_no_comment_or_docstring_is_written_in_french() -> None:
    """A comment quoting a document no reader can open costs a reader the
    same thing whether the quotation is a coordinate or a sentence -- and
    a sentence in a language the product does not ship in costs every
    reader who does not have it, every time.

    State the rule the module keeps, in the module's own voice. If a
    published document really is the point, quote what it actually says:
    `D-26` says "Verify the shape that will actually be deployed, never a
    convenient local one", in English, on a page the handbook serves.
    """
    found = {
        name: sorted(set(windows))
        for name, body in swept()
        if (windows := french_windows(body))
    }
    report = "; ".join(
        f"{name} reads as French around {markers}" for name, markers in found.items()
    )
    assert not found, (
        report + ". This product's comments and docstrings ship in British "
        "English. Say what the rule is rather than quoting it in another "
        "language, and never attribute a French sentence to a document "
        "published in English. See this module's own docstring for the "
        "shapes this sweep deliberately does not catch."
    )


#: What the sweep must refuse, and what it must leave alone. The second
#: half is the load-bearing one: every entry there is a sentence this
#: repository actually ships, and a rule that refused any of them would
#: need an exemption list longer than itself.
LANGUAGE_CASES: tuple[tuple[str, bool], ...] = (
    # Refused: the three shapes this module was written for.
    (
        "les cles publiques anterieures restent publiees, pour que la "
        "rotation n'invalide jamais un certificat deja emis",
        True,
    ),
    ("aucune donnee ... dans le depot", True),
    ("on verifie a la forme deployee, jamais a une forme locale", True),
    ("Une cle par evenement n'est une cle par evenement", True),
    ("le fichier chiffre est reecrit sans l'enregistrement concerne", True),
    # Left alone: English this repository ships today.
    ("the register holds no name and no address", False),
    ("served at the address it will actually be served at", False),
    ("a de facto standard nobody wrote down", False),
    ("it's the transport's own decision, don't second-guess it", False),
    ("the poster takes A4 rather than A3, and every printer has it", False),
    ("Bezier control points, measured against the drawn outline", False),
    ("font-family: Archivo, sans-serif", False),
    ("Est. 2019, and on par with the rest of the sector", False),
)


def test_the_sweep_refuses_french_and_leaves_english_alone() -> None:
    """Both halves, because only the second can go quietly wrong.

    A rule that fired on `sans-serif` or on `de facto` would be answered
    by an exemption rather than by a rewrite, and the exemptions are what
    this module is built to avoid having.
    """
    for line, refused in LANGUAGE_CASES:
        assert bool(french_windows(line)) is refused, line


def test_a_french_docstring_is_caught(tmp_path: Path) -> None:
    """Not "the repository is clean today", which a broken sweep also
    reports. A file written to fail, read through the same extractor."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        '"""Une cle par evenement n\'est une cle par evenement."""\n', "utf-8"
    )
    body = prose_of("probe.py", probe.read_text(encoding="utf-8"))
    assert french_windows(body)


def test_a_french_quotation_inside_english_prose_is_caught(tmp_path: Path) -> None:
    """The commonest shape of the three, and the one an English-reading
    eye slides past: one sentence of French in quotation marks, with the
    English argument carrying on around it."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        '# The rule is explicit: "les cles publiques anterieures restent\n'
        "# publiees, pour que la rotation n'invalide jamais un certificat\n"
        '# deja emis" -- so a retired key still verifies.\n',
        "utf-8",
    )
    body = prose_of("probe.py", probe.read_text(encoding="utf-8"))
    assert french_windows(body)


def test_french_in_a_string_literal_is_not_caught(tmp_path: Path) -> None:
    """A fixture's own value is content, not prose. `config-from-app.yml`
    carries an accented label precisely to prove it survives a round
    trip, and a sweep that flattened it would be destroying the evidence
    a different test depends on."""
    probe = tmp_path / "probe.py"
    probe.write_text('LABEL = "Affiches imprimees dans les instituts"\n', "utf-8")
    body = prose_of("probe.py", probe.read_text(encoding="utf-8"))
    assert french_windows(body) == []


def test_a_french_label_too_short_to_carry_the_signal_is_not_caught() -> None:
    """The limit, held as a test rather than left in the docstring alone.

    "Verification sans divulgation" was a real comment in this repository
    and was rewritten by hand, because two French words are not enough
    signal to refuse without a dictionary. Somebody widening this rule
    should have to change this assertion deliberately.
    """
    assert french_windows("Verification sans divulgation, made into a page") == []


# ------------------------------------------------------------------ #
# What the spell check itself is pointed at.
# ------------------------------------------------------------------ #


def cspell_files() -> list[str]:
    """The `files` list `cspell.json` declares, read rather than restated."""
    declared = json.loads((ROOT / CSPELL).read_text(encoding="utf-8"))
    listed = declared["files"]
    assert isinstance(listed, list)
    return [str(entry) for entry in listed]


def test_every_page_this_project_writes_at_the_root_is_spell_checked() -> None:
    """Derived from what is tracked, not from a second copy of the list.

    `README.md` was in `cspell.json` and `TRADEMARK.md` was not, for no
    reason anybody wrote down. A page added at the root should have to be
    gated or have its exemption argued, rather than simply arriving
    unchecked.
    """
    listed = cspell_files()
    at_the_root = sorted(
        name for name in _tracked() if name.endswith(".md") and "/" not in name
    )
    missing = [name for name in at_the_root if name not in listed]
    assert not missing, (
        f"{missing} sit at the repository root and no `files` entry in "
        f"{CSPELL} covers them -- this product's own prose is gated in "
        "British English, and a page nobody points the check at is a page "
        "nobody checks"
    )
    assert "TRADEMARK.md" in at_the_root, (
        "TRADEMARK.md is no longer a tracked page at the repository root, "
        "so this check no longer holds the file it was written for"
    )


def test_the_licence_is_not_spell_checked() -> None:
    """The other half of that decision, and the one that needs writing
    down: `LICENSE` must stay outside the list.

    It is the Free Software Foundation's own text, reproduced verbatim --
    `test_notice.py` pins it byte for byte against the published file by
    digest. It is American English throughout ("license", "authorize",
    "defense") and a British-English check over it would report every one
    of those as an error nobody may fix. Quieting them would mean
    teaching `project-words.txt` American spellings this product uses
    nowhere else, which would then stop the check catching them where it
    should.
    """
    assert not any("LICENSE" in entry for entry in cspell_files()), (
        f"{CSPELL} now points the British-English spell check at LICENSE. "
        "That file is the FSF's text, verbatim and American-spelled, and "
        "test_notice.py pins it by digest -- every spelling the check "
        "reports there is one that must not be corrected. See this "
        "module's own docstring."
    )
