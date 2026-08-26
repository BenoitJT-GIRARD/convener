"""The D-05 platform interface, and the manual implementation of it.

D-06 splits an event in two: *"the platform
provides the room and the recording. We provide the registration and the
identity."* `Platform` is the seam that split creates -- four operations,
`get_room`, `get_attendance`, `get_recording` and `delete_recording`, that
any concrete platform must answer. `ManualPlatform` below is one answer.
`platform_fcc.py` is the other, calling the chosen provider's
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
ordinary case, not a degraded one. The API implementation does not replace
this module; it sits beside it, and the choice between the two is made by
whoever wires them together, not by anything in here.

Where "the event's configuration" lives (revised on review)
------------------------------------------------------------
The first version of this module opened its own file,
`data/events/<id>/config.yml`, reasoning that `data/speakers.yml`'s
`zoom_link` and `youtube_url` belonged to a schema it had no
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
* **`event_id` is `edition_code`, lower-cased.** Nothing else in the
  codebase defines that mapping, and it cannot be implemented without one:
  `edition_code` is the only candidate consistent with existing convention
  (`app/src/state/consent.ts` already treats it as the event's public id,
  and `tools/convener_ops/validate.py` fixes its shape as the prefix this
  instance declares followed by digits), and it is what this project's own
  tests already use (`mrg-042` for `MRG-042`). `find_speaker` below is the one
  place this rule is written down.
* **`instructions` lives in `data/config.yml`, not on the speaker
  record.** The cost of the alternative is real -- a `Speaker` field must
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

The plaintext CSV is never committed -- the encrypted export is
-----------------------------------------------------------------
`attendance-import.csv` is a raw export off the chosen platform:
`display_name` and `email` are personal data. "No personal data in the
repository, ever" is a hard constraint of this phase, so this path is
`.gitignore`d (`data/events/*/attendance-import.csv`) even though it sits
under `data/` like everything else here -- it is dropped locally (or into
an ephemeral job workspace) for this reader to consume once, never checked
in.

That, on its own, used to make acceptance criterion 8 ("the whole chain is
executable end to end with the manual implementation, without any external
account") undemonstrable for this path: `EVENT_PRIVATE_KEY` must never
leave a CI job's environment (`eventkeys.py`'s own module docstring), yet
the plaintext CSV can never reach a CI checkout at all (the `.gitignore`
rule above forbids it) -- so the manual path could run neither in CI (no
file) nor locally (no key). That gap was recorded rather than glossed
over, and stood for a long time.

**The fix is the same trick this design already plays twice for
`registrations.enc` and `survey-responses.enc`: encrypt under the event's
own *public* key, which needs no secret at all, and commit the ciphertext.**
`get_attendance` below looks first for
`data/events/<event id>/attendance-import.csv.enc`, produced locally by a
host running `convener-encrypt-attendance-export` against the plaintext export
and the event's already-published `keys/events/<id>.pub`, then committed
like any other file under `data/`. A CI job holds the matching private
half already (`EVENT_PRIVATE_KEY`, the same secret every other command in
this event's chain reads to decrypt `registrations.enc`), so it can
decrypt this file the moment it is checked out -- no plaintext ever has to
reach a CI runner, and no key ever has to leave one. This is what makes
the whole chain genuinely true for the manual implementation:
`tools/tests/test_event_chain.py` drives the real
`convener-encrypt-attendance-export` and `convener-match-attendance` /
`convener-issue-certificates` commands against nothing but committed,
encrypted fixtures and asserts the chain completes -- not "by hand against
a real drop", a real, automated proof.

**One independent envelope per row, not one envelope for the whole
file.** The first version of this wrapped the
entire CSV text in a single `eventkeys.encrypt` call, unlike
`registrations.enc` and `survey-responses.enc`, which are already one
envelope per record -- a divergence that was not merely a style
inconsistency: `registration.py`'s own module docstring gives the real
reason ("The file shape, and why it is not one envelope for the whole
event") and it applies here word for word. A single blob means a bit
flipped anywhere costs the whole event's attendance rather than one row,
and -- the concrete failure this round closes -- there is no way to
remove one person's rows from it without decrypting and re-encrypting
everyone else's. `ATTENDANCE_FILE_VERSION`, `AttendanceExportFile`,
`load_attendance_export_file` and `dump_attendance_export_file` below
mirror `registration.py`'s `RegistrationFile` shape exactly: each entry is
its own `eventkeys.encrypt` call over one row's fields, decoded back to a
`dict` rather than kept as a nested JSON string, for the identical reason
`registration.py` gives. `encrypt_attendance_rows` and
`decrypt_attendance_rows` are the encode/decode halves;
`erase_attendance_rows` is what `convener-erase-registration` now calls
alongside `registration.erase`: the encrypted file is rewritten without
the record concerned and nothing else moves -- with a blob, everything
moved; with one envelope per
row, nothing else does, and the "compare the neighbours" test
shape applies unchanged. One person can hold several rows (a
reconnection); `erase_attendance_rows` removes all of theirs, the same
"erasure removes every row" rule a reconnection already gets from
`attendance.py`'s own summing.

Reading the encrypted export requires `private_pem` (below); its absence,
with the encrypted file present, is not D-13's ordinary state -- it is the
same "guards personal data, fails closed" exception `eventkeys.py` already
carves out for `registrations.enc`, so `get_attendance` refuses outright
rather than silently reporting "no attendance" for an event that plainly
has some, committed and waiting. A row whose own envelope fails to decrypt
(wrong key, corrupted ciphertext) is skipped rather than treated as fatal
-- the same tolerance `registration.py::to_registration`'s callers already
give a stray undecryptable entry -- so one damaged row costs one row, not
the whole file.

The plaintext path (`attendance-import.csv`, no `.enc`) is kept, unchanged,
as a second, lower-priority source: a host or a test working entirely
outside CI, with no reason to encrypt anything first, can still drop the
raw file directly. Production traffic through `ManualPlatform` is expected
to use the encrypted path exclusively, since the plaintext one still
cannot exist in a CI checkout for the reason above.

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
  `attendance.py`'s job, done once, in the one place that also
  has to decide what "per person" means (the address).
* Name capitalisation varies between two connections by the same person.
  `display_name` is returned verbatim, never normalised here -- normalising
  it in the reader would hide from the matching code the very fact it is
  written to rely on: the address is the join key, never the name.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from . import eventkeys
from .commit_format import _TOKEN
from .paths import repo_root
from .registration import normalize_email

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
#:
#: Length-capped the same way, and for the same reason, `eventkeys.py`'s
#: own copy of this pattern is -- see that
#: module's own comment on `_EVENT_ID_MAX_LENGTH` for the full reasoning
#: against `services/signup-relay/src/index.js::EVENT_ID_RE`'s own 64.
_EVENT_ID_MAX_LENGTH: Final = 64
_EVENT_ID_RE: Final = re.compile(rf"^(?=.{{1,{_EVENT_ID_MAX_LENGTH}}}$){_TOKEN}$")


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
    #: has no way to measure this and always reports 0. The API
    #: implementation, which does hold the file under the chosen platform's
    #: own quota, is expected to report the real size.
    size: int
    available: bool


@runtime_checkable
class Platform(Protocol):
    """The D-05 interface. `ManualPlatform` below and
    `PlatformFCC` both satisfy this structurally -- neither inherits from
    the other or from this class; `Protocol` exists so a caller can accept
    "a platform" without knowing or caring which one it was handed."""

    def get_room(self, event_id: str) -> Room: ...

    def get_attendance(self, event_id: str) -> list[AttendanceRow]: ...

    def get_recording(self, event_id: str) -> Recording: ...

    def delete_recording(self, event_id: str) -> None: ...


#: The committed, encrypted attendance export -- one JSON file holding one
#: independent `eventkeys` envelope per attendance row (see the module
#: docstring's "one independent envelope per
#: row" section for why this is not one envelope for the whole file), the
#: same per-record shape `registrations.enc` and `survey-responses.enc`
#: already use. Produced by `convener-encrypt-attendance-export` and checked in
#: like those two. Read in preference to the plaintext filename below.
ENCRYPTED_ATTENDANCE_FILENAME: Final = "attendance-import.csv.enc"

#: `attendance-import.csv.enc`'s own format version -- the file-level
#: analogue of `eventkeys.WIRE_VERSION` and `registration.FILE_VERSION`, in
#: case the file's shape (not the envelope inside it) ever has to change.
ATTENDANCE_FILE_VERSION: Final = 1

#: The never-committed raw export -- `.gitignore`d, see the module
#: docstring.
PLAINTEXT_ATTENDANCE_FILENAME: Final = "attendance-import.csv"


class AttendanceImportError(Exception):
    """The attendance export could not be read at all: the file is absent,
    it could not be decrypted, or its header is missing one of the required
    columns. Always names the event or the column, never just "could not
    import" -- a volunteer reading this needs to know what to fix, not that
    something failed."""


class EventNotFoundError(Exception):
    """No speaker record's `edition_code` matches an event id. Raised
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
        # Never echoes `duration_raw` itself: a column shift (an export
        # tool that reorders a name or an address into this column by
        # mistake) would otherwise put that cell's content straight into
        # `ManualPlatform.get_attendance`'s printed report -- the same
        # leak this whole module's "no plaintext to a log" rule exists to
        # rule out, reached from an angle a header check cannot catch.
        # The column name and what was wrong with it are always enough
        # for a volunteer to fix the file; the cell's own text never is.
        raise _RowError("duration_seconds is not a whole number") from None
    if duration_seconds < 0:
        raise _RowError("duration_seconds is negative")

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
        # This used to echo the duplicated
        # column *names* -- the file's own header text, written by
        # whatever export tool produced it -- into the exception message,
        # which every caller in `cli.py` prints straight to a job log.
        # The committed encrypted export is what makes this branch
        # reachable from CI at all (the
        # manual path had no file to read there before); once it is,
        # the same "never echo the file's own content" rule `_parse_row`
        # already holds itself to for a malformed cell applies here too.
        # The count and the 1-based header positions are always enough
        # for a volunteer to find and fix the file; the column text
        # never has to leave their own screen to do it.
        positions = sorted(
            i + 1 for i, name in enumerate(fieldnames) if fieldnames.count(name) > 1
        )
        raise AttendanceImportError(
            f"attendance-import.csv has {len(duplicate_columns)} duplicate "
            "column name(s), at header position(s): "
            + ", ".join(str(p) for p in positions)
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


#: The exact field set one attendance row's plaintext carries -- the
#: per-row analogue of `registration._FIELDS`. `to_registration`'s own
#: "closed shape" discipline applies here too: an entry whose decrypted
#: plaintext does not match this set exactly is treated as malformed,
#: never partially trusted.
_ATTENDANCE_ROW_FIELDS: Final = frozenset(
    {"display_name", "email", "joined_at", "left_at", "duration_seconds"}
)


def _row_to_plaintext(row: AttendanceRow) -> bytes:
    """The inverse of `_row_from_plaintext` -- the JSON
    `encrypt_attendance_rows` encrypts fresh for one row. Field order does
    not have to match anything on the other side; only the same five keys
    have to round trip, the same discipline
    `registration._to_plaintext`/`to_registration` already follow."""
    return json.dumps(
        {
            "display_name": row.display_name,
            "email": row.email,
            "joined_at": row.joined_at,
            "left_at": row.left_at,
            "duration_seconds": row.duration_seconds,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _row_from_plaintext(plaintext: bytes) -> AttendanceRow | None:
    """Decode one row's decrypted plaintext back into an `AttendanceRow`,
    or `None` for anything that is not exactly this module's own shape --
    not JSON, not an object, a field missing or extra, or a field of the
    wrong type. Mirrors `registration.to_registration`'s own "every cause
    becomes the same `None`" discipline: a row that fails to parse this
    way is a malformed or foreign entry, not a bug worth raising on, and
    `decrypt_attendance_rows` below skips it exactly the way it already
    skips a row whose envelope fails to decrypt at all."""
    try:
        data: Any = json.loads(plaintext)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # See `registration.to_registration`'s identical catch for why
        # `UnicodeDecodeError` joins `JSONDecodeError` here, and why
        # neither exception's own `.object` may ever be logged.
        return None
    if not isinstance(data, dict) or set(data) != _ATTENDANCE_ROW_FIELDS:
        return None
    display_name, email, joined_at, left_at, duration_seconds = (
        data["display_name"],
        data["email"],
        data["joined_at"],
        data["left_at"],
        data["duration_seconds"],
    )
    if not isinstance(display_name, str) or not display_name:
        return None
    if email is not None and not isinstance(email, str):
        return None
    if not isinstance(joined_at, str) or not isinstance(left_at, str):
        return None
    #: `bool` is a `int` subclass in Python -- excluded explicitly, the
    #: same guard `registration.to_registration` applies to
    #: `membership_opt_in` in the other direction.
    if not isinstance(duration_seconds, int) or isinstance(duration_seconds, bool):
        return None
    return AttendanceRow(
        display_name=display_name,
        email=email,
        joined_at=joined_at,
        left_at=left_at,
        duration_seconds=duration_seconds,
    )


@dataclass(frozen=True)
class AttendanceExportFile:
    """`attendance-import.csv.enc`'s in-memory shape: a version and the
    entries -- the per-row analogue of `registration.RegistrationFile`.
    Every entry is a `dict` carrying exactly `eventkeys`'s wire-format keys
    (`v`, `encrypted_key`, `iv`, `ciphertext`), never a bespoke class, for
    the identical reason `RegistrationFile`'s own docstring gives."""

    entries: tuple[Mapping[str, Any], ...] = ()


def load_attendance_export_file(text: str | None) -> AttendanceExportFile:
    """Parse `attendance-import.csv.enc`, or start empty when `text` is
    `None`. Mirrors `registration.load_registration_file` field for field:
    raises `ValueError` on anything committed that is not this exact
    format -- unlike a missing file, a malformed one is not a normal state
    to paper over -- including the same structural guard against a
    "helpful" extra field sitting in plain sight beside the ciphertext it
    was meant to replace."""
    if text is None:
        return AttendanceExportFile()
    data: Any = json.loads(text)
    if not isinstance(data, dict) or data.get("v") != ATTENDANCE_FILE_VERSION:
        raise ValueError("attendance-import.csv.enc is not a supported format version")
    entries = data.get("rows")
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ValueError("attendance-import.csv.enc is malformed")
    if not all(set(e) == eventkeys.ENVELOPE_FIELDS for e in entries):
        raise ValueError(
            "attendance-import.csv.enc holds an entry that is not exactly ciphertext"
        )
    return AttendanceExportFile(entries=tuple(entries))


def dump_attendance_export_file(file: AttendanceExportFile) -> str:
    """The bytes `attendance-import.csv.enc` is written as: stable
    structure, two-space indent, one trailing newline -- the same shape
    `registration.dump_registration_file` already uses, for the same
    "readable in a diff" reason."""
    return json.dumps(
        {"v": ATTENDANCE_FILE_VERSION, "rows": list(file.entries)}, indent=2
    ) + chr(10)


def encrypt_attendance_rows(public_pem: str, rows: Sequence[AttendanceRow]) -> str:
    """Encrypt every row in `rows` under an event's own published public
    key, one independent `eventkeys.encrypt` call each, and return the
    whole committable `attendance-import.csv.enc` text
    (see the module docstring's "one independent envelope per row"
    section for why this replaced a single whole-file envelope).

    Takes `public_pem`, never a private key or a secret -- see
    `eventkeys.py`'s own module docstring, "the public half is a file, not
    a secret" -- so the host running this, on their own laptop, needs
    nothing this project keeps in CI.
    """
    entries = tuple(
        json.loads(eventkeys.encrypt(public_pem, _row_to_plaintext(row)))
        for row in rows
    )
    return dump_attendance_export_file(AttendanceExportFile(entries=entries))


def decrypt_attendance_rows(
    file: AttendanceExportFile, private_pem: str
) -> list[AttendanceRow]:
    """The inverse of `encrypt_attendance_rows`: every row this
    `private_pem` can actually read. A row whose envelope fails to decrypt
    (wrong key, corrupted ciphertext) or whose decrypted plaintext is not
    exactly this module's own row shape is skipped, never treated as
    fatal on its own -- the same tolerance `registration.py`'s own callers
    already give a stray undecryptable entry in `registrations.enc`. One
    damaged or foreign row costs one row, not the whole file.

    **Zero rows out of a non-empty file is a refusal,
    not an answer.** *Some* rows failing is a damaged file -- tolerable,
    the case the paragraph above describes. *All* rows failing is the
    wrong file -- an export encrypted under a different event's public
    key, or a private key that does not match the one that produced it,
    both one copied identifier away from an operator's actual keyboard.
    Read as "0 rows" and carried into matching or issuance, that becomes
    "nobody attended", the one reading of that number that is certainly
    false whenever the committed file is not itself empty. So: any entry
    at all in `file.entries`, and none of them survives decryption or
    parsing, raises `AttendanceImportError` instead of returning `[]` --
    the same fail-closed shape `get_attendance` already gives an absent
    `private_pem`. An empty `file.entries` (nothing was ever committed)
    is unaffected and still returns `[]`; that case is handled before
    this function is ever reached, by `get_attendance`'s own "no
    attendance export" refusal."""
    rows: list[AttendanceRow] = []
    for entry in file.entries:
        try:
            plaintext = eventkeys.decrypt(private_pem, json.dumps(entry))
        except eventkeys.DecryptionError:
            continue
        row = _row_from_plaintext(plaintext)
        if row is not None:
            rows.append(row)
    if file.entries and not rows:
        raise AttendanceImportError(
            "none of this event's committed attendance rows could be "
            "decrypted with this private key -- the export was likely "
            "encrypted under a different event's public key, or this "
            "private key does not match the one that produced it"
        )
    return rows


def erase_attendance_rows(
    file: AttendanceExportFile, email: str, private_pem: str
) -> tuple[AttendanceExportFile, int]:
    """Remove every row addressed to `email` from `file` -- the attendance
    half of an early erasure request, called by
    `cli.py::erase_registration` alongside `registration.erase` so the two
    stores stay in step. Early erasure means
    "le fichier chiffre est reecrit sans l'enregistrement concerne, et
    rien d'autre ne bouge" -- hold here exactly as they do for
    `registrations.enc`, because the shape is now the same: every entry
    kept is returned byte for byte as found, never re-serialised, the same
    property `registration.erase`'s own docstring explains in full.

    Returns the updated file and how many rows were removed -- `0` is not
    an error, it means this address joined nothing this event recorded
    (or joined only by telephone, `email=None`, never matched by address
    at all). One person can carry several rows (a reconnection); every
    one of theirs is removed, not just the first found.

    A row that fails to decrypt under `private_pem` is kept exactly as
    found and never treated as a match -- the same defensive handling
    `registration.erase` already gives an undecryptable entry."""
    target = normalize_email(email)
    kept: list[Mapping[str, Any]] = []
    removed = 0
    for entry in file.entries:
        try:
            plaintext = eventkeys.decrypt(private_pem, json.dumps(entry))
        except eventkeys.DecryptionError:
            kept.append(entry)
            continue
        row = _row_from_plaintext(plaintext)
        if (
            row is not None
            and row.email is not None
            and normalize_email(row.email) == target
        ):
            removed += 1
            continue
        kept.append(entry)
    return AttendanceExportFile(entries=tuple(kept)), removed


def _matches_event(record: Mapping[str, Any], event_id: str) -> bool:
    edition_code = record.get("edition_code")
    return isinstance(edition_code, str) and edition_code.lower() == event_id


def find_speaker(
    speakers: Sequence[Mapping[str, Any]], event_id: str
) -> Mapping[str, Any]:
    """The rule, and the one place it is written down: `event_id` is
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
    #: The loaded contents of `data/config.yml`, for `instructions`.
    #: `None` -- the default -- reads as `''`: no config supplied is not a
    #: data-integrity failure the way a missing speaker record is, it is
    #: the same "nothing more to say" an explicit empty string would be.
    config: Mapping[str, Any] | None = None
    #: The event's own decrypted private key, read from
    #: `EVENT_PRIVATE_KEY` by whoever constructs this class (`cli.py`,
    #: never this module) -- the same key every other command touching
    #: `registrations.enc` already holds. Only needed to read
    #: `ENCRYPTED_ATTENDANCE_FILENAME`; `None` is fine as long as no event
    #: has an encrypted export committed yet (see `get_attendance`).
    private_pem: str | None = None

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
        event_dir = self._event_dir(event_id)
        encrypted_path = event_dir / ENCRYPTED_ATTENDANCE_FILENAME
        plain_path = event_dir / PLAINTEXT_ATTENDANCE_FILENAME

        if encrypted_path.exists():
            # The committed, encrypted export takes priority over
            # a local plaintext drop -- see the module docstring's "the
            # encrypted export" section. An absent or wrong `private_pem`
            # here is not D-13's ordinary state: this file is personal
            # data, committed on the promise that only the matching
            # private key can ever read it, so this refuses outright
            # rather than reporting "no attendance" for an event that
            # plainly has some.
            if not self.private_pem:
                raise AttendanceImportError(
                    f"no private key configured to decrypt the attendance "
                    f"export for event {event_id!r}"
                )
            try:
                file = load_attendance_export_file(
                    encrypted_path.read_text(encoding="utf-8")
                )
            except ValueError as exc:
                raise AttendanceImportError(
                    f"the attendance export for event {event_id!r} could "
                    f"not be read: {exc}"
                ) from exc
            # One independent envelope per row, not
            # one envelope for the whole file. A row that fails to decrypt
            # or fails to parse is skipped rather than failing this whole
            # call -- unless *every* row
            # failed, which `decrypt_attendance_rows` itself refuses
            # rather than silently returning "nobody attended". See that
            # function's own docstring for both halves of the rule.
            return decrypt_attendance_rows(file, self.private_pem)

        if plain_path.exists():
            text = plain_path.read_text(encoding="utf-8-sig")
            rows, issues = parse_attendance_csv(text)
            for issue in issues:
                print(f"attendance-import.csv line {issue.line_number}: {issue.reason}")
            return rows

        # Named relative to the repository,
        # never as the absolute `path` this class actually checked --
        # that would carry CONVENER_REPO_ROOT (a CI runner's own filesystem
        # layout, or a test's tmp_path) into a job's log for no reason,
        # the same leak already closed for
        # `cli.py`'s own register-path messages. `_validate_event_id`
        # inside `_event_dir` above has already accepted `event_id` by
        # this point, so it is safe to reuse verbatim in a relative,
        # hand-built path rather than in either path above.
        relative = Path("data") / "events" / event_id / ENCRYPTED_ATTENDANCE_FILENAME
        raise AttendanceImportError(
            f"no attendance export for event {event_id!r}: expected "
            f"{relative.as_posix()} (or its never-committed plaintext "
            f"equivalent, {PLAINTEXT_ATTENDANCE_FILENAME})"
        )

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
