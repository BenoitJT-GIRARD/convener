"""What a second-instance build runs before the bundler.

`app/package.json`'s own `prebuild` copies seven things into `app/public/`
before Vite is asked for anything -- the fonts, the handbook, the published
event keys, the signing keys, the certificate register, the survey status,
and the product's mark as `public/favicon.svg`. A second-instance build has
to run the same seven, and it used to run six: `copy-mark.mjs` was missing
from a list somebody had typed out beside the real one.

Nothing caught it, and two things went wrong at once. The demonstration --
hosted since the showcase started publishing one -- served a cockpit with no
icon file in it at all; and Vite, finding no `public/favicon.svg` to resolve
`index.html`'s own `/favicon.svg` against, left that reference exactly as
written. A root-relative reference under a project's GitHub Pages address
points above the published tree, which is the defect D-26 exists to catch,
and no sweep of this repository reads the cockpit's own document for it.

So the list is derived now, and this is what holds the derivation: the
scripts the build runs are the scripts `app/package.json` names, in its
order, and a `prebuild` shaped in a way the reader does not understand stops
the build rather than being partly run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import second_instance_build

from convener_ops.declaration.paths import repo_root


def _prebuild_line(root: Path) -> str:
    manifest = json.loads((root / "app" / "package.json").read_text(encoding="utf-8"))
    return str(manifest["scripts"]["prebuild"])


def test_it_runs_every_script_the_application_s_own_prebuild_runs() -> None:
    """The whole claim, against the real `app/package.json`."""
    root = repo_root()
    named = [
        step.strip().split("/")[-1]
        for step in _prebuild_line(root).split("&&")
        if step.strip()
    ]
    assert named, "app/package.json declares no prebuild step"
    assert second_instance_build.prebuild_scripts(root) == named


def test_the_mark_is_one_of_them() -> None:
    """The one that was missing, by name.

    Pinned rather than left to the equality above: that assertion would go
    on passing if both sides lost the same script, which is the shape the
    defect had.
    """
    assert "copy-mark.mjs" in second_instance_build.prebuild_scripts(repo_root())


def test_every_named_script_exists() -> None:
    """A name that resolves to nothing is a step this build would run and
    fail on, at the far end of a long build."""
    root = repo_root()
    for script in second_instance_build.prebuild_scripts(root):
        assert (root / "app" / "scripts" / script).is_file(), script


def _repository(tmp_path: Path, prebuild: str) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "package.json").write_text(
        json.dumps({"scripts": {"prebuild": prebuild}}), encoding="utf-8"
    )
    return tmp_path


def test_a_prebuild_step_it_cannot_run_stops_the_build(tmp_path: Path) -> None:
    """Refuses rather than running the part it understood."""
    root = _repository(tmp_path, "node scripts/copy-fonts.mjs && npm run something")
    with pytest.raises(SystemExit) as refusal:
        second_instance_build.prebuild_scripts(root)
    assert "npm run something" in str(refusal.value)
    assert "may not quietly skip it" in str(refusal.value)


def test_no_prebuild_at_all_stops_the_build(tmp_path: Path) -> None:
    """An empty declaration is not an empty list of steps: it is a
    `package.json` this build no longer recognises."""
    root = _repository(tmp_path, "")
    with pytest.raises(SystemExit) as refusal:
        second_instance_build.prebuild_scripts(root)
    assert "no prebuild step" in str(refusal.value)
