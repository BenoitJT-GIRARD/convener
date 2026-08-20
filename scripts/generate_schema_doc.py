"""The schema appendix of the handbook, derived from the model it describes.

`docs/reference/schema.md` is the page a volunteer opens to find out what a
record holds. It was written by hand, next to a model that kept moving, and it
drifted every time the model did: during phase 2 it defined `proposed_by` as
the board member handling the lead, then went on listing fields the model had
dropped; phase 3 corrected it twice more and it still named a thirty-day view
count under a window that had become configuration. Every one of those was
found by a person reading two files side by side, which is not a control.

So the page is derived. `app/src/data/types.ts` is the model both readers
share -- the browser validates against it and `tools/convener_ops/validate.py`
enforces the same schema without becoming a second source -- and this script
turns its interfaces, its enumerations and its documentation comments into the
appendix. A field added to the model is a row in the handbook on the same
commit, or `--check` fails the build.

What is derived and what is written
-----------------------------------
Every **field name, type and enumerated value** comes from the types, and so
does every **note**: the first paragraph of a field's documentation comment is
the note the table shows. The rest of that comment -- the paragraphs arguing
why the field is shaped the way it is -- stays in the code, where the person
who needs it is already reading.

What this file holds instead is the **narrative**: the sentences around the
tables that say what the two YAML files are for and why the vote threshold is
not stored. Those are prose about the repository rather than facts about the
model, nothing derives them, and pretending otherwise would only mean an
appendix that no longer explained anything. Whoever writes a new one writes it
here, not in the generated page, and the page says so at the top.

Pure, so `--check` means something
----------------------------------
The rendering reads `types.ts` and nothing else: no clock, no `data/*.yml`, no
environment. Two runs over the same model produce byte-identical files, so a
difference can only be an edit made outside the types -- which is exactly what
`--check` refuses, without repairing it. A check that silently rewrote the file
it was checking would report success on a repository that still held the wrong
page.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python ../scripts/generate_schema_doc.py            # write the page
    uv run python ../scripts/generate_schema_doc.py --check    # assert only

There is no mode that prints the page: the appendix is written in the
handbook's British English and the rest of it, and nothing this repository's
Python writes to a terminal is allowed to be non-ASCII.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from convener_ops.paths import repo_root

#: The model, relative to the repository root. The one source this script has.
TYPES_PATH: Final = Path("app") / "src" / "data" / "types.ts"

#: The page it writes, relative to the repository root.
DOC_PATH: Final = Path("docs") / "reference" / "schema.md"

#: How the script is invoked, quoted in the page and in the failure message.
#: One string, so the page and the message cannot come to name two commands.
COMMAND: Final = "uv run python ../scripts/generate_schema_doc.py"


# --------------------------------------------------------------------------
# The model, as read out of `types.ts`
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    """One declared field: its name, its type as written, and its note."""

    name: str
    type_expr: str
    doc: str


@dataclass(frozen=True)
class Interface:
    """One `interface` block, in declaration order."""

    name: str
    fields: tuple[Field, ...]


@dataclass(frozen=True)
class Enumeration:
    """A closed set of string values, however the model spells it.

    `values` keeps declaration order, because the order the model lists them
    in is the order a reader of the handbook meets them.
    """

    name: str
    values: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Model:
    """Everything this script knows, all of it read from one file."""

    interfaces: dict[str, Interface]
    enums: dict[str, Enumeration]


_DOC_LINE = re.compile(r"^\s*\*+ ?")
_FIELD = re.compile(r"^\s*(\w+)(\??):\s*(.+?);\s*$")
_OPEN_OBJECT = re.compile(r"^\s*(\w+)(\??):\s*\{\s*$")
_INTERFACE = re.compile(r"^export interface (\w+)(?: extends (\w+))? \{\s*$")
_CONST_ARRAY = re.compile(r"^export const (\w+) = \[")
_TYPE_ALIAS = re.compile(r"^export type (\w+) =")
_ALIAS_OF_ARRAY = re.compile(r"^export type (\w+) = \(typeof (\w+)\)\[number\];")
_LITERAL = re.compile(r"'([^']*)'")


def _paragraph(doc_lines: Sequence[str]) -> str:
    """The first paragraph of a documentation comment, as a single line.

    First paragraph and not the whole comment: the table wants the sentence
    that says what the field is, and the argument for why it is shaped that
    way belongs next to the code that has to keep obeying it. A comment with
    no blank line is one paragraph and is taken whole.
    """
    stripped = [_DOC_LINE.sub("", line).rstrip() for line in doc_lines]
    paragraph: list[str] = []
    for line in stripped:
        if not line.strip():
            if paragraph:
                break
            continue
        paragraph.append(line.strip())
    return re.sub(r"\s+", " ", " ".join(paragraph)).strip()


def _trailing_note(line: str) -> str:
    """The `//` note written after a union member, or `''` when there is none."""
    _, marker, note = line.partition("//")
    return note.strip() if marker else ""


def parse_types(text: str) -> Model:
    """Read the model out of the TypeScript source.

    A reader of the declarations, not of TypeScript: it understands the four
    forms this file uses -- an interface, an inline object field, a `const`
    tuple of string literals, and a union of string literals -- and nothing
    else. That is a deliberate ceiling, and it is worth being exact about what
    happens at it, because the obvious answer is wrong: a field declared in a
    fifth form is not seen, and `--check` cannot notice. Both sides of that
    comparison come from this parser, so a short page matches itself. What
    catches it is `tools/tests/test_schema_doc.py`, in two steps that do not
    go through here at all: `SPEAKER_FIELD_SET` is read out of `types.ts` as
    text and held against `tools/tests/conftest.py::speaker()`, and every key
    of that double is then required to have a row on the page. A field this
    parser cannot read is still in `SPEAKER_FIELD_SET` -- the compiler holds
    that record exhaustive over `keyof Speaker` -- so it still reaches the
    double, and the missing row fails with the field's name.
    """
    interfaces: dict[str, Interface] = {}
    enums: dict[str, Enumeration] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("/**"):
            index, _doc = _read_doc(lines, index)
            continue
        alias = _ALIAS_OF_ARRAY.match(line)
        if alias:
            source = enums.get(alias.group(2))
            if source is not None:
                enums[alias.group(1)] = Enumeration(
                    alias.group(1), source.values, source.notes
                )
            index += 1
            continue
        interface = _INTERFACE.match(line)
        if interface:
            index, fields = _read_fields(lines, index + 1, interface.group(1), enums)
            inherited = interfaces.get(interface.group(2) or "")
            base = inherited.fields if inherited else ()
            interfaces[interface.group(1)] = Interface(
                interface.group(1), (*base, *fields)
            )
            continue
        const = _CONST_ARRAY.match(line)
        if const:
            index, enum = _read_enum(lines, index, const.group(1))
            enums[enum.name] = enum
            continue
        type_alias = _TYPE_ALIAS.match(line)
        if type_alias:
            index, enum = _read_enum(lines, index, type_alias.group(1))
            if enum.values:
                enums[enum.name] = enum
            continue
        index += 1
    return Model(interfaces, enums)


def _read_enum(lines: Sequence[str], start: int, name: str) -> tuple[int, Enumeration]:
    """Every string literal of a declaration, with the note after each one."""
    values: list[str] = []
    notes: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        code, _, _rest = line.partition("//")
        found = _LITERAL.findall(code)
        note = _trailing_note(line)
        for position, value in enumerate(found):
            values.append(value)
            notes.append(note if position == len(found) - 1 else "")
        index += 1
        if ";" in code:
            break
    return index, Enumeration(name, tuple(values), tuple(notes))


def _read_fields(
    lines: Sequence[str], start: int, owner: str, enums: dict[str, Enumeration]
) -> tuple[int, tuple[Field, ...]]:
    """The fields of one interface body, in declaration order.

    An inline object field (`sla_days: { ... }`) is recorded twice: as a field
    whose type names a synthetic interface, and -- by the caller of this
    function through `enums`' sibling dictionary -- nowhere else. The synthetic
    name is `Owner.field`, which no TypeScript declaration can collide with.
    """
    fields: list[Field] = []
    doc: list[str] = []
    index = start
    while index < len(lines) and not lines[index].startswith("}"):
        line = lines[index]
        if line.strip().startswith("/**"):
            index, doc = _read_doc(lines, index)
            continue
        nested = _OPEN_OBJECT.match(line)
        if nested:
            index, inner = _read_nested(lines, index + 1)
            name = f"{owner}.{nested.group(1)}"
            _NESTED[name] = Interface(name, inner)
            fields.append(Field(nested.group(1), name, _paragraph(doc)))
            doc = []
            continue
        field = _FIELD.match(line)
        if field:
            fields.append(Field(field.group(1), field.group(3), _paragraph(doc)))
            doc = []
            index += 1
            continue
        if line.strip():
            doc = []
        index += 1
    return index + 1, tuple(fields)


def _read_nested(lines: Sequence[str], start: int) -> tuple[int, tuple[Field, ...]]:
    """The fields of an inline object, up to its closing brace."""
    fields: list[Field] = []
    doc: list[str] = []
    index = start
    while index < len(lines) and not lines[index].strip().startswith("}"):
        line = lines[index]
        if line.strip().startswith("/**"):
            index, doc = _read_doc(lines, index)
            continue
        field = _FIELD.match(line)
        if field:
            fields.append(Field(field.group(1), field.group(3), _paragraph(doc)))
            doc = []
        elif line.strip():
            doc = []
        index += 1
    return index + 1, tuple(fields)


def _read_doc(lines: Sequence[str], start: int) -> tuple[int, list[str]]:
    """One documentation comment, and the line after it."""
    doc: list[str] = []
    index = start
    while index < len(lines) and "*/" not in lines[index]:
        doc.append(lines[index].replace("/**", "", 1))
        index += 1
    if index < len(lines):
        doc.append(lines[index].replace("/**", "", 1).replace("*/", "", 1))
    return index + 1, doc


#: Inline object types met while reading, keyed by their synthetic name. Held
#: aside rather than threaded through the parser, and emptied at the start of
#: every parse, so two parses in one process cannot see each other's.
_NESTED: dict[str, Interface] = {}


# --------------------------------------------------------------------------
# The tables
# --------------------------------------------------------------------------

#: How a TypeScript type is spelled for a volunteer. The YAML file holds
#: integers and booleans, so those are the words the page uses.
_TYPE_WORDS: Final = {
    "string": "string",
    "number": "int",
    "boolean": "bool",
    "number | null": "int | null",
    "string | null": "string | null",
}


def _escape(text: str) -> str:
    """A cell that cannot break the table it sits in, or the page around it."""
    return text.replace("|", r"\|").replace("<", "&lt;").replace(">", "&gt;")


def _enum_of(type_expr: str, model: Model) -> Enumeration | None:
    """The closed set this type is, whether named or written out in place."""
    named = model.enums.get(type_expr)
    if named is not None:
        return named
    if "'" in type_expr:
        parts = [part.strip() for part in type_expr.split("|")]
        if all(part.startswith("'") and part.endswith("'") for part in parts):
            values = tuple(part.strip("'") for part in parts)
            return Enumeration(type_expr, values, ("",) * len(values))
    return None


def _values_sentence(enum: Enumeration) -> str:
    """The enumerated values, as the sentence appended to a note."""
    spelled = [f"`{value}`" if value else "empty" for value in enum.values]
    if len(spelled) == 1:
        return f"Always {spelled[0]}."
    return f"One of {', '.join(spelled[:-1])} or {spelled[-1]}."


def _type_word(type_expr: str, model: Model) -> str:
    """The type column, for one field."""
    if _enum_of(type_expr, model) is not None:
        return "enum"
    if type_expr in _TYPE_WORDS:
        return _TYPE_WORDS[type_expr]
    if type_expr.endswith("[]"):
        inner = type_expr[:-2]
        return f"list<{_TYPE_WORDS.get(inner, _entry_word(inner))}>"
    record = re.match(r"^Record<(\w+), (.+)>$", type_expr)
    if record:
        value = _TYPE_WORDS.get(record.group(2), _entry_word(record.group(2)))
        return f"map<{record.group(1)}, {value}>"
    return _entry_word(type_expr)


def _entry_word(type_expr: str) -> str:
    """What one element of a list or map is called on the page."""
    return "entry" if "." in type_expr else type_expr


@dataclass(frozen=True)
class Row:
    """One line of a field table, and where its own table hangs off it."""

    path: str
    type_expr: str
    note: str


def _rows(fields: Sequence[Field], model: Model, prefix: str = "") -> list[Row]:
    """A table's rows, expanding a field whose type is an object one level.

    One level and not all of them: `selection.ballots` is a list of records,
    and flattening a list into dotted rows would say that a speaker has one
    ballot. Lists get a table of their own instead, which is also how a reader
    meets them in the file.
    """
    rows: list[Row] = []
    for field in fields:
        path = f"{prefix}{field.name}"
        nested = _lookup(field.type_expr, model)
        if nested is not None:
            rows.extend(_rows(nested.fields, model, f"{path}."))
            continue
        rows.append(Row(path, field.type_expr, field.doc))
    return rows


def _lookup(type_expr: str, model: Model) -> Interface | None:
    """The interface this type names, when it names one and is not a list."""
    if type_expr.endswith("[]") or "<" in type_expr:
        return None
    return model.interfaces.get(type_expr) or _NESTED.get(type_expr)


def _table(rows: Sequence[Row], model: Model) -> str:
    """One field table."""
    lines = ["| Field | Type | Notes |", "|---|---|---|"]
    for row in rows:
        note = row.note
        enum = _enum_of(row.type_expr, model)
        if enum is not None:
            sentence = _values_sentence(enum)
            note = f"{note} {sentence}".strip() if note else sentence
        word = _escape(_type_word(row.type_expr, model))
        lines.append(f"| `{row.path}` | {word} | {_escape(note)} |")
    return "\n".join(lines)


def _element_name(type_expr: str) -> str | None:
    """The record type a list or map holds, when it holds one."""
    if type_expr.endswith("[]"):
        return type_expr[:-2]
    record = re.match(r"^Record<\w+, (\w+)>$", type_expr)
    return record.group(1) if record else None


def _element_tables(
    rows: Sequence[Row], model: Model, seen: set[str], within: str = ""
) -> list[str]:
    """A table for each record the rows point at, in reading order.

    Titled by the path a reader followed to get there, so the objections
    inside a nomination and the objections inside a publication are two
    headings rather than the same one twice.
    """
    out: list[str] = []
    for row in rows:
        name = _element_name(row.type_expr)
        if name is None:
            continue
        element = model.interfaces.get(name)
        if element is None or element.name in seen:
            continue
        seen.add(element.name)
        path = f"{within}{row.path}"
        inner = _rows(element.fields, model)
        out.append(f"### `{path}` entries\n\n{_table(inner, model)}")
        out.extend(_element_tables(inner, model, seen, f"{path}."))
    return out


def _status_list(model: Model) -> str:
    """The statuses, each with the note written beside it in the model."""
    enum = model.enums["SpeakerStatus"]
    lines = []
    for value, note in zip(enum.values, enum.notes, strict=True):
        lines.append(f"- `{value}` — {note}" if note else f"- `{value}`")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# The narrative around the tables
# --------------------------------------------------------------------------

_HEADER: Final = f"""# Data schema

*This page is generated from `app/src/data/types.ts` — the model the browser
and `convener-validate` both read. Do not edit it: run* `{COMMAND}` *from `tools/`
and commit what it writes, and CI refuses a page the types do not derive.
Every field, type, enumerated value and note below comes from the model; the
prose between the tables lives in `scripts/generate_schema_doc.py`.*

The repository stores all operational data in two YAML files under `data/`:

- `data/speakers.yml` — the unified speaker + event entity, one entry per
  invitation lifecycle
- `data/config.yml` — repository-wide configuration: the board, the thresholds,
  the season counters

Both files are validated in CI by `convener-validate` (see
`docs/reference/operations.md`) on every commit.
"""

_SPEAKERS: Final = """## `data/speakers.yml`

Top-level: a list of speaker entries. Each entry covers the full lifecycle from
lead to archived. Speaker and event are the same record — the speaker fields
describe the human; the edition fields (`edition_code`, `date`, runbook,
metrics) describe the workshop they deliver.

### Fields

Every field below is a key each entry carries. A key left out is an incomplete
record and both readers refuse the file; an empty value is an answer — "none
given" — and is well formed.
"""

_THRESHOLD: Final = """There is no stored vote threshold. It is computed from the
eligible Board — active members, minus those who declared an absence, minus those
recused on this lead — as two thirds rounded up, never fewer than three yes ballots.
Below three eligible members the vote is suspended rather than decided on a bar that has
stopped meaning anything. The rule lives in `app/src/state/governance.ts` and
`tools/convener_ops/governance.py`, pinned in both languages by
`tools/tests/fixtures/governance-cases.json`.
"""

_STATUSES: Final = """### Status values

The state machine governs transitions. Statuses:
"""

_RUNBOOK: Final = """### `runbook_progress` key convention

Keys follow `phase/item` (e.g. `approved/host_1`, `scheduled/T-14/zoom-link`).
The phase definitions and gate semantics live in `app/src/state/phases.ts`, and
the countdown in `docs/workflow/2-preparation.md` is checked against them.
Checking the last gate of a phase auto-advances the speaker to the next status.

`checklist` is keyed the same way, one entry per line somebody has been put
down for:

```yaml
checklist:
  scheduled/T-30/visuals:
    assignee: ada
```

A line with no entry is nobody's in particular and stays the hosts'. Naming an
owner has never been asked of anybody and is not asked for here either: the app
raises no warning and no reminder over an empty checklist.
"""

_CONFIG: Final = """## `data/config.yml`

One mapping, with the keys below.
"""

_CONFIG_PROSE: Final = """`board` replaces the former flat `board_members` list of
logins: a member now carries the date they joined, whether they are still active, and
any declared absence, because all three feed the vote threshold. There is no
`vote_threshold` key — see the ballot table above for why it is computed rather than
stored.

Each channel becomes one line of the promotion phase, keyed `promotion/<key>`,
so it carries an owner in `checklist` exactly like every other line. The `key`
is what records store, so renaming one re-keys what is already written and is a
migration rather than an edit; the `label` is only ever shown, and can be
reworded at any time. Removing a channel has the same property from the other
side: the owners already written under `promotion/<key>` stay in
`data/speakers.yml`, on a line no screen shows any more. They are harmless, and
nothing in the app offers to clear them: the record page lists the lines the
journey currently has, so a key it no longer has has no control beside it.
Clearing one means putting the channel back in `channels`, taking the name off
the line on the record page, and removing the channel again — or editing
`data/speakers.yml` on GitHub. Neither is urgent: an entry under a key no phase
holds is read by nothing. An empty list is a legal answer and means nothing is
promoted through this app; a `channels` that is missing, that is not a list,
that repeats a key, or that holds a channel with no label stops the file being
read at all, with a message naming the entry — a broken list must not read as a
deliberately empty one.

The `board` entries are used as a fallback when the GitHub team API call (for
role detection) fails or returns no membership information. The authoritative
source is the organisation's `editorial-board` team; the config is a safety
net.
"""

_HISTORY: Final = """## History

`data/speakers.yml` was originally split across two files, joined on an event
id. `scripts/` holds the one-shot scripts that merged them into today's unified
schema; they already ran and are kept only as a record, not as something to run
again.
"""


def render_schema_doc(model: Model) -> str:
    """The whole page, for exactly this model.

    Pure: the same model always renders the same bytes, which is what makes
    `--check` a statement about the repository rather than about the moment it
    happened to run.
    """
    speaker_rows = _rows(model.interfaces["Speaker"].fields, model)
    config_rows = _rows(model.interfaces["Config"].fields, model)
    seen: set[str] = set()
    blocks = [
        _HEADER,
        _SPEAKERS,
        _table(speaker_rows, model),
        *_element_tables(speaker_rows, model, seen),
        _THRESHOLD,
        _STATUSES,
        _status_list(model),
        _RUNBOOK,
        _CONFIG,
        _table(config_rows, model),
        *_element_tables(config_rows, model, seen),
        _CONFIG_PROSE,
        _HISTORY,
    ]
    return "\n".join(block.rstrip("\n") + "\n" for block in blocks)


def schema_doc(root: Path) -> str:
    """The page this repository's model derives."""
    _NESTED.clear()
    model = parse_types((root / TYPES_PATH).read_text(encoding="utf-8"))
    return render_schema_doc(model)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the schema appendix from app/src/data/types.ts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the committed page is not what the types derive",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    rendered = schema_doc(root)
    path = root / DOC_PATH
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if args.check:
        if current != rendered:
            # Naming the file, the reason and the command, and repairing
            # nothing: a check that wrote the file it was checking would pass
            # on a repository that still held the wrong page.
            print(
                f"{DOC_PATH.as_posix()} is not what {TYPES_PATH.as_posix()} derives.",
                file=sys.stderr,
            )
            print(
                f"It is generated, not authored: run `{COMMAND}` from `tools/`"
                " and commit the file it writes.",
                file=sys.stderr,
            )
            return 1
        print(f"{DOC_PATH.as_posix()} matches the types")
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
