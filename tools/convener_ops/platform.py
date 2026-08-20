"""The D-05 platform interface, and the manual implementation of it.

Phase 4's guiding decision (D-06) splits an event in two: *"the platform
provides the room and the recording. We provide the registration and the
identity."* `Platform` is the seam that split creates -- four operations,
`get_room`, `get_attendance`, `get_recording` and `delete_recording`, that
any concrete platform must answer. `ManualPlatform` below is one answer.
Task 3's `platform_fcc.py` is the other, calling the chosen provider's
undocumented (but empirically verified) HTTP endpoint instead of reading a
file. Both satisfy `Platform` structurally -- neither inherits from the
other, and nothing here ever will.

`ManualPlatform` is the default, not the fallback
---------------------------------------------------
It needs no account, no secret, no network call. That is what makes
acceptance criterion 8 of the spec true -- "the whole chain is executable
end to end with the manual implementation, without any external account" --
and what D-13 means when it calls a missing integration a normal state:
`config/integrations.yml`'s `meeting_provider` row already says so. Without
`CONVENER_MEETING_API_TOKEN`, this is the implementation in use, which is the
ordinary case, not a degraded one. Task 3 will not replace this module; it
will sit beside it, and the choice between the two is made by whoever wires
them together, not by anything in here.

Where "the event's configuration" lives (revised on review, R-5 / R-6)
--------------------------------------------------------------------------
The first version of this module opened its own file,
`data/events/<id>/config.yml`, reasoning that `data/speakers.yml`'s
`zoom_link` and `youtube_url` belonged to a phase-1 schema this task had no
licence to change. Review found the reasoning sound but pointed at the
wrong file: every `convener_ops` business-logic module except `cli.py` is pure,
receiving already-loaded data rather than reading a file itself --
`governance.py`, `notify.py`, `sweep.py` and `public_data.py` all follow
that rule, and it is the right one. The defect was that `ManualPlatform`
was reading a file at all, not which file it was reading. So:

* **`ManualPlatform` takes the loaded speaker records as a constructor
  parameter (`speakers`) and never touches `data/speakers.yml` itself.**
  `get_room` and `get_recording` find the matching record and read its
  existing `zoom_link` and `youtube_url` -- the very fields the first
  version rejected, now reached the way every other pure module in this
  package reaches `data/speakers.yml`'s content: already loaded, by
  whoever wires this class up (`cli.py`, in the end).
* **`event_id` is `edition_code`, lower-cased (R-5).** Nothing else in the
  codebase defines that mapping, and it cannot be implemented without one:
  `edition_code` is the only candidate consistent with existing convention
  (`app/src/state/consent.ts` already treats it as the event's public id,
  `tools/convener_ops/validate.py::EDITION_RE` fixes its shape as `MRG-` followed
  by digits), and it is what task 1's own tests already use (`mrg-042` for
  `MRG-042`). `find_speaker` below is the one place this rule is written
  down.
* **`instructions` lives in `data/config.yml`, not on the speaker record
  (R-6).** The cost of the alternative is real -- a `Speaker` field must
  also join the exhaustive field set, be classified in `consent.ts`,
  mirrored in `public_data.py`, and added to the cross-language fixture
  that binds the two -- but the deciding argument is D-06 itself: the
  chosen platform's account *is* the permanent room, so join instructions
  for a room that never changes are a property of the series, not of one
  event. Putting them on the speaker record would invite writing different
  instructions per event for a room that is the same room every time. So
  `ManualPlatform` takes a second, optional constructor parameter
  (`config`, the loaded `data/config.yml`) and reads `instructions` from
  it; `None` (no config supplied) reads as `''`, the same "nothing more to
  say" answer an explicit empty string would give.

For attendance, the file stays exactly where the brief named it -- nothing
about that path was in question:

    data/events/<id>/attendance-import.csv

The CSV is never committed
-----------------------------
`attendance-import.csv` is a raw export off the chosen platform:
`display_name` and `email` are personal data. "No personal data in the
repository, ever" is a hard constraint of this phase, so this path is
`.gitignore`d (`data/events/*/attendance-import.csv`) even though it sits
under `data/` like everything else here -- it is dropped locally (or into
an ephemeral job workspace) for this reader to consume once, never checked
in.

One consequence worth stating rather than leaving for an auditor to
rediscover: acceptance criterion 8 ("the whole chain is executable end to
end with the manual implementation, without any external account") cannot
be *demonstrated in CI* for this path, and that is correct, not a gap. A
CI job has no attendance export to read, on purpose -- the only way one
could is by checking a real export into the repository, which the
constraint above forbids outright. "Manual" means a human drops the file
and runs the job; it does not mean "reproducible from a fixture committed
alongside the code." AC8 is exercised by running the chain by hand against
a real drop, not by a test in this suite, and no test here claims
otherwise.

The CSV columns, and what "reads it" means
----------------------------------------------
Five columns, by name, in any order: `display_name`, `email`, `joined_at`,
`left_at`, `duration_seconds`. Two columns with the same name are a
whole-file failure too, named like a missing one -- `csv.DictReader` keeps
only the last one's value, silently, and nothing downstream could tell a
duplicate from a single well-formed column without this check.
`parse_attendance_csv` is the pure reader -- text in, rows and issues out,
no filesystem, fully unit-testable -- and `ManualPlatform.get_attendance`
is the thin wrapper that finds the file, calls it, and prints one line per
dropped row to the job log (the same "printed where any volunteer can read
it" idiom `cli.py` already uses for `board_notifications`'s fallback)
before returning the rows that parsed. A column missing from the header is
a whole-file failure, named in the exception (step 3 of the brief); a
single malformed row is reported and excluded, never silently dropped, and
never aborts the rows around it.

`get_attendance` reads the file as `utf-8-sig`, not `utf-8`: a plain
`utf-8` read leaves a leading byte-order mark on the first header cell,
turning `display_name` into a string starting with a BOM and making this
module report *that* column missing -- on a file that has it. Windows and
Excel-adjacent export tools write a BOM often enough that this is not a
theoretical case, and getting the diagnosis wrong is exactly what the task
exists to prevent: `utf-8-sig` strips a BOM when present and reads
identically to `utf-8` when it is not, so this is a strict widening, not a
behaviour change for the files that already worked.

The email boundary (do not "fix" this)
------------------------------------------
`AttendanceRow.email` is `str | None`, not `str`. A participant who joins by
telephone has no address to give -- the platform never collects one -- and
no matching cascade this project can build, present or future, will ever
reach them by address or by normalised name, for want of both. The spec's
2026-08-20 revalidation (SS5) writes this down as a **boundary**, not a
matching weakness: "a certificate is only ever available to someone who
joins by the link." `email=None` forces every caller to confront that case
in the type checker rather than in production; mapping a phone joiner's
blank cell to `""` instead would let a caller compare two telephone rows'
`""` addresses and read them as the same person, which they may not be.

Two more facts this module deliberately does *not* act on, established
empirically and reserved for later tasks:

* A disconnect-and-rejoin produces **several rows** for the same person.
  This reader returns every row as read; summing durations per person is
  `attendance.py`'s job (task 8/9), done once, in the one place that also
  has to decide what "per person" means (the address).
* Name capitalisation varies between two connections by the same person.
  `display_name` is returned verbatim, never normalised here -- normalising
  it in the reader would hide from the matching code the very fact it is
  written to rely on: the address is the join key, never the name.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from .commit_format import _TOKEN
from .paths import repo_root

#: The five columns `attendance-import.csv` must carry, by name. Extra
#: columns an export tool adds are harmless and ignored; only a column
#: missing from this set fails the whole file.
_REQUIRED_ATTENDANCE_COLUMNS: Final = frozenset(
    {"display_name", "email", "joined_at", "left_at", "duration_seconds"}
)

#: An event id, validated the same way `eventkeys.py` validates one --
#: `commit_format._TOKEN`, imported rather than copied so the two cannot
#: drift into two different definitions of "a token" by hand-edit. The
#: regex itself is rebuilt here, not imported from `eventkeys`: this task
#: does not depend on event keys at all (nothing here handles registration
#: data), and importing a private name from a sibling module for a two-line
#: regex would create a coupling the brief explicitly says does not exist.
#: The id becomes a path component (`events_dir / event_id / ...`); the
#: leading-character rule (`[A-Za-z0-9]`, never `.`) already refuses `..`
#: and any id starting with a dot, and the charset admits no `/`, so a
#: validated id cannot walk out of `events_dir`.
_EVENT_ID_RE: Final = re.compile(rf"^{_TOKEN}$")


def _validate_event_id(event_id: str) -> None:
    if not _EVENT_ID_RE.fullmatch(event_id):
        raise ValueError(f"not a valid event id: {event_id!r}")


@dataclass(frozen=True)
class Room:
    """Where and how to join, per D-05: `get_room(event) -> { join_url,
    instructions }`."""

    join_url: str
    instructions: str


@dataclass(frozen=True)
class AttendanceRow:
    """One connection to the room. Several of these can belong to the same
    person (a reconnection) -- see the module docstring for why this type
    does not deduplicate or sum them."""

    display_name: str
    #: `None` when the person joined by telephone. See the module
    #: docstring's "email boundary" section -- this is the field the whole
    #: task exists to get right.
    email: str | None
    joined_at: str
    left_at: str
    duration_seconds: int


@dataclass(frozen=True)
class Recording:
    """Per D-05: `get_recording(event) -> { url, size, available }`."""

    url: str
    #: Bytes, when known. The manual implementation never hosts the file
    #: itself -- it is uploaded by hand wherever the host chooses -- so it
    #: has no way to measure this and always reports 0. Task 3's
    #: implementation, which does hold the file under the chosen platform's
    #: own quota, is expected to report the real size.
    size: int
    available: bool


@runtime_checkable
class Platform(Protocol):
    """The D-05 interface. `ManualPlatform` below and task 3's
    `PlatformFCC` both satisfy this structurally -- neither inherits from
    the other or from this class; `Protocol` exists so a caller can accept
    "a platform" without knowing or caring which one it was handed."""

    def get_room(self, event_id: str) -> Room: ...

    def get_attendance(self, event_id: str) -> list[AttendanceRow]: ...

    def get_recording(self, event_id: str) -> Recording: ...

    def delete_recording(self, event_id: str) -> None: ...


class AttendanceImportError(Exception):
    """The attendance export could not be read at all: the file is absent,
    or its header is missing one of the required columns. Always names the
    event or the column, never just "could not import" -- a volunteer
    reading this needs to know what to fix, not that something failed."""


class EventNotFoundError(Exception):
    """No speaker record's `edition_code` matches an event id (R-5). Raised
    by `find_speaker`, and by `get_room` / `get_recording` through it --
    both need the matching record before they can answer, and "no such
    event" is the whole failure; there is nothing else here to name."""


@dataclass(frozen=True)
class AttendanceIssue:
    """One malformed row: reported, and excluded from the rows returned --
    never silently dropped, and never allowed to abort the rows around it.
    `line_number` counts from 1 at the header, so a data row's first line is
    2 -- what a volunteer opening the file in a spreadsheet would call it."""

    line_number: int
    reason: str


class _RowError(Exception):
    """Internal control flow only, for `_parse_row`. Caught inside
    `parse_attendance_csv` and turned into an `AttendanceIssue`; never
    raised past this module."""


def _required(raw: Mapping[str, str | None], key: str) -> str:
    value = (raw.get(key) or "").strip()
    if not value:
        raise _RowError(f"{key} is empty")
    return value


def _parse_row(raw: Mapping[str, str | None]) -> AttendanceRow:
    display_name = _required(raw, "display_name")
    joined_at = _required(raw, "joined_at")
    left_at = _required(raw, "left_at")
    duration_raw = _required(raw, "duration_seconds")

    try:
        duration_seconds = int(duration_raw)
    except ValueError:
        raise _RowError(
            f"duration_seconds is not a whole number: {duration_raw!r}"
        ) from None
    if duration_seconds < 0:
        raise _RowError(f"duration_seconds is negative: {duration_raw!r}")

    #: A blank cell is a telephone joiner (see the module docstring); the
    #: `or None` is what keeps that case from ever becoming `""`.
    email = (raw.get("email") or "").strip() or None

    return AttendanceRow(
        display_name=display_name,
        email=email,
        joined_at=joined_at,
        left_at=left_at,
        duration_seconds=duration_seconds,
    )


def parse_attendance_csv(
    text: str,
) -> tuple[list[AttendanceRow], list[AttendanceIssue]]:
    """The pure half of attendance reading: CSV text in, valid rows and
    reported issues out. No filesystem, so every case the brief's step 3
    asks for is testable directly, without a temp file.

    Raises `AttendanceImportError` if a required column is missing from the
    header, or if the header repeats a column name -- both are whole-file
    failures, not per-row ones. A malformed row never raises past this
    function; it becomes an `AttendanceIssue` instead, and reading
    continues.
    """
    reader: csv.DictReader[str] = csv.DictReader(io.StringIO(text))
    fieldnames = list(reader.fieldnames or ())

    #: `set(fieldnames)` below would silently collapse a repeated column
    #: name before the missing-column check ever saw it, and
    #: `csv.DictReader` itself keeps only the last one's value -- so a
    #: duplicate is checked first, on the list, while the repetition is
    #: still visible.
    duplicate_columns = sorted(
        {name for name in fieldnames if fieldnames.count(name) > 1}
    )
    if duplicate_columns:
        raise AttendanceImportError(
            "attendance-import.csv has duplicate column(s): "
            + ", ".join(duplicate_columns)
        )

    missing_columns = _REQUIRED_ATTENDANCE_COLUMNS - set(fieldnames)
    if missing_columns:
        raise AttendanceImportError(
            "attendance-import.csv is missing required column(s): "
            + ", ".join(sorted(missing_columns))
        )

    rows: list[AttendanceRow] = []
    issues: list[AttendanceIssue] = []
    for line_number, raw in enumerate(reader, start=2):
        try:
            rows.append(_parse_row(raw))
        except _RowError as exc:
            issues.append(AttendanceIssue(line_number=line_number, reason=str(exc)))
    return rows, issues


def _matches_event(record: Mapping[str, Any], event_id: str) -> bool:
    edition_code = record.get("edition_code")
    return isinstance(edition_code, str) and edition_code.lower() == event_id


def find_speaker(
    speakers: Sequence[Mapping[str, Any]], event_id: str
) -> Mapping[str, Any]:
    """The R-5 rule, and the one place it is written down: `event_id` is
    `edition_code`, lower-cased -- `mrg-1` matches the record whose
    `edition_code` is `MRG-1`. `event_id` is expected to already be
    lower-case (that is what "is edition_code lower-cased" means); this
    does not also lower-case `event_id` itself before comparing, so a
    caller holding `MRG-1` has to lower it first, the same as everywhere
    else in this module.

    Raises `EventNotFoundError`, naming `event_id`, when no record's
    `edition_code` matches -- never returns a placeholder, and never
    guesses at a near match.
    """
    _validate_event_id(event_id)
    for record in speakers:
        if _matches_event(record, event_id):
            return record
    raise EventNotFoundError(f"no event found for id {event_id!r}")


@dataclass(frozen=True)
class ManualPlatform:
    """The manual implementation of `Platform`. See the module docstring
    for why it is the default, where the room and recording come from
    (constructor parameters, not a file this class reads itself), and why
    `attendance-import.csv` -- the one file it does read -- is treated
    differently by `.gitignore` than everything else under `data/`."""

    events_dir: Path = field(default_factory=lambda: repo_root() / "data" / "events")
    #: The loaded contents of `data/speakers.yml` -- already validated and
    #: read by whoever constructs this class, never by this class itself
    #: (see the module docstring's "Where the event's configuration lives"
    #: section). `()` is a legal, if useless, default: any lookup then
    #: raises `EventNotFoundError` for every id, which is the honest
    #: answer to "no speaker data was supplied".
    speakers: Sequence[Mapping[str, Any]] = ()
    #: The loaded contents of `data/config.yml`, for `instructions` (R-6).
    #: `None` -- the default -- reads as `''`: no config supplied is not a
    #: data-integrity failure the way a missing speaker record is, it is
    #: the same "nothing more to say" an explicit empty string would be.
    config: Mapping[str, Any] | None = None

    def _event_dir(self, event_id: str) -> Path:
        _validate_event_id(event_id)
        return self.events_dir / event_id

    def _instructions(self) -> str:
        if self.config is None:
            return ""
        return str(self.config.get("instructions", "") or "")

    def get_room(self, event_id: str) -> Room:
        record = find_speaker(self.speakers, event_id)
        join_url = str(record.get("zoom_link", "") or "")
        return Room(join_url=join_url, instructions=self._instructions())

    def get_attendance(self, event_id: str) -> list[AttendanceRow]:
        path = self._event_dir(event_id) / "attendance-import.csv"
        if not path.exists():
            raise AttendanceImportError(
                f"no attendance export for event {event_id!r}: expected {path}"
            )
        #: Not "utf-8" -- see the module docstring's note on the BOM a
        #: Windows or Excel-adjacent export tool commonly writes.
        rows, issues = parse_attendance_csv(path.read_text(encoding="utf-8-sig"))
        for issue in issues:
            print(f"attendance-import.csv line {issue.line_number}: {issue.reason}")
        return rows

    def get_recording(self, event_id: str) -> Recording:
        record = find_speaker(self.speakers, event_id)
        url = str(record.get("youtube_url", "") or "")
        return Recording(url=url, size=0, available=bool(url))

    def delete_recording(self, event_id: str) -> None:
        """A documented no-op. `delete_recording` exists in D-05 because of
        the *chosen platform's* storage quota (spec SS2): a 90-minute
        recording there costs roughly its free tier's entire allowance. The
        manual implementation holds no recording storage of its own -- the
        file lives wherever the host uploaded it by hand -- so there is
        nothing here to reclaim. Still validates `event_id`: a caller that
        gets this far should never be holding an id that could not have
        named a real event directory."""
        _validate_event_id(event_id)
        return None
