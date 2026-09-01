"""The standing-up sequence, rendered as a procedure for an agent.

`STANDING-UP.yml` declares what somebody with no repositories and no accounts
does, in order, to have a running instance.
`tools/scripts/generate_standing_up_doc.py` renders it as the page a person follows.
This script renders the same declaration as
`docs/operating/standing-up-for-an-agent.md`: the procedure whatever carries
the sequence out follows instead.

What is derived, and how little of it there is
----------------------------------------------
Four things about a step reach the run sheet: its **position**, its
**identifier**, its **title**, and one word -- `carry out` or `hand over` --
which is `actor` translated one for one and nothing else. Everything a step
says stays where it is declared: `does`, `check`, `command`, `sets`,
`degraded` and `walkthrough` are read out of `STANDING-UP.yml` at the moment
the step comes up, by the agent following this page.

That line is the whole design. A run sheet that copied the steps into it
would be a third statement of one procedure, and the copy is always the one
that goes stale -- this repository has paid for that with three palettes,
five addresses and two path lists. What is left here is a **run sheet**: the
order, so that no step is skipped or taken early, and the actor, so that a
browser-only flow is never attempted by something with no browser.

The prose around the run sheet -- how to prove a step, when to stop, and what
may never be printed -- is written in this file, for the reason the page
generator gives for its own narrative: it is prose about the product rather
than a fact about the sequence, and nothing derives it.

One run sheet, not one per agent
--------------------------------
The run sheet sits under `docs/`, beside the guide that is the same
declaration's other rendering, and `AGENTS.md` points at it rather than
restating it. It is deliberately not under any agent vendor's own
conventional directory: such a path is found by one tool's discovery and by
no other, so it ships a preference between vendors, and the answer to a
second vendor is another line in `AGENTS.md` rather than a second copy.
Three renderings of one sequence would be the defect the declaration exists
to remove, arriving by a different door.

Pure, so `--check` means something
----------------------------------
The rendering reads `STANDING-UP.yml` and nothing else: no clock, no
environment, no `config/`, no `instance/data/`. Two runs over the same file produce
byte-identical output, so a difference can only be an edit made outside it --
which is what `--check` refuses, without repairing it.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python scripts/generate_standing_up_run_sheet.py            # write
    uv run python scripts/generate_standing_up_run_sheet.py --check    # assert

There is no mode that prints the page, for the reason the page generator
gives: nothing this repository's Python writes to a terminal is allowed to be
non-ASCII, and this page is written in the handbook's English.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from collections.abc import Sequence as Seq
from pathlib import Path
from typing import Final

from generate_standing_up_doc import (
    AGENT,
    DECLARATION_PATH,
    DOC_PATH,
    HUMAN,
    Sequence,
    Step,
    load_sequence,
)

from convener_ops.declaration.paths import repo_root

#: Where the run sheet lives. Inside the repository, so that a duplicate has
#: it from its first clone; under `docs/` beside the guide rather than under
#: an agent vendor's own directory, so that no tool reaches it by a route the
#: others do not have.
RUN_SHEET_PATH: Final = Path("docs") / "operating" / "standing-up-for-an-agent.md"

#: This file, named on the page so that nobody edits the page instead.
GENERATOR: Final = "tools/scripts/generate_standing_up_run_sheet.py"

#: What to run to rewrite it.
COMMAND: Final = "uv run python scripts/generate_standing_up_run_sheet.py"

#: The page every agent reaches this one through, and now the only route in:
#: nothing discovers a page under `docs/` on its own.
ENTRY_POINT: Final = "AGENTS.md"

#: The report most of the later checks are read out of.
REPORT: Final = "cd tools && uv run convener-check-config"

#: `actor`, translated into the one thing an agent does about it. Fixed
#: strings rather than something composed per step: `tools/tests/
#: test_standing_up.py` reads them back out of the committed page, so a step
#: whose actor changed in the declaration and not here is a failing test
#: rather than an agent quietly attempting a browser form.
ACTION: Final[dict[str, str]] = {
    HUMAN: "hand over",
    AGENT: "carry out",
}

#: What the page announces itself as, in one line under its own title. It
#: was a skill manifest's `description:` while the page sat where an agent's
#: tooling matched it against a situation; nothing matches it now, and a
#: reader sent here by `AGENTS.md` still needs a sentence saying what they
#: have been sent to.
DESCRIPTION: Final = (
    "Carry out STANDING-UP.yml, the declared sequence that turns no "
    "repositories and no accounts into a running instance of this product: "
    "run the steps it marks for an agent, hand the browser-only steps to the "
    "person word for word, and prove each one with its own declared check. "
    "Use when standing an instance up, resuming a half-standing one, or "
    "working out which steps are still outstanding."
)

#: The column the prose is wrapped to, matching the pages beside it.
WIDTH: Final = 78


def _wrap(text: str, *, indent: str = "", first: str | None = None) -> str:
    return textwrap.fill(
        text,
        width=WIDTH,
        initial_indent=first if first is not None else indent,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _bullets(items: Seq[str]) -> str:
    return "\n".join(_wrap(item, indent="  ", first="- ") for item in items)


def _numbered(items: Seq[str]) -> str:
    return "\n".join(
        _wrap(item, indent=" " * len(f"{index}. "), first=f"{index}. ")
        for index, item in enumerate(items, 1)
    )


def _summary() -> str:
    """The one line a reader who has been sent here meets first."""
    return _wrap(f"*{DESCRIPTION}*")


_NOTICE: Final = "\n\n".join(
    [
        "# Carrying out the standing-up sequence",
        _wrap(
            f"This page is generated from `{DECLARATION_PATH.as_posix()}`, the "
            f"one declaration of this sequence. Do not edit it: run `{COMMAND}` "
            "from `tools/` and commit what it writes, and continuous "
            "integration refuses a page the declaration does not derive. "
            f"`{DOC_PATH.as_posix()}` is the same declaration rendered for a "
            f"person, and `{ENTRY_POINT}` is where an agent is sent here "
            f"from -- nothing discovers this page on its own, so that pointer "
            f"is the only route in. The prose below lives in "
            f"`{GENERATOR}`; the run sheet at the end comes from the "
            "declaration."
        ),
    ]
)


def _introduction(sequence: Sequence) -> str:
    handed = sum(1 for step in sequence.steps if step.actor == HUMAN)
    return "\n\n".join(
        [
            "## What this page is, and what it is not",
            _wrap(
                f"`{DECLARATION_PATH.as_posix()}` declares what somebody with "
                "no repositories and no accounts does, in order, to have a "
                "running instance. It is a declaration rather than a page "
                "because more than one thing reads it, and this is one of them."
            ),
            _wrap(
                "**No step's content is repeated here, deliberately.** What a "
                "step does, what proves it is done, what an instance loses by "
                "skipping it, and the lines a person is handed word for word "
                "are all fields of that file, read out of it when the step "
                "comes up. The run sheet at the end of this page carries the "
                "order, the identifier and who acts — nothing else. A run "
                "sheet that restated the steps would be a second copy of one "
                "procedure, and the copy is the one that goes stale."
            ),
            _wrap(
                "**The guide is the product; this page is an accelerator.** "
                "One person with a web browser and a text editor finishes the "
                "whole sequence without an agent, and that is the path the "
                "product is designed around: nothing it does may depend on a "
                "tool somebody has to pay for. So nothing here makes that path "
                "slower or less complete, and no step below is reachable only "
                f"through an agent. {handed} of the {len(sequence.steps)} "
                "steps are a person's whatever else is available — a flow that "
                "exists only in a browser, or a value that must never leave "
                "the hands of whoever minted it."
            ),
        ]
    )


_BEFORE: Final = "\n\n".join(
    [
        "## Before the first step",
        _numbered(
            [
                f"Read `{DECLARATION_PATH.as_posix()}` from its first line to "
                "its last, header included. The header states what each field "
                "means, why a step belongs to a person or to an agent, and the "
                "five places where the order carries weight.",
                f"Run `{REPORT}` and show the person what it prints. Each row "
                "reported absent is a step below that has not happened yet, "
                "and that row's `meanwhile:` line is what its absence costs "
                "today.",
                "Work out where the sequence has already got to from the "
                "checks, never from what anybody remembers doing. Resuming a "
                "half-standing instance is the ordinary case, not the "
                "exception.",
                "Say which steps you will carry out and which you will hand "
                "over, before starting either.",
            ]
        ),
    ]
)


_LOOP: Final = "\n\n".join(
    [
        "## The loop",
        _wrap("For each step in the declared order, one step at a time:"),
        _numbered(
            [
                "Read that step's own entry in the declaration: `does`, "
                "`check`, `command` where it has one, `sets`, `walkthrough`, "
                "and either `degraded` or `integrations`.",
                "Where the run sheet says **carry out**, do it — with `gh`, "
                "`wrangler`, `tools/scripts/create_tally_form.py`, a file edit, or "
                "one of this repository's own commands.",
                "Where it says **hand over**, stop, give the person the step, "
                "and wait for them.",
                "Prove it with that step's own `check`.",
                "Only then move to the next one.",
            ]
        ),
        _wrap(
            "Never run two steps together, and never take one early. The "
            "declaration's own note above `steps:` names the five places where "
            "the order is load-bearing and what each one costs to get wrong."
        ),
    ]
)


_HANDOVER: Final = "\n\n".join(
    [
        "## Handing a step over",
        _wrap(
            "A step belongs to a person for one of two reasons, both "
            "operational rather than a preference about who ought to do the "
            "work. Either the flow exists only in a browser and has no "
            "interface anything could call — GitHub mints no fine-grained "
            "personal access token through an API, and an App is registered on "
            "a form from start to finish — or the value the step produces must "
            "never exist anywhere but in the hands of whoever minted it. "
            "Neither is worked around."
        ),
        _wrap("Hand one over like this:"),
        _bullets(
            [
                "Name the step and read out its `does`.",
                "Read out every line of its `walkthrough`, in order and "
                "unaltered. Those lines are written to be complete on their "
                "own; summarising one drops the sentence that stops somebody "
                "choosing the wrong option on a form with twenty fields.",
                "Read out its `check`, so the person knows what they are aiming at.",
                "Add nothing. A screen described from memory rather than from "
                "the declaration is worse than no description, because it is "
                "specific and wrong.",
            ]
        ),
        _wrap(
            "Then wait. Do not offer to do the person's half, and never ask "
            "for a value so that you can set it on their behalf."
        ),
    ]
)


_PROOF: Final = "\n\n".join(
    [
        "## Proving a step",
        _wrap(
            "The check belongs to the step, not to you. Satisfy the one the "
            "declaration gives, as it is written."
        ),
        _bullets(
            [
                "Where it names a command, run the command and read what it prints.",
                f"Where it names the configuration report, run `{REPORT}` and "
                "find the row the check names by its own label.",
                "Where it can only be read in a browser, ask the person what "
                "the page shows and take their answer. Asking is the check "
                "working; inferring is the check skipped.",
            ]
        ),
        _wrap(
            "**A step that looks done is not done.** Several of the failures "
            "this sequence exists to surface are green runs: a publishing "
            "workflow that logs one line and exits cleanly because no token is "
            "set, a deploy that skips itself while a placeholder identifier "
            "stands, a Pages source answering 200 with a repository's README "
            "over a site that does not exist. An exit code of zero is not a "
            "check, and neither is your own reading of what probably happened."
        ),
    ]
)


_STOPPING: Final = "\n\n".join(
    [
        "## When a check fails",
        _wrap(
            "Stop. Report which step, quote its `check`, and say what happened "
            "instead. Do not attempt the next step, do not reach the same "
            "effect by another route, and do not guess at a value."
        ),
        _wrap(
            "A half-configured instance that reports success is worse than one "
            "that stops. This product's own rule is that an absent integration "
            "stays visible, and an instance believed to be finished is one "
            "nobody looks at again."
        ),
        _wrap(
            "Stopping on purpose is a different thing, and it is a normal end. "
            "The last stage is a menu rather than a queue. Where somebody "
            "decides to stop there, say what each remaining step costs — from "
            "that step's own `degraded`, or, for a step that names integration "
            "rows, from the report's `meanwhile:` line for those rows. Do not "
            "write that sentence yourself."
        ),
    ]
)


_SECRETS: Final = "\n\n".join(
    [
        "## Secrets",
        _wrap(
            "None of these is a preference, and none has an exception that is "
            "not written here."
        ),
        _bullets(
            [
                "**Never read, print, echo, log or write a secret value.** Not "
                "into your own session log, not into a file, not into a command line, "
                "not into an example that looks real. If a value reaches you "
                "anyway, say so and ask for it to be replaced rather than "
                "carrying on with it.",
                "**A repository secret is set by the person, under their own "
                "credentials.** `gh secret set <NAME>` reads the value from "
                "its own prompt under that person's `gh auth`; run it only "
                "with somebody at the keyboard, and never with `--body`, which "
                "puts the value in a command line and in a shell history. That "
                "prompt is a gate rather than an obstacle. Where a browser is "
                "easier, the declaration's `secrets:` table carries the menu "
                "path for every credential it names, and the browser is a "
                "complete route.",
                "**A worker secret has the same shape.** `npx wrangler secret "
                "put <NAME>` prompts too, and the declaration carries that "
                "command beside the dashboard path for each one.",
                "**Where a walkthrough says a value must never be written to a "
                "file, that is the whole rule.** Do not offer to generate it, "
                "do not offer a shell to generate it in, and do not read the "
                "terminal it is generated in. `docs/operating/operations.md` "
                "states the same refusal for the certificate signing key, "
                "which is the one credential in this product that nothing "
                "automated is allowed near.",
                "**A local `.env` is allowed exactly once, and is deleted.** "
                "One credential in this sequence is spent from a shell rather "
                "than set on a repository or a worker: the key that builds the "
                "public proposal form. The person writes it into `.env` at the "
                "repository root — never you — and `git check-ignore .env` "
                "confirms the file is ignored before it is created. Delete it "
                "as soon as the form exists, whether or not the run succeeded, "
                "and say that you have.",
            ]
        ),
    ]
)


_CLOSING: Final = "\n\n".join(
    [
        "## When the sequence ends",
        _bullets(
            [
                f"Run `{REPORT}` once more and show the person every row and "
                "its state.",
                "Confirm no `.env` is left anywhere in the working tree.",
                "Confirm the working tree holds nothing else you did not mean "
                "to leave in it.",
                "List the steps that were not done and what each costs, from "
                "the declaration.",
                "Say that every credential minted along the way belongs in the "
                "store two people can open. A value held only in one person's "
                "browser is what the first stage exists to prevent, and it is "
                "the one failure in this sequence that cannot be corrected "
                "later.",
            ]
        ),
        _wrap(
            "`docs/operating/operations.md` is what an instance runs on "
            "afterwards. This page hands over to it and does not repeat it."
        ),
    ]
)


def _row(step: Step, sequence: Sequence) -> str:
    """One run-sheet row, and the shape the binding test reads back."""
    return (
        f"| {sequence.number_of(step)} | `{step.id}` | "
        f"{ACTION[step.actor]} | {step.title} |"
    )


def _run_sheet(sequence: Sequence) -> list[str]:
    """The order, the identifier, the actor and the title. Nothing else."""
    handed = sum(1 for step in sequence.steps if step.actor == HUMAN)
    blocks = [
        "## The sequence, in order",
        _wrap(
            f"{len(sequence.steps)} steps in {len(sequence.stages)} stages. "
            f"{handed} are handed over; the rest an agent carries out. Read "
            f"each step's own entry in `{DECLARATION_PATH.as_posix()}` before "
            "carrying it out or handing it over."
        ),
    ]
    for index, stage in enumerate(sequence.stages, 1):
        blocks.append(f"### Stage {index} — {stage.title}")
        rows = ["| # | Step | Action | Title |", "|---|---|---|---|"]
        rows.extend(_row(step, sequence) for step in sequence.steps_in(stage.id))
        blocks.append("\n".join(rows))
    return blocks


def render_run_sheet(sequence: Sequence) -> str:
    """The run sheet the declaration derives."""
    blocks: list[str] = [
        _NOTICE,
        _summary(),
        _introduction(sequence),
        _BEFORE,
        _LOOP,
        _HANDOVER,
        _PROOF,
        _STOPPING,
        _SECRETS,
        *_run_sheet(sequence),
        _CLOSING,
    ]
    return "\n".join(block.rstrip("\n") + "\n" for block in blocks)


def standing_up_run_sheet(root: Path) -> str:
    """The run sheet this repository's declaration derives, today."""
    return render_run_sheet(load_sequence(root))


def main(argv: Seq[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the standing-up run sheet from STANDING-UP.yml."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the committed page is not what it derives",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    rendered = standing_up_run_sheet(root)
    path = root / RUN_SHEET_PATH
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if args.check:
        if current != rendered:
            print(
                f"{RUN_SHEET_PATH.as_posix()} is not what "
                f"{DECLARATION_PATH.as_posix()} derives.",
                file=sys.stderr,
            )
            print(
                f"It is generated, not authored: run `{COMMAND}` from `tools/`"
                " and commit the file it writes.",
                file=sys.stderr,
            )
            return 1
        print(f"{RUN_SHEET_PATH.as_posix()} matches the declaration")
        return 0

    if current == rendered:
        print(f"{RUN_SHEET_PATH.as_posix()} unchanged")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8", newline="")
    print(f"wrote {RUN_SHEET_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
