"""Every browser this repository opens is opened by one file.

`tools/visuals/browser.mjs` states the single argument any launch here ever
passes -- `--no-sandbox` -- together with the conditions under which it is
passed and the reason it is acceptable under them. Six scripts launch a
browser: the five renderers and checkers in `tools/visuals/`, and
`site/scripts/check-a11y.mjs`. Each of them called `puppeteer.launch`
directly until the first run of this repository on Linux, where five of the
six died inside Chrome's zygote for want of a user namespace, and the
obliging repair was the same flag typed into five files.

What this module refuses is that repair. A security boundary removed in
five places is five places a reader finds it removed with no argument
beside it, and five places to correct when the argument stops holding.

**The three shapes, and why each is a substring rather than a behaviour.**
Running any of these for real needs a browser binary, a built `app/` and a
built `site/` beneath it -- exactly what `gates.sh`'s own header says keeps
`check-a11y`, `render-and-compare`, `check-templates` and `check-posters`
out of that runner. So the properties held here are the ones reading the
files can establish, and the behaviour they stand for is exercised by the
four workflows that own those scripts.

* No file but the helper calls `puppeteer.launch`. That is what makes the
  helper the only door.
* No file but the helper names the sandbox waiver. A second file naming it
  has taken a decision the helper exists to hold.
* The helper's own rule still has both halves in it: the platform, and
  whether the browser is one this repository downloaded. Either half
  deleted widens the waiver in silence -- to Windows, where the sandbox
  works, or to the packaged browser the accessibility checker is handed,
  which starts its sandbox on the same runner that refused the other five.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from convener_ops.declaration.paths import repo_root

ROOT = repo_root()

#: The one file allowed to say either of the two things below.
HELPER = "tools/visuals/browser.mjs"

#: What a launch through the helper looks like at a call site. The scripts
#: import it under this name so that a reader of any one of them sees that
#: the launch is not local to the file they are in.
CALL = re.compile(r"\blaunchBrowser\s*\(")

#: A direct call on a puppeteer module, which only the helper makes.
#: Anchored on the dot: the helper's own parameter is a puppeteer module
#: handed in by the caller, and every other file reaches it the same way
#: or not at all.
DIRECT = re.compile(r"\bpuppeteer\s*\.\s*launch\s*\(")

#: The flag itself, wherever it is spelled. Narrow on purpose: every one
#: of these scripts parses its own `--out`, `--chrome`, `--app-dir` and
#: the rest, so a rule against "a string beginning with two dashes" would
#: fire on argument parsing in all six and be turned off within a week. It
#: is the waiver that may live in one file only, and this is its name.
WAIVER = re.compile(r"no-sandbox")

#: Where a top-level function ends in a file formatted the way this
#: repository formats its ES modules: a closing brace in the first column.
#: Written as a literal rather than matched, because the *first* `}` in the
#: predicate's text belongs to its own `options = {}` default.
END_OF_FUNCTION = """
}"""


def _scripts() -> dict[str, str]:
    """Every tracked ES module and CommonJS script in this repository, by
    repository-relative path.

    `git ls-files` rather than a walk, the same reason
    `test_writing_rules.py::_tracked_root_pages` gives: a file the index
    does not carry reaches nobody who clones this, and a scratch copy left
    in a working tree is not a subject. `node_modules` is untracked, which
    is what keeps a walk of `tools/visuals/` from reading puppeteer's own
    sources.
    """
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.mjs", "*.cjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return {
        name: (ROOT / name).read_text(encoding="utf-8")
        for name in listed
        if (ROOT / name).is_file()
    }


def test_the_sweep_reads_the_scripts_that_launch_a_browser() -> None:
    """Non-vacuity. A reader that stopped finding the scripts -- a rename,
    a move out of the index -- would pass all three rules below by having
    nothing to apply them to."""
    scripts = _scripts()

    assert HELPER in scripts, (
        f"{HELPER} is not tracked -- the file that carries this "
        "repository's launch argument is the one this module is about"
    )
    callers = sorted(name for name, text in scripts.items() if CALL.search(text))
    assert len(callers) == 6, (
        f"{len(callers)} script(s) launch a browser through the helper "
        f"({callers}) -- six did when this was written: five under "
        "tools/visuals/ and site/scripts/check-a11y.mjs. If a seventh has "
        "arrived, raise this count; if one has gone, lower it. A launch "
        "that stopped coming through the helper is what this notices"
    )
    assert any(name.startswith("site/") for name in callers), (
        "no script outside tools/visuals/ reaches the helper any more -- "
        "the accessibility checker is the caller that proves the rule "
        "narrows rather than simply waives"
    )


def test_no_script_but_the_helper_launches_a_browser_itself() -> None:
    """The first shape. A direct `puppeteer.launch` elsewhere is a launch
    whose arguments nothing holds, and the door the helper is."""
    offenders = sorted(
        name
        for name, text in _scripts().items()
        if name != HELPER and DIRECT.search(text)
    )

    assert offenders == [], (
        f"{offenders} call puppeteer.launch directly. Launch through "
        f"`launch` in {HELPER} instead: it is where what a browser is "
        "started with is decided, and a second caller is a second place "
        "for that to be decided differently"
    )


def test_no_script_but_the_helper_waives_the_sandbox() -> None:
    """The second shape, and the one the Linux failure would have produced
    five times over. The flag written at a call site is a boundary removed
    where nothing says why it was safe to remove it."""
    offenders = sorted(
        name
        for name, text in _scripts().items()
        if name != HELPER and WAIVER.search(text)
    )

    assert offenders == [], (
        f"{offenders} name the sandbox waiver. It is passed from {HELPER} "
        "alone, where what it costs and the two conditions it is passed "
        "under are written out -- named here, it is that argument made "
        "somewhere nobody reading it will find"
    )


def test_the_waiver_still_turns_on_both_of_its_conditions() -> None:
    """The third shape. The helper waives the sandbox for a Linux runner
    launching a browser puppeteer downloaded for itself, and for nothing
    else. Either condition dropped is a wider waiver than anybody argued
    for, and the file would still read as though it had been argued."""
    helper = (ROOT / Path(HELPER)).read_text(encoding="utf-8")
    rule = helper.split("export function sandboxIsUnavailable", 1)
    assert len(rule) == 2, (
        f"{HELPER} no longer defines `sandboxIsUnavailable` -- the "
        "predicate that decides the waiver is what the two halves below "
        "are read out of"
    )
    # To the closing brace in the first column: the signature's own
    # `options = {}` default puts a `}` inside the parameter list, so the
    # first one in the text is not the end of anything.
    body = rule[1].split(END_OF_FUNCTION, 1)[0]

    assert "process.platform === 'linux'" in body, (
        "the waiver no longer asks what platform it is on, so it now "
        "applies on Windows and macOS, whose sandboxes start. The "
        "maintainer's own machine is one of them"
    )
    assert "executablePath" in body, (
        "the waiver no longer asks whether the caller named a browser the "
        "machine already had, so it now applies to the packaged Chrome "
        "site/scripts/check-a11y.mjs is handed -- which keeps its sandbox "
        "on the same runner that refused the downloaded one"
    )
    assert "--no-sandbox" not in body, (
        "the predicate now carries the flag as well as the condition; the "
        "flag is a named constant above it so that one search finds it"
    )
