"""Every command a page tells a reader to type, on the shell they have.

`cd app && npm install && npm run dev` was the first command `README.md`
gave. On Windows PowerShell 5.1 -- the shell a Windows machine opens by
default -- it prints *The token '&&' is not a valid statement separator in
this version* and runs nothing at all. It was not one command: `&&` stood
22 times in `docs/operating/standing-up.md`, 14 times in
`docs/operating/operations.md`, 6 times in
`docs/operating/publishing-the-product.md` and twice in `README.md`, and
the standing-up guide is the page somebody with a browser and a text
editor walks before there is anything else here to read.

What a command is, here
-----------------------
Every line of a fenced block in a tracked Markdown page, and every inline
code span outside one. A block is swept unless its info string names a
language that is not a shell, which puts the default on the safe side: a
block nobody labelled is read as a command, so a label left off costs a
red suite rather than a silent hole. `LANGUAGES` is what exempts a block
and it names languages -- there is no page on it and no line on it, so
this cannot become the list of the commands somebody decided not to fix.

What it refuses
---------------
`&&` and `||`, the two shell control operators Windows PowerShell 5.1 does
not have. They are refused wherever a reader is told to type them; nothing
here reads `gates.sh`, `package.json` or a workflow, which are run by the
shell each one declares rather than typed by anybody.

The fix is never `;`. A command a reader types is one command, and where
it needs a directory the directory is a line of its own inside the block
(`cd tools`, then the command) or a phrase in the prose beside an inline
span (*run `uv run convener-validate` from `tools/`*). Both spellings work
on every shell this product is opened on, and neither asks the reader to
know which shell they are on.

Where a generated page's fix is
-------------------------------
`docs/operating/standing-up.md` and `docs/operating/standing-up-for-an-agent.md`
are rendered from `declarations/standing-up.yml`, and each says so on its
first line. A command corrected on the page is a command the next
`--check` deletes, so the failure below names the page and the page names
the declaration.

The class this does not cover, and why it is here rather than swept in
----------------------------------------------------------------------
Three commands are given with an environment variable in front of them, in
four places: `EVENT_ID=<event id> uv run convener-encrypt-attendance-export`
in `docs/handbook/workflow/4-after.md` and again in
`docs/operating/operations.md`, and `convener-encrypt-identifier` and
`convener-record-destructions` in the same page. PowerShell has no form of
that prefix, and there is no third spelling both shells accept, so no
rewording closes it: each of those three commands would have to take the
value as an option instead of reading it out of the environment, which is a
change to what this product offers rather than to what a page says about
it. Detecting the shape here without that change would be a red suite over
two pages nobody may fix, so it is written here instead, where the next
person to widen this sweep will read it.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
from typing import Final

from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

#: A fenced block's info string when the block is not a command. Anything
#: else -- `bash`, `sh`, `console`, or no info string at all -- is read as
#: commands. The list is of languages, so a page cannot be exempted and a
#: command cannot be exempted; only a block that says it is something else.
LANGUAGES: Final = frozenset(
    {
        "css",
        "diff",
        "html",
        "ini",
        "js",
        "json",
        "jsx",
        "mermaid",
        "python",
        "text",
        "toml",
        "ts",
        "tsx",
        "yaml",
        "yml",
    }
)

#: What PowerShell 5.1 answers with when it meets either of them, quoted so
#: that a failure says what the reader would see rather than only what the
#: rule is.
REFUSAL: Final = "The token '&&' is not a valid statement separator in this version"

#: The two operators. `;` is not among them: it separates statements in
#: both shells, and it is not what this repository writes either.
OPERATORS: Final = ("&&", "||")

#: One inline code span. Backticks do not nest and a span does not wrap, so
#: the shortest run between two backticks on one line is the whole of it.
INLINE_SPAN: Final = re.compile(r"`([^`\n]+)`")


def pages() -> list[tuple[str, str]]:
    """Every tracked Markdown page, with its text.

    The index rather than a walk: a page the index does not carry reaches
    nobody who clones this repository, and a scratch file left in a
    working copy is not a page this product publishes.
    """
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    return [
        (name, (ROOT / name).read_text(encoding="utf-8"))
        for name in sorted(listed)
        if (ROOT / name).is_file()
    ]


def commands(text: str) -> list[tuple[int, str]]:
    """Every command the page gives, as `(line number, command)`.

    A fenced block contributes each of its lines; a line outside one
    contributes each of its inline code spans. Which of the two a piece of
    text came through is not recorded, because the rule is the same for
    both and a failure names the line either way.
    """
    found: list[tuple[int, str]] = []
    language: str | None = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = line.strip()
        if marker.startswith("```"):
            language = None if language is not None else marker[3:].strip().lower()
            continue
        if language is not None:
            if language not in LANGUAGES and marker:
                found.append((number, marker))
            continue
        for match in INLINE_SPAN.finditer(line):
            found.append((number, match.group(1)))
    return found


def offences(swept: list[tuple[str, str]]) -> list[str]:
    """Every command carrying an operator, as `path:line: the command`."""
    found: list[str] = []
    for name, text in swept:
        for number, command in commands(text):
            if any(operator in command for operator in OPERATORS):
                found.append(f"{name}:{number}: {command}")
    return found


# ------------------------------------------------------------------ #
# The sweep is real.
# ------------------------------------------------------------------ #


def test_the_sweep_reads_the_pages_and_finds_the_commands_on_them() -> None:
    """A corpus that went empty, or a reader that found no command in it,
    would make the rule below pass by reading nothing."""
    swept = pages()

    assert len(swept) > 80, (
        f"{len(swept)} tracked Markdown pages reached the sweep, which is "
        "not this repository's documentation"
    )
    found = {name: commands(text) for name, text in swept}
    for page in (
        "README.md",
        "docs/operating/standing-up.md",
        "docs/operating/operations.md",
    ):
        assert found.get(page), f"no command was read out of {page}"
    everything = [command for lines in found.values() for _, command in lines]
    assert sum("uv run convener-check-config" in one for one in everything) > 10, (
        "the reader found almost none of the configuration report's own "
        "invocations, so it is not reading the pages that give them"
    )


def test_the_detector_reads_a_command_out_of_each_shape_a_page_uses() -> None:
    """Both doors: a fenced block, labelled or bare, and an inline span."""
    page = (
        "Run `cd tools && uv run convener-validate` first.\n"
        "\n"
        "```bash\n"
        "cd app && npm install\n"
        "```\n"
        "\n"
        "```\n"
        "cd site && npm ci\n"
        "```\n"
    )

    assert offences([("made-up.md", page)]) == [
        "made-up.md:1: cd tools && uv run convener-validate",
        "made-up.md:4: cd app && npm install",
        "made-up.md:8: cd site && npm ci",
    ]


def test_a_block_that_says_it_is_another_language_is_not_a_command() -> None:
    """The exemption, and the only one: `a && b` is an expression in every
    language this repository is written in, and a page showing one is not
    telling anybody to type it at a prompt."""
    page = "```ts\nconst ready = signed && loaded;\n```\n"

    assert offences([("made-up.md", page)]) == []


def test_the_second_operator_is_refused_as_well() -> None:
    """`||` is the other one PowerShell 5.1 has no form of, and this
    repository has never published it -- which is exactly why nothing
    would notice it arriving."""
    page = "```bash\nuv run convener-validate || echo failed\n```\n"

    assert offences([("made-up.md", page)]) == [
        "made-up.md:2: uv run convener-validate || echo failed"
    ]


# ------------------------------------------------------------------ #
# The rule.
# ------------------------------------------------------------------ #


def test_no_command_a_page_gives_uses_a_shell_operator() -> None:
    """The rule, on every page this repository publishes."""
    found = offences(pages())

    assert found == [], (
        f"these commands carry {' or '.join(OPERATORS)}, and a reader on "
        f'Windows PowerShell 5.1 is answered "{REFUSAL}" and runs nothing: '
        f"{found}. Put the directory on a line of its own inside the block, "
        "or name it in the prose beside an inline span; where the page is "
        "generated, the declaration it names on its first line is where the "
        "command is written"
    )
