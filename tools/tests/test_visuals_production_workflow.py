"""Pins `.github/workflows/visuals-production.yml` and
`tools/visuals/render-production.mjs` against the properties a green run does not,
by itself, prove -- the same idiom `test_visuals_workflow.py` already uses
for the regression workflow beside it.

Read as text and (for the path filter's own contents) parsed as YAML,
exactly as that module does, for the identical reason: this file's own
explanatory comments deliberately name `instance/data/speakers.yml`, `pull_request`
and `og:image` to say why each is absent or handled the way it is, and a
plain substring check would trip over its own prose. Never executed here:
running it for real needs a real browser download, exactly the network
access this suite must not take on. It was instead run by hand once
(`convener-render-visuals` and `render-production.mjs`, both executed for real
against a throwaway fixture repository, screenshots produced and
inspected), with two mutation proofs beside it (the path filter, and
the JS file-count guard).
"""

from __future__ import annotations

import yaml
from conftest import workflow_triggers

from convener_ops.declaration.paths import repo_root

_ROOT = repo_root()
_WORKFLOW_PATH = _ROOT / ".github" / "workflows" / "visuals-production.yml"
_WORKFLOW = _WORKFLOW_PATH.read_text(encoding="utf-8")
_SCRIPT = (_ROOT / "tools" / "visuals" / "render-production.mjs").read_text(
    encoding="utf-8"
)
_VISUALS_WORKFLOW = (_ROOT / ".github" / "workflows" / "visuals.yml").read_text(
    encoding="utf-8"
)
#: The `on:` block is reached through `conftest.workflow_triggers`, which
#: owns the reason it cannot simply be looked up as `"on"`.
_WORKFLOW_DATA = yaml.safe_load(_WORKFLOW)
_TRIGGERS = workflow_triggers(_WORKFLOW_DATA)
_JOB = _WORKFLOW_DATA["jobs"]["visuals-production"]


def test_the_workflow_has_exactly_one_path_list_no_anchor_needed() -> None:
    """Unlike visuals.yml, this workflow carries no `pull_request` trigger
    (see the module docstring / the workflow's own comment for why), so
    there is only ever one `paths:` list here -- nothing to bind with an
    anchor in the first place, and so nothing for the anchor/alias trap
    that caught visuals.yml's first version to catch here too. This test
    only pins that the single list is non-empty and parses as expected;
    `test_workflows.py::test_no_workflow_uses_a_yaml_anchor_or_alias`
    already sweeps every workflow file, this one included, for the
    anchor/alias itself."""
    assert _TRIGGERS["push"]["branches"] == ["main"]
    paths = _TRIGGERS["push"]["paths"]
    assert paths, "push trigger carries no path filter"
    assert "workflow_dispatch" in _TRIGGERS


def test_the_workflow_has_no_pull_request_trigger() -> None:
    """This job downloads a ~430MB pinned Chromium and uploads a real
    artefact -- worth paying for on `main`, not on every push to a review
    branch (see the workflow's own comment). Unlike visuals.yml's cheap
    regression check, a `pull_request` trigger here would be a real,
    recurring Actions-minutes cost on a private repository (D-15) for a
    job whose whole point is to publish something, not merely check it."""
    assert "pull_request" not in _TRIGGERS


def test_data_speakers_yml_is_the_one_new_path_this_job_adds() -> None:
    """The one deliberate difference from visuals.yml's own list: that
    workflow names `instance/data/speakers.yml` only to say why it is absent (it
    never touches real data); this workflow exists *because* real data can
    change, so the file real editions live in must be in its own filter."""
    paths = _TRIGGERS["push"]["paths"]
    assert "instance/data/speakers.yml" in paths


#: The *code* both jobs render through. A change to any of these changes
#: what a real edition looks like and what visuals.yml's fixture looks
#: like, so neither filter may drop one without the other.
#:
#: The declaration and the charter are deliberately not here. They used to
#: be: both jobs rendered this instance's, so both had to
#: watch the same two files. visuals.yml renders `instances/example/`'s
#: now, so the two jobs watch *different* declarations and *different*
#: charters, and `test_the_two_jobs_watch_their_own_instances_files` below
#: pins that difference rather than letting it read as a drop.
_SHARED_COMPOSITION_PATHS = {
    "tools/convener_ops/visual.py",
    "tools/convener_ops/ribbon.py",
    "tools/convener_ops/registration_code.py",
    "tools/convener_ops/journey/registration.py",
    "tools/convener_ops/formats.py",
    "tools/convener_ops/governance/governance.py",
    "tools/convener_ops/cli.py",
    "tools/convener_ops/declaration/published.py",
    "tools/convener_ops/brand.py",
    "fonts/**",
    "tools/uv.lock",
    "tools/visuals/**",
}


def test_every_composition_module_visuals_yml_names_is_named_here_too() -> None:
    """Every *module* that can change what a real rendered edition looks
    like changes what visuals.yml's own fixture looks like too -- this
    pins that this job's own filter never drops one of those without also
    dropping it from visuals.yml (an unlikely but real drift: two lists,
    maintained by hand, in two different files)."""
    this_paths = set(_TRIGGERS["push"]["paths"])
    for path in _SHARED_COMPOSITION_PATHS:
        assert path in this_paths, (
            f"{path} is missing from visuals-production.yml's own filter"
        )
        assert f"'{path}'" in _VISUALS_WORKFLOW, (
            f"{path} is claimed to be shared with visuals.yml but is not "
            "in that file either"
        )


def test_the_two_jobs_watch_their_own_instances_files() -> None:
    """The one asymmetry between the two filters, pinned so that it stays
    a decision and cannot decay into an omission.

    This job renders *real* editions, as the instance that runs this
    repository, so it watches `instance/config.json` and
    `instance/data/brand.json`. visuals.yml renders a fixed fictional fixture as
    `instances/example/`, so it watches that instance's two files instead
    -- which is what stopped it going red for every duplicate that chose
    its own colours and had them diffed against a committed image of
    somebody else's poster.

    `brand/convener/brand.json`, the product's default charter, stays here
    and only here: a duplicate that has written no `instance/data/brand.json` falls
    back to it for a real render, while the example always declares one of
    its own."""
    mine = set(_TRIGGERS["push"]["paths"])
    production_only = (
        "instance/config.json",
        "instance/data/brand.json",
        "brand/convener/brand.json",
    )
    for path in production_only:
        assert path in mine, f"{path} is missing from this job's own filter"
        assert f"'{path}'" not in _VISUALS_WORKFLOW, (
            f"{path} is back in visuals.yml, which renders the example "
            "instance and cannot be affected by it"
        )
    for path in (
        "instances/example/instance/config.json",
        "instances/example/instance/data/brand.json",
    ):
        assert f"'{path}'" in _VISUALS_WORKFLOW, (
            f"{path} is missing from visuals.yml, which renders from it"
        )
        assert path not in mine, (
            f"{path} is in this job's filter, which renders real editions "
            "and never reads the example"
        )


def test_public_data_py_is_in_the_filter_the_consent_gate_needs() -> None:
    """`render_visuals` and
    `render_announcements` (this job's own two commands) each call
    `public_data.to_public` directly before either one reads a row -- the
    consent gate every one of `cli.py`'s, `announce.py`'s and
    `visual.py`'s own docstrings names as the reason a portrait or a room
    link cannot reach a rendered page. A change to the gate's own logic
    must re-trigger this job the same way a change to `visual.py` itself
    already does."""
    paths = _TRIGGERS["push"]["paths"]
    assert "tools/convener_ops/public_data.py" in paths


def test_the_workflow_names_its_own_file_in_its_own_filter() -> None:
    assert ".github/workflows/visuals-production.yml" in _TRIGGERS["push"]["paths"]


def test_job_permissions_cover_the_commit_and_dispatch_with_a_bounded_timeout() -> None:
    """This job commits `site/src/banners/` back to
    this repository and dispatches `publish-vitrine.yml` -- `contents:
    write` and `actions: write` are exactly the pair `sweep.yml`,
    `retention.yml` and the three certificate workflows already carry for
    the identical reason (this file's own header comment). Nothing else:
    still no `pull-requests`, `issues` or any other scope this job never
    touches."""
    assert _JOB["permissions"] == {"contents": "write", "actions": "write"}
    assert isinstance(_JOB.get("timeout-minutes"), int)


def test_the_workflow_reads_no_repository_secret() -> None:
    """This job never reads private data beyond this repository's own
    checkout, and its own commit-and-dispatch step authenticates
    with `github.token` -- the ambient, scoped token every job already
    receives, granted through the `permissions:` block above, never a
    repository secret. Unlike publish-vitrine.yml, this workflow needs no
    `VITRINE_DEPLOY_TOKEN` or any other secret at all. The same check
    `test_preview_workflow.py`'s own `test_the_workflow_reads_no_
    repository_secret` makes for preview.yml, for the identical reason."""
    assert "secrets." not in _WORKFLOW
    assert "github.token" in _WORKFLOW


def test_the_commit_step_uses_a_distinct_bot_identity() -> None:
    """The same `convener-<task>` naming convention `sweep.yml` (`convener-sweep`),
    `retention.yml` (`convener-retention`) and the certificate workflows
    (`convener-certificates`) already use -- a distinct identity per writer
    makes the commit log say which job produced a given commit without
    opening it."""
    assert 'git config user.name "convener-visuals"' in _WORKFLOW
    assert (
        'git config user.email "convener-visuals@users.noreply.github.com"' in _WORKFLOW
    )


def test_the_commit_step_dispatches_publish_vitrine_after_a_successful_push() -> None:
    """GitHub's recursion guard: a push made with this job's own
    `GITHUB_TOKEN` cannot fire `publish-vitrine.yml`'s own `push` trigger,
    even though `site/**` (which `site/src/banners/` sits under) is one of
    the paths that trigger names -- the identical mechanism `sweep.yml`'s
    own header comment documents for `instance/data/speakers.yml`. Without this
    dispatch, a freshly committed banner would sit in this repository
    unpublished until something else happened to touch `site/**` or
    `tools/**`."""
    assert "gh workflow run publish-vitrine.yml" in _WORKFLOW
    assert '--ref "$TARGET_BRANCH"' in _WORKFLOW


def test_the_sync_step_regenerates_the_banner_directory_whole() -> None:
    """`rm -rf` before repopulating, the same "regenerated whole, never
    accumulated into" discipline `convener-render-visuals`'s own `OUTPUT_DIR`
    handling already applies -- an edition no longer scheduled must lose
    its banner in the same run, not leave a stale file sitting at a live
    public address.

    This file's own sync step was merged into the commit
    step below it (`sync_banners`, a shell function called once before
    the retry loop and again on every re-derive, since `git reset --hard`
    would otherwise discard the local commit's own banner files along
    with it) -- the sync logic itself is unchanged, only where it lives."""
    sync_step = next(
        s for s in _JOB["steps"] if s.get("name") == "Sync and commit the share banner"
    )
    assert "if" not in sync_step, (
        "the sync-and-commit step must run even when nothing is scheduled "
        "(D-13) -- that is exactly the run that has to clear a stale banner"
    )
    assert "rm -rf site/src/banners" in sync_step["run"]
    assert "banner.png" in sync_step["run"]


def test_the_sync_step_only_carries_the_banner_format_not_square_or_print() -> None:
    """This file's own header comment: `square.png` and `print.png` stay
    artefact-only, downloaded on demand -- only the one format a
    link-preview bot fetches unprompted is committed to a stable address."""
    sync_step = next(
        s for s in _JOB["steps"] if s.get("name") == "Sync and commit the share banner"
    )
    assert "square.png" not in sync_step["run"]
    assert "print.png" not in sync_step["run"]


def test_concurrency_group_is_scoped_to_the_ref_and_cancels_in_progress() -> None:
    concurrency = _WORKFLOW_DATA.get("concurrency")
    assert isinstance(concurrency, dict)
    assert "github.ref" in concurrency["group"]
    assert concurrency.get("cancel-in-progress") is True


def test_concurrency_group_does_not_collide_with_another_workflow() -> None:
    """The same guard `test_workflows.py::test_deploy_workflow_
    concurrency_group_cannot_collide_with_another_workflow` makes for
    deploy.yml, applied to this workflow's own literal group name: no
    other workflow file in this repository declares the identical
    `visuals-production-` prefix."""
    group = _WORKFLOW_DATA["concurrency"]["group"]
    for path in (_ROOT / ".github" / "workflows").glob("*.yml"):
        if path == _WORKFLOW_PATH:
            continue
        other = yaml.safe_load(path.read_text(encoding="utf-8"))
        other_concurrency = other.get("concurrency")
        if isinstance(other_concurrency, dict):
            assert other_concurrency.get("group") != group, (
                f"{path.name} shares visuals-production.yml's own concurrency group"
            )


def test_the_render_step_calls_the_production_command_not_the_fixture_one() -> None:
    """The one substantive difference from visuals.yml's own first step:
    this job must call `convener-render-visuals` (real, scheduled editions),
    never `convener-render-visual-fixtures` (the fixed, fictional one)."""
    assert "convener-render-visuals " in _WORKFLOW
    assert "convener-render-visual-fixtures" not in _WORKFLOW


def test_a_skip_is_visible_not_merely_absent() -> None:
    """D-25: a job that renders nothing must say so, not merely show every
    later step as skipped with no line of its own explaining why."""
    assert "steps.pages.outputs.count" in _WORKFLOW
    assert "::notice::" in _WORKFLOW
    assert "no scheduled edition" in _WORKFLOW


def test_every_heavy_step_after_the_page_count_is_conditional_on_it() -> None:
    """Every step from the Chrome cache to the production render only runs
    when there is an HTML page to screenshot -- the whole point of
    counting first (D-25's "filter deliberately" applied at the step
    level, since the workflow's own trigger-time path filter cannot see
    *how many* scheduled editions a matching push actually leaves behind).
    "Upload the rendered visuals" is deliberately not in this set any more
    -- see `test_the_upload_step_also_runs_when_only_
    announcement_texts_exist` for why its own condition is now broader."""
    heavy_step_names = {
        "Cache the pinned Chrome-for-Testing download",
        "Install the pinned renderer",
        "Dependency audit",
        "Render the production visuals",
    }
    steps = _JOB["steps"]
    found = set()
    for step in steps:
        name = step.get("name")
        uses = step.get("uses", "")
        is_setup_node = uses.startswith("actions/setup-node@")
        if name in heavy_step_names or is_setup_node:
            found.add(name or "setup-node")
            assert step.get("if") == "steps.pages.outputs.count != '0'", (
                f"step {name or uses!r} is not gated on the page count"
            )
    assert found == heavy_step_names | {"setup-node"}, (
        f"expected to find every heavy step, only found {found!r}"
    )


def test_the_announcement_command_runs_unconditionally() -> None:
    """`convener-render-announcements` is pure Python (no ~430MB
    Chrome download to gate) and covers a case `convener-render-visuals`'s own
    page count cannot see -- a freshly-published recording announcement
    for an `archived` edition with zero editions currently `scheduled`.
    Gating this step on the page count would silently drop that case."""
    steps = _JOB["steps"]
    render_step = next(
        s
        for s in steps
        if s.get("name") == "Render the announcement texts (pure Python, no browser)"
    )
    assert "if" not in render_step
    assert "convener-render-announcements " in render_step["run"]


def test_the_upload_step_also_runs_when_only_announcement_texts_exist() -> None:
    """A recording announcement for an archived edition, with no scheduled
    edition at all, must still reach the artefact -- gating the upload on
    the (expensive) Chrome pipeline's own page count alone would silently
    drop it, since that pipeline never even runs in that case."""
    steps = _JOB["steps"]
    upload_step = next(
        s for s in steps if s.get("name") == "Upload the rendered visuals"
    )
    condition = upload_step.get("if", "")
    assert "steps.pages.outputs.count != '0'" in condition
    assert "steps.announcements.outputs.count != '0'" in condition


def test_the_skip_notice_requires_both_counts_to_be_zero() -> None:
    """The one state that is genuinely "nothing to do" is both counts at
    zero -- a page count of zero with an announcement still to upload must
    not print the "nothing to render" notice."""
    steps = _JOB["steps"]
    notice_step = next(
        s
        for s in steps
        if s.get("name") == "Nothing scheduled -- nothing to render this run"
    )
    condition = notice_step.get("if", "")
    assert "steps.pages.outputs.count == '0'" in condition
    assert "steps.announcements.outputs.count == '0'" in condition
    assert "&&" in condition


def test_the_chrome_cache_key_is_shared_with_visuals_yml() -> None:
    """The identical cache key visuals.yml's own job uses -- the ~430MB
    Chrome-for-Testing download is then paid for at most once across
    *both* workflows combined, never once per workflow (the workflow's own
    comment on this step)."""
    key_line = (
        "key: puppeteer-${{ runner.os }}-"
        "${{ hashFiles('tools/visuals/package-lock.json') }}"
    )
    assert key_line in _WORKFLOW
    assert key_line in _VISUALS_WORKFLOW


def test_node_version_meets_puppeteers_own_floor() -> None:
    assert "node-version: '22'" in _WORKFLOW


def test_npm_ci_and_audit_run_from_the_visuals_working_directory() -> None:
    assert "working-directory: tools/visuals" in _WORKFLOW
    assert "run: npm ci" in _WORKFLOW
    assert "run: npm audit" in _WORKFLOW


def test_the_upload_step_refuses_an_empty_artefact_and_sets_a_retention() -> None:
    steps = _JOB["steps"]
    upload_step = next(
        s for s in steps if s.get("name") == "Upload the rendered visuals"
    )
    assert upload_step["with"]["if-no-files-found"] == "error"
    assert isinstance(upload_step["with"]["retention-days"], int)
    assert upload_step["with"]["name"] == "announcement-visuals"


def test_the_upload_step_uses_the_production_renderers_own_output_directory() -> None:
    steps = _JOB["steps"]
    render_step = next(
        s for s in steps if s.get("name") == "Render the production visuals"
    )
    upload_step = next(
        s for s in steps if s.get("name") == "Upload the rendered visuals"
    )
    assert "production-visuals-out" in render_step["run"]
    assert "production-visuals-out" in upload_step["with"]["path"]


# ---------------------------------------------------------------------------
# render-production.mjs
# ---------------------------------------------------------------------------


def test_puppeteer_is_the_scripts_only_dependency() -> None:
    """No new dependency was added: `tools/visuals/package.json`'s own
    `devDependencies` still lists only the one already pinned;
    this script imports it, adds nothing of its own."""
    assert "import puppeteer from 'puppeteer';" in _SCRIPT


def test_an_empty_manifest_is_a_normal_exit_not_an_error() -> None:
    body = _SCRIPT.split("if (manifest.length === 0)")[1].split("}\n\n  await mkdir")[0]
    assert "return;" in body
    assert "::error::" not in body


def test_the_file_count_guard_exists_and_refuses_success_on_a_mismatch() -> None:
    """The property a mutation proved by hand: a run that wrote fewer images
    than the manifest promised must fail, not report
    success -- `actions/upload-artifact`'s own `if-no-files-found: error`
    cannot see this (it only ever sees "some" or "none")."""
    assert "written !== manifest.length" in _SCRIPT
    body = _SCRIPT.split("if (written !== manifest.length)")[1].split("return;")[0]
    assert "::error::" in body
    assert "process.exitCode = 1" in body


def test_the_server_is_never_file_url() -> None:
    """Same property `test_visuals_workflow.py::test_the_server_is_never_
    file_url` pins for render-and-compare.mjs, checked here for its own
    duplicate copy: a relative `@font-face url(...)` cannot load from a
    bare `file://` origin without a flag this project has no reason to
    carry."""
    assert "createServer" in _SCRIPT
    assert "const baseUrl = `http://127.0.0.1:${port}/`;" in _SCRIPT
    assert "await page.goto(`${baseUrl}${entry.file}`" in _SCRIPT


def test_the_renderer_waits_for_self_hosted_fonts_before_screenshotting() -> None:
    assert "document.fonts.ready" in _SCRIPT


def test_images_are_written_under_a_per_edition_directory() -> None:
    """Multiple editions can be scheduled at once -- each edition's own
    three formats must land in their own subdirectory, never flattened
    into one that could collide `square.png` from two different
    editions."""
    assert "path.join(args.out, entry.event_id)" in _SCRIPT
