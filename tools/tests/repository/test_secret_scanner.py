"""What the secret scanner may pass over, held against what it passes over.

`.github/workflows/security.yml` runs `gitleaks` over every commit of every
branch, and `.pre-commit-config.yaml` runs the same scanner, pinned to the
same version, over what is about to become one. Neither names a
configuration file: the scanner reads `<target>/.gitleaks.toml` when no
`--config` is given, so both find the one at this repository's root on
their own, and neither can be pointed at a different one by accident.

That file carries one allowlist entry, and an allowlist is the one part of
a scanner's configuration whose only possible effect is to make it
quieter. The argument for the entry -- why this repository publishes one
private key on purpose, and what it is and is not safe against -- is
written beside the clause in the file itself, where whoever reads the
exemption meets it. What is written here is the other half: that the
clause still stands for something, that what it stands for is a value at
a path rather than a path, and that the scanner it configures is still
running every rule it came with.

**Nothing here runs the scanner.** The binary is a network download, no
test in this project reaches the network, and every clause below is a
property of files this repository already tracks: the configuration, the
one file the configuration names, and the two places the scanner's
version is pinned. A control that has to fetch a tool before it can run is
a control that does not run.

**The order is not arbitrary.** A configuration file *replaces* the
scanner's default ruleset unless it says otherwise, so the cheapest way to
turn the `secrets` job green would have been to hand it a configuration
with no rules in it -- green for the reason a control may never be green.
That is the first test below, and it is first because every clause after
it is worthless without it. Without any of this the job was red on its
first run and stayed red, which is where it stood for a long time: nothing
had ever run it, so nobody had seen it.

**How the subject is reached.** Not from a list here. The path clause is
compiled and asked which of this repository's tracked files it matches,
and the value clause is searched for in that file -- so the two halves of
the exemption are read out of the configuration and held against the
repository, and a clause repointed at a file that is not there, or at a
value that is not in it, fails by being about nothing. Nothing in this
module writes the key, the path or the anchor down; a module that quoted
any of them would be the second copy the exemption exists to avoid.

**What is deliberately not checked.** That the exempted value is *safe*.
That is a judgement about one fixture, it is argued in `.gitleaks.toml`
beside the clause, and no test can hold an argument. What is checked is
that the judgement is still about the thing it was made about.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops.declaration.paths import repo_root
from convener_ops.journey import eventkeys
from repository.test_cross_references import _tracked

ROOT: Final = repo_root()

#: The scanner's configuration, found by name rather than named by a
#: caller, which is what stops the workflow and the hook from drifting
#: onto different ones.
CONFIG: Final = ROOT / ".gitleaks.toml"

#: Where the same scanner is pinned twice. A configuration option is a
#: property of a version -- `condition` and `targetRules` are both
#: recent -- so an allowlist argued against one version and executed by
#: another is an allowlist nobody has checked.
SECURITY_WORKFLOW: Final = ROOT / ".github" / "workflows" / "security.yml"
PRE_COMMIT_CONFIG: Final = ROOT / ".pre-commit-config.yaml"
SCANNER_REPO: Final = "https://github.com/gitleaks/gitleaks"

#: A private key as a whole block: a header, a body of base64 and a
#: matching footer. A header alone is a string anybody may write *about*
#: keys, and matching it would make this module refuse every test in this
#: repository that asserts what a generated key starts with.
#:
#: **Written as a repeat count rather than as five dashes**, so that this
#: module's own source does not carry the shape it matches. The body
#: admits a literal backslash-n as well as a real newline, because a key
#: pasted into a JSON string carries the first and not the second, and the
#: one file this configuration exempts is exactly that.
KEY_BLOCK: Final = re.compile(
    "-{5}BEGIN [A-Z0-9 ]*PRIVATE KEY-{5}"
    r"(?:[A-Za-z0-9+/=\s]|\\n){40,}?"
    "-{5}END [A-Z0-9 ]*PRIVATE KEY-{5}"
)


def _configuration() -> dict[str, Any]:
    loaded: dict[str, Any] = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    return loaded


def _allowlist() -> dict[str, Any]:
    """The one entry `.gitleaks.toml` carries."""
    entries = _configuration()["allowlists"]
    assert len(entries) == 1, entries
    entry: dict[str, Any] = entries[0]
    return entry


def exempted_path() -> str:
    """The one file this repository tracks that the path clause matches.

    Asked of `git ls-files` rather than of a constant, because the whole
    claim the path clause makes is about a file in this repository: a
    clause matching nothing exempts nothing and is an exemption nobody can
    audit, and a clause matching two files is a decision about one of them
    quietly covering the other.
    """
    pattern = re.compile(_allowlist()["paths"][0])
    matched = sorted(name for name in _tracked() if pattern.search(name))
    assert len(matched) == 1, (
        f"the allowlist's path clause matches {matched} -- an exemption "
        "keyed on a path has to name exactly one file this repository "
        "tracks, or it is either exempting nothing or exempting more than "
        "somebody decided about"
    )
    return matched[0]


def exempted_block() -> str:
    """The key the value clause anchors on, read out of the file the path
    clause names and never typed here."""
    anchor = _allowlist()["regexes"][0]
    text = (ROOT / exempted_path()).read_text(encoding="utf-8")
    blocks = [
        match.group(0)
        for match in KEY_BLOCK.finditer(text)
        if re.search(anchor, match.group(0))
    ]
    assert blocks, (
        f"{exempted_path()} holds no private key the allowlist's value "
        "clause matches. A clause that matches nothing is an exemption "
        "that has quietly become a blank cheque: repoint it, or delete it."
    )
    return blocks[0]


def key_shaped(body: str) -> str:
    """A private key's shape around `body`.

    Assembled rather than written out for the reason `KEY_BLOCK` is: a
    literal here would put the shape this module is about into a file of
    this repository, and the scanner reads this file too.
    """
    dashes = "-" * 5
    header = f"{dashes}BEGIN PRIVATE KEY{dashes}"
    footer = f"{dashes}END PRIVATE KEY{dashes}"
    return f"{header}\n{body}\n{footer}\n"


def test_the_scanner_still_runs_every_rule_it_came_with() -> None:
    """First, because every clause below is worthless without it."""
    loaded = _configuration()
    assert loaded["extend"]["useDefault"] is True
    assert "rules" not in loaded, (
        "this repository defines no rule of its own; a rule here would "
        "silently replace the default of the same id"
    )


def test_the_scanner_is_pinned_to_one_version_in_both_places() -> None:
    """The workflow downloads it and the hook resolves it, and the
    allowlist below was verified against one of the two. Two pins that
    disagree is an exemption checked in a version that is not the version
    running."""
    workflow = yaml.safe_load(SECURITY_WORKFLOW.read_text(encoding="utf-8"))
    from_workflow = workflow["jobs"]["secrets"]["env"]["GITLEAKS_VERSION"]
    hooks = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    pinned = [repo for repo in hooks["repos"] if repo["repo"] == SCANNER_REPO]
    assert len(pinned) == 1, pinned
    assert pinned[0]["rev"] == f"v{from_workflow}"


def test_the_exemption_is_a_value_at_a_path_and_never_a_path() -> None:
    """`paths` on its own would exempt the whole file, and the file most
    likely to grow a second key is the file that already holds one: one
    decision would have become a standing hole in exactly the wrong place.
    `condition = "AND"` is what requires both clauses to hold."""
    entry = _allowlist()
    assert entry["targetRules"] == ["private-key"]
    assert entry["condition"] == "AND"
    assert entry["regexTarget"] == "secret"
    assert len(entry["paths"]) == 1
    assert len(entry["regexes"]) == 1


def test_the_path_clause_names_one_file_and_is_anchored_to_it() -> None:
    """The path half, held against the repository rather than against a
    constant. An unanchored clause is the failure that looks like success:
    it names the right file and covers a neighbour nobody decided about."""
    named = exempted_path()
    assert (ROOT / named).is_file()
    pattern = re.compile(_allowlist()["paths"][0])
    assert not pattern.search(named + ".bak")
    assert not pattern.search("docs/" + named)


def test_the_anchor_is_the_key_at_that_path_and_no_other_key() -> None:
    """The value half.

    **Where the anchor sits is the assertion that matters**, and it is
    checked by position rather than by luck. A PKCS#8 RSA key opens with a
    structure every key of its size shares -- around fifty base64
    characters of it, its exact length varying by a byte or two with the
    key -- and all of it lands inside the *first* body line. An anchor
    taken from there would exempt **any** private key at that path instead
    of this one, which is the failure the whole arrangement exists to
    avoid. So the anchor has to lie past that line entirely, which is also
    why it can be modulus: the public half, which the same file already
    publishes in the clear beside it.

    A freshly generated key is the empirical half of the same claim, and
    it is the product's own generator rather than an invented shape.
    """
    block = exempted_block()
    anchor = _allowlist()["regexes"][0]
    assert not re.search(anchor, key_shaped("\n".join(["A" * 64] * 3)))
    real = block.replace(chr(92) + "n", "\n")
    header_and_first_body_line = "\n".join(real.splitlines()[:2])
    assert anchor not in header_and_first_body_line, (
        "the anchor reaches into the first body line, where the structure "
        "every key of this kind shares still runs -- an anchor there "
        "exempts any private key at this path, not this one"
    )
    fresh, _public = eventkeys.generate()
    assert not re.search(anchor, fresh)


def test_the_configuration_is_not_a_second_copy_of_the_key() -> None:
    """An allowlist that quoted the key would have put a second copy of it
    in this repository, at a path nothing exempts. The anchor is modulus --
    the public half -- which is what makes the clause safe to publish."""
    text = CONFIG.read_text(encoding="utf-8")
    assert KEY_BLOCK.search(text) is None
    anchor = _allowlist()["regexes"][0]
    assert "PRIVATE KEY" not in anchor
    assert "-" not in anchor


def test_this_module_writes_neither_the_path_nor_the_value_it_is_about() -> None:
    """The claim the two readers above rest on, made checkable.

    Every clause here is reached by reading the configuration and then the
    file it names. If the path or the anchor were typed into this module,
    a clause repointed at something else would go on passing against the
    copy, which is the one way a control like this fails silently.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    entry = _allowlist()
    assert entry["paths"][0] not in source
    assert entry["regexes"][0] not in source
    assert exempted_path() not in source
