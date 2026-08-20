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

Where "the event's configuration" lives
------------------------------------------
Nothing in this codebase already models "one event's manual settings" --
`data/speakers.yml` carries `zoom_link` and `youtube_url` for the *old*,
one-Zoom-link-per-talk world, keyed by a speaker record's lifecycle, not by
the event this phase's key pairs, encrypted registrations and attendance
already key everything else on (`data/events/<id>/`, see
`tools/convener_ops/eventkeys.py`). Reusing `zoom_link` would tie a phase-4
adapter to a phase-1 schema this task has no licence to change, for a
"permanent room" whose link will in practice be the same string on every
row of that file, which is not what the field was built for. So this module
opens its own file, shaped the way `data/config.yml` already is -- a flat
mapping, every key required, an empty string a legal answer, a missing key
refused by name:

    data/events/<id>/config.yml
        join_url: ''         # the room link, typed in by hand
        instructions: ''     # anything beyond the link; '' if nothing
        recording_url: ''    # typed in by hand once the host uploads it

and, for attendance, the export the brief names directly:

    data/events/<id>/attendance-import.csv

The CSV is never committed
-----------------------------
Unlike `config.yml` above, `attendance-import.csv` is a raw export off the
chosen platform: `display_name` and `email` are personal data. "No personal
data in the repository, ever" is a hard constraint of this phase, so this
path is `.gitignore`d (`data/events/*/attendance-import.csv`) even though it
sits under `data/` like everything else here -- it is dropped locally (or
into an ephemeral job workspace) for this reader to consume once, never
checked in. `config.yml` alongside it holds no personal data and is
committed normally.

The CSV columns, and what "reads it" means
----------------------------------------------
Five columns, by name, in any order: `display_name`, `email`, `joined_at`,
`left_at`, `duration_seconds`. `parse_attendance_csv` is the pure reader --
text in, rows and issues out, no filesystem, fully unit-testable --  and
`ManualPlatform.get_attendance` is the thin wrapper that finds the file,
calls it, and prints one line per dropped row to the job log (the same
"printed where any volunteer can read it" idiom `cli.py` already uses for
`board_notifications`'s fallback) before returning the rows that parsed. A
column missing from the header is a whole-file failure, named in the
exception (step 3 of the brief); a single malformed row is reported and
excluded, never silently dropped, and never aborts the rows around it.

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
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from .commit_format import _TOKEN
from .paths import repo_root
from .yaml_safe import safe_load

#: The five columns `attendance-import.csv` must carry, by name. Extra
#: columns an export tool adds are harmless and ignored; only a column
#: missing from this set fails the whole file.
_REQUIRED_ATTENDANCE_COLUMNS: Final = frozenset(
    {"display_name", "email", "joined_at", "left_at", "duration_seconds"}
)

#: The keys `data/events/<id>/config.yml` must carry. Every one is required
#: -- a missing key is an incomplete record, refused by name, the same rule
#: `data/config.yml` itself is validated by -- but an *empty* value is a
#: legal answer for any of the three: no extra instructions, no recording
#: yet.
_REQUIRED_ROOM_KEYS: Final[tuple[str, ...]] = (
    "join_url",
    "instructions",
    "recording_url",
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


class RoomConfigError(Exception):
    """The event's `config.yml` could not be read at all: the file is
    absent, is not a mapping, or is missing one of the required keys.
    Always names the event, the path, or the key -- see
    `AttendanceImportError`, the same rule applies here."""


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
    header -- that is a whole-file failure, not a per-row one. A malformed
    row never raises past this function; it becomes an `AttendanceIssue`
    instead, and reading continues.
    """
    reader: csv.DictReader[str] = csv.DictReader(io.StringIO(text))
    header = set(reader.fieldnames or ())
    missing_columns = _REQUIRED_ATTENDANCE_COLUMNS - header
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


@dataclass(frozen=True)
class ManualPlatform:
    """The manual implementation of `Platform`. See the module docstring
    for why it is the default, where each file lives, and why the two
    files it reads are treated so differently by `.gitignore`."""

    events_dir: Path = field(default_factory=lambda: repo_root() / "data" / "events")

    def _event_dir(self, event_id: str) -> Path:
        _validate_event_id(event_id)
        return self.events_dir / event_id

    def _load_room_config(self, event_id: str) -> dict[str, str]:
        path = self._event_dir(event_id) / "config.yml"
        if not path.exists():
            raise RoomConfigError(
                f"no configuration for event {event_id!r}: expected {path}"
            )
        raw = safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RoomConfigError(f"{path} does not contain a mapping")
        missing_keys = [key for key in _REQUIRED_ROOM_KEYS if key not in raw]
        if missing_keys:
            raise RoomConfigError(
                f"{path} is missing required key(s): {', '.join(missing_keys)}"
            )
        config: dict[str, str] = {}
        for key in _REQUIRED_ROOM_KEYS:
            value = raw[key]
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise RoomConfigError(
                    f"{path}: {key!r} must be a string, got {value!r}"
                )
            config[key] = value
        return config

    def get_room(self, event_id: str) -> Room:
        config = self._load_room_config(event_id)
        return Room(join_url=config["join_url"], instructions=config["instructions"])

    def get_attendance(self, event_id: str) -> list[AttendanceRow]:
        path = self._event_dir(event_id) / "attendance-import.csv"
        if not path.exists():
            raise AttendanceImportError(
                f"no attendance export for event {event_id!r}: expected {path}"
            )
        rows, issues = parse_attendance_csv(path.read_text(encoding="utf-8"))
        for issue in issues:
            print(f"attendance-import.csv line {issue.line_number}: {issue.reason}")
        return rows

    def get_recording(self, event_id: str) -> Recording:
        config = self._load_room_config(event_id)
        url = config["recording_url"]
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
