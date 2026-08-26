"""D-14: `paris_standing_start`/`date_line` (Python),
`parisStandingStart` (`.eleventy.js`) and `parisStandingStart`/`dateLine`
(TypeScript, `app/src/state/derived.ts`) are three independent
implementations of the identical Europe/Paris seasonal-offset rule -- three
languages, three runtimes, so three implementations are legitimate (D-14),
but nothing before this file bound them together: each side's own test
suite pinned its own hand-typed list of dates, and two of those lists had
already drifted apart -- `tools/tests/test_visual.py`'s own fixture-edition
list pinned `2025-06-12` as its one committed summer case, while
`app/tests/announce-drafts.test.ts`'s own list pinned `2026-06-11`, a
different date asserted for the identical "this is the CEST case" claim.

`tools/tests/fixtures/paris-standing-start.json` is the one list every side
now reads, so a change to the rule in any one language breaks every other
side's own suite, not just its own. It is a separate fixture from
`test_visual.py`'s own `_FIXTURE_EDITIONS`, deliberately: that list proves
something else (today's real, committed editions in `site/src/_data/
events.json` resolve correctly), while this one exists purely to bind the
three *implementations* to each other, spanning both sides of both DST
transitions -- a boundary the real editions in `events.json` do not
reliably straddle, since nothing requires a real edition's date to fall
next to a transition.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from convener_ops.paths import repo_root
from convener_ops.visual import date_line, paris_standing_start

_ROOT = repo_root()
_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "paris-standing-start.json"
_FIXTURE: list[dict[str, Any]] = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _FIXTURE, ids=lambda c: c["iso_date"])
def test_python_matches_the_shared_fixture(case: dict[str, Any]) -> None:
    talk_date = date.fromisoformat(case["iso_date"])
    assert paris_standing_start(talk_date) == (case["offset"], case["abbreviation"])
    assert date_line(talk_date) == case["date_line"]


def test_the_fixture_covers_both_sides_of_both_dst_boundaries() -> None:
    """An empty, one-sided or single-year fixture would make the
    parametrized test above pass for the wrong reason."""
    abbreviations = {c["abbreviation"] for c in _FIXTURE}
    assert abbreviations == {"CET", "CEST"}
    years = {c["iso_date"][:4] for c in _FIXTURE}
    assert len(years) >= 2, "the fixture should span more than one year"
    assert len(_FIXTURE) == 8, (
        "expected one date on each side of both DST transitions, in two "
        "different years (2 sides x 2 transitions x 2 years)"
    )


def test_eleventy_js_matches_the_shared_fixture() -> None:
    """`site/.eleventy.js::parisStandingStart` is the third implementation
    -- checked here, not in a JS test runner, because `site/` carries none
    (`tools/tests/test_site.py`'s own module docstring: this suite is this
    project's only quality gate on `.eleventy.js`). `check-paris-standing-
    start.cjs` is a plain, dependency-free Node script that reads the
    identical fixture file and requires the real, committed `.eleventy.js`
    directly -- no build, no network, no new dependency."""
    script = _ROOT / "site" / "scripts" / "check-paris-standing-start.cjs"
    result = subprocess.run(
        ["node", str(script)],
        cwd=_ROOT / "site",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
