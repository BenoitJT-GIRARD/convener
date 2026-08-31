"""Pins `.github/workflows/visuals.yml`,
`tools/visuals/render-and-compare.mjs` and `tools/visuals/package.json` against the
properties a green run does not, by itself, prove -- the same idiom
`test_a11y_workflow.py` already uses for the accessibility checker.

Read as text and (for the properties a plain substring check would trip
over its own explanatory comments for -- the path filter's contents, a
step's own `if:`) parsed as YAML/JSON instead. Never executed: running
this for real needs a real browser download and a real GitHub Actions
runner, exactly the network access this suite must not take on. Every
`run:` step in the workflow has been executed directly by hand against the
real committed lockfile and reference images, and the mutation proved the
same way (an element moved a few pixels, the check turning red, then green
again on revert).
"""

from __future__ import annotations

import json
import re

import yaml
from conftest import workflow_triggers

from convener_ops.declaration.paths import repo_root

_ROOT = repo_root()
_WORKFLOW = (_ROOT / ".github" / "workflows" / "visuals.yml").read_text(
    encoding="utf-8"
)
_SCRIPT = (_ROOT / "tools" / "visuals" / "render-and-compare.mjs").read_text(
    encoding="utf-8"
)
_PACKAGE_JSON = json.loads(
    (_ROOT / "tools" / "visuals" / "package.json").read_text(encoding="utf-8")
)
#: Parsed structurally where a plain substring check would also match this
#: file's own explanatory comments (which quite deliberately *do* mention
#: `speakers.yml`, `--update` and `file://` -- to say why the workflow
#: never uses them). The `on:` block is reached through
#: `conftest.workflow_triggers`, which owns the reason it cannot simply be
#: looked up as `"on"`.
_WORKFLOW_DATA = yaml.safe_load(_WORKFLOW)
_TRIGGERS = workflow_triggers(_WORKFLOW_DATA)


def test_puppeteer_is_pinned_to_an_exact_version_not_a_range() -> None:
    """A full puppeteer, at a fixed version -- a caret or tilde range
    would let a future `npm install` silently resolve a newer Chromium
    build, exactly the drift pinning the engine exists to rule out."""
    version = _PACKAGE_JSON["devDependencies"]["puppeteer"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"puppeteer is pinned as {version!r} -- expected an exact "
        "MAJOR.MINOR.PATCH with no ^/~ range operator"
    )


def test_no_other_dependency_was_added_to_render_or_compare() -> None:
    """The image comparison decodes both PNGs through the pinned browser's
    own <canvas>/getImageData (see render-and-compare.mjs's own module
    comment) specifically so no image-diffing library (pixelmatch, pngjs,
    ...) had to be added on top of puppeteer itself."""
    assert list(_PACKAGE_JSON["devDependencies"]) == ["puppeteer"]


def test_puppeteer_core_still_lives_only_with_the_accessibility_checker() -> None:
    """The other half: `puppeteer-core` (no bundled browser) stays with
    the a11y checker; the full `puppeteer` package added here must not
    also creep into `site/package.json`, which would make every one of
    that package's five other workflows pay the Chrome-for-Testing
    download too."""
    site_package = json.loads(
        (_ROOT / "site" / "package.json").read_text(encoding="utf-8")
    )
    assert "puppeteer" not in site_package.get("dependencies", {})
    assert "puppeteer" not in site_package.get("devDependencies", {})
    assert "puppeteer-core" in site_package["devDependencies"]


def test_workflow_is_path_filtered_on_both_triggers() -> None:
    """D-25/the budget note: a plain `on: push` would pay the Chrome
    download (or at best a cache restore) on every push to any part of
    this repository, for a check that cannot possibly have anything to
    say about most of them. Both `push` and `pull_request` must filter,
    not just one -- a PR run is exactly where this check matters most.

    This file used to bind the two lists with a YAML anchor
    and alias (`&visual_paths`/`*visual_paths`); GitHub Actions' own
    workflow parser does not support either (a documented limitation, not
    a version question), so both are now hand-written copies instead. This
    assertion, via the parsed document, only shows the two happen to
    resolve to equal lists today -- exactly what an unnoticed anchor would
    also show, since PyYAML expands one without complaint. The guarantee
    that actually catches drift (or a reintroduced anchor) is
    `test_the_two_path_filters_are_identical_lists`, below, which reads the
    raw file text instead."""
    assert _TRIGGERS["push"]["branches"] == ["main"]
    assert _TRIGGERS["push"]["paths"], "push trigger carries no path filter"
    assert _TRIGGERS["pull_request"]["paths"] == _TRIGGERS["push"]["paths"]


#: A literal `- '...'` sequence item, the shape every path filter entry in
#: this file takes. Matched line by line so an alias line (`paths:
#: *visual_paths`, carrying no `- '...'` items of its own) yields an empty
#: list rather than silently reusing the other trigger's items -- which is
#: exactly the failure mode this test exists to catch if this file is ever
#: "simplified" back into an anchor.
_PATH_ITEM_RE = re.compile(r"^\s*-\s*'([^']+)'\s*$", re.MULTILINE)


def _paths_block(text: str, start_marker: str, end_marker: str) -> list[str]:
    """The `- '...'` items between two markers in the *raw* workflow text.

    Read this way, not through `yaml.safe_load`: a YAML anchor/alias
    resolves into an identical list either way, which would hide the one
    thing this test exists to catch (see its own docstring). `end_marker`
    is searched for strictly after `start_marker`, so two calls can each be
    pointed at their own slice of the file.
    """
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return _PATH_ITEM_RE.findall(text[start:end])


def test_the_two_path_filters_are_identical_lists() -> None:
    """GitHub Actions' own workflow parser does not support
    YAML anchors (`&name`) or aliases (`*name`) -- a long-standing,
    documented limitation of that parser, not a version question. This
    file used to bind `push.paths` and `pull_request.paths` with exactly
    that (`&visual_paths`/`*visual_paths`); PyYAML expands them without
    complaint, which is exactly why the earlier version parsed clean in
    every check this suite already ran and would still have failed to
    *trigger* on the very first real push -- no workflow in this
    repository has ever executed, which is confirmed rather than assumed.

    The fix is two hand-written copies, each carrying a comment naming
    this parser limitation so a future edit is not tempted to "simplify"
    it back into an anchor. This test is what holds the two copies
    together instead of that comment alone: read from the raw file text,
    never through `yaml.safe_load` (used everywhere else in this module),
    because a resolved anchor/alias would compare as "equal" precisely
    when it should not -- see `_paths_block`'s own docstring.
    """
    push_paths = _paths_block(_WORKFLOW, "push:", "pull_request:")
    pull_request_paths = _paths_block(_WORKFLOW, "pull_request:", "\njobs:")
    assert push_paths, (
        "no `- '...'` path items found under push: -- the markers this "
        "test slices the file on may have moved"
    )
    assert pull_request_paths == push_paths, (
        "push.paths and pull_request.paths have drifted apart: push has "
        f"{push_paths!r}, pull_request has {pull_request_paths!r}"
    )


def test_the_path_filter_names_every_module_the_composition_reads() -> None:
    """Each of these is named, with its own reasoning, in the workflow's
    own comment -- this only pins that none of them was quietly dropped
    later. Deliberately over-inclusive rather than under: `tools/convener_ops/
    cli.py` re-runs this job for plenty of unrelated commands too, kept
    anyway because a path filter has no finer grain than a file."""
    expected_paths = {
        "tools/convener_ops/publication/visual.py",
        "tools/convener_ops/publication/motifs/**",
        "tools/convener_ops/publication/registration_code.py",
        "tools/convener_ops/publication/formats.py",
        "tools/convener_ops/governance/rule.py",
        "tools/convener_ops/cli.py",
        "instances/example/instance/config.json",
        "tools/convener_ops/declaration/published.py",
        "tools/convener_ops/journey/registration.py",
        "instances/example/instance/data/brand.json",
        "tools/convener_ops/publication/brand.py",
        "fonts/**",
        "tools/uv.lock",
        "tools/visuals/**",
        ".github/workflows/visuals.yml",
    }
    for path in expected_paths:
        assert f"'{path}'" in _WORKFLOW, f"{path} is missing from the path filter"


def test_the_path_filter_never_reacts_to_real_speaker_data() -> None:
    """This job renders one fixed, fictional fixture (Ada Lovelace, no
    photograph) -- never `instance/data/speakers.yml` or any real edition -- so a
    change to real speaker data has nothing for it to check, and must not
    trigger a run that would only ever be a no-op.

    Checked against the *parsed* path list, not a whole-file substring --
    this file's own comment names `instance/data/speakers.yml` deliberately, to say
    why it is absent, and a bare `in` check would trip over its own
    explanation."""
    assert not any("speakers.yml" in path for path in _TRIGGERS["push"]["paths"])


def test_the_path_filter_never_reacts_to_this_instances_own_charter() -> None:
    """The fixture is rendered from `instances/example/`,
    so this instance's own declaration and charter change nothing this job
    could compare -- and naming them would do worse than waste a run. It
    is what made this check go red for a duplicate that had done nothing
    but choose its own colours: the job rendered them and diffed them
    against a committed image of somebody else's poster.

    Checked against the *parsed* path list rather than a substring, for
    the reason the test above gives: the two entries that are here name
    the same two files under `instances/example/`, and a bare `in` check
    would match those and pass for the wrong reason. `visuals-production.
    yml` carries the real pair and must -- that job renders real editions,
    as this instance (`test_visuals_production_workflow.py`)."""
    paths = _TRIGGERS["push"]["paths"]
    assert "instance/config.json" not in paths
    assert "instance/data/brand.json" not in paths
    assert "instances/example/instance/config.json" in paths
    assert "instances/example/instance/data/brand.json" in paths


def test_the_path_filter_never_reacts_to_the_consent_gate_either() -> None:
    """`tools/convener_ops/publication/public_data.py` (the
    module `instance/data/speakers.yml` is read *through*, the consent gate
    included) is deliberately absent here for the identical reason the
    test above gives for `instance/data/speakers.yml` itself --
    `render_visual_fixtures` renders `FIXTURE_ANNOUNCEMENT`, a fixed,
    hand-built identity that never goes through `public_data.to_public` at
    all, so a change to the gate's own logic has nothing for this fixture
    to see. `visuals-production.yml` is where that module belongs, and
    does carry it (`test_visuals_production_workflow.py::
    test_public_data_py_is_in_the_filter_the_consent_gate_needs`)."""
    assert (
        "tools/convener_ops/publication/public_data.py"
        not in _TRIGGERS["push"]["paths"]
    )


def test_job_permissions_are_read_only() -> None:
    assert "permissions:\n      contents: read" in _WORKFLOW


def test_node_version_meets_puppeteers_own_floor() -> None:
    """puppeteer 25.8.0 declares `engines.node: >=22.12.0`. This workflow
    was the first here to clear that floor while every other one still
    installed Node 20; they all install 22 now, and
    `test_workflows.py::test_every_workflow_installs_the_same_node_version`
    is what keeps this one from drifting away from them again. Kept beside
    that sweep rather than folded into it: the sweep says the workflows
    agree with each other, and this says what they agree on has to clear
    the floor this package's own dependency declares."""
    assert "node-version: '22'" in _WORKFLOW


def test_npm_ci_installs_from_the_visuals_lockfile() -> None:
    assert "working-directory: tools/visuals" in _WORKFLOW
    assert "run: npm ci" in _WORKFLOW


def test_a_dependency_audit_step_exists_for_the_new_lockfile() -> None:
    """Every surface with a lockfile
    gets an audit in this same quality chain -- this is a new lockfile,
    so it does not become the one surface that escapes it."""
    assert "Dependency audit" in _WORKFLOW
    assert "run: npm audit" in _WORKFLOW


def test_the_chrome_download_is_cached_by_the_lockfile_hash() -> None:
    """Without this, every run -- even one a path filter judged worth
    running -- re-fetches the ~430MB Chrome-for-Testing build the
    postinstall step downloads. Keyed on the
    lockfile so a puppeteer version bump changes the key and fetches the
    new build exactly once, rather than serving a stale cached browser
    forever."""
    assert "~/.cache/puppeteer" in _WORKFLOW
    assert "hashFiles('tools/visuals/package-lock.json')" in _WORKFLOW


def _run_strings() -> list[str]:
    """Every `run:` step's own shell script, across every job -- what
    actually executes, as opposed to this file's prose comments (which
    quite deliberately *do* mention `--update`, to say why CI never passes
    it)."""
    return [
        step["run"]
        for job in _WORKFLOW_DATA["jobs"].values()
        for step in job["steps"]
        if "run" in step
    ]


def test_the_render_step_never_passes_update() -> None:
    """`--update` overwrites a committed reference with whatever just
    rendered -- exactly the "regenerate on every failure" reflex pinning
    the engine exists to close off. Only a human, running `npm run update-references`
    by hand after reviewing the result, may ever produce that flag; CI
    must never pass it."""
    assert not any("--update" in run for run in _run_strings())


def test_a_failing_comparison_uploads_the_rendered_images() -> None:
    steps = _WORKFLOW_DATA["jobs"]["visuals"]["steps"]
    upload_step = next(
        step
        for step in steps
        if step.get("name") == "Upload the rendered images for inspection"
    )
    assert upload_step["if"] == "failure()"
    assert "actions/upload-artifact@" in upload_step["uses"]
    assert "visual-actual" in upload_step["with"]["path"]


def test_per_pixel_threshold_is_a_named_justified_constant() -> None:
    """ "A threshold, stated and justified" -- this pins that the constant
    exists, is a single number (not a magic literal repeated inline), and
    carries a comment naming what it tolerates (anti-aliasing) and why
    that is safe (measured against a real re-render, and against the real
    gap between any two colours this composition paints)."""
    assert "const PER_CHANNEL_THRESHOLD = 24;" in _SCRIPT
    assert "const MAX_DIFF_PIXEL_FRACTION = 0.001;" in _SCRIPT
    comment = _SCRIPT.split("const PER_CHANNEL_THRESHOLD")[0][-2000:]
    assert "anti-aliasing" in comment.lower()
    assert "empirically" in comment.lower() or "confirmed" in comment.lower()


def test_the_comparison_decodes_pngs_through_the_pinned_browser_itself() -> None:
    """No image-diffing dependency was added: both PNGs are decoded with
    the browser's own <canvas>/getImageData, inside `page.evaluate`, using
    the same pinned Chromium already launched to render them."""
    assert "getImageData" in _SCRIPT
    assert "page.evaluate(" in _SCRIPT
    assert "new Image()" in _SCRIPT


def test_a_regression_reports_what_differs_and_where() -> None:
    """A regression has to fail loudly, naming what differs and where:
    this pins that a failing comparison names the format, the
    fraction of differing pixels, the worst channel delta and a bounding
    box, not merely "images differ"."""
    assert "diffCount" in _SCRIPT
    assert "boundingBox" in _SCRIPT
    assert "::error::" in _SCRIPT
    assert "Worst single-channel delta" in _SCRIPT


def test_a_missing_reference_fails_rather_than_creating_one() -> None:
    """D-25: a check that silently supplies its own missing baseline can
    never fail on a first run against a new format -- this pins that a
    missing reference is reported as an error, never auto-written, when
    `--update` was not explicitly passed."""
    assert "missingReference" in _SCRIPT
    body = _SCRIPT.split("if (result.missingReference)")[1].split("continue;")[0]
    assert "failed = true" in body


def test_a_dimension_mismatch_fails_rather_than_being_silently_compared() -> None:
    assert "dimensionMismatch" in _SCRIPT
    body = _SCRIPT.split("if (result.dimensionMismatch)")[1].split("continue;")[0]
    assert "failed = true" in body


def test_the_renderer_waits_for_self_hosted_fonts_before_screenshotting() -> None:
    """A screenshot taken before the self-hosted webfont finished loading
    could capture a system fallback face on a slow run and the real one on
    a fast one -- exactly the run-to-run instability this comparison must
    not have before a single design change is even in question."""
    assert "document.fonts.ready" in _SCRIPT


def test_the_server_is_never_file_url() -> None:
    """A relative `@font-face url(...)` cannot load from a bare `file://`
    origin without a flag this project has no reason to carry -- every
    render of this composition already used a local HTTP server for exactly
    this reason. Checked against the actual
    `goto` call, not a blanket ban on the substring `file://` anywhere in
    the file -- this module's own comment names it deliberately, to say
    why it is never used."""
    assert "createServer" in _SCRIPT
    assert "const baseUrl = `http://127.0.0.1:${port}/`;" in _SCRIPT
    assert "await page.goto(`${baseUrl}${entry.file}`" in _SCRIPT
