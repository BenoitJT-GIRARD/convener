"""The numbers the handbook states, against the files they are configuration in.

A page that states a number the code also holds is a copy, and this repository
has paid for that four times: the schema appendix drifted twice, the
preparation countdown drifted six windows out of date, and both did it
*underneath a sentence claiming they could not*. A marker is not a control.

`docs/workflow/4-after.md` carried the same shape. It typed the view-counting
window as prose and then said "the handbook and the form cannot end up
claiming different windows" - but only the form's label is derived
(`viewCountLabel`, `app/src/state/phases.ts`); nothing read the page. Setting
`view_count_window_days: 60` left the form saying 60 and the page saying 30,
under the sentence saying that could not happen.

This module is the control the sentence names. It is on the Python side
because the number is `data/config.yml`'s, which is the series' own file
rather than a test double: the app suite deliberately reads doubles so that a
Board edit cannot turn a screen test red, and this claim is precisely a claim
about what the Board has set.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from convener_ops.paths import repo_root
from convener_ops.yaml_safe import safe_load

ROOT = repo_root()
PAGE = Path("docs/workflow/4-after.md")

#: The sentence the page states the window in. Written as a pattern rather
#: than searched for loosely: `contains("30")` would pass on any page that
#: mentions T-30, which is a different number about a different thing.
_WINDOW = re.compile(r"reads them \*\*(\d+) days after the talk\*\*")


def _config() -> dict[str, Any]:
    loaded = safe_load((ROOT / "data" / "config.yml").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_page_states_the_window_the_configuration_sets() -> None:
    page = (ROOT / PAGE).read_text(encoding="utf-8")
    stated = _WINDOW.search(page)
    assert stated is not None, (
        f"{PAGE.as_posix()} no longer states the view-counting window in the "
        "form this test reads; the page and data/config.yml can drift again."
    )
    assert int(stated.group(1)) == _config()["view_count_window_days"]
