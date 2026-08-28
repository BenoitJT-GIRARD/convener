"""The standing-up guide, rendered from the sequence it describes.

`docs/reference/standing-up.md` is the page somebody with no repositories and
no accounts reads. A later agent skill carries the same sequence out. Two
documents describing one procedure diverge -- this repository has already paid
for that with three palettes, five addresses and two path lists -- so there is
one declaration, `STANDING-UP.yml`, and this script renders the page from it.

What is derived and what is written
-----------------------------------
Every **step, its actor, its check, its command and its degradation** comes
from the declaration, and so does every **credential row**. What is written
here instead is the **narrative**: the sentences around the steps that say
what the page is, who it is for and how to read a step. Those are prose about
the product rather than facts about the sequence, nothing derives them, and
whoever writes a new one writes it here, not in the generated page -- which
says so at the top.

One thing is derived from a *second* file, and deliberately. A step that
completes an integration names the rows in `config/integrations.yml` rather
than restating what an absent integration costs, and this script renders what
`convener-check-config` already prints for those rows. That report is the
authority on the question; a paragraph copied out of it into the declaration
would be a second source for the one fact it answers.

Why this and not the handbook's own transclusion
------------------------------------------------
`app/src/content/transclude.ts` includes one *registered page's* section into
another registered page, in the browser, at read time. It cannot help here for
two reasons that are both structural. The declaration is YAML, not a page with
headings, and a fragment is a window onto a heading; and this page is
deliberately not registered, for the reason `docs/reference/operations.md` is
not -- it names every secret an instance uses, and the registry is the
allowlist of what `app/scripts/copy-handbook.mjs` publishes into a bundle
served from a *public* repository. So the binding is the one
`scripts/generate_schema_doc.py` already established for a page derived from a
file that is not a page: generate, commit, and let `--check` refuse anything
else.

Pure, so `--check` means something
----------------------------------
The rendering reads the declaration and `config/integrations.yml` and nothing
else: no clock, no environment, no `instance/data/`. Two runs over the same two files
produce byte-identical output, so a difference can only be an edit made
outside them -- which is exactly what `--check` refuses, without repairing it.
A check that silently rewrote the file it was checking would report success on
a repository that still held the wrong page.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python ../scripts/generate_standing_up_doc.py            # write it
    uv run python ../scripts/generate_standing_up_doc.py --check    # assert

There is no mode that prints the page: it is written in the handbook's British
English and the rest of it, and nothing this repository's Python writes to a
terminal is allowed to be non-ASCII.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from collections.abc import Sequence as Seq
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

from convener_ops.integrations import Integration, load_declaration
from convener_ops.paths import repo_root

#: The declaration this page is rendered from. At the repository root rather
#: than in `config/`, and that file's own header argues why.
DECLARATION_PATH: Final = Path("STANDING-UP.yml")

#: The page it renders.
DOC_PATH: Final = Path("docs") / "reference" / "standing-up.md"

#: The other file read, and the only one: what an absent integration costs.
INTEGRATIONS_PATH: Final = Path("config") / "integrations.yml"

#: What to run, named in the page itself so nobody edits the page instead.
COMMAND: Final = "uv run python ../scripts/generate_standing_up_doc.py"

#: The declaration's own format version.
DECLARATION_VERSION: Final = 1

#: The two answers to "who carries this out", and the only two. See
#: `STANDING-UP.yml`'s header for what each one means and why the line
#: between them is where it is.
HUMAN: Final = "human"
AGENT: Final = "agent"
ACTORS: Final = (HUMAN, AGENT)

#: How each actor is written on the page. Fixed strings rather than something
#: composed per step: `tools/tests/test_standing_up.py` reads them back out of
#: the committed page, so a step whose actor changed in the declaration and
#: not on the page is a failing test rather than a guide that lies about who
#: has to be at the keyboard.
ACTOR_LINE: Final[dict[str, str]] = {
    HUMAN: "**Who:** a person.",
    AGENT: "**Who:** an agent, or a person.",
}

#: Where a credential is set, and what `home` means for each. A repository
#: kind names one of the declared repositories; a worker kind names the
#: directory its worker deploys from; `operator-shell` names nowhere at all,
#: which is the point of it having a kind of its own.
REPOSITORY_KINDS: Final = ("repository-secret", "repository-variable")
KINDS: Final = (*REPOSITORY_KINDS, "worker-secret", "operator-shell")

#: How wide the prose is wrapped. The handbook is read in a narrow column on
#: GitHub and inside a cockpit panel; 78 is what the pages beside this one
#: already sit at.
WIDTH: Final = 78


@dataclass(frozen=True)
class Repository:
    """One of the two repositories an instance runs on."""

    id: str
    visibility: str
    what: str


@dataclass(frozen=True)
class Stage:
    """A run of steps that ends somewhere a person can stop."""

    id: str
    title: str
    purpose: str


@dataclass(frozen=True)
class Step:
    """One act, and everything needed to tell whether it has been done.

    `degraded` and `integrations` are alternatives, never both: a step that
    completes an integration says which rows, and what its absence costs is
    read from `config/integrations.yml` at render time rather than written
    down twice.
    """

    id: str
    stage: str
    title: str
    actor: str
    does: str
    check: str
    command: str | None = None
    degraded: str | None = None
    integrations: tuple[str, ...] = ()
    sets: tuple[str, ...] = ()
    walkthrough: tuple[str, ...] = ()


@dataclass(frozen=True)
class Secret:
    """One credential, where it belongs, and the menu path it is set by.

    Never a value. `set_command` is the equivalent for somebody who would
    rather type than click, and it is optional because most of these have no
    equivalent -- a repository secret is set in a browser or not at all.
    """

    name: str
    kind: str
    home: str
    set_through: str
    why: str
    set_command: str | None = None


@dataclass(frozen=True)
class Deferred:
    """A secret that exists and is deliberately not part of standing up."""

    secret: str
    reason: str


@dataclass(frozen=True)
class Sequence:
    """The whole declaration, parsed."""

    repositories: tuple[Repository, ...]
    stages: tuple[Stage, ...]
    steps: tuple[Step, ...]
    secrets: tuple[Secret, ...]
    not_at_setup: tuple[Deferred, ...]
    #: Every secret name any step sets, computed once.
    set_names: frozenset[str] = field(default_factory=frozenset)

    def steps_in(self, stage: str) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if step.stage == stage)

    def number_of(self, step: Step) -> int:
        """Its position in the whole sequence, counting from one."""
        return self.steps.index(step) + 1


def _text(raw: Any, what: str) -> str:
    """One non-empty string, or a `ValueError` naming what it was meant to be.

    A declaration that cannot be read stops the render rather than being
    guessed at: this file is what a person with no repositories follows, and a
    field silently defaulted here is a step nobody is told to take.
    """
    named = DECLARATION_PATH.as_posix()
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{named}: {what} must be a non-empty string, got {raw!r}")
    return " ".join(raw.split())


def _strings(raw: Any, what: str) -> tuple[str, ...]:
    named = DECLARATION_PATH.as_posix()
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{named}: {what} must be a list, got {raw!r}")
    return tuple(_text(item, f"an entry of {what}") for item in raw)


def _repositories(raw: Any) -> tuple[Repository, ...]:
    named = DECLARATION_PATH.as_posix()
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{named}: repositories: must be a non-empty list")
    out: list[Repository] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{named}: repositories: holds {item!r}, not an entry")
        visibility = _text(item.get("visibility"), "a repository's visibility")
        if visibility not in ("private", "public"):
            raise ValueError(
                f"{named}: a repository is private or public, got {visibility!r}"
            )
        out.append(
            Repository(
                id=_text(item.get("id"), "a repository id"),
                visibility=visibility,
                what=_text(item.get("what"), "what a repository is"),
            )
        )
    _refuse_repeats([r.id for r in out], "repository id")
    return tuple(out)


def _stages(raw: Any) -> tuple[Stage, ...]:
    named = DECLARATION_PATH.as_posix()
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{named}: stages: must be a non-empty list")
    out: list[Stage] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{named}: stages: holds {item!r}, not an entry")
        out.append(
            Stage(
                id=_text(item.get("id"), "a stage id"),
                title=_text(item.get("title"), "a stage title"),
                purpose=_text(item.get("purpose"), "a stage's purpose"),
            )
        )
    _refuse_repeats([s.id for s in out], "stage id")
    return tuple(out)


def _refuse_repeats(names: list[str], what: str) -> None:
    named = DECLARATION_PATH.as_posix()
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ValueError(f"{named}: {name!r} is declared twice as a {what}")
        seen.add(name)


def _steps(raw: Any, stages: tuple[Stage, ...]) -> tuple[Step, ...]:
    named = DECLARATION_PATH.as_posix()
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{named}: steps: must be a non-empty list")
    known = {stage.id for stage in stages}
    out: list[Step] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{named}: steps: holds {item!r}, not an entry")
        identifier = _text(item.get("id"), "a step id")
        stage = _text(item.get("stage"), f"{identifier}'s stage")
        if stage not in known:
            raise ValueError(
                f"{named}: {identifier} names no declared stage: {stage!r}"
            )
        actor = _text(item.get("actor"), f"{identifier}'s actor")
        if actor not in ACTORS:
            raise ValueError(
                f"{named}: {identifier}'s actor is one of "
                f"{', '.join(ACTORS)}, got {actor!r}"
            )
        degraded = item.get("degraded")
        integrations = _strings(
            item.get("integrations"), f"{identifier}'s integrations"
        )
        if bool(degraded) == bool(integrations):
            raise ValueError(
                f"{named}: {identifier} must carry either degraded: or "
                "integrations:, and not both -- a step that completes an "
                "integration reads what its absence costs from "
                f"{INTEGRATIONS_PATH.as_posix()} rather than restating it"
            )
        walkthrough = _strings(item.get("walkthrough"), f"{identifier}'s walkthrough")
        if actor == HUMAN and not walkthrough:
            raise ValueError(
                f"{named}: {identifier} is a {HUMAN} step and carries no "
                "walkthrough. Those sections are handed to a person verbatim, "
                "so they have to be complete on their own."
            )
        if actor == AGENT and walkthrough:
            raise ValueError(
                f"{named}: {identifier} is an {AGENT} step and carries a "
                "walkthrough. A browser walkthrough beside a command is the "
                "second source this declaration exists to refuse."
            )
        command = item.get("command")
        out.append(
            Step(
                id=identifier,
                stage=stage,
                title=_text(item.get("title"), f"{identifier}'s title"),
                actor=actor,
                does=_text(item.get("does"), f"what {identifier} does"),
                check=_text(item.get("check"), f"what proves {identifier} is done"),
                command=_text(command, f"{identifier}'s command") if command else None,
                degraded=(
                    _text(degraded, f"what {identifier} costs to skip")
                    if degraded
                    else None
                ),
                integrations=integrations,
                sets=_strings(item.get("sets"), f"what {identifier} sets"),
                walkthrough=walkthrough,
            )
        )
    _refuse_repeats([step.id for step in out], "step id")
    _refuse_scattered_stages(out, stages)
    return tuple(out)


def _refuse_scattered_stages(steps: list[Step], stages: tuple[Stage, ...]) -> None:
    """Every stage's steps sit together, in the order the stages are declared.

    The page renders one heading per stage and the steps under it in order, so
    a stage revisited later would either lose those steps or reorder the
    sequence somebody is meant to follow. Refusing it here means the page can
    never disagree with the numbering the declaration implies.
    """
    named = DECLARATION_PATH.as_posix()
    order = [stage.id for stage in stages]
    seen: list[str] = []
    for step in steps:
        if not seen or seen[-1] != step.stage:
            if step.stage in seen:
                raise ValueError(
                    f"{named}: {step.stage!r} is returned to at {step.id!r} after "
                    "another stage. A stage's steps sit together."
                )
            seen.append(step.stage)
    if seen != order[: len(seen)]:
        raise ValueError(
            f"{named}: the steps run through the stages as {seen}, which is not "
            f"the order stages: declares ({order})"
        )


def _secrets(raw: Any, repositories: tuple[Repository, ...]) -> tuple[Secret, ...]:
    named = DECLARATION_PATH.as_posix()
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{named}: secrets: must be a non-empty list")
    homes = {repository.id for repository in repositories}
    out: list[Secret] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{named}: secrets: holds {item!r}, not an entry")
        name = _text(item.get("name"), "a secret's name")
        kind = _text(item.get("kind"), f"{name}'s kind")
        if kind not in KINDS:
            raise ValueError(
                f"{named}: {name}'s kind is one of {', '.join(KINDS)}, got {kind!r}"
            )
        home = _text(item.get("home"), f"where {name} is set")
        if kind in REPOSITORY_KINDS and home not in homes:
            raise ValueError(
                f"{named}: {name} is set on {home!r}, which is not one of the "
                f"declared repositories ({', '.join(sorted(homes))})"
            )
        if kind == "worker-secret" and not home.startswith("services/"):
            raise ValueError(
                f"{named}: {name} is a worker secret, so its home is the "
                f"directory its worker deploys from, got {home!r}"
            )
        set_command = item.get("set_command")
        out.append(
            Secret(
                name=name,
                kind=kind,
                home=home,
                set_through=_text(item.get("set_through"), f"how {name} is set"),
                why=_text(item.get("why"), f"what {name} is for"),
                set_command=(
                    _text(set_command, f"{name}'s command") if set_command else None
                ),
            )
        )
    _refuse_repeats([f"{s.name} on {s.home}" for s in out], "credential")
    return tuple(out)


def _deferred(raw: Any) -> tuple[Deferred, ...]:
    named = DECLARATION_PATH.as_posix()
    if not isinstance(raw, list):
        raise ValueError(f"{named}: not_at_setup: must be a list")
    out: list[Deferred] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{named}: not_at_setup: holds {item!r}, not an entry")
        secret = _text(item.get("secret"), "a deferred secret's name")
        out.append(Deferred(secret=secret, reason=_text(item.get("reason"), secret)))
    return tuple(out)


def sequence_from_data(data: Any) -> Sequence:
    """Parse an already YAML-loaded `STANDING-UP.yml`.

    Refuses rather than repairs. Every rule refused here is one that would
    otherwise reach the page as a step nobody can carry out: an actor that is
    neither of the two, a human step with no walkthrough, a credential set on
    a repository that does not exist, a step whose degradation is written
    twice.
    """
    named = DECLARATION_PATH.as_posix()
    if not isinstance(data, dict) or data.get("v") != DECLARATION_VERSION:
        raise ValueError(f"{named} is not a supported format version")
    repositories = _repositories(data.get("repositories"))
    stages = _stages(data.get("stages"))
    steps = _steps(data.get("steps"), stages)
    secrets = _secrets(data.get("secrets"), repositories)
    declared = {secret.name for secret in secrets}
    set_names: set[str] = set()
    for step in steps:
        for name in step.sets:
            if name not in declared:
                raise ValueError(
                    f"{named}: {step.id} sets {name!r}, which secrets: does not "
                    "declare. Where a credential belongs, and the menu path it "
                    "is set by, is written once."
                )
            set_names.add(name)
    unset = sorted(declared - set_names)
    if unset:
        raise ValueError(
            f"{named}: nothing sets {', '.join(unset)}. A credential no step "
            "reaches is one a reader is never told to create."
        )
    return Sequence(
        repositories=repositories,
        stages=stages,
        steps=steps,
        secrets=secrets,
        not_at_setup=_deferred(data.get("not_at_setup")),
        set_names=frozenset(set_names),
    )


def load_sequence(root: Path) -> Sequence:
    """The declaration as this repository holds it."""
    raw = (root / DECLARATION_PATH).read_text(encoding="utf-8")
    return sequence_from_data(yaml.safe_load(raw))


def integration_rows(root: Path) -> dict[str, Integration]:
    """`config/integrations.yml`, by row name."""
    return {row.name: row for row in load_declaration(root / INTEGRATIONS_PATH)}


def uncovered_integrations(
    sequence: Sequence, rows: dict[str, Integration]
) -> tuple[str, ...]:
    """Integration secrets this sequence neither sets nor defers.

    The other direction of the binding: `sequence_from_data` refuses a step
    that sets an undeclared credential, and this refuses a credential the
    product's own integrations declaration knows about and this sequence has
    never heard of. A row added to `config/integrations.yml` therefore has to
    be decided about -- set at standing-up time, or named in `not_at_setup:`
    with a reason -- rather than quietly left out of the one page that says
    how to stand an instance up.
    """
    deferred = {entry.secret for entry in sequence.not_at_setup}
    known = sequence.set_names | deferred
    return tuple(
        sorted(
            {
                secret
                for row in rows.values()
                for secret in row.secrets
                if secret not in known
            }
        )
    )


def unnamed_integrations(
    sequence: Sequence, rows: dict[str, Integration]
) -> tuple[str, ...]:
    """Integration rows nothing here accounts for, and rows named that do not
    exist.

    A row is accounted for when a step completes it, or when every secret it
    names is deferred with a reason -- which is the shape `event_keys` has,
    being one key per event rather than one per instance. Anything else is a
    row a reader will meet in the report with nothing on this page that turns
    it green, or a name in this declaration pointing at a row that has been
    removed.
    """
    named = {name for step in sequence.steps for name in step.integrations}
    deferred = {entry.secret for entry in sequence.not_at_setup}
    accounted = {
        name
        for name, row in rows.items()
        if name in named or (row.secrets and set(row.secrets) <= deferred)
    }
    return tuple(sorted((set(rows) - accounted) | (named - set(rows))))


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _wrap(text: str, *, indent: str = "", first: str | None = None) -> str:
    return textwrap.fill(
        text,
        width=WIDTH,
        initial_indent=first if first is not None else indent,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _quote(text: str) -> str:
    """A blockquote, wrapped, for a passage this page is quoting rather than
    stating: what `convener-check-config` prints for one integration row."""
    return _wrap(text, indent="> ")


_HEADER: Final = f"""# Standing up an instance

*This page is generated from* `{DECLARATION_PATH.as_posix()}` — *the one
declaration of this sequence, which the agent that carries it out reads too.
Do not edit it: run* `{COMMAND}` *from* `tools/` *and commit what it writes,
and continuous integration refuses a page the declaration does not derive.
Every step, actor, check, command and degradation below comes from that file;
what an absent integration costs comes from*
`{INTEGRATIONS_PATH.as_posix()}`*, which* `convener-check-config` *already
prints. The prose between the steps lives in*
`scripts/generate_standing_up_doc.py`*.*
"""

_INTRODUCTION: Final = """\
Everything else written here is written for an instance that already exists.
This page is the other half: what somebody with no repositories and no
accounts does, in order, to have a seminar series running at the end of it.

**It costs nothing, and it needs nothing installed.** Every step below can be
carried out with a web browser and a text editor. Where a command is faster it
is given, and the browser equivalent is given beside it — an operator who
cannot install a command-line tool, or will not, is not a second-class reader
of this page. Every account it asks for has a free tier that this project fits
inside; none of them asks for a card.

**Nothing here depends on anybody's goodwill.** Each account belongs to the
organisation rather than to a person, each credential is written into a store
two people can open, and the whole of it can be handed to a successor by
transferring two repositories. That is not a nicety — it is the constraint
the rest of the design follows from.

Read it once before starting. The order matters in five places, each of them
noted where it arises, and reordering those is the difference between a
working instance and one that has published something it cannot take back.\
"""

_HOW_TO_READ: Final = """\
Each step says who has to carry it out, what it does, what proves it is done,
and what an instance loses by skipping it.

**Who.** A step marked *a person* has no other option: either the flow exists
only in a browser and has no interface anything could call (creating a
mailbox, registering a GitHub App, minting a personal access token), or the
value it produces must never exist anywhere but in the hands of whoever minted
it. A step marked *an agent, or a person* is a file edit, a command or an API
call, and it makes no difference which of you does it.

**Proves it is done.** Stated so that a browser is enough to read it. A step
with a command carries it underneath; the command is faster, never required.

**Without it.** What the instance loses. For most of these the answer is a
feature that degrades visibly and nothing else — an absent integration is a
normal state in this project, not an error, and an instance that stops
halfway down this page is a working instance. The steps where that is *not*
true say so in those words.

**Run the report.** `cd tools && uv run convener-check-config` prints every
integration this product declares, what each one is waiting on, and what
happens meanwhile. It is the same source the *Without it* paragraphs below
quote, so it is worth running before the first step and after each of the
later ones.\
"""

_CLOSING: Final = """\
`docs/reference/operations.md` is the page to read next, and the one to keep
open afterwards: it covers everything an instance does *after* it is standing
— handling a registration, matching attendance, issuing and revoking a
certificate, draining the queue, the retention sweep and the early-erasure
path. This page hands over to it and does not repeat it.\
"""


def _repository_table(sequence: Sequence) -> list[str]:
    rows = ["| Repository | Visibility | What it is |", "|---|---|---|"]
    for repository in sequence.repositories:
        rows.append(
            f"| `{repository.id}` | {repository.visibility} | {repository.what} |"
        )
    return rows


def _credential_table(sequence: Sequence) -> list[str]:
    rows = ["| Credential | Kind | Where | Set through |", "|---|---|---|---|"]
    for secret in sequence.secrets:
        home = secret.home if secret.kind.startswith("worker") else f"`{secret.home}`"
        if secret.kind == "operator-shell":
            home = secret.home
        through = secret.set_through
        if secret.set_command:
            through = f"{through}, or `{secret.set_command}`"
        rows.append(f"| `{secret.name}` | {secret.kind} | {home} | {through} |")
    return rows


def _without_it(step: Step, rows: dict[str, Integration]) -> list[str]:
    if step.degraded:
        return [_wrap(f"**Without it.** {step.degraded}")]
    out: list[str] = []
    for name in step.integrations:
        row = rows[name]
        lead = (
            f"**Without it.** *The* **{row.label}** *row of* "
            f"`{INTEGRATIONS_PATH.as_posix()}`*, which* `convener-check-config` "
            f"*prints as this row's* `meanwhile:` *line. It is maintained there,"
            " and quoted here.*"
        )
        out.append(_wrap(lead))
        out.append("")
        out.append(_quote(row.absent_behaviour))
        if not row.absent_is_normal:
            out.append("")
            out.append(
                _wrap(
                    "This is one of the rows whose absence is not an ordinary "
                    "state. The report marks it so, on the row and again in its "
                    "closing line."
                )
            )
    return out


def _step_block(step: Step, sequence: Sequence, rows: dict[str, Integration]) -> str:
    lines = [f"### {sequence.number_of(step)}. {step.title}", ""]
    lines.append(ACTOR_LINE[step.actor])
    lines.append("")
    lines.append(_wrap(step.does))
    lines.append("")
    lines.append(_wrap(f"**Proves it is done.** {step.check}"))
    if step.command:
        lines.extend(["", "```bash", step.command, "```"])
    lines.append("")
    lines.extend(_without_it(step, rows))
    if step.sets:
        lines.append("")
        named = ", ".join(f"`{name}`" for name in step.sets)
        lines.append(_wrap(f"**Credentials.** {named}"))
    if step.walkthrough:
        lines.append("")
        lines.append("**In a browser, in full:**")
        lines.append("")
        for index, item in enumerate(step.walkthrough, 1):
            marker = f"{index}. "
            lines.append(_wrap(item, indent=" " * len(marker), first=marker))
    return "\n".join(lines)


def render_page(sequence: Sequence, rows: dict[str, Integration]) -> str:
    """The page the declaration derives."""
    blocks: list[str] = [_HEADER, _INTRODUCTION]
    blocks.append("## The two repositories, and why they are two")
    blocks.append("\n".join(_repository_table(sequence)))
    blocks.append(
        _wrap(
            "The split is forced, not preferred, and "
            "`docs/decisions/d-15-publication-topology.md` is the argument in "
            "full. Both exist before anything else works."
        )
    )
    blocks.append("## How to read a step")
    blocks.append(_HOW_TO_READ)
    for index, stage in enumerate(sequence.stages, 1):
        blocks.append(f"## Stage {index} — {stage.title}")
        blocks.append(_wrap(stage.purpose))
        for step in sequence.steps_in(stage.id):
            blocks.append(_step_block(step, sequence, rows))
    blocks.append("## Every credential, in one table")
    blocks.append(
        _wrap(
            "No value is written down here or anywhere else in this repository. "
            "What follows is which credential exists, which repository or worker "
            "it belongs to, and the menu path a person reaches it by. Every "
            "repository credential is set on the private repository: the public "
            "one holds none, because nothing runs in it."
        )
    )
    blocks.append("\n".join(_credential_table(sequence)))
    blocks.append("## What is deliberately not on this page")
    for entry in sequence.not_at_setup:
        blocks.append(_wrap(f"**`{entry.secret}`.** {entry.reason}"))
    blocks.append("## After this page")
    blocks.append(_CLOSING)
    return "\n".join(block.rstrip("\n") + "\n" for block in blocks)


def standing_up_doc(root: Path) -> str:
    """The page this repository's declaration derives, today."""
    return render_page(load_sequence(root), integration_rows(root))


def main(argv: Seq[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the standing-up guide from STANDING-UP.yml and "
            "config/integrations.yml."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the committed page is not what they derive",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    rendered = standing_up_doc(root)
    path = root / DOC_PATH
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if args.check:
        if current != rendered:
            print(
                f"{DOC_PATH.as_posix()} is not what "
                f"{DECLARATION_PATH.as_posix()} derives.",
                file=sys.stderr,
            )
            print(
                f"It is generated, not authored: run `{COMMAND}` from `tools/`"
                " and commit the file it writes.",
                file=sys.stderr,
            )
            return 1
        print(f"{DOC_PATH.as_posix()} matches the declaration")
        return 0

    if current == rendered:
        print(f"{DOC_PATH.as_posix()} unchanged")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8", newline="")
    print(f"wrote {DOC_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
