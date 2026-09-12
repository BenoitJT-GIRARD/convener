# The operations package and its harnesses

`convener_ops` is the Python package every automated workflow in this
repository runs. Nothing schedules itself: each command is invoked by a
step in `.github/workflows/`, by a maintainer at a prompt, or by another
command, and each one either reads the records or writes something a person
or a page can read afterwards.

For where this directory sits in the system, and what a duplicate owns of
it, read [the architecture page](../docs/engineering/architecture.md).

## Running a command

```bash
cd tools
uv sync --all-extras
uv run --frozen convener-validate
```

`--frozen` on every invocation, because an unfrozen run rewrites `uv.lock`
— a change to the environment made by the act of using it.

## Where the commands are declared

`pyproject.toml`'s own `[project.scripts]` table, and nowhere else: 52
entries, each mapping the name an operator types to a function in
`convener_ops.cli`. That table is a published surface. A workflow names one
of those strings, an operator has one in their shell history, and
`docs/operating/` sends a reader to several by name, so a command keeps its
name when the function behind it moves.

`convener_ops/cli/` carries one module per sub-package it dispatches into,
and it is the only `__init__.py` in the package that re-exports anything —
exactly the names that table declares.

## Adding one

Three edits, and they are in three files on purpose. The work goes in a
module of the sub-package it belongs to, where the rule it applies already
lives. What an operator types goes in `pyproject.toml`. What connects the
two — reading the arguments, printing the lines, choosing the exit code —
goes in `convener_ops/cli/<sub-package>.py`, so that a rule stays testable
without a process and a command stays one thing to invoke.

## The sub-packages

One per subject, and the table below is the list. Each one's own
`__init__.py` opens with a single sentence saying what it gathers, which
is the sentence to read before opening anything inside it.

| Sub-package | Roughly |
|---|---|
| `cli/` | The way in. |
| `declaration/` | What one instance says about itself. |
| `governance/` | Deciding, and recording the decision. |
| `journey/` | One participant, one event, start to certificate. |
| `maintenance/` | Upkeep nobody is watching. |
| `publication/` | What the series shows the world. |

## What is not the package

**`scripts/`** holds the generators and the two operator scripts that are
not console commands. Six of the generators write a file this repository
also commits — the decision register, the schema appendix, both renderings
of the standing-up sequence, the charter tokens, the motif and the
directory map — and every one of them takes `--check`, which is how
continuous integration refuses a committed file that has drifted from what
generates it. They are scripts rather than commands because nobody outside
this repository ever runs one.

**`visuals/`** is a Node package with its own lockfile and its own README.

**`tests/`** holds the suite for all of the above, in eleven directories:
one per sub-package, one for `scripts/`, one for the checks on this
repository itself, one for the fixtures both languages read, and one for
what several modules need and none owns.
