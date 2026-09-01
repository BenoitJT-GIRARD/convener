"""`templates.yml` renders the three downloadable files for every charter
this repository holds crossed with every motif family it draws, and
measures whether any stroke crosses any word.

Mirrors `test_visuals_workflow.py`'s own idiom throughout, including
reading the raw file text for the one property that actually matters -- a
real YAML anchor resolves identically once parsed, which is exactly what
would hide a reintroduced one from a check comparing parsed lists.

The one thing worth reading these two modules side by side for is the pair
of filters. `visuals.yml` must *not* react to this instance's own charter
(it renders the example's, and a duplicate that had only chosen its own
colours went red against images of somebody else's poster); this workflow
must, because it renders every charter and a stroke weight nobody has
drawn before is how a word ends up behind a drawing. The two tests that
say so are `test_the_path_filter_never_reacts_to_this_instances_own_
charter` there and `test_the_path_filter_reacts_to_every_charter_swept`
here.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from typing import Final

import yaml
from conftest import workflow_triggers

from convener_ops.cli.publication import _template_charters
from convener_ops.declaration.paths import repo_root

_ROOT: Final = repo_root()
_PATH: Final = _ROOT / ".github" / "workflows" / "templates.yml"
_WORKFLOW: Final = _PATH.read_text(encoding="utf-8")
_TRIGGERS: Final = workflow_triggers(yaml.safe_load(_WORKFLOW))

_PATH_ITEM_RE: Final = re.compile(r"^\s*-\s*'([^']+)'\s*$", re.MULTILINE)


def _paths_block(start_marker: str, end_marker: str) -> list[str]:
    """The `- '...'` items between two markers in the *raw* workflow text."""
    start = _WORKFLOW.index(start_marker) + len(start_marker)
    end = _WORKFLOW.index(end_marker, start)
    return _PATH_ITEM_RE.findall(_WORKFLOW[start:end])


def test_workflow_is_path_filtered_on_both_triggers() -> None:
    """A job that downloads a browser must not run on every push."""
    for trigger in ("push", "pull_request"):
        assert _TRIGGERS[trigger].get("paths"), (
            f"templates.yml's {trigger} trigger carries no path filter"
        )


def test_the_two_path_filters_are_identical_lists() -> None:
    """GitHub Actions' own parser cannot resolve a YAML anchor, so the two
    copies are written out by hand and bound here instead."""
    push = _paths_block("  push:", "  pull_request:")
    pull = _paths_block("  pull_request:", "concurrency:")
    assert push == pull


def test_no_anchor_binds_the_two_copies() -> None:
    """The failure this repository has already had once: an anchored
    filter parses clean in every local check and fails to *trigger* the
    first time it runs for real."""
    assert "&" not in _WORKFLOW.replace("&&", "")
    assert not re.search(r"^\s*-?\s*\*[a-z_]+\s*$", _WORKFLOW, re.MULTILINE)


def test_the_path_filter_names_every_module_the_three_templates_read() -> None:
    """Each is named, with its own reasoning, in the workflow's own
    comment; this pins that none was quietly dropped later."""
    expected = {
        "tools/convener_ops/publication/brand_templates.py",
        "tools/convener_ops/publication/typeface.py",
        "tools/convener_ops/publication/motifs/**",
        "tools/convener_ops/publication/brand.py",
        "tools/convener_ops/publication/lockup.py",
        "tools/convener_ops/publication/visual.py",
        "tools/convener_ops/publication/composition.py",
        "tools/convener_ops/publication/formats.py",
        "tools/convener_ops/publication/registration_code.py",
        "tools/convener_ops/declaration/published.py",
        "tools/convener_ops/journey/registration.py",
        "tools/convener_ops/cli/publication.py",
        "assets/fonts/**",
        "tools/uv.lock",
        "tools/visuals/**",
        ".github/workflows/templates.yml",
    }
    assert expected <= set(_TRIGGERS["push"]["paths"])


def test_the_path_filter_reacts_to_every_charter_swept() -> None:
    """Every charter the job actually renders, this instance's own among
    them -- the opposite of `visuals.yml`, and for the opposite reason:
    this job renders every charter in the repository, so a duplicate
    editing its own `motif` is exactly the change it exists to measure.

    Read off `cli._template_charters` rather than listed here, because
    that function reads `assets/brand/` rather than a list of its own: a charter
    committed there is swept on the commit that adds it, and this is what
    says the filter noticed. `fnmatch` because the filter's own entry for
    those is a glob, for the same reason.
    """
    paths = set(_TRIGGERS["push"]["paths"])
    assert "instance/config.json" in paths
    assert "examples/the-example-collective/instance/config.json" in paths

    swept = {
        charter.as_posix() for _label, charter, _declared in _template_charters(_ROOT)
    }
    assert len(swept) >= 4, (
        f"the sweep renders {sorted(swept)}, which is fewer charters than "
        "this repository holds -- a filter checked against an empty sweep "
        "would pass for free"
    )
    for charter in sorted(swept):
        assert any(fnmatch(charter, pattern) for pattern in paths), (
            f"{charter} is rendered by this job and no entry in the path "
            "filter names it, so a change to it runs nothing"
        )


def test_the_path_filter_never_reacts_to_real_speaker_data() -> None:
    """These three files carry `{{speaker.*}}` placeholders rather than an
    edition -- that is what makes them templates -- so no real speaker
    record and no consent gate has anything for this job to see."""
    paths = _TRIGGERS["push"]["paths"]
    assert not any("speakers.yml" in path for path in paths)
    assert "tools/convener_ops/publication/public_data.py" not in paths


def test_job_permissions_are_read_only() -> None:
    assert "permissions:\n      contents: read" in _WORKFLOW


def test_the_fixtures_are_rendered_before_the_browser_is_installed() -> None:
    """The Python half writes bytes and the Node half reads them, which is
    the boundary D-14 asks for -- and it means a broken render fails
    before a 430MB download rather than after it. Both sets of fixtures,
    because both halves cost the same download."""
    install = _WORKFLOW.index("npm ci")
    for command in (
        "convener-render-template-fixtures",
        "convener-render-poster-fixtures",
    ):
        assert _WORKFLOW.index(command) < install


def test_the_poster_sweep_runs_here_and_over_the_same_cross_product() -> None:
    """The composition nobody downloads and every duplicate publishes.

    It belongs in this workflow rather than in `visuals.yml` for the
    reason the two filters already differ over: that one renders the
    example's charter and must not react to a duplicate's own, and this
    one renders every charter and must. The poster is the third
    composition drawn from a charter, and it was the one nothing swept.
    """
    assert "convener-render-poster-fixtures" in _WORKFLOW
    assert "check-posters.mjs" in _WORKFLOW
    assert (_ROOT / "tools" / "visuals" / "check-posters.mjs").is_file()
    # The same cross product the templates are swept over: the checker
    # reads the manifest, and the manifest is what the command writes.
    assert "convener_ops.cli:render_poster_fixtures" in (
        _ROOT / "tools" / "pyproject.toml"
    ).read_text(encoding="utf-8")


def test_the_chrome_download_shares_the_key_visuals_uses() -> None:
    """Two jobs, one Chrome-for-Testing download: whichever runs first
    pays for it. A key of its own would double the cost of a private
    repository's metered minutes for nothing."""
    visuals = (_ROOT / ".github" / "workflows" / "visuals.yml").read_text(
        encoding="utf-8"
    )
    key = (
        "key: puppeteer-${{ runner.os }}-"
        "${{ hashFiles('tools/visuals/package-lock.json') }}"
    )
    assert key in _WORKFLOW
    assert key in visuals


def test_a_failing_measurement_uploads_the_numbers() -> None:
    """The offending block is already in the log; this is for somebody who
    wants every block's clearance rather than only the ones that failed."""
    assert "if: failure()" in _WORKFLOW
    assert "template-clearance" in _WORKFLOW
