"""D-14: `visual.start_local` (Python), `eventStartLocal` (`.eleventy.js`)
and `startLocal` (TypeScript, `app/src/state/derived.ts`) are three
independent implementations of one rule -- an edition's start hour comes off
its own record, falling back to the series' standing hour when the record
carries none -- so `tools/tests/fixtures/edition-start.json` is the one list
every side reads, and a change to the rule in any single language breaks the
other two.

A separate fixture from `paris-standing-start.json` beside it, on purpose.
That one binds the Europe/Paris *seasonal* rule and needs dates either side
of both DST transitions in two years to do it; this one binds *where the
hour comes from* and needs recorded hours above, below and equal to the
convention, plus the blank. One combined list would have proved each thing
half as well, and the arithmetic justifying either list's size would have
stopped holding.

**What was wrong before any of this existed.** Every surface that stated an
edition's time composed it from the standing constant: `date_line`
substituted it, `agenda.py::_edition_start` combined it, the showcase build
hard-typed it, and `render.ts` fed both `speaker.when` and `public.when`
through a one-argument `dateLine`. The record had carried the agreed hour
since `dates.ts::lockDate` began copying it off the accepted slot, and the
negotiation offers evenings at hours of their own -- the worked example this
repository ships offers 18:00. So an edition agreed for 18:00 was announced,
postered, syndicated and *calendared* at 12:30, and
`instance/public-data/agenda-internal.ics` carried
`DTSTART:20261008T103000Z` for an edition whose record said `18:00` --
committed, five and a half hours out, for a seminar a week away.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest

from convener_ops.declaration.paths import repo_root
from convener_ops.publication.visual import (
    STANDING_START_LOCAL,
    date_line,
    start_local,
)

_ROOT = repo_root()
_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "edition-start.json"
_FIXTURE: list[dict[str, Any]] = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _ids(case: dict[str, Any]) -> str:
    return f"{case['iso_date']}-{case['recorded_time'] or 'blank'}"


@pytest.mark.parametrize("case", _FIXTURE, ids=_ids)
def test_python_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    resolved = start_local(case["recorded_time"])

    assert resolved == time.fromisoformat(case["start_local"]), case["why"]
    # The composition the posters and drafts actually render, so a correct
    # `start_local` wired into nothing would still be caught.
    line = date_line(date.fromisoformat(case["iso_date"]), resolved)
    assert line == case["date_line"]


def test_the_fixture_exercises_both_branches_and_both_sides_of_the_convention() -> None:
    """A fixture of blanks, or one of recorded hours only, would make the
    parametrized test above pass for the wrong reason -- and so would one
    whose every recorded hour was later than 12:30, which a reading of
    "anything after the standing hour" would also satisfy."""
    recorded = [c["recorded_time"] for c in _FIXTURE]
    hours = [time.fromisoformat(t) for t in recorded if t]

    assert "" in recorded, "no case covers a record with no agreed hour"
    assert any(h > STANDING_START_LOCAL for h in hours), (
        "no case runs later than the convention"
    )
    assert any(h < STANDING_START_LOCAL for h in hours), (
        "no case runs earlier than the convention"
    )
    assert any(h == STANDING_START_LOCAL for h in hours), (
        "no case records the convention explicitly -- the one that proves the "
        "hour is read rather than merely defaulted to"
    )
    assert {c["offset"] for c in _FIXTURE} == {"+01:00", "+02:00"}, (
        "the hour and the season have to vary independently, or a case could "
        "pass by reading the wrong one of the two"
    )


def test_a_recorded_hour_of_another_shape_is_refused_rather_than_guessed() -> None:
    """`governance.validate` holds `time` to `HH:MM` and *Validate data* is
    a gate, so a value of another shape means the record reached a
    publication step without passing it. Publishing an invented hour would
    be worse than stopping."""
    with pytest.raises(ValueError, match="not an HH:MM start time"):
        start_local("half past six")


def test_eleventy_js_matches_the_shared_fixture() -> None:
    """`.eleventy.js::eventStartLocal` is the third implementation --
    checked here, not in a JS test runner, because `site/` carries none
    (`tools/tests/repository/test_site.py`'s own module docstring: this
    suite is this project's only quality gate on `.eleventy.js`).
    `check-edition-start.cjs` is a plain, dependency-free Node script that
    reads the identical fixture file and requires the real, committed
    `.eleventy.js` directly -- no build, no network, no new dependency."""
    script = _ROOT / "site" / "scripts" / "check-edition-start.cjs"
    result = subprocess.run(
        ["node", str(script)],
        cwd=_ROOT / "site",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
