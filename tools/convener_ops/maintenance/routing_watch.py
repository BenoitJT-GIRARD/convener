"""Evidence, inside this repository, that a registration can still be queued.

The gap the submission queue leaves behind:
"the saving can disappear in silence". A registration has
two lanes, and `registration_routing.py` states in as many words that
**every** failure to resolve `instance/public-data/registration-routing.json`
resolves to the *immediate* lane -- a 404, a body that will not decode, a
version the relay does not know, an event absent from the file, a rate
limit, an unreachable GitHub. That direction is right, and nothing here
touches it: the confirmation carries the room link and the matching code,
there is no second channel for either, and doubt has to resolve towards
sending it now. The cost of guessing wrong in that direction is one billed
run.

The cost of *never finding out* is the whole phase. If the projection goes
stale, or an event never reaches it, every registration takes the immediate
lane and bills a run each -- exactly the behaviour the queue replaced.
Nobody is harmed, nothing is lost, the queue is simply empty, and an empty
queue looks like a quiet day. The only backstop before this module was
the budget alarm, which speaks a week later and about a different
thing. A control that cannot fail loudly is not a control (D-25); this
module is that requirement applied to a saving rather than to a protection.

The signal: what the file can still route, never how old it is
----------------------------------------------------------------
This module recomputes the projection from `instance/data/speakers.yml` and
`instance/registration-lanes.yml` -- the same pure function `deploy.yml`
runs, called here rather than reimplemented -- and compares it with the
committed file, **restricted to the events whose lane a registration
arriving right now still depends on**.

An age check was the obvious candidate and it is the wrong one, for two
mechanical reasons rather than a preference:

* Between seminars nothing that feeds the projection moves at all, so a
  file untouched for a month is exactly right. An age threshold that did
  not cry wolf across a quiet season would have to be longer than the gap
  between seminars, by which point it is longer than the notice an event
  gets.
* This repository's own jobs push to the default branch with the run's
  `GITHUB_TOKEN`, which GitHub's recursion guard stops from starting
  `deploy.yml` (`sweep-and-notify.yml`'s own comment records this and
  dispatches `publish-showcase.yml` by hand because of it). A healthy
  repository can therefore go a long time with no deploy at all.

There was a third, and it stopped being true twice over. It read
`deploy.yml` declares `paths-ignore: config/**`, so editing the lane file
changes every cutoff and starts nothing -- written when the file was
`config/registration-lanes.yml`. The file is `instance/registration-lanes.yml`
now, and `config/**` left `deploy.yml`'s `paths-ignore` when the published
address moved into `instance/config.json`. A person editing the lane file
today does start `deploy.yml`, and it does rewrite the projection. The two
above are untouched by either move: the projection's other input,
`instance/data/speakers.yml`, is rewritten by this repository's own jobs
under the recursion guard, and a quiet season moves nothing at all.

Both say the same thing: the file's age is uncorrelated with the only
property that matters, which is whether it still answers correctly for the
events that can still be registered for.

What "still depends on" means, and what it deliberately excludes
------------------------------------------------------------------
An event is **live** here when a registration arriving now would take the
queue lane according to the cutoff this repository would publish, or
according to the one the file actually carries -- `live_events` asks that
question through `registration_routing.lane`, the same function the
relay's own `registrationLane` mirrors, so the alarm and the relay cannot
come to different conclusions about the same instant.

That scope is what keeps this quiet when it should be quiet:

* **An event inside the threshold** -- less than `queue_beyond_hours` from
  its start -- routes to the immediate lane whatever the file says. Nothing
  is at stake, so a file that has forgotten it is not a finding. Without
  this, every seminar would raise an alarm for its own last four days.
* **A file naming only past events is a quiet season, not a failure.** If
  no event is live, there is nothing to route and no saving to lose, so
  this module says nothing. That is the direct consequence of measuring the
  ability to route rather than freshness, and it is the case an age check
  gets exactly backwards.
* **An event the file names that `instance/data/speakers.yml` no longer dates** is
  in scope only while its published cutoff is still in the future -- the
  one shape of that case where somebody could still be queued for an event
  this repository can no longer place in time -- a question about routing,
  not about the bill.

A missing or unreadable file is the one unconditional finding
---------------------------------------------------------------
`UNPUBLISHED` fires whether or not anything is live, because it is not a
statement about the season: it says the projection does not exist, and it
will still not exist on the morning an announcement goes out and
registrations start arriving. Every other finding here is a disagreement
between two files; this one is the absence of one of them.

No threshold, and that is a decision
--------------------------------------
There is no `config/` file beside `actions-budget.yml`,
`registration-lanes.yml` and `queue-drain.yml` for this control, because
nothing in it is a matter of taste. The comparison is exact -- two strings
either match or they do not -- and the one boundary it has, "is this event
still live", is `instance/registration-lanes.yml`'s own `queue_beyond_hours`
read through the lane rule itself. A knob added here would be a number with
no correct setting, and this repository already has thirteen recorded
instances of what an unsettable control is worth.

What this still cannot see, written down rather than implied
--------------------------------------------------------------
* **It compares the committed file, never the one the relay reads.** The
  relay fetches it through the Contents API and can be refused by a rate
  limit, an expired credential or an unreachable GitHub -- every one of
  which falls open to the immediate lane, and none of which leaves a trace
  in this repository. What is checked here is that the answer *exists and
  is right*; that the relay can obtain it is beyond anything an offline
  check can say.
* **One narrow race can make it early.** A push landing between this
  checkout and `deploy.yml`'s own commit is observed here as a divergence,
  because at that instant it is one. It fires once and the next day is
  quiet. The window is the few minutes a deploy takes, on a repository
  whose data changes a handful of times a year.
* **Nothing here says whether a registration actually took the queue.**
  That would need the relay's own logs, which this project deliberately
  does not have. This control proves the *ability* to queue, which is the
  half that can be proved from files.

Everything in this module is a pure function. `cli.py` supplies the parsed
files and the clock; nothing here reads a file, an environment variable or
a clock, and nothing here goes near the network.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from ..journey import registration_routing

#: How `registration_routing.to_routing_data` spells an instant. Seconds
#: precision, always UTC, always the same width. Not shared with that
#: module as one constant on purpose: what has to hold is that this reader
#: can read what that writer writes, and
#: `tools/tests/maintenance/test_routing_watch.py` proves it by parsing that
#: function's real output rather than by comparing two literals.
INSTANT_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"

#: The workflow that regenerates and commits the projection. Named here
#: because the reader of this alarm will not deduce it: every finding
#: below is about a *deployment*, never about the data, and the fix is to
#: run this rather than to edit anything.
PUBLISHER_PATH: Final = Path(".github") / "workflows" / "deploy.yml"

#: That workflow's own `name:`, which is what the Actions tab shows.
PUBLISHER_NAME: Final = "Deploy app"

#: The projection does not exist, or cannot be read as the shape this
#: repository publishes. Every registration for every event takes the
#: immediate lane.
UNPUBLISHED: Final = "unpublished"

#: A live event the published file does not name. Every registration for
#: it takes the immediate lane and bills a run.
UNNAMED: Final = "unnamed"

#: A live event the published file names with a cutoff that is not the one
#: this repository would publish now.
STALE: Final = "stale"

#: How many events the annotations and the board message name one by one
#: before they say "and N more".
#:
#: A bound rather than a preference, for `queue_watch.MOST_LISTED`'s own
#: recorded reason: a comment body past what GitHub accepts is no message
#: at all, which is the exact silence this module exists to refuse. The
#: count is always exact; only the enumeration is trimmed.
MOST_LISTED: Final = 10


@dataclass(frozen=True)
class Divergence:
    """One event the published file gets wrong, and both sides of it.

    `expected` is the cutoff this repository would publish for it right
    now, `published` is what the file carries; either may be `None`,
    meaning that side does not name the event at all. Both are the
    `INSTANT_FORMAT` strings the file is made of, never parsed instants:
    what goes in a message is what a reader will find in the file.

    `event` is a lower-cased `edition_code`, which is what the projection
    is keyed on and is public by construction -- this message reaches a
    repository thread, so nothing else could be allowed in it.
    """

    event: str
    expected: str | None
    published: str | None


@dataclass(frozen=True)
class Finding:
    """One reason to be loud, and the sentence that says it -- the same
    shape `queue_watch.Alarm` and `actions_usage.Alarm` have, so `kind`
    can be pinned by a test without matching prose."""

    kind: str
    text: str


def published_from_data(data: Any) -> dict[str, str]:
    """Parse an already JSON-loaded `instance/public-data/registration-routing.json`.

    Raises `ValueError`, naming the file, on anything that is not the shape
    `registration_routing.to_routing_data` writes. Refusing rather than
    salvaging is the point: `services/signup-relay` applies exactly these
    checks and reads a failure of any of them as "no cutoff", i.e. as the
    immediate lane for every event -- so a file this function had to guess
    at is a file the relay has already given up on, and reporting it as
    partly usable would describe a repository that does not exist.

    Values are kept as the strings they are. One that will not parse as an
    instant is not rejected here: the relay reads it as no cutoff for that
    one event, which is a per-event finding (`UNNAMED` in effect, reported
    as `STALE` because the file does name it) and not a reason to declare
    the whole file unreadable.
    """
    named = registration_routing.ROUTING_PATH.as_posix()
    if not isinstance(data, dict):
        raise ValueError(f"{named} does not hold a JSON object")
    if data.get("v") != registration_routing.ROUTING_FILE_VERSION:
        raise ValueError(f"{named} is not a supported format version")
    cutoffs = data.get("queue_until")
    if not isinstance(cutoffs, dict):
        raise ValueError(f"{named} holds no queue_until mapping")
    published: dict[str, str] = {}
    for event, value in cutoffs.items():
        if not isinstance(event, str) or not event:
            raise ValueError(f"{named} holds a cutoff under an unusable key")
        if not isinstance(value, str):
            raise ValueError(f"{named} holds a non-string cutoff for {event}")
        published[event] = value
    return published


def parse_published(value: str) -> datetime | None:
    """One cutoff out of the published file, or `None` when it is not one.

    `None` rather than an exception because that is precisely what the
    relay does with it: `registrationCutoff` ends on
    `Number.isFinite(Date.parse(value))` and returns `null` otherwise, and
    `null` means the immediate lane. A value this cannot read is therefore
    a real, per-event loss of the queue lane, not a malformed file.
    """
    try:
        return datetime.strptime(value, INSTANT_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_expected(value: str) -> datetime:
    """One cutoff this repository has just produced, parsed.

    Raises `ValueError`, unlike `parse_published`, and the asymmetry is the
    whole reason both exist. The published file may have been written by a
    deploy from another era; a value on *this* side came out of
    `registration_routing.to_routing_data` in this very process, so one
    this module cannot read is a contradiction inside the repository. Read
    leniently, it would make every event look not-live and buy this control
    total silence -- the failure mode it exists to refuse.
    """
    parsed = parse_published(value)
    if parsed is None:
        raise ValueError(
            f"{registration_routing.ROUTING_PATH.as_posix()} would be written "
            f"with the cutoff {value!r}, which this repository's own reader "
            "cannot parse -- the writer and the reader have drifted apart"
        )
    return parsed


def _would_queue(cutoff: datetime | None, now: datetime) -> bool:
    """Whether a registration arriving at `now` would wait for the drain.

    Asked through `registration_routing.lane` rather than with a bare
    comparison so that this control and the relay cannot answer the same
    question differently -- including at the boundary, which is closed on
    the immediate side.
    """
    return registration_routing.lane(cutoff, now) == "queue"


def live_events(
    expected: Mapping[str, str], published: Mapping[str, str], now: datetime
) -> tuple[str, ...]:
    """Every event whose lane a registration arriving at `now` still
    depends on, sorted.

    An event counts as live if **either** side would still queue for it:
    the expected side is what is at stake for the bill, the published side
    is what is at stake for a person who could still be put in the queue
    for an event this repository can no longer date. An event both sides
    place in the past is history and is deliberately out of scope -- see
    the module docstring for why that keeps a quiet season quiet.
    """
    live = []
    for event in sorted(set(expected) | set(published)):
        raw_expected = expected.get(event)
        raw_published = published.get(event)
        if raw_expected is not None and _would_queue(parse_expected(raw_expected), now):
            live.append(event)
            continue
        if raw_published is not None and _would_queue(
            parse_published(raw_published), now
        ):
            live.append(event)
    return tuple(live)


def divergences(
    expected: Mapping[str, str], published: Mapping[str, str], now: datetime
) -> tuple[Divergence, ...]:
    """Every live event the published file does not route the way this
    repository would, sorted by event.

    Equality is on the strings, not on the instants they parse to, and that
    is deliberate: the two are written by one function in one spelling, so
    a difference in bytes with no difference in meaning cannot arise from
    anything but a hand edit -- which is a finding.
    """
    return tuple(
        Divergence(
            event=event,
            expected=expected.get(event),
            published=published.get(event),
        )
        for event in live_events(expected, published, now)
        if expected.get(event) != published.get(event)
    )


def describe(divergence: Divergence) -> str:
    """One line saying what is wrong with one event, in the terms a person
    can check against the file itself."""
    if divergence.published is None:
        return (
            f"{divergence.event}: absent from the published file, so every "
            "registration for it takes the immediate lane and bills a run"
        )
    if divergence.expected is None:
        return (
            f"{divergence.event}: the published file still queues "
            f"registrations for it until {divergence.published}, but "
            "instance/data/speakers.yml no longer gives it a usable date"
        )
    return (
        f"{divergence.event}: the published file says {divergence.published}, "
        f"this repository would publish {divergence.expected}"
    )


def remedy() -> str:
    """What to do about any of this, in one sentence.

    Its own function because every finding ends with it and because it is
    the half a reader cannot deduce: nothing in the daily job, and nothing
    an operator edits, regenerates this file.
    """
    return (
        f"{registration_routing.ROUTING_PATH.as_posix()} is regenerated and "
        f"committed by *{PUBLISHER_NAME}* ({PUBLISHER_PATH.as_posix()}), "
        "which is not started by the pushes this repository's own jobs "
        "make -- so nothing here will fix it on its own. Run that workflow "
        "from the Actions tab."
    )


def findings(
    diverged: Sequence[Divergence], unreadable: str | None = None
) -> tuple[Finding, ...]:
    """Every reason this observation should make a noise. Empty is a
    projection that can still route.

    `unreadable` is `cli.py`'s one-line account of why the file could not
    be read at all, or `None`. When it is set it is the **only** finding
    returned: every divergence in that case is a consequence of it, and two
    findings describing one cause is how an operator learns to skim.
    """
    if unreadable is not None:
        at_stake = (
            f"{len(diverged)} event(s) can be registered for right now, and "
            "every one of them is affected"
            if diverged
            else "No event is open for registration today, so nothing is "
            "being lost yet -- and this will still be true on the morning "
            "an announcement goes out, which is why it is said now"
        )
        return (
            Finding(
                UNPUBLISHED,
                f"{unreadable} Until it is published, every registration for "
                "every event is dispatched the instant it arrives and bills "
                f"a run of its own. {at_stake}. Nothing is lost and nobody "
                f"is kept waiting; the saving is. {remedy()}",
            ),
        )
    fired: list[Finding] = []
    unnamed = [item for item in diverged if item.published is None]
    stale = [item for item in diverged if item.published is not None]
    if unnamed:
        fired.append(
            Finding(
                UNNAMED,
                f"{len(unnamed)} event(s) can be registered for right now "
                f"that {registration_routing.ROUTING_PATH.as_posix()} does "
                "not name, so every registration for them is dispatched "
                "immediately and bills a run of its own instead of waiting "
                f"for the drain. {remedy()}",
            )
        )
    if stale:
        fired.append(
            Finding(
                STALE,
                f"{len(stale)} event(s) are published with a cutoff this "
                "repository would no longer write. The relay is routing "
                "registrations on it, so the lane they take is decided by a "
                f"deployment older than the data. {remedy()}",
            )
        )
    return tuple(fired)


def _listed(diverged: Sequence[Divergence]) -> tuple[tuple[Divergence, ...], int]:
    """The events to name one by one, and how many are left over -- see
    `MOST_LISTED`."""
    return tuple(diverged[:MOST_LISTED]), max(0, len(diverged) - MOST_LISTED)


def annotation_lines(
    fired: Sequence[Finding], diverged: Sequence[Divergence]
) -> list[str]:
    """Every line the daily job prints for GitHub Actions to render on the
    run: one `::error::` per finding, then one per event, because the fix
    is the same everywhere but the reader still has to know which events
    were affected while it lasted.

    `::error::` throughout. Unlike `submission_queue.annotation_lines`
    there is no stranger-controlled half to keep out of the colour of the
    run: nothing a submitter does can put an event in this list.

    Composed here rather than in `cli.py` so a test can read the exact text
    without capturing stdout.
    """
    lines = [f"::error::[{finding.kind}] {finding.text}" for finding in fired]
    named, beyond = _listed(diverged)
    lines += [f"::error::{describe(item)}" for item in named]
    if beyond:
        lines.append(f"::error::and {beyond} more event(s) routed on stale data")
    return lines


def message(fired: Sequence[Finding], diverged: Sequence[Divergence]) -> str | None:
    """The alert body, or `None` when nothing fired.

    Text only -- no address. `notify.dispatch` is what pairs this with a
    thread and a team mention, so an unconfigured repository composes
    nothing postable at all rather than a message addressed to nobody.

    Every identifier in it is an `edition_code`, which the published file
    is keyed on and which is public by construction: this message goes to a
    repository thread, and nothing decrypted, nothing typed by a submitter
    and no address may ever reach one.
    """
    if not fired:
        return None
    lines = ["Workshop series - registrations are no longer being queued", ""]
    for finding in fired:
        lines += [f"  - [{finding.kind}] {finding.text}", ""]
    if diverged:
        named, beyond = _listed(diverged)
        lines.append("Events affected:")
        lines += [f"  - {describe(item)}" for item in named]
        if beyond:
            lines.append(f"  - and {beyond} more")
        lines.append("")
    lines += [
        "No registration is lost and nobody waits longer: every one of them "
        "is confirmed within the minute, exactly as before this repository "
        "had a queue. What has stopped is the saving.",
    ]
    return "\n".join(lines)


def summary(live: Sequence[str], diverged: Sequence[Divergence]) -> str:
    """The one line the daily job prints on a healthy run as well as on a
    loud one. One line, deliberately: what a person is meant to be *told*
    is the finding (`queue_watch.summary`'s own note)."""
    return (
        f"{len(live)} event(s) can be registered for right now, "
        f"{len(diverged)} of them not routed the way this repository would"
    )
