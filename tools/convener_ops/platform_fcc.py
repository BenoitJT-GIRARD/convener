"""The chosen platform's `Platform` implementation (D-05), beside
`platform.py`'s `ManualPlatform` rather than instead of it.

This is what `platform.py`'s own module docstring calls "the other" answer
to the same four operations: `get_room`, `get_attendance`, `get_recording`
and `delete_recording`. `PlatformFCC` calls the meeting provider's own HTTP
API instead of reading a file or a hand-typed field. Neither implementation
inherits from the other, and `Platform` is a structural `Protocol` for
exactly that reason -- a caller written against "a platform" accepts either
without knowing which one it was handed.

The endpoint is not documented by the vendor
---------------------------------------------
`GET /api/v4/conferences/{id}/calls` returns one row per participant --
`custom_name`, `email`, `service_types`, `time_created_utc`,
`time_disconnected_utc`, `audio_duration`, `is_host` -- and it answers.
Verified against a real token, against a real conference, more than once.
But it is absent from the provider's own published API reference: the
reference declares the `Call` object this response matches field for
field, and a `CallsResponse` wrapper, and neither is attached to any
documented path. That gap is evidence about the documentation, not about
the capability -- FCC's own developer page advertises "real-time and
historical call detail records", and a 401 on an unauthenticated probe of
any path, real or invented, proves nothing about routing. Still: nothing
here promises the vendor will keep answering. `ManualPlatform` is not a
fallback kept around out of caution -- it is D-13's default, is still
correct on its own terms, and `platform_from_env` below is what lets the
whole chain keep working through it the day this endpoint stops answering,
exactly as it does today when no account is configured at all.

The email boundary, inherited rather than re-decided
----------------------------------------------------
`service_types == ["toll"]` is a telephone joiner. `email` becomes `None`
for that row -- never `""` -- for the same reason `platform.py` gives for
the manual CSV path: a phone joiner has no address to give, the platform
never collects one, and mapping the empty case to `""` would let two
telephone joiners collide on the same "address" when matched against a
registration. `AttendanceRow.email: str | None` is `platform.py`'s type,
consumed here unchanged.

Two facts this module deliberately does not act on, for the same reason
`platform.py` does not act on its CSV equivalents
-------------------------------------------------------------------------
* **A disconnect-and-rejoin produces several rows.** Verified empirically
  (conference `618516753`): one person, two rows, the same address, 12
  seconds then 157 seconds of real audio. This reader returns both --
  summing them (169 seconds, not either row alone, and not the span between
  first join and last leave) is `attendance.py`'s job, done once, in the
  one place that also has to decide what "per person" means. Summing here
  would make it impossible to do correctly later: once two rows are merged
  into one, which reconnection contributed which part of the total is gone
  for good.
* **Name capitalisation varies between two connections by the same
  person**, retyped fresh on each join. `custom_name` is returned verbatim
  as `display_name`. The address is the join key, never the name --
  normalising the name here would hide from the matching code the very
  fact it is written to rely on.

The token, and why renewing it is a step of an event's journey, not a
secret set once
----------------------------------------------------------------------
`CONVENER_MEETING_API_TOKEN` (`TOKEN_ENV` below) is the bearer access token
itself, sent as `Authorization: Bearer <token>` -- not a client id and
secret this module exchanges for one. Two things follow from how the
provider's OAuth works, and neither is solved in this module:

1. **The access token expires** (31 days on one grant observed, 14 on
   another) -- short enough against a monthly series that renewal cannot
   be "do it once and forget it".
2. **The refresh token rotates on every use.** Exchanging it for a new
   access token also issues a new refresh token, and the old one stops
   working -- so a refresh token cannot simply be stored once as a secret
   the way an access token is; whatever holds it must be rewritten on
   every renewal, including by the person renewing, not by an unattended
   job with write access to repository secrets.

The design this points to -- and what a later task is expected to wire
into the event journey `phases.ts` already drives, beside a line like
"Waiting room and co-host rights set up" -- is a **human-in-the-loop
renewal**, not automation: the refresh token lives in the shared vault,
never in this repository; a volunteer does a short browser consent step
roughly monthly, matching the series' own cadence, and pastes the new
access token into `CONVENER_MEETING_API_TOKEN`; and if nobody has, before the
token's remaining life runs low, a **notice is posted to the board thread**
(the same channel `notify.py` already posts through) rather than the
integration failing silently on the day of a seminar. Skipping the step
costs a manual attendance import for that one event, through
`platform_from_env` below -- not a cancelled seminar, and not a security
incident. None of that renewal or notice logic lives in this module: this
module only ever *uses* whatever token it is given, the same "receives what
it needs, does not go looking" rule `platform.py` already follows for
speaker records and config. See `docs/reference/operations.md`'s "Meeting
platform" section for the renewal procedure as a reader would follow it.

Which FCC conference is which event -- the one thing this module does
not attempt, and why release_recording stays a manual, per-event step
------------------------------------------------------------------------
The account is a single permanent room (D-06): every seminar is a fresh
*conference* under it, each with its own numeric id the provider assigns,
and nothing in the documented or undocumented API ties one to a
`data/speakers.yml` record. A partner's working rule -- match a conference
to an event by its timestamp, sound at one seminar a month -- was floated
during research, but doing that automatically means listing conferences
(`GET /conferences`) and trusting a response shape that was never
empirically verified the way `/calls` was; this module does not build on
an endpoint nobody has actually read a response from. So `PlatformFCC`
takes `conference_ids`, an already-resolved `event_id -> FCC conference id`
mapping, as a constructor parameter -- the same "receives already-loaded
data, does not read a file or call an endpoint to go find it" rule
`ManualPlatform` follows for `speakers` and `config`. Populating that
mapping (by hand today; perhaps by the timestamp rule tomorrow, once it is
verified) is left to whoever constructs this class.

**This is a deliberate, standing limit, not a gap left for a reader to
find.** `cli.py::release_recording` reads its one entry of `conference_ids`
from `CONVENER_FCC_CONFERENCE_ID`, a value a human types into
`.github/workflows/recording.yml`'s `workflow_dispatch` form for the one
event that run is about -- so nothing in this chain can run unattended,
and `recording.yml` is `workflow_dispatch`-only, never `schedule:`, for
that reason. This does not close the "the quota problem is a forgetting
problem" risk the design ruling below names -- a host who must remember to
open the Actions tab is still a host who can forget. Automation of the
*trigger* waits on a verified way to resolve an event id to its FCC
conference id; until one exists, releasing a recording is a runbook step,
documented as one in `docs/reference/operations.md`, not something this
module quietly promises to do on its own.

get_room does not call the API
-------------------------------
D-06 again: the provider does not create meetings, so there is no request
that could return a join link `ManualPlatform.get_room` does not already
give from the same two sources -- `zoom_link` on the matching speaker
record, `instructions` from `data/config.yml` (R-4, R-6). `PlatformFCC`
reads them the same way rather than composing `ManualPlatform`, so that
constructing a room never has to build the unrelated `events_dir` default
`ManualPlatform` needs only for `get_attendance`.

get_recording and delete_recording are the raw primitives, not the
retrieval discipline
-------------------------------------------------------------------------
A 90-minute recording is roughly 1,645 MB against the free tier's 1 GB
quota, so `delete_recording` is a condition of operation rather than an
optimisation -- confirmed by direct measurement. `get_recording` reports
what the provider says about the conference's recording (`recording_url`,
`file_size`, `is_recorded`, `deleted`); `delete_recording` calls
`DELETE /conferences/{id}`, verified to remove the recording while leaving
the conference record and every `/calls` row intact -- but the deletion
itself is real and irreversible, with no confirmation parameter and no
precondition, see its own docstring. Neither method decides **when** it is
safe to call `delete_recording` -- `Platform`'s four-method shape is fixed
by task 2, so that sequencing cannot live in either method's signature.

Verifying retrieval before delete_recording (task 10)
-------------------------------------------------------
`missing_retrieval_evidence` below is the sequencing task 3 deferred: the
caller-side check that must come back empty before `delete_recording` may
be invoked at all. The two-trace shape below is not this module's own
invention -- it reproduces a design ruling already recorded in
`.superpowers/sdd/phase-4-prep-notes.md`, "2026-08-19 -- DESIGN RULING for
the spec: who deletes the recording, and on what evidence", including its
own reasoning for why a ticked box is a claim and not a fact ("a distracted
click would destroy someone's recording"). This module's job was to carry
that ruling into working, tested code within `Platform`'s fixed shape --
not to derive it again.

"Verified" means **two independent traces, neither producible by this
module or by any code path in this repository, only by the host's own
hands**:

1. **A `runbook_progress` tick, `RETRIEVED_TICK` below** -- set on the
   event's own speaker record once the host has downloaded the recording
   and archived it somewhere durable. Cheap to check (no network call:
   the same already-loaded speaker record every other method here reads),
   but alone it is only a claim: nothing stops a stray or premature tick.
   **This used to be `youtube_url`, and that was wrong**, caught on
   review: `app/src/state/phases.ts`'s own `delivered/youtube-url` item
   documents `youtube_url` as recording *where the video is*, gated
   separately from *whether it is shown* (`publication.outcome`,
   `public_data.py`'s own gate) -- but in practice a recording nobody is
   going to publish gets no YouTube upload at all, and by extension no
   `youtube_url`, however genuinely the host retrieved it. Gating deletion
   on a publication-shaped field meant a legitimately-never-published
   recording (a speaker who withheld consent; the discussion segment,
   never uploaded anywhere, see below) could never be released, and the
   quota it occupies would never be freed -- the exact failure this task
   exists to prevent, reached *through* the guard. `RETRIEVED_TICK` is a
   distinct, single-purpose fact -- "this was retrieved" and nothing else
   -- read from `runbook_progress`, the free-form per-step tick map
   `app/src/data/validate.ts` already documents ("free-form step names,
   each ticked or not... they follow the runbook"), beside the existing
   `scheduled/T-0/recording-*` family. Naming a new key there needs no
   schema change on either language's side. **Not yet wired into
   `app/src/state/phases.ts`'s journey UI** -- that is a later task's
   work, the same way task 3 left the token-renewal notice documented but
   unwired; until then a host (or whoever maintains `data/speakers.yml`)
   sets it by hand.
2. **`converted_recording_is_reachable`** confirms, independently, that
   the provider's own side shows a *successful open* of the converted
   recording -- proof the host's Download click actually happened, not
   merely that someone typed an address or ticked a box. This is
   deliberately the stronger of the two: a byte count and a checksum are
   unavailable (this module never downloads the recording, and holds no
   local copy to hash or count); a bare "the platform still reports it as
   available" proves the *source* still has the file, never that anyone
   retrieved a copy of it; and a bare 2xx status proves even less than
   that -- see its own docstring for why status alone was not enough
   either, caught on the same review.

**Never trigger a conversion.** Neither this check nor anything else in
this module ever requests one: verified empirically, an untouched
recording's `<recording_url>.video.mp4` answers 404, and merely asking
for it (a `HEAD` request, reading no body) does not change that --
conversion only ever starts from the host's own click inside
FreeConferenceCall's web interface, a UI action this codebase has no
route to and never will. This matters beyond correctness: a converted
recording stays publicly reachable at that address **even after the
conference itself is deleted** (verified empirically), which is harmless
for a talk (already destined for YouTube) and never acceptable for the
unpublished discussion segment. No function here can cause that; the only
human action that can is the host's, by hand, once, deliberately.

**The discussion segment is a separate, unresolved case, named rather than
solved here.** Phase 3's own recording discipline stops the FCC recording
after the talk and starts a fresh one for the discussion, so an event may
have more than one FCC conference -- and the discussion's is, by the rule
above, one that must *never* pass trace 2 (nothing ever converts it) and
never gets a durable-archive destination either. Whether `release_recording`
is even the right mechanism to reclaim *that* conference's quota, or
whether it needs a distinct, narrower path of its own, is outside what
this task's review asked it to resolve; flagged in the task 10 fix report
for the controller rather than guessed at here.

The single call site is `cli.py::release_recording` -- `Platform`'s shape
is fixed by task 2, so the guard cannot live in `delete_recording`'s own
signature, and `tools/tests/test_cli.py` pins that it is the *only* place
in the whole package that calls `delete_recording` at all, immediately
after `missing_retrieval_evidence` has already come back empty.

No transport is exercised by a test
-------------------------------------
`FCCTransport` is the seam: `PlatformFCC` is constructed with one, real
callers get `_UrllibTransport` (the only place in this module that imports
`urllib`), and every test in `tools/tests/test_platform_fcc.py` substitutes
a fake that returns fixture data built to match the fields verified
empirically. No test opens a socket.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from .platform import (
    AttendanceRow,
    EventNotFoundError,
    ManualPlatform,
    Recording,
    Room,
    find_speaker,
)

#: The secret `config/integrations.yml` declares for `meeting_provider`.
#: `test_platform_fcc.py::test_token_env_matches_the_declared_integration_secret`
#: pins the two together, so a rename on one side without the other fails a
#: test instead of silently drifting.
TOKEN_ENV: Final = "CONVENER_MEETING_API_TOKEN"

_BASE_URL: Final = "https://www.freeconferencecall.com/api/v4"

#: A bare run of digits -- every real FCC conference id observed
#: (618516753, 618517384, 618515381, phase-4-prep-notes.md) has this shape.
#: `PlatformFCC._conference_id` validates every id against it before one
#: reaches a URL this module builds.
_CONFERENCE_ID_RE: Final = re.compile(r"^[0-9]+$")

#: The `runbook_progress` key a host ticks once this event's recording has
#: been retrieved and archived -- independent of whether it is ever
#: published. See the module docstring's "Verifying retrieval before
#: delete_recording" section for why this replaced `youtube_url` as trace
#: 1 (a publication signal, not a retrieval one). Not yet a checklist item
#: `app/src/state/phases.ts` shows a host -- read here, not written; a
#: later task's own work to wire in, the same way task 3 left the
#: token-renewal notice documented but unwired.
RETRIEVED_TICK: Final = "delivered/recording-retrieved"


class FCCRequestError(Exception):
    """A call to the provider's API did not come back usable: a network
    failure, a non-2xx status, or a response whose shape this module does
    not recognise. Named generically rather than "attendance" or
    "recording" -- `get_attendance`, `get_recording` and `delete_recording`
    all raise it the same way, because from a caller's point of view "the
    platform did not answer" needs the same handling regardless of which
    operation asked. Never silently read as "no data": a caller that wants
    to fall back to the manual path on this exception has to decide to,
    the same way `platform_from_env` decides once, up front, from whether a
    token is configured at all -- see the module docstring."""


class FCCTransport(Protocol):
    """What `PlatformFCC` needs from an HTTP client: one authenticated GET
    that returns parsed JSON, one authenticated DELETE, and one
    unauthenticated `HEAD` against an arbitrary absolute URL, returning its
    status-relevant headers (task 10's `head` -- see
    `converted_recording_is_reachable`). The real implementation
    (`_UrllibTransport`) wraps `urllib.request`; every test substitutes a
    fake, which is what keeps this whole suite off the network (task 3
    brief, step 2)."""

    def get_json(self, path: str, token: str) -> Any: ...

    def delete(self, path: str, token: str) -> None: ...

    def head(self, url: str) -> Mapping[str, str] | None: ...


@dataclass(frozen=True)
class _UrllibTransport:
    """The only piece of this module that touches the network. Never
    constructed by a test -- `PlatformFCC`'s `transport` parameter exists
    so a test never has to."""

    base_url: str = _BASE_URL
    timeout: float = 15.0

    def _request(self, path: str, token: str, method: str) -> bytes:
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
        try:
            # `base_url` is the module constant above, always https; `path`
            # is built from a conference id that `PlatformFCC._conference_id`
            # validates digits-only before this method is ever reached. That
            # id may originate from operator-typed input (a
            # `workflow_dispatch` field, since task 10) -- not "never raw
            # user input", the claim this comment made before task 10's
            # review round found it false -- but the digit-only validation
            # forecloses `/`, `..` and every other URL-structuring
            # character, so this is not the "URL built from unchecked
            # input" bandit's urlopen check (B310) exists to catch.
            with urllib.request.urlopen(  # nosec B310
                request, timeout=self.timeout
            ) as response:
                return response.read()  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            raise FCCRequestError(f"{method} {path} returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FCCRequestError(f"{method} {path} failed: {exc}") from exc

    def get_json(self, path: str, token: str) -> Any:
        body = self._request(path, token, "GET")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FCCRequestError(f"GET {path} did not return valid JSON") from exc

    def delete(self, path: str, token: str) -> None:
        self._request(path, token, "DELETE")

    def head(self, url: str) -> Mapping[str, str] | None:
        """`HEAD url` -- an absolute address the provider's own API already
        returned in a prior response, never built from anything a caller
        typed -- and report the three headers `converted_recording_is_reachable`
        needs (`content_type`, `accept_ranges`, `content_length`), or `None`
        if the request did not come back with a successful status at all.
        This method never inspects those headers itself and never decides
        what they mean -- interpreting them is `converted_recording_is_reachable`'s
        job, kept separate so a fake in a test can hand this a plain `dict`
        without faking an HTTP response object.

        Reads no response body, ever, so it never pulls any part of a
        multi-hundred-megabyte recording across the wire, and issuing it
        triggers nothing on the provider's side -- see the module
        docstring's "never trigger a conversion" section.

        No `Authorization` header: `url` is not necessarily under
        `base_url` (the recording's own media URLs are public, verified to
        need no token -- phase-4-prep-notes.md, 2026-08-19), and this class
        never sends the bearer token to an address it did not build from
        `base_url` itself.

        Any failure -- a non-2xx status, a network error, a timeout, a
        malformed response, a non-`https` address -- reads as `None`, the
        same "not yet" a genuinely unconverted recording answers with. A
        caller deciding whether to delete something irreversible must
        never be able to mistake "this check itself broke" for "verified".
        `Request(...)` construction lives inside the same `try` as the
        request itself: a malformed URL can raise there too, and that must
        read as `None` exactly like every other way this can fail, not
        propagate past this method.
        """
        if not url.startswith("https://"):
            return None
        try:
            # `url` is validated https-only immediately above, and always
            # originates from this same class's own prior authenticated GET
            # to the provider's fixed `base_url` -- never from anything a
            # caller typed -- so this is not the "URL built from unchecked
            # input" bandit's urlopen check (B310) exists to catch.
            request = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(  # nosec B310
                request, timeout=self.timeout
            ) as response:
                if not (200 <= response.status < 300):
                    return None
                headers: dict[str, str] = {}
                content_type = response.headers.get("Content-Type")
                if content_type is not None:
                    headers["content_type"] = content_type
                accept_ranges = response.headers.get("Accept-Ranges")
                if accept_ranges is not None:
                    headers["accept_ranges"] = accept_ranges
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    headers["content_length"] = content_length
                return headers
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            http.client.HTTPException,
            ValueError,
        ):
            # urllib.error.HTTPError subclasses URLError, so a non-2xx
            # status (404 on an unconverted recording, verified empirically)
            # is caught here too, alongside a genuine network failure. A
            # malformed status line (`http.client.HTTPException`, not an
            # `OSError`) and a malformed URL (`ValueError`, from either
            # `Request(...)` or `urlopen`) are caught the same way -- every
            # one of them reads as "not yet", never as a crash.
            return None


def _iso_utc(epoch_seconds: Any) -> str:
    """`time_created_utc` / `time_disconnected_utc` are exact-second UTC
    epoch integers (verified empirically). Rendered as the same
    `YYYY-MM-DDTHH:MM:SSZ` shape `platform.py`'s manual CSV path already
    uses for `joined_at` / `left_at`, so a caller reading either platform's
    rows sees one convention, not two."""
    try:
        seconds = int(epoch_seconds)
    except (TypeError, ValueError):
        seconds = 0
    stamp = datetime.fromtimestamp(seconds, tz=UTC)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_telephone_joiner(call: Mapping[str, Any]) -> bool:
    """The rule is keyed on `service_types`, exactly `["toll"]" -- not on
    whatever the `email` field happens to hold, so a payload that sends an
    empty string instead of `null` for a toll row still gets `None`.

    Deliberately an exact match, not `"toll" in service_types`: only
    `["toll"]` was ever empirically verified as the telephone-joiner shape.
    An absent key, an empty list, and a multi-value list that includes
    `"toll"` alongside another type (someone whose audio fell back to the
    phone line while still connected some other way) all fall through to
    the non-toll branch below and keep whatever `email` the payload sent --
    the safe default, since it never manufactures a telephone joiner the
    verified fact does not describe. Pinned by
    `test_platform_fcc.py::test_non_exact_toll_service_types_keep_the_raw_email`
    against a future "tidy-up" that widens the match."""
    service_types = call.get("service_types")
    return isinstance(service_types, list) and service_types == ["toll"]


def _row_from_call(call: Mapping[str, Any]) -> AttendanceRow:
    display_name = str(call.get("custom_name", "") or "")
    if _is_telephone_joiner(call):
        email = None
    else:
        raw_email = call.get("email")
        email = str(raw_email).strip() or None if raw_email else None
    try:
        duration_seconds = int(call.get("audio_duration", 0) or 0)
    except (TypeError, ValueError):
        duration_seconds = 0
    # Not clamped or rejected when negative, unlike `platform.py`'s CSV
    # path, which drops a negative `duration_seconds` because a person
    # typed it. `audio_duration` here is computed by the provider from its
    # own two timestamps, has never been observed negative, and if it ever
    # were, that would be a fact about the response worth seeing, not a
    # typo to quietly correct. This reader builds no second per-row
    # issue-reporting mechanism for API data (see the module docstring);
    # an anomalous value is returned exactly as received, the same "give
    # the truth, however odd" rule already applied to `display_name` and
    # to the reconnection rows themselves.
    return AttendanceRow(
        display_name=display_name,
        email=email,
        joined_at=_iso_utc(call.get("time_created_utc")),
        left_at=_iso_utc(call.get("time_disconnected_utc")),
        duration_seconds=duration_seconds,
    )


def _extract_calls(payload: Any) -> list[Mapping[str, Any]]:
    """The endpoint is undocumented by the vendor -- everything verified
    about it came from reading real responses, and every one of them was a
    bare JSON array (`test_platform_fcc.py`'s fixtures are shaped that
    way). The `data` key below is a defensive fallback only, never itself
    verified against the real service -- see the module docstring."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        wrapped = payload.get("data")
        if isinstance(wrapped, list):
            return wrapped
    raise FCCRequestError(
        "the calls endpoint returned a shape this module does not recognise"
    )


@dataclass(frozen=True)
class PlatformFCC:
    """The chosen platform's implementation of `Platform` (D-05). See the
    module docstring for the token, the conference-id boundary, and the
    get_recording / delete_recording split with task 10."""

    #: The bearer access token, already obtained -- this class never
    #: exchanges credentials or a refresh token for one. See the module
    #: docstring's token section for why that exchange does not belong
    #: here.
    access_token: str
    #: The loaded contents of `data/speakers.yml`, read the same way
    #: `ManualPlatform` reads them -- never from a file this class opens
    #: itself.
    speakers: Sequence[Mapping[str, Any]] = ()
    #: The loaded contents of `data/config.yml`, for `instructions` (R-6),
    #: read the same way `ManualPlatform` reads it.
    config: Mapping[str, Any] | None = None
    #: `event_id -> FCC conference id`, already resolved by whoever
    #: constructs this class. See the module docstring's "which FCC
    #: conference is which event" section for why this module does not
    #: resolve it itself.
    conference_ids: Mapping[str, str] = field(default_factory=dict)
    #: The HTTP seam. Defaults to the real implementation; every test
    #: substitutes a fixture-backed fake.
    transport: FCCTransport = field(default_factory=_UrllibTransport)

    def _conference_id(self, event_id: str) -> str:
        """Resolves the FCC conference id for `event_id` from
        `conference_ids` -- the one piece of data `get_attendance`,
        `get_recording` and `delete_recording` need that does not come from
        a speaker record (see the module docstring's "which FCC conference
        is which event" section). Raises `EventNotFoundError` -- the same
        exception `find_speaker` raises for "no such event" -- naming
        `event_id`, so a caller sees one exception type for "nothing to
        answer with for this id" regardless of which `Platform` operation
        or which implementation asked.

        Every real conference id observed (618516753, 618517384,
        618515381 -- phase-4-prep-notes.md) is a bare run of digits, so
        that shape is validated here, once, for every caller: raises
        `ValueError` -- distinct from `EventNotFoundError`, the same
        "malformed" vs "unknown" split `platform.py::find_speaker` already
        draws for `event_id` -- naming both `event_id` and the offending
        value, never silently passed through. `conference_ids` has no
        production populator yet (the module docstring's own seam); its
        one caller today, `cli.py::release_recording`, reads a value an
        operator types into a `workflow_dispatch` form, and this is the
        one place that value is validated before it can reach a URL this
        class builds -- closing the path a hand-typed
        `"618/../999"`-shaped id would otherwise ride into `DELETE
        /conferences/618/../999`, found on review."""
        try:
            conference_id = self.conference_ids[event_id]
        except KeyError:
            raise EventNotFoundError(
                f"no FCC conference is recorded for event {event_id!r}"
            ) from None
        if not _CONFERENCE_ID_RE.fullmatch(conference_id):
            raise ValueError(
                f"not a valid FCC conference id for event {event_id!r}: "
                f"{conference_id!r}"
            )
        return conference_id

    def get_room(self, event_id: str) -> Room:
        """D-06: the account is the permanent room. Reads the same two
        sources `ManualPlatform.get_room` reads -- never the API, see the
        module docstring."""
        record = find_speaker(self.speakers, event_id)
        join_url = str(record.get("zoom_link", "") or "")
        instructions = ""
        if self.config is not None:
            instructions = str(self.config.get("instructions", "") or "")
        return Room(join_url=join_url, instructions=instructions)

    def get_attendance(self, event_id: str) -> list[AttendanceRow]:
        conference_id = self._conference_id(event_id)
        payload = self.transport.get_json(
            f"/conferences/{conference_id}/calls", self.access_token
        )
        calls = _extract_calls(payload)
        return [_row_from_call(call) for call in calls]

    def get_recording(self, event_id: str) -> Recording:
        conference_id = self._conference_id(event_id)
        payload = self.transport.get_json(
            f"/conferences/{conference_id}", self.access_token
        )
        if not isinstance(payload, Mapping):
            raise FCCRequestError(
                "the conference endpoint returned a shape this module "
                "does not recognise"
            )
        url = str(payload.get("recording_url", "") or "")
        is_recorded = bool(payload.get("is_recorded", False))
        deleted = bool(payload.get("deleted", False))
        available = bool(url) and is_recorded and not deleted
        size = 0
        if available:
            try:
                size = int(payload.get("file_size", 0) or 0)
            except (TypeError, ValueError):
                size = 0
        return Recording(url=url, size=size, available=available)

    def delete_recording(self, event_id: str) -> None:
        """Calls `DELETE /conferences/{id}`, verified empirically to
        remove the recording while leaving the conference record and every
        `/calls` row intact -- deleting the recording never loses
        attendance.

        **This is irreversible.** There is no undo, no trash, no soft
        delete: once this call succeeds, the recording is gone from the
        provider for good, and nothing in this codebase can get it back. A
        90-minute session recorded once is not recoverable a second time.

        This method performs the deletion unconditionally. It does not
        check whether the host's own copy was ever downloaded, accepts no
        confirmation parameter, and raises nothing to stop a caller who has
        not verified retrieval -- because it structurally cannot: nothing
        this class holds can tell it whether a file landed safely on
        someone's laptop. **A caller MUST confirm the recording was
        retrieved before invoking this method.** Deciding how, and on what
        evidence, is deliberately not this method's job: `Platform`'s
        four-method shape is fixed by task 2 and this class does not
        extend it, so the structural guard lives at the call site instead
        -- `missing_retrieval_evidence` below, and `cli.py::release_recording`,
        the one place in this package that is allowed to call this
        method at all (pinned by
        `tools/tests/test_cli.py::test_delete_recording_has_exactly_one_call_site_in_the_whole_package`)."""
        conference_id = self._conference_id(event_id)
        self.transport.delete(f"/conferences/{conference_id}", self.access_token)


def converted_recording_is_reachable(
    recording: Recording, transport: FCCTransport
) -> bool:
    """Whether the recording's converted MP4 already exists at the
    provider's own storage -- the stronger of the two independent traces
    `missing_retrieval_evidence` requires before `delete_recording` may be
    called (see that function, and the module docstring's "Verifying
    retrieval before delete_recording" section for the full reasoning).

    Verified empirically (phase-4-prep-notes.md, 2026-08-19): an untouched
    recording's `<recording_url>.video.mp4` answers 404; once the host has
    clicked Download in FreeConferenceCall's own web interface, the same
    address answers 200, content type `video/mp4`, `Accept-Ranges: bytes`,
    no token required -- and stays reachable there even after the
    conference's own recording is later deleted through this module (also
    verified). That is proof the host's own click already happened;
    nothing here can trigger it -- the check reads no body, and hitting
    this address was itself confirmed, against a real untouched recording,
    to leave it untouched (still 404 afterwards, never converted by the
    mere asking).

    **A bare 2xx status is not enough, found on review**: `urlopen` follows
    redirects transparently, and a CDN answering an absent object with its
    own 200 error page -- `Content-Type: text/html`, say -- would satisfy a
    status-only check while proving nothing about a converted recording.
    So this also requires the two headers the prep notes record for a
    genuine converted file: `content_type` exactly `video/mp4` (ignoring
    any `;`-separated parameter -- the prep notes' own "do not branch on
    content type" caution is explicitly about `.mp3`, whose `Content-Type`
    is sometimes `text/plain` over a real MP3 body; that caveat does not
    apply here, `.video.mp4` was never observed to lie about its type) and
    `accept_ranges` exactly `bytes`. `content_length`, free from the same
    `HEAD`, is checked too when present -- a `0` would mean an empty body
    behind headers that otherwise look right, and is rejected the same
    way.

    `recording.url` with no `recording_url` reported at all (never
    recorded, or `get_recording`'s payload was malformed) has nothing to
    check and reads as `False` -- there is no converted artefact to be
    reachable in the first place.

    **Unstated-until-now assumption, named rather than silently relied
    on** (found on review): this treats `recording.url` as identifying one
    specific recording, permanently. If the provider ever reuses a
    `recording_url` for a later re-recording of the same conference, a
    converted file left over from an *earlier* recording would still
    answer here, and a stale-but-still-true `RETRIEVED_TICK` from that
    earlier recording's own retrieval would agree with it -- both traces
    satisfied for a recording nobody has retrieved. Uniqueness of
    `recording_url` across re-recordings of one conference has not been,
    and from this repository cannot be, empirically verified; a successor
    relying on this function must either confirm it or design around not
    needing to."""
    if not recording.url:
        return False
    headers = transport.head(recording.url + ".video.mp4")
    if headers is None:
        return False
    content_type = headers.get("content_type", "").split(";")[0].strip().lower()
    if content_type != "video/mp4":
        return False
    accept_ranges = headers.get("accept_ranges", "").strip().lower()
    if accept_ranges != "bytes":
        return False
    content_length = headers.get("content_length")
    if content_length is not None:
        try:
            if int(content_length) <= 0:
                return False
        except ValueError:
            return False
    return True


def missing_retrieval_evidence(
    platform: PlatformFCC,
    recording: Recording,
    runbook_progress: Mapping[str, Any],
) -> list[str]:
    """What must still be true before `delete_recording` may be called for
    this conference's recording. An empty list means both independent,
    host-driven traces agree the recording has already been retrieved;
    any non-empty list names, in plain words, what is still missing --
    never raises, so a caller can report every gap at once rather than
    stopping at the first.

    This is the whole answer to the ordering task 10 exists to enforce
    (`delete_recording`'s own docstring: "A caller MUST confirm the
    recording was retrieved before invoking this method"). Two checks,
    neither producible by this function, by `PlatformFCC`, or by anything
    else in this repository -- only by the host's own hands:

    1. `runbook_progress[RETRIEVED_TICK]` -- ticked by the host once the
       recording has been retrieved and archived, independent of whether
       it will ever be published. Free to check (no network call: the
       same already-loaded speaker record every other method here reads),
       but alone it is a claim, not a fact -- a stray or premature tick
       would satisfy it without anyone having retrieved anything. **Not
       `youtube_url`** -- see the module docstring's "Verifying retrieval"
       section for why that was the wrong field, caught on review.
    2. `converted_recording_is_reachable` -- a genuine, independent,
       provider-side confirmation that the host's Download click already
       happened. See its own docstring for what makes this the strongest
       signal available without downloading the recording itself (which
       this module never does) or trusting a human-typed field alone.

    Calls no method on `platform` other than reading its `transport` --
    never `get_recording`, never `delete_recording`. The caller already
    holds `recording` (from its own earlier `get_recording` call) and
    decides what to do with an empty or non-empty result; this function
    only answers the question, it never acts on it."""
    problems: list[str] = []
    if not bool(runbook_progress.get(RETRIEVED_TICK, False)):
        problems.append(
            f"the {RETRIEVED_TICK!r} step is not ticked on this event's "
            "runbook yet -- the host has not confirmed retrieving the "
            "recording"
        )
    if not converted_recording_is_reachable(recording, platform.transport):
        problems.append(
            "the converted recording is not reachable at the provider yet "
            "-- the host may not have clicked Download in FreeConferenceCall"
        )
    return problems


def platform_from_env(
    env: Mapping[str, str],
    speakers: Sequence[Mapping[str, Any]] = (),
    config: Mapping[str, Any] | None = None,
    conference_ids: Mapping[str, str] | None = None,
) -> ManualPlatform | PlatformFCC:
    """D-13, applied in full: an absent `CONVENER_MEETING_API_TOKEN` is the
    ordinary case, not a degraded one, and the whole chain keeps working
    through `ManualPlatform` -- the default, not a fallback bolted on.
    Mirrors `notify.py::resolve_channel`'s shape: given the environment as
    a plain mapping (never read from `os.environ` itself, so this stays as
    pure as every other `convener_ops` module bar `cli.py`), decide once, up
    front, which implementation a caller gets.

    A blank token counts as unset, the same "empty string is not a value"
    rule `convener_ops.integrations.resolve_states` already applies to every
    other secret this project reads."""
    token = (env.get(TOKEN_ENV) or "").strip()
    if not token:
        return ManualPlatform(speakers=speakers, config=config)
    return PlatformFCC(
        access_token=token,
        speakers=speakers,
        config=config,
        conference_ids=conference_ids or {},
    )
