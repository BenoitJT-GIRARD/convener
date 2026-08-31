"""Every figure a `config/` header works out, against the declarations it
works it out from.

`instance/queue-drain.yml` and `instance/registration-lanes.yml` bound each
other. The alarm's floor is twice the drain's own cron period; its ceiling
is the lane threshold next door minus that same margin; and the lane
threshold's own floor is the margin again. Both headers say so at length,
and both say it in worked figures -- *48 hours today*, *96 - 48 = 48 hours
today*, *a range of 48 to 120*. Each of those is a number one file states
about another file's value, which is the arrangement
`tools/tests/test_handbook_claims.py` exists for, one level below the
handbook: same drift, same remedy, a different set of readers.

**Why the figures stay written out.** Rendering a `config/` header from the
declarations would mean generating the one file a maintainer is most likely
to open in an editor, and a paragraph nobody may edit is not a comment. So
the worked example stays where it reads best and the claim is bound
instead.

**Why a claim here is optional, and required in the handbook.** A handbook
page is the product's, shipped filled in, and every duplicate serves it to
its own volunteers: the page states the window and the test says which
window. These two files are the *instance's* -- `owner: instance` in their
own headers -- and the copies a fresh duplicate starts from are
`instances/example/instance/`'s, whose headers are five lines and work
nothing out. Requiring the sentences would therefore fail on a duplicate
that had done nothing wrong. So a header that states a figure is held to
it, and a header that states none is held to nothing; what stops that
being a check nobody can fail is
`test_a_header_stating_a_stale_figure_is_reported`, which drives the same
reader over a header whose every figure is wrong.

**What is deliberately not read.** *Twelve hours* in
`instance/registration-lanes.yml` -- an invented value in a sentence about
somebody shortening the threshold, derived from nothing. *Two drain
periods*, in both files -- a count of drains
(`registration_routing.MISSED_DRAINS_COVERED`), not a figure the
declarations move. And the same claim where it is already bound or where
binding it would buy nothing: `docs/operating/operations.md` states the
coupled bounds and `test_handbook_claims.py` reads them, while
`app/src/settings/bounds.ts` and `app/src/screens/Settings.tsx` state it in
a docstring explaining why the settings screen exists -- product files, in
which a fourth and fifth reading of one claim would tell a maintainer
nothing the first three have not, and would put two more product files on
the edit list of any duplicate that moves its own lane threshold.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.yaml_safe import safe_load
from convener_ops.journey import registration_routing
from convener_ops.maintenance import queue_watch

ROOT: Final = repo_root()

DRAIN: Final = registration_routing.DRAIN_WORKFLOW_PATH
QUEUE_DRAIN: Final = queue_watch.CONFIG_PATH
LANES: Final = registration_routing.CONFIG_PATH

#: Both headers convert between hours and days in prose. Written here for
#: the same reason `test_handbook_claims.py` writes it: no module in the
#: package exports the number, and a test that imported a private one would
#: be reaching past the interface to avoid typing 24.
_HOURS_PER_DAY: Final = 24

#: The headers write a small count in words rather than in digits, and a
#: reader that only knew digits would pass straight over "two full days".
#: Only as far as the figures these two files actually reach: a spelled-out
#: ninety is not a form either of them writes.
_SPELLED: Final = {1: "one", 2: "two", 3: "three", 4: "four"}


@dataclass(frozen=True)
class Settings:
    """What the two headers work their figures out from: the drain's own
    cadence, the margin every bound reserves, the two bounds on the alarm,
    and the lane threshold they are derived against."""

    period: int
    margin: int
    floor: int
    ceiling: int
    lane: int


@dataclass(frozen=True)
class Claim:
    """One sentence a header states, and the figures the declarations make
    it true with.

    `inputs` is the number of leading capture groups that are the
    sentence's *own* hypothetical rather than anything derived -- the
    header that works out what an instance announcing a week ahead would
    get names the week itself, and nothing in this repository decides it.
    Those groups are fed to the arithmetic and never compared, so the claim
    can be checked without the figure it starts from having to be one this
    repository declares.
    """

    path: Path
    what: str
    pattern: re.Pattern[str]
    figures: Callable[[Settings, re.Match[str]], tuple[str, ...]]
    inputs: int = 0


def _meeting(settings: Settings) -> str:
    """The value the two bounds meet at, or a phrase saying they do not.

    A sentence claiming they meet is wrong in two different ways -- the
    figure has moved, or the coupling has come apart -- and a header
    reporting the second as though it were the first would send a
    maintainer to correct a number when what has changed is the pair.
    """
    if settings.floor != settings.ceiling:
        return (
            f"no single value: the floor is {settings.floor} hours and the "
            f"ceiling {settings.ceiling}"
        )
    return str(settings.floor)


def _in_words(count: int) -> str:
    """A small count as these headers spell it."""
    return _SPELLED.get(count, f"[{count}, which no header here spells]")


def _whole_days(hours: int) -> str:
    """`hours` in whole days, spelled, or a phrase saying it is not a whole
    number of them -- a header calling a gap "two full days" when it is
    fifty-two hours is stating a roundness the declarations no longer
    have."""
    days, remainder = divmod(hours, _HOURS_PER_DAY)
    if remainder:
        return f"[{hours} hours, which is not a whole number of days]"
    return _in_words(days)


#: Every figure the two headers work out, in the order each file writes
#: them. `finditer` reads each pattern everywhere it matches, so a sentence
#: a header repeats -- "its own 48-hour floor", twice in `queue-drain.yml`
#: -- is checked at both.
CLAIMS: Final = (
    Claim(
        path=QUEUE_DRAIN,
        what="the value the floor and the ceiling meet at",
        pattern=re.compile(
            r"With today's settings the floor and the ceiling meet at (\d+)"
        ),
        figures=lambda s, _m: (_meeting(s),),
    ),
    Claim(
        path=QUEUE_DRAIN,
        what="the range a lane threshold of a week would leave",
        pattern=re.compile(
            r"`queue_beyond_hours: (\d+)` gets a range of (\d+) to (\d+)"
        ),
        figures=lambda s, m: tuple(
            str(bound) for bound in queue_watch.alarm_bounds(s.period, int(m.group(1)))
        ),
        inputs=1,
    ),
    Claim(
        path=QUEUE_DRAIN,
        what="the lane threshold's own floor",
        pattern=re.compile(r"its own (\d+)-hour floor"),
        figures=lambda s, _m: (str(registration_routing.floor_hours(s.period)),),
    ),
    Claim(
        path=QUEUE_DRAIN,
        what="the alarm's floor",
        pattern=re.compile(r"The floor is two drain periods \((\d+) hours today\)"),
        figures=lambda s, _m: (str(s.floor),),
    ),
    Claim(
        path=QUEUE_DRAIN,
        what="the alarm's ceiling, worked out",
        pattern=re.compile(
            r"minus those same two periods \((\d+) - (\d+) = (\d+) hours today\)"
        ),
        figures=lambda s, _m: (str(s.lane), str(s.margin), str(s.ceiling)),
    ),
    Claim(
        path=QUEUE_DRAIN,
        what="the value the two bounds meet at, stated a second time",
        pattern=re.compile(r"the two meet at (\d+), so this is the only value"),
        figures=lambda s, _m: (_meeting(s),),
    ),
    Claim(
        path=QUEUE_DRAIN,
        what="the smallest lane threshold that leaves the alarm any room",
        pattern=re.compile(
            r"(\d+) hours is the smallest lane threshold that leaves this alarm"
        ),
        figures=lambda s, _m: (str(2 * s.margin),),
    ),
    Claim(
        path=LANES,
        what="the lane threshold's own floor",
        pattern=re.compile(r"With the drain running daily that floor is (\d+) hours"),
        figures=lambda s, _m: (str(registration_routing.floor_hours(s.period)),),
    ),
    Claim(
        path=LANES,
        what="the threshold, and how far above its floor it sits",
        pattern=re.compile(r"(\d+) is (\w+) full days above that floor"),
        figures=lambda s, _m: (
            str(s.lane),
            _whole_days(s.lane - registration_routing.floor_hours(s.period)),
        ),
    ),
    Claim(
        path=LANES,
        what="what the worst case still leaves a registrant",
        pattern=re.compile(r"still leaves a clear (\d+) hours"),
        figures=lambda s, _m: (
            str(s.lane - registration_routing.floor_hours(s.period)),
        ),
    ),
    Claim(
        path=LANES,
        what="the window whose registrations that generosity costs a run each",
        pattern=re.compile(r"arrive between (\w+) days and (\w+) days before an event"),
        figures=lambda s, _m: (
            _whole_days(s.lane),
            _whole_days(registration_routing.floor_hours(s.period)),
        ),
    ),
)


def _declaration(path: Path) -> Any:
    return safe_load((ROOT / path).read_text(encoding="utf-8"))


def settings_in_force() -> Settings:
    """The drain's cadence and the bounds it and the lane threshold make,
    read from the files themselves through the package's own arithmetic
    rather than worked out a second time here."""
    period = registration_routing.drain_period_hours(_declaration(DRAIN))
    lane = registration_routing.threshold_from_data(_declaration(LANES))
    floor, ceiling = queue_watch.alarm_bounds(period, lane)
    return Settings(
        period=period,
        margin=period * registration_routing.MISSED_DRAINS_COVERED,
        floor=floor,
        ceiling=ceiling,
        lane=lane,
    )


def header_prose(text: str) -> str:
    """A file's comment lines, unwrapped: each one with its `#` taken off,
    joined by a single space.

    A claim that spans a line break therefore reads as one sentence, and
    rewrapping a paragraph -- which changes where every break falls and
    nothing about what the header says -- cannot silently unbind one.
    """
    return " ".join(
        line.lstrip().removeprefix("#").strip()
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    )


def stale_figures(prose: dict[Path, str], settings: Settings) -> list[str]:
    """One sentence per figure a header states that the declarations do not
    make true. The empty list is the whole of the good outcome."""
    findings: list[str] = []
    for claim in CLAIMS:
        for found in claim.pattern.finditer(prose[claim.path]):
            stated = found.groups()[claim.inputs :]
            expected = claim.figures(settings, found)
            if stated != expected:
                findings.append(
                    f"{claim.path.as_posix()} states {claim.what} as "
                    f"{stated}, and the declarations make it {expected} "
                    f"(drain period {settings.period}h, lane threshold "
                    f"{settings.lane}h)"
                )
    return findings


def _prose_in_force() -> dict[Path, str]:
    return {
        path: header_prose((ROOT / path).read_text(encoding="utf-8"))
        for path in (QUEUE_DRAIN, LANES)
    }


def test_every_figure_these_headers_work_out_is_the_one_in_force() -> None:
    """The claim this module exists for: raising the lane threshold without
    rewriting the paragraph beside it fails, rather than leaving a worked
    example that no longer works."""
    assert stale_figures(_prose_in_force(), settings_in_force()) == []


def test_a_header_stating_a_stale_figure_is_reported() -> None:
    """The reader, driven over a header whose every figure is wrong.

    Written out rather than read from the files, and that is the point: in
    a repository whose `config/` is still the product's example, the files
    state no figures at all and a check over them can only pass. This one
    fails wherever it runs if a pattern stops reading its sentence or a
    comparison stops biting -- every claim above has to appear in the
    findings, by name.

    The lines below are deliberately wrapped where the real headers wrap,
    so `header_prose` is exercised on a claim that spans a line break.
    """
    settings = Settings(period=24, margin=48, floor=48, ceiling=48, lane=96)
    wrong = {
        QUEUE_DRAIN: header_prose(
            "# With today's settings the floor and the ceiling meet at 60, so\n"
            "# `queue_beyond_hours: 168` gets a range of 12 to 300 and one\n"
            "# that cuts it towards its own 12-hour floor is worse.\n"
            "# The floor is two drain periods (60 hours today).\n"
            "# The ceiling is queue_beyond_hours minus those same two\n"
            "# periods (12 - 12 = 12 hours today). And so, with today's\n"
            "# settings the two meet at 60, so this is the only value: 12\n"
            "# hours is the smallest lane threshold that leaves this alarm\n"
            "# any room at all.\n"
            "alarm_after_hours: 48\n"
        ),
        LANES: header_prose(
            "# With the drain running daily that floor is 12 hours. And 12\n"
            "# is nine full days above that floor: the worst case still\n"
            "# leaves a clear 300 hours, and the whole cost is the\n"
            "# registrations that arrive between nine days and one days\n"
            "# before an event.\n"
            "queue_beyond_hours: 96\n"
        ),
    }
    findings = stale_figures(wrong, settings)
    assert len(findings) == len(CLAIMS), findings
    for claim in CLAIMS:
        assert any(claim.what in finding for finding in findings), (
            f"{claim.path.as_posix()}'s claim about {claim.what} was not "
            "reported, so either its pattern no longer reads the sentence "
            "or its comparison no longer bites"
        )


def test_a_header_that_works_nothing_out_is_held_to_nothing() -> None:
    """The example instance's own headers, which is what a fresh duplicate
    starts from: five lines, no arithmetic, nothing to be stale."""
    example = ROOT / "instances" / "example" / "instance"
    prose = {
        QUEUE_DRAIN: header_prose(
            (example / QUEUE_DRAIN.name).read_text(encoding="utf-8")
        ),
        LANES: header_prose((example / LANES.name).read_text(encoding="utf-8")),
    }
    assert stale_figures(prose, settings_in_force()) == []


def test_a_coupling_that_has_come_apart_is_reported_as_that() -> None:
    """A lane threshold raised to a week leaves the alarm a range rather
    than one value, and a header still claiming the two meet is not one
    digit out -- it is claiming a coupling the declarations no longer
    have. A finding that named a number would send a maintainer to correct
    a digit in a sentence that has stopped being about anything."""
    floor, ceiling = queue_watch.alarm_bounds(24, 168)
    apart = Settings(period=24, margin=48, floor=floor, ceiling=ceiling, lane=168)
    prose = {
        QUEUE_DRAIN: header_prose(
            "# With today's settings the floor and the ceiling meet at 48.\n"
        ),
        LANES: "",
    }
    findings = stale_figures(prose, apart)
    assert len(findings) == 1, findings
    assert "no single value: the floor is 48 hours and the ceiling 120" in findings[0]
