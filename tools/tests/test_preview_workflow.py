"""Task 13 (phase 5): pins `.github/workflows/preview.yml` against the
properties a green run does not, by itself, prove -- spec S:7's "a preview
mode on a pull request" only means something if a reviewer can trust what
the run uploaded, and if the workflow degrades the same way for a fork PR
as for a same-repo one.

Four things a passing job could still be wrong about, each with its own
test below (the identical shape `test_a11y_workflow.py`'s and
`test_performance_workflow.py`'s own module docstrings already name for
their own checkers):

* it could quietly need a secret a fork PR can never provide (D-13) --
  pinned by asserting no `secrets.` reference exists anywhere in the file;
* it could upload an empty or broken build and call that a preview --
  D-25's own "a control that cannot fail loudly is not a control", applied
  here to three distinct emptiness failures: no site at all, a site with
  no islands (the "empty box" this task's own brief warns against), and a
  room link that reached a built page;
* it could assemble the preview at a bare `localhost` root rather than the
  path prefix GitHub Pages actually serves this project under (D-26) --
  the exact defect that cost phase 5 seven earlier screenshot rounds;
* it could read a stale, hand-typed copy of that prefix instead of the one
  place `config/instance.json` declares it.

Read as text and asserted against with `in`/regex checks and `safe_load`,
the same idiom every workflow-pinning module in this suite already uses --
never parsed and executed, which here would mean a real `npm ci` and a
real build, exactly the network access this suite must not take on.
Running the workflow's own steps for real -- extracted with `safe_load` and
executed byte-for-byte, including the four mutations that prove each guard
above actually fails the run -- is this task's own report, not this
module: see `.superpowers/sdd/2026-08-22-phase-5-vitrine-publique/
task-13-report.md`.
"""

from __future__ import annotations

import re
from typing import Any

from conftest import WorkflowYaml

from convener_ops.paths import repo_root
from convener_ops.yaml_safe import safe_load

_ROOT = repo_root()
_WORKFLOW_PATH = _ROOT / ".github" / "workflows" / "preview.yml"
_WORKFLOW_TEXT = _WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow() -> WorkflowYaml:
    loaded = safe_load(_WORKFLOW_TEXT)
    assert isinstance(loaded, dict)
    return loaded


def _job() -> dict[str, Any]:
    job = _workflow()["jobs"]["preview"]
    assert isinstance(job, dict)
    return job


def _step_names() -> list[str]:
    return [step.get("name", step.get("uses", "")) for step in _job()["steps"]]


def _step_run(name: str) -> str:
    for step in _job()["steps"]:
        if step.get("name") == name:
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(f"preview.yml has no step named {name!r}")


_ASSEMBLE_STEP = "Assemble the preview at its published address"
_NOT_A_SITE_STEP = "Refuse to package a preview that is not a site"
_LEAK_STEP = "Refuse to package a preview that leaks a room link"
_KEYGEN_STEP = "Generate throw-away event keys for the preview"


def test_the_workflow_triggers_only_on_pull_request() -> None:
    """Read as raw text, not through `safe_load`: PyYAML's YAML-1.1 bool
    resolver reads a bare `on:` key as the boolean `True`, not the string
    `"on"` -- the same gotcha `test_workflows.py::
    test_publish_vitrine_paths_trigger_includes_the_certificate_register`
    already documents and works around for the identical reason. S:7 asks
    for a preview *on a pull request*; this must never also fire on a push
    to `main` (that is `quality.yml`'s and `a11y.yml`'s own job), or every
    merge would spend a build assembling and uploading an artefact nobody
    asked for and nobody will ever download."""
    trigger = _WORKFLOW_TEXT.split("jobs:")[0]
    assert "pull_request:" in trigger
    assert "push:" not in trigger
    assert "branches:" not in trigger


def test_the_job_is_read_only_with_a_bounded_timeout() -> None:
    """This job only ever reads the checkout, builds, and uploads a build
    artefact -- it never commits or pushes, so `contents: read` is the
    correct, minimal scope, the same one `a11y.yml`'s and
    `match-attendance.yml`'s own upload-artifact-carrying job already use.
    A job-level `timeout-minutes` is asserted explicitly here (not only
    relying on `test_workflows.py::test_every_job_declares_a_timeout`'s
    own repository-wide sweep), because a hung `npm ci` or a stuck browser
    download this job never intends to trigger would otherwise run to
    GitHub's own six-hour default on every pull request push."""
    job = _job()
    assert job["permissions"] == {"contents": "read"}
    assert isinstance(job.get("timeout-minutes"), int)
    assert job["timeout-minutes"] <= 15


def test_the_workflow_reads_no_repository_secret() -> None:
    """D-13's own hard edge: a pull request opened from a fork is never
    handed a repository secret by GitHub, no matter what this file asks
    for in its own `permissions:` or `env:` blocks -- so a preview that
    depended on one would work for a same-repo PR and silently do
    something different for a fork one, exactly the asymmetry this task's
    own brief refuses. Asserted the strong way: no `secrets.` reference
    anywhere in the file, not merely "no secret named `VITRINE_DEPLOY_
    TOKEN`" (`test_a11y_workflow.py::
    test_the_workflow_never_pushes_or_writes_repository_state` checks only
    the latter, narrower property for its own file)."""
    assert "secrets." not in _WORKFLOW_TEXT


def test_the_workflow_never_writes_or_pushes_repository_state() -> None:
    """The same property `test_a11y_workflow.py`'s own analogous test
    pins for `a11y.yml`: this job only ever reads, builds, and uploads a
    build artefact. The throw-away event key pair it generates
    (`_KEYGEN_STEP`) must never reach a commit -- a *real* private half is
    exactly the secret `eventkeys.py`'s own module docstring says must
    never touch disk outside a job holding the matching secret, which
    this job never does."""
    for forbidden in ("git push", "git commit", "secrets.VITRINE_DEPLOY_TOKEN"):
        assert forbidden not in _WORKFLOW_TEXT


def test_the_workflow_builds_both_the_site_and_the_app() -> None:
    """D-26's own consequence for this task, the identical property
    `test_a11y_workflow.py::test_the_workflow_builds_both_the_site_and_
    the_app` pins for that checker: the two islands live in the app's
    build, never the site's, so a job that only ever built `site/` could
    not assemble a preview showing either one -- exactly the "empty box"
    failure this task's own brief warns against."""
    for working_directory in ("site", "app"):
        marker = f"working-directory: {working_directory}"
        assert marker in _WORKFLOW_TEXT, (
            f"preview.yml never runs a step in {working_directory}/"
        )
        section = _WORKFLOW_TEXT.split(marker, 1)[1][:200]
        assert "npm run build" in section or "npm ci" in section


def test_the_workflow_generates_event_keys_before_building_the_app() -> None:
    """Without a usable event key, `SignupForm.tsx` never reaches its
    `ready` state, so its real `<input>`/`<label>` markup would never
    appear in this preview at all -- only the "not available" fallback,
    which reads exactly like a production error (see this workflow's own
    header comment for why that is the wrong thing for a preview to
    show). The identical property `test_a11y_workflow.py::
    test_the_workflow_generates_event_keys_before_building_the_app`
    already pins for `a11y.yml`'s own copy of this recipe."""
    assert "eventkeys.generate()" in _WORKFLOW_TEXT
    names = _step_names()
    assert _KEYGEN_STEP in names
    assert "Build app" in names
    assert names.index(_KEYGEN_STEP) < names.index("Build app")


def test_the_site_build_never_regenerates_data_from_the_private_repository() -> None:
    """Unlike `publish-vitrine.yml`'s own "Refresh site data" step, this
    job must never run `uv run convener-public-data` (or an equivalent) to
    overwrite `site/src/_data/events.json` from `data/speakers.yml` --
    that data is private, a fork PR has no access to it, and this preview
    exists to reread a template or layout change against the committed
    fixture, not this week's real programme (see this workflow's own
    header comment, and `site/README.md`, for why the fixture is the
    right thing to build here)."""
    # Checked against the parsed steps, not the raw file text: this
    # workflow's own header comment legitimately *names*
    # "Refresh site data" in prose, contrasting itself with
    # `publish-vitrine.yml`'s own step of that name -- a raw text search
    # would trip on its own explanation.
    step_texts = [step.get("name", "") for step in _job()["steps"]]
    step_texts += [step["run"] for step in _job()["steps"] if "run" in step]
    joined = "\n".join(step_texts)
    for forbidden in ("convener-public-data", "Refresh site data", "data/speakers.yml"):
        assert forbidden not in joined


def test_the_path_prefix_is_derived_not_retyped() -> None:
    """D-26: a second, hand-typed prefix standing in for the one
    `config/instance.json` declares could silently drift from it the way
    the site's own templates once could. Phase 10 task 2 replaced this
    workflow's `grep -oP` over `.eleventy.js` -- which had become a scrape
    of a file that no longer holds the value -- with a `node -p` call into
    `site/scripts/published.cjs`, the very module the site's own build
    reads the declaration through. Asserted by the extraction's own text,
    not by re-deriving the value here, so a future edit to the extraction
    itself fails this test rather than silently assembling at the wrong
    address."""
    assemble = _step_run(_ASSEMBLE_STEP)
    assert "node -p" in assemble
    assert "published.cjs" in assemble
    # The extraction itself must never fall back to a hardcoded default
    # if the declaration stops being readable: `node -p` exits non-zero
    # and `set -e` is what stops the step.
    extraction_line = [line for line in assemble.splitlines() if "node -p" in line]
    assert extraction_line
    assert "publishedAddress().pathPrefix" in extraction_line[0]
    assert "set -e" in assemble


def test_a_missing_or_empty_path_prefix_refuses_to_assemble_a_guessed_address() -> None:
    """If `site/.eleventy.js` ever stopped defining `PATH_PREFIX` (or
    defined it as an empty string), the extraction above would produce an
    empty `$prefix`/`$segment` -- assembling a preview at a guessed
    address (or the domain root, exactly the mistake D-26 exists to rule
    out) rather than failing loudly (D-25)."""
    assemble = _step_run(_ASSEMBLE_STEP)
    assert 'if [ -z "$prefix" ]; then' in assemble
    assert 'if [ -z "$segment" ]; then' in assemble
    # A closing `fi` is found by the newline immediately before it, never
    # a bare `.split("fi", 1)` -- the word "PREFIX" itself contains the
    # substring "fi" (pre**fi**x), which a naive split matches long before
    # the real closing `fi`, the same isolation problem
    # `test_workflows.py::test_deploy_workflow_push_step_guards_on_
    # missing_token` already works around for an unrelated step.
    for marker in ('if [ -z "$prefix" ]; then', 'if [ -z "$segment" ]; then'):
        start = assemble.index(marker)
        end = assemble.find("\nfi", start)
        assert end != -1, f"no closing fi found for {marker!r}"
        block = assemble[start:end]
        assert "exit 1" in block, f"{marker!r}'s own guard does not exit 1"


def test_the_empty_site_guard_never_counts_the_app_subtree() -> None:
    """D-25, applied to a failure mode a bare file-count floor would miss
    entirely: a real app build merged on top of a site build that quietly
    wrote nothing (Eleventy exits 0 on "wrote 0 files" -- see this
    workflow's own header comment) would still leave plenty of files under
    the assembled tree, just none of them the site's own. `find` must
    exclude `$root/app/*` from the count it compares against the floor."""
    guard = _step_run(_NOT_A_SITE_STEP)
    assert 'find "$root" -type f -not -path "$root/app/*"' in guard
    assert "site_file_count" in guard
    floor_line = [
        line for line in guard.splitlines() if '"$site_file_count" -lt' in line
    ]
    assert floor_line, "no floor comparison found on site_file_count"


def test_the_empty_site_guard_checks_index_html_and_can_fail_the_run() -> None:
    """D-25: the guard must be able to actually stop the job, not merely
    print a warning -- the same shape `publish-vitrine.yml`'s own
    identical `index.html` check already uses (task 13's own recipe is
    deliberately the same guard, run one step earlier, before an artefact
    is ever produced rather than before a push)."""
    guard = _step_run(_NOT_A_SITE_STEP)
    check_at = guard.find('if [ ! -f "$root/index.html" ]')
    assert check_at != -1
    fi_at = guard.find("fi", check_at)
    assert fi_at != -1
    block = guard[check_at:fi_at]
    assert "exit 1" in block


def test_the_guard_checks_both_island_bundles_by_name_and_refuses_an_empty_one() -> (
    None
):
    """The exact failure this task's own brief names as worse than no
    preview at all: an "empty box where the form belongs". `[ ! -s ... ]`
    (not `-f` or `-e`) is required -- a bundle that exists but was
    truncated to zero bytes by a broken build must still trip this,
    which a mere existence check would not catch."""
    guard = _step_run(_NOT_A_SITE_STEP)
    for bundle in (
        "$root/app/islands/signup/signup.js",
        "$root/app/islands/verify/verify.js",
    ):
        assert bundle in guard, f"{bundle} is not named in the island guard"
    assert '[ ! -s "$bundle" ]' in guard
    loop_body = guard.split("for bundle in", 1)[1]
    assert "exit 1" in loop_body


def test_the_leak_guard_reads_the_fixture_never_the_private_speakers_file() -> None:
    """This job builds `site/` from its own committed fixture (see
    `test_the_site_build_never_regenerates_data_from_the_private_
    repository`, above), so the only place a room link could come from
    here is that same fixture's own `registration_link` field -- never
    `data/speakers.yml`'s `zoom_link`, which `publish-vitrine.yml`'s own
    analogous guard reads instead, and which this job has no access to
    build from in the first place."""
    leak_guard = _step_run(_LEAK_STEP)
    assert "site/src/_data/events.json" in leak_guard
    assert "registration_link" in leak_guard
    assert "data/speakers.yml" not in _WORKFLOW_TEXT
    assert "zoom_link" not in _WORKFLOW_TEXT


def test_the_leak_guard_sweeps_the_assembled_artefact_and_can_fail_the_run() -> None:
    """ "The same guard that sweeps the built site applies to anything you
    publish" (this task's own brief, verbatim): the sweep below must run
    against `preview` -- the exact directory the upload step below reads
    from -- not only `site/_site`, the intermediate build. And it must be
    able to fail the job, not merely log a hit (D-25)."""
    leak_guard = _step_run(_LEAK_STEP)
    assert 'grep -rlF -- "$link" preview' in leak_guard
    assert 'if [ "$leaked" -ne 0 ]; then' in leak_guard
    tail = leak_guard.split('if [ "$leaked" -ne 0 ]; then', 1)[1]
    assert "exit 1" in tail


def test_the_readme_documents_the_non_obvious_serving_step() -> None:
    """D-26: opening the assembled tree at its own root, or serving the
    nested prefix folder itself, breaks every internal link this
    build writes. Nothing about that is obvious from a downloaded zip, so
    the artefact must say so itself -- this asserts the instructions are
    actually written into `preview/README.txt` by the workflow, not left
    to tribal knowledge or a task report nobody reading the artefact will
    ever see."""
    assemble = _step_run(_ASSEMBLE_STEP)
    assert "cat > preview/README.txt <<EOF" in assemble
    readme_body = assemble.split("cat > preview/README.txt <<EOF", 1)[1]
    for expected in (
        "http://localhost:8080$prefix",
        "fixture data",
        "throw-away encryption key",
        "Registration is not open for this event yet.",
        "certificate register",
    ):
        assert expected in readme_body, f"README.txt heredoc is missing {expected!r}"


def test_the_steps_run_in_an_order_that_never_uploads_a_bad_build() -> None:
    """Both guards must run after the tree they check has been assembled,
    and both must run before the artefact is uploaded -- a guard that ran
    too early would check a tree that does not exist yet (and pass
    vacuously, or error for the wrong reason); one that ran after the
    upload would find the problem one step too late."""
    names = _step_names()
    upload_index = next(
        i
        for i, step in enumerate(_job()["steps"])
        if "uses" in step and "upload-artifact" in step["uses"]
    )
    assemble_index = names.index(_ASSEMBLE_STEP)
    not_a_site_index = names.index(_NOT_A_SITE_STEP)
    leak_index = names.index(_LEAK_STEP)
    assert assemble_index < not_a_site_index < upload_index
    assert assemble_index < leak_index < upload_index


def test_the_upload_step_targets_the_assembled_tree_and_refuses_an_empty_one() -> None:
    """`path:` must point at exactly what "Assemble the preview" built
    (`preview`, the directory both guards above check too) -- a drifted
    path would upload something the guards never swept. `if-no-files-
    found: error` is the belt-and-suspenders D-25 layer beside the two
    guards: if a future edit ever reordered a step so nothing survived
    into `preview/`, this stops the run instead of quietly shipping an
    empty artefact."""
    for step in _job()["steps"]:
        if "uses" in step and "upload-artifact" in step["uses"]:
            with_block = step["with"]
            assert with_block["path"] == "preview"
            assert with_block["if-no-files-found"] == "error"
            return
    raise AssertionError("preview.yml has no upload-artifact step")


# ------------------------------------------------------------------ #
# Every action pin reused here already carries a full commit SHA
# elsewhere in this project -- not a fresh pin trusted for the first
# time. This does not replace `test_workflows.py::
# test_every_action_reference_is_pinned_to_a_full_commit_sha` (which
# already sweeps this file too, generically); it pins the stronger
# property this task's own brief asks for: reusing an SHA another
# workflow already relies on is one less thing that has never executed
# in any form, versus a SHA nobody else in this project has ever used.
# ------------------------------------------------------------------ #

_USES_RE = re.compile(r"^\s*-\s*uses:\s*(\S+)@([0-9a-f]{40})\s*(#.*)?$", re.MULTILINE)


def test_every_pinned_action_sha_is_already_used_elsewhere_in_this_project() -> None:
    workflows_dir = _ROOT / ".github" / "workflows"
    other_texts = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(workflows_dir.glob("*.yml"))
        if path.name != "preview.yml"
    }
    pins = _USES_RE.findall(_WORKFLOW_TEXT)
    assert pins, "no uses: lines found in preview.yml -- the regex itself may be wrong"
    for action, sha, _comment in pins:
        reused = any(f"{action}@{sha}" in text for text in other_texts.values())
        assert reused, (
            f"{action}@{sha} in preview.yml is not used by any other workflow "
            "in this project -- confirm this SHA independently before adding "
            "a pin nothing else here has ever relied on"
        )
