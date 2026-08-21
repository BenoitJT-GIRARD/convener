"""The app publishes to the vitrine, not to GitHub Pages on this repo.

`example-cockpit` is private; GitHub Pages does not serve a private repo without
a paid plan, so the three Pages actions (`configure-pages`,
`upload-pages-artifact`, `deploy-pages`) and the `deploy` job that used them
can never succeed here. Nothing in this repository read workflow YAML before
this module, which made that a config file no test could catch drifting back
in.

Two things are asserted instead of the two things the brief names:

* Rather than running `npm run build` and grepping `app/dist/index.html`
  (slow, and this suite runs on every push), the base path is asserted
  straight from `app/vite.config.ts` — the one source Vite reads it from.
* The publish step is a hand-written shell script, the same shape as
  `publish-vitrine.yml`'s own push step. It is asserted against as text
  (`in` checks on the parsed `run:` block) rather than executed, because
  running it means a real clone of a real repo, which is exactly the kind
  of network access this suite must not take on.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import stat
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

import pytest

from convener_ops import (
    certificate,
    confirmation,
    platform_fcc,
    registration,
    signing,
    survey_invite,
)
from convener_ops import cli as cli_module
from convener_ops.paths import repo_root
from convener_ops.yaml_safe import safe_load

ROOT = repo_root()
DEPLOY_WORKFLOW = Path(".github/workflows/deploy.yml")
VITE_CONFIG = Path("app/vite.config.ts")
APP_TSX = Path("app/src/App.tsx")

#: The base path the brief names verbatim: the app is served from the
#: public vitrine repo, under its own `app/` subtree, not from the private
#: cockpit repo's own Pages site (which cannot exist on the free plan).
EXPECTED_BASE_PATH = "/example-showcase/app/"


def _load_workflow() -> dict[str, Any]:
    loaded = safe_load((ROOT / DEPLOY_WORKFLOW).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _build_job() -> dict[str, Any]:
    job = _load_workflow()["jobs"]["build"]
    assert isinstance(job, dict)
    return job


def _step_uses(job: dict[str, Any]) -> list[str]:
    return [step["uses"] for step in job["steps"] if "uses" in step]


def _push_step_script() -> str:
    """The `run:` block of the step that pushes into example-showcase.

    Found by the secret it reads rather than by its `name:`, so a rename
    of the step does not silently stop this module from checking it.
    """
    for step in _build_job()["steps"]:
        env = step.get("env", {})
        if any("VITRINE_DEPLOY_TOKEN" in str(value) for value in env.values()):
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        "no step in the build job reads VITRINE_DEPLOY_TOKEN — "
        "the push-to-vitrine step is missing or was renamed away from it"
    )


def _survey_status_step_script() -> str:
    """The `run:` block of the step that commits
    `public-data/survey-status.json` back to this repository (R-41, fix
    round 2).

    Found by the file it writes rather than by its `name:`, the identical
    reasoning `_push_step_script` above gives for its own lookup -- a
    rename of the step does not silently stop this module from checking
    it.
    """
    for step in _build_job()["steps"]:
        run = step.get("run")
        if isinstance(run, str) and "public-data/survey-status.json" in run:
            return run
    raise AssertionError(
        "no step in the build job writes public-data/survey-status.json — "
        "the survey-status commit step is missing or was renamed away from it"
    )


def test_deploy_workflow_survey_status_retry_re_derives_rather_than_rebases() -> None:
    """Fix round 3: the same defence `registration.yml`'s and
    `survey.yml`'s own retry loops use -- a rejected push is handled by
    fetching the branch tip, hard-resetting, and re-running the
    projection command, never actually *running* `git rebase`.

    `public-data/survey-status.json` is a generated JSON array, the same
    shape `registrations.enc` and `survey_responses.enc` are: task 6's
    Critical 1, reproduced end to end with real git, showed that
    `git rebase` on two runs each rewriting an array's own closing lines
    returns 1 on the conflict, and `set -e` kills the step before the
    `::error::` line is ever reached -- an unexplained red with the tree
    left mid-rebase. Before fix round 3, this exact step ran `git rebase`
    on a rejected push (the phrase itself is named in an explanatory
    comment, which this checks for separately, on uncommented lines
    only)."""
    script = _survey_status_step_script()
    commands = [
        line for line in script.splitlines() if not line.strip().startswith("#")
    ]
    assert not any("git rebase" in line for line in commands), (
        "the survey-status commit step still rebases on a rejected push -- "
        "see registration.yml's own comment for why replaying a diff over "
        "a generated array is unsafe"
    )
    assert not any("git pull" in line for line in commands)
    assert 'git fetch origin "$GITHUB_REF_NAME"' in script
    assert 'git reset --hard "origin/$GITHUB_REF_NAME"' in script
    assert (
        "uv run convener-survey-status-public-data" in script.split("for attempt", 1)[-1]
    ), (
        "the retry loop must re-run the projection command on every "
        "attempt, not only build it once before the loop starts"
    )
    assert "for attempt in 1 2 3; do" in script


def test_vite_config_base_path_targets_the_vitrine_app_subtree() -> None:
    config = (ROOT / VITE_CONFIG).read_text(encoding="utf-8")
    assert f"base: '{EXPECTED_BASE_PATH}'" in config, (
        f"{VITE_CONFIG.as_posix()} does not set base to {EXPECTED_BASE_PATH!r}; "
        "a build off this config would ship broken asset URLs once served "
        "from the vitrine's app/ subtree."
    )


def test_vite_config_base_no_longer_points_at_the_private_repo() -> None:
    config = (ROOT / VITE_CONFIG).read_text(encoding="utf-8")
    assert "/example-cockpit/" not in config, (
        f"{VITE_CONFIG.as_posix()} still references /example-cockpit/; a bundle "
        "built from it would 404 every asset once served from example-showcase."
    )


def test_app_route_matches_certificate_verification_base() -> None:
    """Important 3 (fix round 1, task 13): App.tsx declares
    `<Route path="/verify/:identifier" element={<VerifyRoute />} />` --
    mutating that path left the full app suite at 1097 passed, 0 failures,
    and the consequence is not a 404: App.tsx's own `<Route path="/*"
    element={<Shell />} />` catches everything else, so every already-
    printed QR code would silently start landing a stranger on the
    authenticated cockpit's login screen. No test in app/ reads the
    application's route table at all -- every case in verify.test.tsx
    mounts VerifyPage directly on a MemoryRouter path of its own choosing.

    Same idiom as test_vite_config_base_path_targets_the_vitrine_app_subtree,
    just above: read the source file as text, pinned against the one thing
    that has to agree with it -- certificate.VERIFICATION_BASE, which the
    shared fixture also carries as `verification_base` (D-14: a rule
    written on both sides of the language boundary, bound by one fixture
    read from both, not two hand-typed literals that could drift)."""
    fragment = certificate.VERIFICATION_BASE.split("#", 1)[1]  # "/verify/"
    expected_path = f"{fragment}:identifier"  # "/verify/:identifier"
    app_tsx = (ROOT / APP_TSX).read_text(encoding="utf-8")
    assert f'path="{expected_path}"' in app_tsx, (
        f"{APP_TSX.as_posix()} does not declare a route at "
        f"{expected_path!r} -- this must match "
        "certificate.VERIFICATION_BASE's own fragment, or every printed "
        "QR code lands a stranger on the authenticated Shell instead of "
        "the public verification page"
    )


def test_certificate_verification_base_targets_the_vitrine_app_subtree() -> None:
    """M4, fix round 1 (task 16b's review): the D-14 pin just above binds
    `#/verify/` to `App.tsx`'s route literal, but nothing bound the host
    and path *before* that fragment -- `/example-showcase/app/` -- to
    `vite.config.ts`'s own `base`. Changing that base would make every
    printed QR code 404 with the route pin still green, because the pin
    only ever looks at what comes after `#`."""
    assert EXPECTED_BASE_PATH in certificate.VERIFICATION_BASE, (
        f"certificate.VERIFICATION_BASE does not carry {EXPECTED_BASE_PATH!r} "
        f"-- it would not match app/vite.config.ts's own base, and every "
        "printed QR code would 404 once served"
    )


def test_survey_base_targets_the_vitrine_app_subtree() -> None:
    """M4's identical gap, applied to `survey_invite.SURVEY_BASE`: the D-14
    pin in `test_survey_invite.py` binds `#/survey/` to `App.tsx`'s route,
    but not the deployment base that comes before it."""
    assert EXPECTED_BASE_PATH in survey_invite.SURVEY_BASE, (
        f"survey_invite.SURVEY_BASE does not carry {EXPECTED_BASE_PATH!r} -- "
        "it would not match app/vite.config.ts's own base, and every "
        "survey invitation link would 404 once served"
    )


def test_app_route_matches_registration_signup_base() -> None:
    """Critical 2 (branch review): the same D-14 pin
    `test_app_route_matches_certificate_verification_base` already makes
    for `/verify/:identifier`, applied to the oldest of the three public
    routes -- `registration.SIGNUP_BASE` did not exist before this fix, and
    nothing bound `/signup/:eventId` to anything at all."""
    fragment = registration.SIGNUP_BASE.split("#", 1)[1]  # "/signup/"
    expected_path = f"{fragment}:eventId"  # "/signup/:eventId"
    app_tsx = (ROOT / APP_TSX).read_text(encoding="utf-8")
    assert f'path="{expected_path}"' in app_tsx, (
        f"{APP_TSX.as_posix()} does not declare a route at "
        f"{expected_path!r} -- this must match registration.SIGNUP_BASE's "
        "own fragment"
    )


def test_registration_signup_base_targets_the_vitrine_app_subtree() -> None:
    """Same gap as `test_certificate_verification_base_targets_the_vitrine_
    app_subtree` and `test_survey_base_targets_the_vitrine_app_subtree`,
    applied to the third base."""
    assert EXPECTED_BASE_PATH in registration.SIGNUP_BASE, (
        f"registration.SIGNUP_BASE does not carry {EXPECTED_BASE_PATH!r} "
        "-- it would not match app/vite.config.ts's own base, and every "
        "published signup link would 404 once served"
    )


def test_deploy_workflow_has_a_single_self_sufficient_job() -> None:
    jobs = _load_workflow()["jobs"]
    assert set(jobs) == {"build"}, (
        "the separate `deploy` job existed only to hand the build to the "
        "github-pages environment; that environment is gone, so `build` "
        "should be the only job left"
    )


def test_deploy_workflow_cancels_stale_runs_of_itself() -> None:
    """Two overlapping `deploy.yml` runs both rewrite all of `app/` -- unlike
    this workflow and `publish-vitrine.yml`, which write disjoint subtrees and
    so can safely race through the retry-with-rebase loop instead. Left
    unserialised, the loser's rebase either conflicts on `index.html` or
    replays cleanly and lets the older build silently overwrite the newer
    one; cancelling the older run removes that case by construction."""
    concurrency = _load_workflow().get("concurrency")
    assert isinstance(concurrency, dict), (
        "deploy.yml has no concurrency group -- two overlapping runs can "
        "each push a build, and the loser's rebase-and-retry can replay "
        "cleanly with the older build silently overwriting the newer one"
    )
    assert concurrency.get("cancel-in-progress") is True, (
        "cancel-in-progress must be true, not false: an older deploy run "
        "has no reason to finish once a newer commit has already started "
        "its own, so it should be cancelled outright, not merely queued "
        "behind the newer one"
    )


def test_deploy_workflow_concurrency_group_cannot_collide_with_another_workflow() -> (
    None
):
    group = _load_workflow()["concurrency"]["group"]
    assert "github.workflow" in group, (
        "the group must be derived from `github.workflow`, this workflow's "
        "own name -- so pasting this block into a future workflow file "
        "gives that workflow its own group automatically instead of "
        "silently sharing deploy.yml's"
    )


def test_deploy_workflow_concurrency_is_not_shared_with_publish_vitrine() -> None:
    """`publish-vitrine.yml` writes a disjoint subtree of example-showcase and its
    overlapping pushes are both legitimate -- the retry-with-rebase loop
    already handles that case more cheaply. Grouping the two workflows
    together here would serialise a job that does not need to wait."""
    publish_vitrine = safe_load(
        (ROOT / ".github/workflows/publish-vitrine.yml").read_text(encoding="utf-8")
    )
    assert "concurrency" not in publish_vitrine, (
        "publish-vitrine.yml must not gain a concurrency group shared with "
        "deploy.yml's -- their overlapping pushes are both legitimate and "
        "the existing retry loop already reconciles them"
    )


def test_deploy_workflow_build_job_permissions_allow_committing_survey_status() -> None:
    """R-41, fix round 2: `permissions.contents` moved from `read` to
    `write` when the "Commit survey status" step was added -- unlike the
    push to example-showcase (a separate repository, authenticated over a PAT
    in `DEPLOY_TOKEN`, never the checkout's own token), that step commits
    `public-data/survey-status.json` back to *this* repository using the
    checkout's own `GITHUB_TOKEN`, which needs write access to push at
    all. `write` is still the minimum this job needs -- nothing here asks
    for `pull-requests`, `issues`, or any other scope."""
    assert _build_job()["permissions"] == {"contents": "write"}, (
        "the build job's own 'Commit survey status' step pushes to this "
        "repository over the checkout's GITHUB_TOKEN, which needs "
        "contents: write -- read alone would make that push fail, not "
        "silently skip it"
    )


def test_deploy_workflow_no_longer_uses_pages_actions() -> None:
    banned = ("configure-pages", "upload-pages-artifact", "deploy-pages")
    uses = _step_uses(_build_job())
    offending = [u for u in uses if any(name in u for name in banned)]
    assert offending == [], (
        f"still uses Pages actions: {offending} — these can never succeed "
        "against a private repo without a paid GitHub plan"
    )


def test_deploy_workflow_push_step_guards_on_missing_token() -> None:
    """Isolated to the slice between the token check and its own `fi`.

    A second, unrelated `exit 0` sits later in this same script (the
    no-changes guard); asserting `"exit 0" in script` anywhere would pass
    even if it were that other `exit 0` doing the work and the token check
    fell through to a real push.
    """
    script = _push_step_script()
    check_at = script.find('if [ -z "$DEPLOY_TOKEN" ]')
    assert check_at != -1, 'no `if [ -z "$DEPLOY_TOKEN" ]` guard found in the push step'
    end_at = script.find("\nfi", check_at)
    assert end_at != -1, "the token-check `if` has no matching `fi`"
    guard = script[check_at : end_at + len("\nfi")]
    assert "exit 0" in guard, (
        "a missing VITRINE_DEPLOY_TOKEN must be a normal, silent no-op "
        "(decision D-13), not a failed job"
    )


def test_deploy_workflow_push_step_only_touches_the_app_subtree() -> None:
    script = _push_step_script()
    assert "git add --force app" in script, (
        "the push step must stage only the target repo's app/ subtree, the "
        "same discipline publish-vitrine.yml uses for src/_data/ -- and "
        "with --force, since `git add` still honours the target "
        "repository's own .gitignore"
    )
    assert "git add ." not in script and "git add -A" not in script


def test_deploy_workflow_push_step_clears_stale_files_before_copying() -> None:
    script = _push_step_script()
    remove_at = script.find("rm -rf")
    copy_at = script.find("cp -r")
    assert remove_at != -1, (
        "the old app/ contents in example-showcase must be removed before the "
        "new build is copied in, or a file dropped from the bundle would "
        "survive there indefinitely"
    )
    assert copy_at != -1 and remove_at < copy_at, (
        "the removal must happen before the copy, not after"
    )


def test_deploy_workflow_push_step_skips_committing_when_nothing_changed() -> None:
    script = _push_step_script()
    assert "git diff --staged --quiet" in script, (
        "an unchanged build must not produce an empty commit, the same "
        "guard publish-vitrine.yml already applies"
    )


def _deploy_build_public_data_step() -> str:
    for step in _build_job()["steps"]:
        if step.get("name") == "Build public data":
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        "deploy.yml has no 'Build public data' step -- renamed away from "
        "the name this test looks for"
    )


def test_deploy_workflow_builds_the_certificates_public_data() -> None:
    """Minor 4 (fix round 1, task 13): deploy.yml's own 'Build public
    data' step was pinned by nothing, even though this module already
    carries fourteen assertions about deploy.yml. Deleting the step left
    the suite green while certificates.json -- the file the verification
    page actually fetches -- shipped permanently empty. (Before Minor 5,
    below, this same step also existed, pinned, in publish-vitrine.yml;
    that copy is gone now that this one is the only writer -- see
    test_publish_vitrine_no_longer_builds_the_certificates_public_data.)"""
    assert "convener-certificates-public-data" in _deploy_build_public_data_step(), (
        "deploy.yml's 'Build public data' step no longer runs "
        "convener-certificates-public-data -- app/public/certificates.json "
        "(and therefore app/dist/certificates.json) would ship empty "
        "even with real certificates on record"
    )


def test_deploy_workflow_builds_public_data_before_the_npm_build() -> None:
    """The step above has to run *before* `npm run build`: vite's own
    `prebuild` script is what runs `scripts/copy-certificates.mjs`, which
    reads `public-data/certificates-public.json` -- generated by the step
    above -- into `app/public/`. Reversing the order would leave the copy
    script reading a file that does not exist yet, silently publishing an
    empty register (D-13's own 'absent is normal' path, reached here for
    the wrong reason)."""
    names = [step.get("name") for step in _build_job()["steps"]]
    assert "Build public data" in names, (
        "see test_deploy_workflow_builds_the_certificates_public_data"
    )
    assert "Build" in names, (
        "deploy.yml has no step named 'Build' (npm run build) any more"
    )
    assert names.index("Build public data") < names.index("Build"), (
        "'Build public data' must run before 'Build' (npm run build), or "
        "copy-certificates.mjs's own prebuild step reads a "
        "public-data/certificates-public.json that does not exist yet"
    )


def _deploy_build_survey_status_step() -> str:
    for step in _build_job()["steps"]:
        if step.get("name") == "Build survey status":
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        "deploy.yml has no 'Build survey status' step -- renamed away from "
        "the name this test looks for"
    )


def test_deploy_workflow_builds_the_survey_status_public_data() -> None:
    """R-37's own reachability requirement, the same shape Minor 4 (task
    13) asked for `certificates-public-data`: deleting this step would
    leave the suite green while `survey-status.json` -- the file
    `SurveyForm.tsx` actually fetches before it ever renders a form --
    shipped permanently empty, meaning every event would read as closed."""
    assert "convener-survey-status-public-data" in _deploy_build_survey_status_step(), (
        "deploy.yml's 'Build survey status' step no longer runs "
        "convener-survey-status-public-data -- app/public/survey-status.json "
        "would ship empty even with a survey enabled on record"
    )


def test_deploy_workflow_builds_survey_status_before_the_npm_build() -> None:
    """The same ordering requirement as 'Build public data': vite's own
    `prebuild` runs `scripts/copy-survey-status.mjs`, which reads
    `public-data/survey-status.json` -- generated by this step -- into
    `app/public/`."""
    names = [step.get("name") for step in _build_job()["steps"]]
    assert "Build survey status" in names, (
        "see test_deploy_workflow_builds_the_survey_status_public_data"
    )
    assert names.index("Build survey status") < names.index("Build"), (
        "'Build survey status' must run before 'Build' (npm run build), or "
        "copy-survey-status.mjs's own prebuild step reads a "
        "public-data/survey-status.json that does not exist yet"
    )


# ------------------------------------------------------------------ #
# publish-vitrine.yml: the certificate register's public projection
# (R-19, fix round 1, task 12). Before this, a revocation -- a change to
# data/events/<id>/certificates.yml -- did not even fire this workflow,
# and the file it would have built was never copied to the showcase, so
# spec S:7's "le registre fait foi sur l'état" had no observable effect on
# any verifier. Text assertions on the parsed `run:` block, the same idiom
# test_notify.py uses for notify.yml, because running the script means a
# real clone of a real repository -- exactly the network access this
# suite must not take on (see this module's own docstring).
# ------------------------------------------------------------------ #

PUBLISH_VITRINE_WORKFLOW = Path(".github/workflows/publish-vitrine.yml")


def _publish_vitrine_workflow() -> dict[str, Any]:
    loaded = safe_load((ROOT / PUBLISH_VITRINE_WORKFLOW).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _publish_vitrine_build_step() -> str:
    job = _publish_vitrine_workflow()["jobs"]["publish"]
    for step in job["steps"]:
        if step.get("name") == "Build public data":
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        "publish-vitrine.yml has no 'Build public data' step -- renamed "
        "away from the name this test looks for"
    )


def _publish_vitrine_push_script() -> str:
    job = _publish_vitrine_workflow()["jobs"]["publish"]
    for step in job["steps"]:
        env = step.get("env", {})
        if any("VITRINE_DEPLOY_TOKEN" in str(value) for value in env.values()):
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        "no step in the publish job reads VITRINE_DEPLOY_TOKEN -- the "
        "push-to-vitrine step is missing or was renamed away from it"
    )


def test_publish_vitrine_paths_trigger_includes_the_certificate_register() -> None:
    """Half the original defect (Important 6): a revocation is a change to
    `data/events/<id>/certificates.yml`, and the old `paths:` trigger
    (`data/speakers.yml`, `tools/**`) would not even fire this workflow
    for one.

    Read as raw text, not through `safe_load`: PyYAML's YAML-1.1 bool
    resolver reads a bare `on:` key as the boolean `True`, not the string
    `"on"` -- a real gotcha, not a reason to trust this file less than
    `notify.yml`'s own text assertions already do (test_notify.py's own
    idiom, followed here for exactly this reason)."""
    text = (ROOT / PUBLISH_VITRINE_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "'data/events/*/certificates.yml'" in trigger


def test_publish_vitrine_no_longer_builds_the_certificates_public_data() -> None:
    """Minor 5 (fix round 1, task 13): this step used to also run
    `convener-certificates-public-data`, to feed the push step's own (equally
    removed) copy into the showcase's `src/_data/certificates.json` -- a
    file no Eleventy template there ever read. Regenerating it here with
    nothing left to consume the output would be pure waste; the register
    a verifier actually reads is built by deploy.yml instead (see that
    workflow's own 'Build public data' step and
    test_deploy_workflow_builds_the_certificates_public_data, above)."""
    assert "convener-certificates-public-data" not in _publish_vitrine_build_step(), (
        "publish-vitrine.yml still builds the certificates projection "
        "though nothing here writes it anywhere any more"
    )


def test_publish_vitrine_push_step_no_longer_copies_certificates_data() -> None:
    """Minor 5 (fix round 1, task 13): confirmed independently, at
    <https://example-instance.github.io/example-showcase/> and verified
    against the showcase checkout itself, that no Eleventy template reads
    `src/_data/certificates.json` -- `grep -rn certificates src/` there is
    empty. The write survived three fix rounds because it made the three
    certificate workflows *look* like they refreshed the public register
    (Critical 1's own root cause); removing it is the other half of that
    fix."""
    script = _publish_vitrine_push_script()
    assert "certificates.json" not in script, (
        "publish-vitrine.yml's push step still mentions certificates.json "
        "-- the dead write this test exists to keep gone"
    )
    assert "git add src/_data/events.json" in script, (
        "the events feed itself must still be staged and pushed"
    )


def test_publish_vitrine_workflow_permissions_are_read_only() -> None:
    job = _publish_vitrine_workflow()["jobs"]["publish"]
    assert job["permissions"] == {"contents": "read"}


# ------------------------------------------------------------------ #
# Commit authors: an address on a domain this project administers
# ------------------------------------------------------------------ #

#: Criterion 8 is universal -- no commit author anywhere may carry a domain
#: this project does not administer -- so this scans every workflow file
#: rather than naming the ones known to commit today. A hardcoded list is
#: what let `deploy.yml` through the first time: it copied
#: `publish-vitrine.yml`'s push step, including its stale
#: `forum.example.test` address, and the list here named only
#: `candidate-form.yml` and `publish-vitrine.yml`, so nothing caught it.
#: A scan covers a workflow nobody has written yet, which a list never can.
WORKFLOWS_DIR = Path(".github/workflows")

_USER_EMAIL_RE = re.compile(r'user\.email\s+"([^"]+)"')
_USER_NAME_RE = re.compile(r'user\.name\s+"([^"]+)"')

#: The only domain a commit author here may use: a `users.noreply.github.com`
#: address claims nothing beyond what GitHub itself already vouches for.
_ALLOWED_EMAIL_DOMAIN = "users.noreply.github.com"


def _workflow_files_in(directory: Path) -> list[Path]:
    """`.yml` and `.yaml` both, sorted together -- GitHub Actions runs
    either extension under `.github/workflows/` (every file in this
    repository today happens to be `.yml`, but nothing about that is
    enforced anywhere, and a sweep that only globbed `.yml` would have
    silently had nothing at all to say about a `.yaml` file someone added
    -- sweep evasion 3, fix round 2, minor 1). A plain `list` directory
    argument, not `ROOT / WORKFLOWS_DIR` baked in, so a probe test below
    can exercise this exact glob against a temporary directory instead of
    the real repository."""
    return sorted((*directory.glob("*.yml"), *directory.glob("*.yaml")))


def _workflow_files() -> list[Path]:
    paths = _workflow_files_in(ROOT / WORKFLOWS_DIR)
    assert paths, (
        f"no *.yml or *.yaml files found under {WORKFLOWS_DIR.as_posix()} -- "
        "the glob itself is wrong, which would silently empty this scan"
    )
    return paths


def test_the_workflow_sweep_globs_yaml_files_too_not_only_yml(tmp_path: Path) -> None:
    """Sweep evasion 3 (fix round 2, minor 1), proven with a probe
    directory rather than trusting the real repository to never grow a
    `.yaml` file: before `_workflow_files_in` existed, `_workflow_files`
    globbed `*.yml` only, so a `.yaml` workflow -- which GitHub runs
    identically -- was invisible to every sweep in this module, including
    the SHA-pinning and timeout checks just below."""
    (tmp_path / "a.yml").write_text("jobs: {}\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("jobs: {}\n", encoding="utf-8")
    (tmp_path / "not-a-workflow.txt").write_text("jobs: {}\n", encoding="utf-8")
    found = _workflow_files_in(tmp_path)
    assert sorted(p.name for p in found) == ["a.yml", "b.yaml"]


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_automated_commit_author_is_not_on_a_domain_we_do_not_administer(
    workflow: Path,
) -> None:
    text = workflow.read_text(encoding="utf-8")
    emails = _USER_EMAIL_RE.findall(text)
    for email in emails:
        assert email.endswith(f"@{_ALLOWED_EMAIL_DOMAIN}"), (
            f"{workflow.name} signs a commit as {email!r}, not on "
            f"{_ALLOWED_EMAIL_DOMAIN} -- a domain this project does not "
            "administer (criterion 8)"
        )


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_automated_commit_identity_pairs_a_name_with_its_address(
    workflow: Path,
) -> None:
    """Every `user.email` a workflow sets has a matching `user.name` naming
    the same identity, so an automated commit reads as a recognisable bot
    rather than a bare, unexplained address."""
    text = workflow.read_text(encoding="utf-8")
    emails = _USER_EMAIL_RE.findall(text)
    names = _USER_NAME_RE.findall(text)
    for email in emails:
        local = email.split("@", 1)[0]
        assert local in names, (
            f'{workflow.name} sets user.email "{email}" without a '
            f'matching user.name "{local}"'
        )


# ------------------------------------------------------------------ #
# Minor 2 (fix round 1, task 16): "no repo-wide lint enforces SHA pinning
# or timeout-minutes. Deleting timeout-minutes from survey.yml, or
# swapping a pinned checkout SHA for actions/checkout@v7, leaves
# everything green." Both mutations were real when that finding was
# written -- confirmed against this same `_workflow_files()` sweep before
# either check below existed. Text-scanned, the same idiom every other
# scan in this module uses, never parsed and executed.
# ------------------------------------------------------------------ #

#: A `uses:` line naming an action and a ref: `owner/repo@REF`, optionally
#: followed by a trailing `# ...` comment. Matches the `- uses:` and
#: `uses:` forms both appear in across these files.
_USES_RE = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(\S+)@(\S+)(?:\s*(#.*))?\s*$", re.MULTILINE
)

#: A ref this project treats as pinned: exactly 40 lowercase hex
#: characters -- a full commit SHA, never a tag, a branch, or a short SHA
#: that could be reassigned or become ambiguous.
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_every_action_reference_is_pinned_to_a_full_commit_sha(workflow: Path) -> None:
    """Every `uses:` line names a full 40-character commit SHA, with a
    trailing comment naming the human-readable version it corresponds to
    -- `actions/checkout@v7` (a mutable tag) or a short SHA (reassignable,
    or ambiguous once the object database grows) would both pass a review
    that only reads the diff, and both are refused here."""
    text = workflow.read_text(encoding="utf-8")
    matches = _USES_RE.findall(text)
    assert matches, (
        f"{workflow.name} has no uses: line at all -- the regex itself may be wrong"
    )
    for action, ref, comment in matches:
        assert _FULL_SHA_RE.match(ref), (
            f"{workflow.name}: {action}@{ref} is not pinned to a full "
            "40-character commit SHA"
        )
        assert comment, (
            f"{workflow.name}: {action}@{ref} has no trailing comment "
            "naming the version this SHA corresponds to"
        )


def _job_has_own_timeout(job: Any) -> bool:
    """Whether `job` (one value from a workflow's `jobs:` mapping) carries
    its *own* `timeout-minutes:` key -- deliberately just `job.get(...)`,
    never anything that also looks inside `job["steps"]`: a step-level
    `timeout-minutes:` bounds only that one step, not the job as a whole,
    so it must never count as satisfying this. Shared by the real sweep
    below and by the two probe tests that pin its exact behaviour against
    both evasions the fix round 1 version of this check missed."""
    return isinstance(job, dict) and isinstance(job.get("timeout-minutes"), int)


def test_a_job_level_timeout_satisfies_the_requirement() -> None:
    """Positive control for `_job_has_own_timeout`, so the two probe tests
    below prove an *absence* is detected, not merely that everything
    trivially returns `False`."""
    probe = safe_load(
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 10\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    assert _job_has_own_timeout(probe["jobs"]["build"]) is True


def test_a_step_level_timeout_does_not_satisfy_the_job_level_requirement() -> None:
    """Sweep evasion 2 (fix round 2, minor 1), proven with a probe
    workflow: the fix round 1 version of this check counted every
    `timeout-minutes:\\s*\\d+` occurrence anywhere in the file against a
    count of `runs-on:` lines, so a job with *no* job-level timeout but
    one step carrying its own `timeout-minutes:` still passed -- the
    counts matched, even though the job as a whole remained unbounded at
    GitHub's own six-hour default."""
    probe = safe_load(
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: something slow\n"
        "        timeout-minutes: 5\n"
        "        run: echo hi\n"
    )
    assert _job_has_own_timeout(probe["jobs"]["build"]) is False


def test_a_commented_out_timeout_does_not_satisfy_the_job_level_requirement() -> None:
    """Sweep evasion 1 (fix round 2, minor 1), proven with a probe
    workflow: the fix round 1 version of this check matched
    `timeout-minutes:\\s*\\d+` as plain text anywhere in the file,
    including inside a `#` comment -- a job with no real
    `timeout-minutes:` key at all still passed if someone had merely
    written the phrase in prose. Parsing the YAML structurally, as this
    version does, makes a comment invisible by construction: `safe_load`
    never sees it at all."""
    probe = safe_load(
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    # timeout-minutes: 10 would be nice here\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    assert _job_has_own_timeout(probe["jobs"]["build"]) is False


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_every_job_declares_a_timeout(workflow: Path) -> None:
    """Every job in `jobs:` has its own `timeout-minutes:` key -- a job
    with none defaults to GitHub's own six-hour ceiling, which means a
    hung step is discovered by a human noticing, not by CI.

    Fix round 2, minor 1: rewritten from a text-scanned line count (which
    a step-level `timeout-minutes:` or a `#`-commented one could both
    satisfy without the job itself being bounded at all -- see the two
    probe tests just above) to parsing the real YAML and checking each
    job's own key via `_job_has_own_timeout`, the same structural
    discipline `test_every_action_reference_is_pinned_to_a_full_commit_sha`
    could not use (that one has to see the trailing `# v7`-style comment
    `safe_load` would discard) but this one can."""
    data = safe_load(workflow.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    jobs = data.get("jobs")
    assert isinstance(jobs, dict) and jobs, (
        f"{workflow.name} has no jobs: mapping at all -- the parse itself may be wrong"
    )
    for job_id, job in jobs.items():
        assert _job_has_own_timeout(job), (
            f"{workflow.name}::{job_id} has no job-level timeout-minutes "
            "(a step-level timeout-minutes does not count -- it bounds "
            "only that one step, not the whole job)"
        )


# ------------------------------------------------------------------ #
# issue-certificates.yml / reissue-certificate.yml / revoke-certificate.yml
# (R-23, fix round 2): the finding that opened this round --
# `certificate.issue` had a tested, correct implementation and no caller
# anywhere in this repository, because no workflow ever set
# CONVENER_SIGNING_KEY in a step that ran it. **The check below is the single
# most important one in this round**: task 7 shipped a workflow forwarding
# three of the nine environment variables its own command read, its whole
# suite stayed green, and the gap went unnoticed until a human read the
# workflow file directly, not a test failure. Derived from each command's
# own source (`ast`, the same tool this project's import-graph test in
# test_notify.py already uses to read a module rather than trust a
# docstring) rather than a hand-typed list -- a hand-copied list is the
# same defect one layer up, and would not have caught task 7's own bug
# either, since a list copied *from the workflow* reproduces exactly the
# workflow's own mistake.
# ------------------------------------------------------------------ #

CLI_MODULE_PATH = Path("tools/convener_ops/cli.py")
ISSUE_CERTIFICATES_WORKFLOW = Path(".github/workflows/issue-certificates.yml")
REISSUE_CERTIFICATE_WORKFLOW = Path(".github/workflows/reissue-certificate.yml")
REVOKE_CERTIFICATE_WORKFLOW = Path(".github/workflows/revoke-certificate.yml")
#: Task 14: the delivery step issue-certificates.yml runs after issuance,
#: and the standalone resend workflow keyed by CERTIFICATE_ID.
DELIVER_CERTIFICATE_WORKFLOW = Path(".github/workflows/deliver-certificate.yml")

#: `os.environ.get(signing.SECRET_NAME, ...)` cannot be read as a string
#: literal by the AST walk below -- it is an attribute access, not a
#: constant -- so this maps the one dotted name `issue_certificates` and
#: `reissue_certificate` read that way onto the actual secret name it
#: resolves to, itself read from `signing.py`, never retyped by hand.
_DOTTED_ENV_NAMES: dict[tuple[str, str], str] = {
    ("signing", "SECRET_NAME"): signing.SECRET_NAME
}

#: Excluded from `_env_vars_read`'s own result (R-27, fix round 1):
#: `_write_github_output` reads `GITHUB_OUTPUT` (`cli.py::issue_certificates`
#: is the new caller this round adds, through that shared helper), but this
#: is not a secret or an input a workflow author ever forwards through a
#: step's own `env:` block -- the runner already sets it, unconditionally,
#: for every step in a job. Treating it like `CONVENER_SIGNING_KEY` or
#: `CERTIFICATE_ID` would make `test_issue_certificates_workflow_carries_
#: every_env_var_the_command_reads` demand an `env:` entry that has no
#: right-hand side to write and that no workflow in this repository ever
#: needs.
_RUNNER_PROVIDED_ENV_VARS = frozenset({"GITHUB_OUTPUT"})


def _function_node(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no function named {name!r} in {path.as_posix()}")


def _literal_env_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return _DOTTED_ENV_NAMES.get((node.value.id, node.attr))
    return None


def _is_os_environ(node: ast.expr) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
        isinstance(node, ast.Name) and node.id == "environ"
    )


def _calls_platform_from_env(func: ast.FunctionDef) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "platform_from_env"
        for node in ast.walk(func)
    )


def _calls_delivery_deliver(func: ast.FunctionDef) -> bool:
    """Task 14's own analogue of `_calls_platform_from_env` above: `cli.py`
    calls `delivery.deliver(message, os.environ)` (a module-qualified
    attribute call, `confirmation.deliver`'s own calling convention --
    `cli.py` imports `delivery` as a module, never a bare name), which
    hands `os.environ` down into `confirmation.smtp_config_from_env`
    *inside `delivery.py`*, a read `_env_vars_read` cannot otherwise see
    (the same "out of this function's own scope by design" limitation its
    own docstring already names for `platform_from_env`)."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "deliver"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "delivery"
        for node in ast.walk(func)
    )


def _calls_confirmation_deliver(func: ast.FunctionDef) -> bool:
    """Task 16b's own analogue of `_calls_delivery_deliver` above:
    `cli.py::invite_survey` calls `confirmation.deliver(message, os.environ)`
    directly -- there is no dedicated transport for a survey invitation to
    duplicate (`survey_invite.py`'s own module docstring explains why it
    reuses `confirmation.Confirmation`/`confirmation.deliver` rather than
    building a third copy of the same `smtplib` wiring `delivery.py`
    already had to justify duplicating once). Kept as a second, separate
    check rather than folded into `_calls_delivery_deliver` itself: that
    one is named for, and only ever matches, `delivery.deliver`."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "deliver"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "confirmation"
        for node in ast.walk(func)
    )


def _module_function_names(path: Path) -> frozenset[str]:
    """Every function `path`'s own module defines, at any nesting depth --
    the universe `_env_vars_read`'s recursion (below) is allowed to walk
    into. Bounded to names the module itself defines, so a call to an
    *imported* function that happens to share a name with a local helper
    is never mistaken for one (an import always binds a different name in
    `ast.Call.func` than the module's own `def`, since Python has no way
    to call an imported function through a bare, undotted name that also
    resolves to something else)."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    return frozenset(
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    )


def _env_vars_read(
    path: Path, function_name: str, *, _seen: frozenset[str] = frozenset()
) -> set[str]:
    """Every environment variable `function_name` (defined in `path`)
    reads directly (`os.environ.get(...)` or `os.environ[...]`), plus --
    derived, not hand-typed -- `platform_fcc.TOKEN_ENV` whenever the
    function hands `os.environ` whole to `platform_from_env` (
    `platform_from_env`'s own body is never walked; only the fact that
    this function calls it at all, which is what actually determines
    whether the read happens).

    **Recurses into this module's own helper functions (fix round 3,
    minor 4).** The first version of this walk covered only
    `function_name`'s own body, which made it blind to a read moved out
    of that body and into a private helper -- exactly what
    `cli.py::_conference_ids_from_env` is, this same round: without this
    recursion, adding `CONVENER_FCC_CONFERENCE_ID` there would have silently
    dropped out of the set this function derives, and the check below
    that compares it against the workflow's own forwarded `env:` keys
    would have stopped meaning anything for that one variable without
    ever failing loudly. Every plain, unqualified call
    (`ast.Call.func` an `ast.Name`, never `self.foo(...)` or
    `module.foo(...)`) to a function `path`'s own module defines
    (`_module_function_names`) is walked the same way the top-level call
    is, transitively, with `_seen` guarding against infinite recursion on
    a call cycle -- none exists in this module today; every real call
    here is a strict top-down chain, so this is a safety net, not
    something expected to matter.

    Also derived, not hand-typed (task 14): `confirmation.SMTP_ENV_VARS`
    whenever the function calls `delivery.deliver` -- `_calls_delivery_deliver`,
    below, the second special case this walk knows about by name, for the
    identical reason `platform_from_env` needed one: `delivery.deliver`
    hands `os.environ` on to `confirmation.smtp_config_from_env`, a read
    genuinely inside a different module's own AST. Task 16b adds a third,
    identical case, `_calls_confirmation_deliver`: `cli.py::invite_survey`
    calls `confirmation.deliver` directly, rather than through
    `delivery.deliver`'s own indirection, so the same read needs its own
    name to match on.

    **What this still cannot see**, so the docstring does not claim more
    than the walk does: a call reached only through a name that is not a
    plain `ast.Name` or, for `delivery.deliver`/`confirmation.deliver`, a
    plain `module.attr` (a method call on an instance, a call through a
    variable holding a function reference, `getattr`-style indirection),
    and any read inside a function this module imports from elsewhere --
    `platform_from_env`, `delivery.deliver` and `confirmation.deliver` are
    the only such cases this function already knows about by name, since
    walking a different module's own AST from scratch is out of this
    function's own scope by design (it answers "what does `cli.py` read",
    not "what does everything `cli.py` calls read")."""
    if function_name in _seen:
        return set()
    func = _function_node(path, function_name)
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            callee = node.func
            if (
                isinstance(callee, ast.Attribute)
                and callee.attr == "get"
                and _is_os_environ(callee.value)
                and node.args
            ):
                name = _literal_env_name(node.args[0])
                if name and name not in _RUNNER_PROVIDED_ENV_VARS:
                    names.add(name)
        elif isinstance(node, ast.Subscript) and _is_os_environ(node.value):
            name = _literal_env_name(node.slice)
            if name and name not in _RUNNER_PROVIDED_ENV_VARS:
                names.add(name)
    if _calls_platform_from_env(func):
        names.add(platform_fcc.TOKEN_ENV)
    if _calls_delivery_deliver(func):
        names |= confirmation.SMTP_ENV_VARS
    if _calls_confirmation_deliver(func):
        names |= confirmation.SMTP_ENV_VARS

    seen = _seen | {function_name}
    local_functions = _module_function_names(path)
    called = {
        node.func.id
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for helper in called & local_functions - seen:
        names |= _env_vars_read(path, helper, _seen=seen)
    return names


def _last_path_component(
    expr: ast.expr, assigned: dict[str, ast.expr], _seen: frozenset[str] = frozenset()
) -> str | None:
    """The trailing literal component of a `Path(...) / a / b / c`-style
    chain -- either a string constant (`"registrations.enc"`) or a
    module-level constant `cli_module` itself imports by name
    (`ENCRYPTED_ATTENDANCE_FILENAME`), resolved against the real module
    rather than retyped. Recurses through `assigned` for a variable built
    in an earlier statement (`enc_path = root / rel_path`, `rel_path = ...`),
    the same "follow the assignment, do not hand-type the answer" idiom
    `_env_vars_read` already uses for environment variables."""
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return _last_path_component(expr.right, assigned, _seen)
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.Call):
        # Path("data") -- the innermost call in a chain; only reachable
        # when a chain has no `/` component after it, which none of this
        # module's own path-building does today, but this keeps the walk
        # from silently returning None for it if that ever changes.
        if expr.args:
            return _last_path_component(expr.args[-1], assigned, _seen)
        return None
    if isinstance(expr, ast.Name):
        if hasattr(cli_module, expr.id):
            value = getattr(cli_module, expr.id)
            if isinstance(value, str):
                return value
        if expr.id in assigned and expr.id not in _seen:
            return _last_path_component(assigned[expr.id], assigned, _seen | {expr.id})
    return None


def _files_written(path: Path, function_name: str) -> set[str]:
    """The filename (final path component) of every `<var>.write_text(...)`
    call inside `function_name`, derived from the assignment that built
    `<var>` -- not a hand-typed list, which is exactly the shape that let
    Critical 1 through: a fix that adds a second `write_text` call inside
    the command changes what this function returns without anyone having
    to remember to update a second, separate list."""
    func = _function_node(path, function_name)
    assigned: dict[str, ast.expr] = {}
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            assigned[node.targets[0].id] = node.value

    written: set[str] = set()
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "write_text"
            and isinstance(node.func.value, ast.Name)
        ):
            expr = assigned.get(node.func.value.id)
            if expr is not None:
                component = _last_path_component(expr, assigned)
                if component:
                    written.add(component)
    return written


def _staged_filenames(workflow_path: Path, job: str) -> set[str]:
    """Every filename `git add "..."` stages anywhere in `job`'s steps,
    read from the `run:` text rather than hand-copied -- the workflow side
    of the same derivation `_files_written` makes for the command side."""
    loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    job_data = loaded["jobs"][job]
    staged: set[str] = set()
    for step in job_data["steps"]:
        run = step.get("run", "")
        for match in re.finditer(r'git add "([^"]+)"', run):
            staged.add(Path(match.group(1)).name)
    return staged


def _workflow_step_env_keys(
    workflow_path: Path, job: str, run_contains: str
) -> set[str]:
    """The union of `job`'s own `env:` block and the `env:` block of
    whichever step's `run:` contains `run_contains` -- registration.yml's
    own split (`TARGET_BRANCH` at job level, every secret at step level),
    so a check that only read one of the two would silently pass a
    workflow that moved a variable from one to the other."""
    loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    job_data = loaded["jobs"][job]
    keys = set(job_data.get("env") or {})
    for step in job_data["steps"]:
        if run_contains in step.get("run", ""):
            keys |= set(step.get("env") or {})
            return keys
    raise AssertionError(
        f"no step in {workflow_path.as_posix()}::{job} runs a command "
        f"containing {run_contains!r}"
    )


def test_issue_certificates_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "issue_certificates")
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_SIGNING_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        # Critical B, fix round 3: read inside `_conference_ids_from_env`,
        # a helper `issue_certificates` calls -- present here only because
        # `_env_vars_read` now recurses into it (minor 4, same round).
        "CONVENER_FCC_CONFERENCE_ID",
    }, (
        "the derivation itself found an unexpected set -- either "
        "issue_certificates changed what it reads, or this AST walk no "
        "longer sees it correctly; investigate before trusting the "
        "carried-forward check below"
    )
    carried = _workflow_step_env_keys(
        ISSUE_CERTIFICATES_WORKFLOW, "issue", "convener-issue-certificates"
    )
    missing = expected - carried
    assert not missing, (
        f"issue-certificates.yml does not forward {missing} to the step "
        "that runs convener-issue-certificates, which reads it directly -- "
        "task 7 shipped exactly this gap"
    )


def test_reissue_certificate_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "reissue_certificate")
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_SIGNING_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        "CERTIFICATE_ID",
        # Critical B, fix round 3: see
        # test_issue_certificates_workflow_carries_every_env_var_the_command_reads's
        # own comment on this same addition.
        "CONVENER_FCC_CONFERENCE_ID",
    }
    carried = _workflow_step_env_keys(
        REISSUE_CERTIFICATE_WORKFLOW, "reissue", "convener-reissue-certificate"
    )
    missing = expected - carried
    assert not missing, (
        f"reissue-certificate.yml does not forward {missing} to the step "
        "that runs convener-reissue-certificate, which reads it directly"
    )


def test_revoke_certificate_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "revoke_certificate")
    assert expected == {"EVENT_ID", "CERTIFICATE_ID"}
    carried = _workflow_step_env_keys(
        REVOKE_CERTIFICATE_WORKFLOW, "revoke", "convener-revoke-certificate"
    )
    missing = expected - carried
    assert not missing, (
        f"revoke-certificate.yml does not forward {missing} to the step "
        "that runs convener-revoke-certificate, which reads it directly"
    )


# ------------------------------------------------------------------ #
# Task 14's own instance of the same check above, for the two new jobs:
# the delivery step issue-certificates.yml runs after issuance, and the
# standalone deliver-certificate.yml resend keyed by CERTIFICATE_ID. The
# brief's own instruction: "Both must forward every environment variable
# their command reads, including all five CONVENER_SMTP_* secrets -- task 7
# shipped a workflow that passed three of nine and its whole suite stayed
# green, so extend test_workflows.py's derived-environment test to cover
# the new jobs rather than writing a hand-copied list."
# ------------------------------------------------------------------ #


def test_issue_certificates_delivery_step_carries_every_env_var_it_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "deliver_certificates")
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_SIGNING_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        "CONVENER_FCC_CONFERENCE_ID",
        # R-27, fix round 1: the identifier hand-off from the issuance
        # step above, and the deliberate batch-retry override.
        "DELIVER_ONLY",
        "RESEND_ALL",
        "CONVENER_SMTP_HOST",
        "CONVENER_SMTP_PORT",
        "CONVENER_SMTP_USER",
        "CONVENER_SMTP_PASSWORD",
        "CONVENER_SMTP_FROM",
    }, (
        "the derivation itself found an unexpected set -- either "
        "deliver_certificates changed what it reads, or this AST walk no "
        "longer sees it correctly; investigate before trusting the "
        "carried-forward check below"
    )
    carried = _workflow_step_env_keys(
        ISSUE_CERTIFICATES_WORKFLOW, "issue", "convener-deliver-certificates"
    )
    missing = expected - carried
    assert not missing, (
        f"issue-certificates.yml's delivery step does not forward {missing} "
        "to the step that runs convener-deliver-certificates, which reads it "
        "directly -- task 7 shipped exactly this gap for a different command"
    )


def test_deliver_certificate_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "deliver_certificate")
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_SIGNING_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        "CONVENER_FCC_CONFERENCE_ID",
        "CERTIFICATE_ID",
        "CONVENER_SMTP_HOST",
        "CONVENER_SMTP_PORT",
        "CONVENER_SMTP_USER",
        "CONVENER_SMTP_PASSWORD",
        "CONVENER_SMTP_FROM",
    }, (
        "the derivation itself found an unexpected set -- either "
        "deliver_certificate changed what it reads, or this AST walk no "
        "longer sees it correctly; investigate before trusting the "
        "carried-forward check below"
    )
    carried = _workflow_step_env_keys(
        DELIVER_CERTIFICATE_WORKFLOW, "deliver", "convener-deliver-certificate"
    )
    missing = expected - carried
    assert not missing, (
        f"deliver-certificate.yml does not forward {missing} to the step "
        "that runs convener-deliver-certificate, which reads it directly"
    )


#: Minor 3, fix round 3: the exact names any of these workflows'
#: `workflow_dispatch` inputs may ever carry -- an allowlist, not the
#: one-word denylist (`"email" not in trigger.lower()`) this test used to
#: be. R-22's own docstring calls "never an address" "the one property
#: every input list in this trio must hold", but the old denylist let
#: `attendee_address`, `contact` or `who` sail straight through it
#: untouched. This repository already argues the general case in
#: `certificate.public_register`'s own docstring: an allowlist of exactly
#: what may leave, not a denylist of the one thing that must not.
#: `resend_all` (R-27, fix round 1) joined this set with
#: `issue-certificates.yml`'s own delivery step: a boolean, never
#: personal data, so R-22's own property still holds.
_ALLOWED_CERTIFICATE_WORKFLOW_INPUTS = frozenset(
    {"event_id", "certificate_id", "conference_id", "resend_all"}
)

#: Matches a `workflow_dispatch` input's own name -- a key indented
#: exactly six spaces under `on: / workflow_dispatch: / inputs:` in every
#: workflow file this repository writes by hand (verified against all
#: three below, and against recording.yml's own `conference_id`).
_WORKFLOW_DISPATCH_INPUT_NAME_RE = re.compile(r"^ {6}([A-Za-z_][A-Za-z0-9_]*):$", re.M)


def test_certificate_workflows_accept_only_the_allowlisted_inputs() -> None:
    """R-22: the one property every input list in this trio must hold. A
    scan over the raw `on:` trigger block's own text, the same "read
    around `on:` as raw text" idiom
    `test_publish_vitrine_paths_trigger_includes_the_certificate_register`
    already uses -- PyYAML's YAML-1.1 bool resolver reads a bare `on:` key
    as `True`, not `"on"`, so `safe_load` would silently drop this
    section's own key if it were relied on here instead."""
    for workflow_path in (
        ISSUE_CERTIFICATES_WORKFLOW,
        REISSUE_CERTIFICATE_WORKFLOW,
        REVOKE_CERTIFICATE_WORKFLOW,
        # Task 14: the same R-22 property applies to the new resend
        # workflow's own certificate_id input.
        DELIVER_CERTIFICATE_WORKFLOW,
    ):
        text = (ROOT / workflow_path).read_text(encoding="utf-8")
        trigger = text.split("jobs:")[0]
        names = set(_WORKFLOW_DISPATCH_INPUT_NAME_RE.findall(trigger))
        assert names, (
            f"{workflow_path.as_posix()}: no workflow_dispatch input names "
            "found at all -- the regex itself is wrong, which would "
            "silently empty this scan"
        )
        assert names <= _ALLOWED_CERTIFICATE_WORKFLOW_INPUTS, (
            f"{workflow_path.as_posix()} accepts "
            f"{names - _ALLOWED_CERTIFICATE_WORKFLOW_INPUTS}, not one of "
            f"{sorted(_ALLOWED_CERTIFICATE_WORKFLOW_INPUTS)} -- R-22 "
            "requires an identifier, never an address, and an allowlist "
            "is what actually enforces that, not a denylist of the one "
            "word 'email'"
        )


def test_certificate_workflows_share_one_concurrency_group_per_event() -> None:
    """All three write the same `certificates.yml` for one event -- see
    issue-certificates.yml's own comment on why the group is shared
    rather than one per workflow, the same choice discard-recording.yml
    and recording.yml already made for the FCC recording they both
    touch."""
    groups = set()
    for workflow_path in (
        ISSUE_CERTIFICATES_WORKFLOW,
        REISSUE_CERTIFICATE_WORKFLOW,
        REVOKE_CERTIFICATE_WORKFLOW,
    ):
        loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
        concurrency = loaded.get("concurrency")
        assert isinstance(concurrency, dict), (
            f"{workflow_path.as_posix()} has no concurrency group"
        )
        assert concurrency.get("cancel-in-progress") is False, (
            f"{workflow_path.as_posix()}: a run mid-write to "
            "certificates.yml must finish, never be cancelled by another "
            "one starting"
        )
        groups.add(concurrency["group"])
    assert len(groups) == 1, (
        f"the three certificate workflows use different concurrency "
        f"group templates ({groups}) -- they write the same file and "
        "must serialise against each other, not only against themselves"
    )


@pytest.mark.parametrize(
    "workflow_path,job",
    [
        (ISSUE_CERTIFICATES_WORKFLOW, "issue"),
        (REISSUE_CERTIFICATE_WORKFLOW, "reissue"),
        (REVOKE_CERTIFICATE_WORKFLOW, "revoke"),
    ],
    ids=lambda value: value if isinstance(value, str) else value.name,
)
def test_certificate_workflow_job_has_write_permission_and_a_timeout(
    workflow_path: Path, job: str
) -> None:
    loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    job_data = loaded["jobs"][job]
    # Critical A, fix round 3: `actions: write` joined `contents: write`
    # in all three jobs -- each now dispatches publish-vitrine.yml as its
    # own last step once it has actually committed something, which needs
    # that permission (`workflow_dispatch` is the documented exception to
    # GitHub's recursion guard, so no new secret is needed).
    assert job_data.get("permissions") == {
        "contents": "write",
        "actions": "write",
    }, (
        f"{workflow_path.as_posix()}::{job} commits a change to "
        "certificates.yml (needs contents: write) and dispatches "
        "publish-vitrine.yml afterwards (needs actions: write)"
    )
    assert isinstance(job_data.get("timeout-minutes"), int), (
        f"{workflow_path.as_posix()}::{job} has no timeout-minutes"
    )


# ------------------------------------------------------------------ #
# Critical A, fix round 3: GitHub does not start a new workflow run from
# an event triggered by a job's own GITHUB_TOKEN (the recursion guard),
# so a push made by any of the three certificate workflows -- or by
# sweep.yml -- could never fire publish-vitrine.yml's own `push`-triggered
# `paths:` trigger, no matter how carefully R-19 (fix round 1) worded it.
# Each of those four jobs now dispatches publish-vitrine.yml directly,
# with `gh workflow run`, as its own last step -- `workflow_dispatch` is
# the one documented exception to the recursion guard. Text assertions on
# the parsed `run:` block, the same idiom this module already uses
# throughout (see this module's own docstring for why: running the script
# means a real `gh` call, exactly the kind of network access this suite
# must not take on).
# ------------------------------------------------------------------ #

PUBLISH_VITRINE_DISPATCH = "gh workflow run publish-vitrine.yml"
SWEEP_WORKFLOW = Path(".github/workflows/sweep.yml")


def _job_step_script(workflow_path: Path, job: str, run_contains: str) -> str:
    loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    for step in loaded["jobs"][job]["steps"]:
        if run_contains in step.get("run", ""):
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        f"no step in {workflow_path.as_posix()}::{job} runs a command "
        f"containing {run_contains!r}"
    )


def _guarded_block(script: str, if_line: str) -> str:
    """The slice of `script` between `if_line` and its own matching `fi`
    -- the same "isolate to the one guard, not the whole script" technique
    `test_deploy_workflow_push_step_guards_on_missing_token` already uses,
    so a line that is merely *somewhere* in the script, rather than
    genuinely inside this one guard, cannot satisfy an assertion built on
    this helper.

    The matching `fi` is found at `if_line`'s own indentation, not a fixed
    two spaces: sweep.yml's own "nothing to commit" guard sits at the top
    level (an unindented `fi`), while the three certificate workflows'
    equivalent guard sits inside a `for` loop (a two-space `fi`) -- a
    fixed search would either miss the first or, worse, overshoot past it
    into an unrelated, later `fi` at a different nesting depth and
    silently return a block spanning two guards at once."""
    start_at = script.find(if_line)
    assert start_at != -1, f"no {if_line!r} guard found in this script"
    line_start = script.rfind("\n", 0, start_at) + 1
    indent = script[line_start:start_at]
    closing = f"\n{indent}fi"
    end_at = script.find(closing, start_at)
    assert end_at != -1, f"the {if_line!r} guard has no matching fi"
    return script[start_at : end_at + len(closing)]


@pytest.mark.parametrize(
    "workflow_path,job,run_contains",
    [
        (ISSUE_CERTIFICATES_WORKFLOW, "issue", "convener-issue-certificates"),
        (REISSUE_CERTIFICATE_WORKFLOW, "reissue", "convener-reissue-certificate"),
        (REVOKE_CERTIFICATE_WORKFLOW, "revoke", "convener-revoke-certificate"),
    ],
    ids=lambda value: value if isinstance(value, str) else value.name,
)
def test_certificate_workflow_dispatches_publish_vitrine_only_after_a_real_push(
    workflow_path: Path, job: str, run_contains: str
) -> None:
    """The mutation this round's own ruling names directly: "make the
    publication dispatch step unconditional, or delete it. A test must
    fail." Two halves, both required: the dispatch must be reachable once
    a push genuinely succeeds, and must not be reachable on the "nothing
    to commit" branch, where nothing was ever pushed for a publication to
    reflect."""
    script = _job_step_script(workflow_path, job, run_contains)

    pushed = _guarded_block(script, "if git push; then")
    assert PUBLISH_VITRINE_DISPATCH in pushed, (
        f"{workflow_path.as_posix()}::{job} does not dispatch "
        "publish-vitrine.yml once a change is genuinely pushed -- a "
        "revocation, issuance or correction would reach nobody (Critical A)"
    )

    unchanged = _guarded_block(script, "if git diff --staged --quiet; then")
    assert PUBLISH_VITRINE_DISPATCH not in unchanged, (
        f"{workflow_path.as_posix()}::{job} dispatches publish-vitrine.yml "
        "even when nothing changed this run -- the dispatch step must be "
        "conditional on a real push, not unconditional"
    )


def test_sweep_workflow_dispatches_publish_vitrine_only_after_a_real_push() -> None:
    """The same fix, and the same two-halves guard, for sweep.yml -- the
    re-review found the identical suppression there (a phase-3 defect:
    `events-public.json` has never been republished after a nightly sweep,
    since sweep.yml also pushes `data/speakers.yml` with GITHUB_TOKEN)."""
    script = _job_step_script(SWEEP_WORKFLOW, "sweep", "git commit -m")

    pushed = _guarded_block(script, "if git push; then")
    assert PUBLISH_VITRINE_DISPATCH in pushed, (
        "sweep.yml does not dispatch publish-vitrine.yml once a change is "
        "genuinely pushed -- events-public.json would never be republished "
        "after a sweep (Critical A)"
    )

    unchanged = _guarded_block(script, "if git diff --staged --quiet; then")
    assert PUBLISH_VITRINE_DISPATCH not in unchanged, (
        "sweep.yml dispatches publish-vitrine.yml even when nothing changed this run"
    )


# ------------------------------------------------------------------ #
# Critical 1 (fix round 1, task 13): dispatching publish-vitrine.yml alone
# was never enough for a workflow that changes the certificate register --
# that workflow rebuilds src/_data/certificates.json in the showcase,
# which nothing there ever served (Minor 5, removed). The file
# `src/verify/register.ts` actually fetches is only rebuilt by
# deploy.yml's own "Build public data" step, and nothing dispatched it:
# `grep -rn "gh workflow run" .github/workflows/` returned four hits, all
# four naming publish-vitrine.yml, none naming deploy.yml. This had
# already failed four rounds in a row -- published by no workflow, then a
# trigger no push could fire, then a destination that serves nothing, now
# a rebuild nobody triggers -- so this test is written to catch the whole
# class, not this one instance: it finds every workflow job that actually
# stages a change to a certificates.yml register (by its own `git add`
# line, not a hand-maintained list of workflow names a future
# certificate-writing workflow could simply be left off of), and requires
# *both* dispatches to sit in the same pushed guard. A test that only
# checked "some dispatch exists" -- the shape every earlier round's own
# test family had -- would have passed all four times this broke.
# ------------------------------------------------------------------ #

DEPLOY_DISPATCH = "gh workflow run deploy.yml"

_CERTIFICATES_STAGED_RE = re.compile(r'git add ["\'][^\n"\']*certificates\.yml')


def _register_writing_jobs() -> list[tuple[Path, str]]:
    """Every `(workflow, job)` pair whose own script stages a change to a
    `certificates.yml` register file -- found dynamically rather than
    named by a fixed parametrize list, so a future workflow that starts
    writing the register is covered here automatically, not only the
    three named elsewhere in this module today."""
    hits: list[tuple[Path, str]] = []
    for path in _workflow_files():
        loaded = safe_load((ROOT / path).read_text(encoding="utf-8"))
        for job_name, job in (loaded.get("jobs") or {}).items():
            for step in job.get("steps", []):
                run = step.get("run", "")
                if isinstance(run, str) and _CERTIFICATES_STAGED_RE.search(run):
                    hits.append((path, job_name))
                    break
    assert hits, (
        "no workflow job stages a change to certificates.yml -- this "
        "detector is broken, not that the register has stopped being written"
    )
    return hits


@pytest.mark.parametrize(
    "workflow_path,job",
    _register_writing_jobs(),
    ids=lambda value: value if isinstance(value, str) else value.name,
)
def test_workflow_that_writes_the_certificate_register_dispatches_both_publish_targets(
    workflow_path: Path, job: str
) -> None:
    """A workflow that changes `certificates.yml` and pushes with
    GITHUB_TOKEN must dispatch publish-vitrine.yml *and* deploy.yml once
    that push genuinely lands, or it does not count: publish-vitrine.yml
    alone only ever refreshed a showcase file nothing serves; deploy.yml
    is what rebuilds app/dist/certificates.json, the file a verification
    page actually fetches. One assertion that both names sit in the same
    guard -- not two separate "a dispatch exists" checks, which is
    exactly the weaker shape that let a workflow dispatch only one of the
    two survive three earlier fix rounds undetected."""
    loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    run = next(
        step["run"]
        for step in loaded["jobs"][job]["steps"]
        if isinstance(step.get("run"), str)
        and _CERTIFICATES_STAGED_RE.search(step["run"])
    )
    pushed = _guarded_block(run, "if git push; then")
    assert PUBLISH_VITRINE_DISPATCH in pushed, (
        f"{workflow_path.as_posix()}::{job} changes the certificate "
        "register and pushes it, but does not dispatch publish-vitrine.yml"
    )
    assert DEPLOY_DISPATCH in pushed, (
        f"{workflow_path.as_posix()}::{job} changes the certificate "
        "register and pushes it, but does not dispatch deploy.yml -- the "
        "file src/verify/register.ts actually fetches would never be "
        "rebuilt (Critical 1)"
    )


@pytest.mark.parametrize(
    "workflow_path,job,run_contains",
    [
        (ISSUE_CERTIFICATES_WORKFLOW, "issue", "convener-issue-certificates"),
        (REISSUE_CERTIFICATE_WORKFLOW, "reissue", "convener-reissue-certificate"),
        (REVOKE_CERTIFICATE_WORKFLOW, "revoke", "convener-revoke-certificate"),
    ],
    ids=lambda value: value if isinstance(value, str) else value.name,
)
def test_certificate_workflow_dispatch_step_authenticates_with_the_job_token(
    workflow_path: Path, job: str, run_contains: str
) -> None:
    """`gh workflow run` needs `GH_TOKEN` (or `GITHUB_TOKEN`) in its own
    environment to authenticate at all -- without it, the dispatch call
    itself would fail every time, silently defeating Critical A's own fix
    from inside the one step meant to carry it out."""
    carried = _workflow_step_env_keys(workflow_path, job, run_contains)
    assert "GH_TOKEN" in carried, (
        f"{workflow_path.as_posix()}::{job} calls gh workflow run without "
        "GH_TOKEN in its own env -- the dispatch call would fail to "
        "authenticate"
    )


def test_publish_vitrine_workflow_dispatch_is_enabled() -> None:
    """Critical A (fix round 3): the `paths:` trigger alone is
    unreachable from any of the four jobs that write the paths it names,
    since all four commit with their own GITHUB_TOKEN (the recursion
    guard) -- `workflow_dispatch` is what each of those jobs' own
    dispatch step (above) actually calls."""
    text = (ROOT / PUBLISH_VITRINE_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "workflow_dispatch:" in trigger, (
        "publish-vitrine.yml has no workflow_dispatch trigger -- nothing "
        "could ever call `gh workflow run publish-vitrine.yml`"
    )


@pytest.mark.parametrize(
    "workflow_path,job,run_contains",
    [
        (ISSUE_CERTIFICATES_WORKFLOW, "issue", "convener-issue-certificates"),
        (REISSUE_CERTIFICATE_WORKFLOW, "reissue", "convener-reissue-certificate"),
        (REVOKE_CERTIFICATE_WORKFLOW, "revoke", "convener-revoke-certificate"),
    ],
    ids=lambda value: value if isinstance(value, str) else value.name,
)
def test_certificate_workflow_warns_when_a_dispatched_run_writes_nothing(
    workflow_path: Path, job: str, run_contains: str
) -> None:
    """Small item 1, fix round 3: a dispatched job that writes nothing
    still exits 0 (D-13 still holds -- this is not turned into a
    failure), but a `::warning::` annotation is what stops "it worked" and
    "it skipped" from looking identical on the run's own summary page,
    which matters most for `config/integrations.yml`'s own
    `certificate_fingerprint` row -- the one absence it deliberately
    declares `absent_is_normal: false`."""
    script = _job_step_script(workflow_path, job, run_contains)
    unchanged = _guarded_block(script, "if git diff --staged --quiet; then")
    assert "::warning::" in unchanged, (
        f"{workflow_path.as_posix()}::{job} exits cleanly when it writes "
        "nothing, with no warning annotation -- a dispatched run that did "
        "nothing looks identical to one that worked"
    )


# ------------------------------------------------------------------ #
# deliver-certificate.yml: read-only, unlike the three workflows above --
# it never writes certificates.yml (delivery is not a register state,
# R-20) and never commits anything.
# ------------------------------------------------------------------ #


def _deliver_certificate_workflow() -> dict[str, Any]:
    loaded = safe_load(
        (ROOT / DELIVER_CERTIFICATE_WORKFLOW).read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    return loaded


def test_deliver_certificate_workflow_is_read_only_and_has_a_timeout() -> None:
    job = _deliver_certificate_workflow()["jobs"]["deliver"]
    assert job.get("permissions") == {"contents": "read"}, (
        "deliver-certificate.yml commits nothing and dispatches nothing -- "
        "it needs no write permission at all, unlike the three certificate "
        "workflows that write certificates.yml"
    )
    assert isinstance(job.get("timeout-minutes"), int), (
        "deliver-certificate.yml has no timeout-minutes"
    )


def test_deliver_certificate_workflow_is_dispatchable_by_hand() -> None:
    """A command nothing invokes is not delivered work -- this phase has
    shipped that four times already. This is the check that the resend
    path is actually reachable from the Actions tab."""
    text = (ROOT / DELIVER_CERTIFICATE_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "workflow_dispatch:" in trigger


def test_deliver_certificate_workflow_has_its_own_concurrency_group() -> None:
    """Minor 7, fix round 1: two concurrent dispatches for the *same*
    certificate would otherwise send two e-mails. Keyed on
    `certificate_id` alone -- narrower than, and never shared with, the
    three certificate workflows' own `certificates-<event id>` group
    (which this workflow never writes anything to at all)."""
    loaded = _deliver_certificate_workflow()
    concurrency = loaded.get("concurrency")
    assert isinstance(concurrency, dict), (
        "deliver-certificate.yml has no concurrency group"
    )
    assert concurrency.get("group") == "deliver-${{ inputs.certificate_id }}"
    assert concurrency.get("cancel-in-progress") is False, (
        "a resend mid-flight must finish, never be cancelled by another "
        "dispatch for the same certificate starting"
    )


# ------------------------------------------------------------------ #
# R-27, fix round 1: the issue step hands its own freshly-issued
# identifiers to the delivery step, which restricts itself to that set by
# default; Minor 8 stops a transient delivery failure from masking that
# the certificates were already committed and pushed.
# ------------------------------------------------------------------ #


def _issue_certificates_workflow() -> dict[str, Any]:
    loaded = safe_load((ROOT / ISSUE_CERTIFICATES_WORKFLOW).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_issue_step_has_an_id_the_delivery_step_can_read_outputs_from() -> None:
    loaded = _issue_certificates_workflow()
    steps = loaded["jobs"]["issue"]["steps"]
    issue_step = next(
        step for step in steps if "convener-issue-certificates" in step.get("run", "")
    )
    assert issue_step.get("id") == "issue", (
        "the step running convener-issue-certificates has no id -- "
        "steps.issue.outputs.issued_ids could not resolve to anything"
    )


def test_delivery_step_reads_deliver_only_from_the_issue_steps_own_output() -> None:
    """Pins the exact expression, not only that the key exists (the env
    var test above already covers that): a mutation that hardcoded
    `DELIVER_ONLY` to the empty string, or read some other step's output,
    would still carry the right *name* and pass that test while
    delivering to nobody -- or everybody -- regardless of what the issue
    step actually minted."""
    carried = _workflow_step_env(
        ISSUE_CERTIFICATES_WORKFLOW, "issue", "convener-deliver-certificates"
    )
    assert carried.get("DELIVER_ONLY") == "${{ steps.issue.outputs.issued_ids }}"
    assert carried.get("RESEND_ALL") == "${{ inputs.resend_all }}"


def _workflow_step_env(
    workflow_path: Path, job: str, run_contains: str
) -> dict[str, Any]:
    loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    for step in loaded["jobs"][job]["steps"]:
        if run_contains in step.get("run", ""):
            env = step.get("env") or {}
            assert isinstance(env, dict)
            return env
    raise AssertionError(
        f"no step in {workflow_path.as_posix()}::{job} runs a command "
        f"containing {run_contains!r}"
    )


def test_delivery_step_does_not_fail_the_whole_run_on_its_own() -> None:
    """Minor 8, fix round 1: a transient failure re-fetching attendance in
    this step must not mark the whole run red after the certificates were
    already committed and pushed by the step before it."""
    loaded = _issue_certificates_workflow()
    steps = loaded["jobs"]["issue"]["steps"]
    delivery_step = next(
        step for step in steps if "convener-deliver-certificates" in step.get("run", "")
    )
    assert delivery_step.get("continue-on-error") is True


def test_issue_certificates_workflow_has_a_resend_all_input_defaulting_false() -> None:
    """`loaded[True]`, not `loaded["on"]` -- PyYAML's YAML-1.1 bool
    resolver reads a bare `on:` key as `True`, the same gotcha
    `test_certificate_workflows_accept_only_the_allowlisted_inputs`'s own
    docstring already names for this file."""
    loaded = _issue_certificates_workflow()
    inputs = loaded[True]["workflow_dispatch"]["inputs"]
    assert inputs["resend_all"]["type"] == "boolean"
    assert inputs["resend_all"]["default"] is False
    assert inputs["resend_all"]["required"] is False


# ------------------------------------------------------------------ #
# M1, fix round 1 (task 16b's review): the widened AST walk
# (`_calls_confirmation_deliver`) surfaced a pre-existing gap that
# predates this whole task -- `_send_confirmation` (`cli.py::_send_confirmation`)
# resolves the room link through `platform_from_env`, which reads
# `CONVENER_MEETING_API_TOKEN`, and neither workflow that reaches it forwarded
# it. Benign today (the confirmation falls back to the manual `zoom_link`
# rather than failing), but the same class of defect this whole derived-
# environment idiom exists to catch, so it is asserted here now that the
# walk can see it at all.
# ------------------------------------------------------------------ #

REGISTRATION_WORKFLOW = Path(".github/workflows/registration.yml")
RESEND_CONFIRMATION_WORKFLOW = Path(".github/workflows/resend-confirmation.yml")


def test_registration_workflow_send_step_carries_every_env_var_the_command_reads() -> (
    None
):
    expected = _env_vars_read(CLI_MODULE_PATH, "send_confirmation")
    assert expected == {
        "REGISTRATION_PAYLOAD",
        "EVENT_PRIVATE_KEY",
        "CHANGED_FIELDS",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        *confirmation.SMTP_ENV_VARS,
    }, (
        "the derivation itself found an unexpected set -- either "
        "send_confirmation changed what it reads, or this AST walk no "
        "longer sees it correctly"
    )
    carried = _workflow_step_env_keys(
        REGISTRATION_WORKFLOW, "handle", "convener-send-confirmation"
    )
    missing = expected - carried
    assert not missing, (
        f"registration.yml does not forward {missing} to the step that "
        "runs convener-send-confirmation, which reads it directly"
    )


def test_resend_confirmation_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "resend_confirmation")
    assert expected == {
        "EVENT_ID",
        "REGISTRATION_EMAIL",
        "EVENT_PRIVATE_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        *confirmation.SMTP_ENV_VARS,
    }, (
        "the derivation itself found an unexpected set -- either "
        "resend_confirmation changed what it reads, or this AST walk no "
        "longer sees it correctly"
    )
    carried = _workflow_step_env_keys(
        RESEND_CONFIRMATION_WORKFLOW, "resend", "convener-resend-confirmation"
    )
    missing = expected - carried
    assert not missing, (
        f"resend-confirmation.yml does not forward {missing} to the step "
        "that runs convener-resend-confirmation, which reads it directly"
    )


# ------------------------------------------------------------------ #
# Task 15: retention.yml and erase-registration.yml. Same derived-
# environment idiom as the certificate trio above -- the whole reason it
# exists (this section's own header comment) is a workflow that forwards
# three of nine environment variables its own command reads while its
# test suite stays green; a hand-typed list here would reproduce exactly
# that gap rather than catch it.
# ------------------------------------------------------------------ #

RETENTION_WORKFLOW = Path(".github/workflows/retention.yml")
ERASE_REGISTRATION_WORKFLOW = Path(".github/workflows/erase-registration.yml")


def test_retention_sweep_step_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "retention_sweep")
    assert expected == {"CONVENER_RETENTION_TOKEN"}, (
        "the derivation itself found an unexpected set -- either "
        "retention_sweep changed what it reads, or this AST walk no "
        "longer sees it correctly; investigate before trusting the "
        "carried-forward check below"
    )
    carried = _workflow_step_env_keys(
        RETENTION_WORKFLOW, "retention", "convener-retention-sweep"
    )
    missing = expected - carried
    assert not missing, (
        f"retention.yml does not forward {missing} to the step that runs "
        "convener-retention-sweep, which reads it directly -- R-28's own "
        "failure mode would go unenforced in production"
    )


def test_record_destructions_step_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "record_destructions")
    assert expected == {"DESTROYED_IDS", "DESTROYED_ON"}
    carried = _workflow_step_env_keys(
        RETENTION_WORKFLOW, "retention", "convener-record-destructions"
    )
    missing = expected - carried
    assert not missing, (
        f"retention.yml does not forward {missing} to the step that runs "
        "convener-record-destructions, which reads it directly"
    )


def test_erase_registration_step_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "erase_registration")
    assert expected == {
        "EVENT_ID",
        "MATCHING_CODE",
        "REGISTRATION_EMAIL",
        "EVENT_PRIVATE_KEY",
        "CONVENER_MATCHING_SALT",
    }
    carried = _workflow_step_env_keys(
        ERASE_REGISTRATION_WORKFLOW, "erase", "convener-erase-registration"
    )
    missing = expected - carried
    assert not missing, (
        f"erase-registration.yml does not forward {missing} to the step "
        "that runs convener-erase-registration, which reads it directly"
    )


def test_erase_registration_workflow_stages_every_file_the_command_writes() -> None:
    """Critical 1: `convener-erase-registration` rewrites two files when the
    erased person has attendance rows (R-45, `cli.py:1451-1457`), and
    `erase-registration.yml` staged only one -- the rewritten attendance
    export died with the runner while the job's own log claimed it was
    committed. `_files_written` derives the set from the command's own
    source rather than a hand-typed list, which is how the gap survived
    every review of the two halves separately; a future third file this
    command starts writing needs no matching edit here to stay caught."""
    written = _files_written(CLI_MODULE_PATH, "erase_registration")
    assert written == {"registrations.enc", "attendance-import.csv.enc"}, (
        "the derivation itself found an unexpected set -- either "
        "erase_registration changed what it writes, or this AST walk no "
        "longer sees it correctly; investigate before trusting the "
        "staged-files check below"
    )
    staged = _staged_filenames(ERASE_REGISTRATION_WORKFLOW, "erase")
    missing = written - staged
    assert not missing, (
        f"erase-registration.yml does not stage {missing}, which "
        "convener-erase-registration writes -- that rewrite dies with the "
        "runner while the job reports it committed"
    )


def test_retention_workflow_is_both_scheduled_and_dispatchable() -> None:
    """R-33: a retention job that only runs when somebody remembers is
    the failure this task exists to prevent -- scheduled, with
    workflow_dispatch for a manual run, the same pairing sweep.yml already
    uses for its own daily job."""
    text = (ROOT / RETENTION_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "schedule:" in trigger
    assert "cron:" in trigger
    assert "workflow_dispatch:" in trigger


def test_erase_registration_workflow_is_dispatchable_by_hand() -> None:
    """The same check `test_deliver_certificate_workflow_is_dispatchable_
    by_hand` already makes for task 14's own resend path: a command
    nothing invokes is not delivered work."""
    text = (ROOT / ERASE_REGISTRATION_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "workflow_dispatch:" in trigger


def test_retention_workflow_job_has_write_permission_and_a_timeout() -> None:
    loaded = safe_load((ROOT / RETENTION_WORKFLOW).read_text(encoding="utf-8"))
    job = loaded["jobs"]["retention"]
    # Important 2, branch review: `actions: write` joined `contents:
    # write` -- the same pairing the three certificate workflows and
    # sweep.yml already carry, for the identical recursion-guard reason.
    assert job.get("permissions") == {"contents": "write", "actions": "write"}
    assert isinstance(job.get("timeout-minutes"), int)


def test_retention_workflow_dispatches_both_publish_targets_after_a_real_push() -> None:
    """Important 2, branch review: `record_destructions` deletes a
    destroyed event's `keys/events/<id>.pub` and this job pushes that
    deletion with `GITHUB_TOKEN`, the recursion guard `publish-vitrine.
    yml`'s own header comment names. Without a direct dispatch, nothing
    ever reruns `copy-event-keys.mjs`, so the deployed app bundle keeps
    serving a destroyed event's public key -- the signup relay's own
    "this event is open" gate -- until an unrelated push to `main`
    happens to rebuild it. Same shape as `test_workflow_that_writes_the_
    certificate_register_dispatches_both_publish_targets`: both dispatch
    names must sit in the same pushed guard, and neither in the
    nothing-changed one."""
    script = _job_step_script(
        RETENTION_WORKFLOW, "retention", "convener-record-destructions"
    )

    pushed = _guarded_block(script, "if git push; then")
    assert PUBLISH_VITRINE_DISPATCH in pushed, (
        "retention.yml changes keys/events and the destruction registry "
        "and pushes it, but does not dispatch publish-vitrine.yml"
    )
    assert DEPLOY_DISPATCH in pushed, (
        "retention.yml changes keys/events and the destruction registry "
        "and pushes it, but does not dispatch deploy.yml -- a destroyed "
        "event's public key would keep being served from the deployed "
        "app bundle (Important 2)"
    )

    unchanged = _guarded_block(script, "if git diff --staged --quiet; then")
    assert PUBLISH_VITRINE_DISPATCH not in unchanged, (
        "retention.yml dispatches publish-vitrine.yml even when nothing "
        "changed this run"
    )
    assert DEPLOY_DISPATCH not in unchanged, (
        "retention.yml dispatches deploy.yml even when nothing changed this run"
    )


def test_retention_workflow_dispatch_step_authenticates_with_the_job_token() -> None:
    """`gh workflow run` needs `GH_TOKEN` (or `GITHUB_TOKEN`) in its own
    environment to authenticate at all -- the same check
    `test_certificate_workflow_dispatch_step_authenticates_with_the_job_
    token` already makes for the three certificate workflows."""
    carried = _workflow_step_env_keys(
        RETENTION_WORKFLOW, "retention", "convener-record-destructions"
    )
    assert "GH_TOKEN" in carried, (
        "retention.yml calls gh workflow run without GH_TOKEN in its own "
        "env -- the dispatch call would fail to authenticate"
    )


def test_erase_registration_workflow_job_has_write_permission_and_a_timeout() -> None:
    loaded = safe_load((ROOT / ERASE_REGISTRATION_WORKFLOW).read_text(encoding="utf-8"))
    job = loaded["jobs"]["erase"]
    assert job.get("permissions") == {"contents": "write"}
    assert isinstance(job.get("timeout-minutes"), int)


def test_retention_workflow_has_its_own_concurrency_group() -> None:
    loaded = safe_load((ROOT / RETENTION_WORKFLOW).read_text(encoding="utf-8"))
    concurrency = loaded.get("concurrency")
    assert isinstance(concurrency, dict)
    assert concurrency.get("group") == "retention-sweep"
    assert concurrency.get("cancel-in-progress") is False


def test_erase_registration_workflow_has_a_concurrency_group() -> None:
    """Important 5: every other writing dispatch workflow has one; this
    one shares registration.yml's own group name deliberately, since both
    workflows write the same `registrations.enc`."""
    loaded = safe_load((ROOT / ERASE_REGISTRATION_WORKFLOW).read_text(encoding="utf-8"))
    concurrency = loaded.get("concurrency")
    assert isinstance(concurrency, dict)
    assert concurrency.get("group") == "registration-${{ inputs.event_id }}"
    assert concurrency.get("cancel-in-progress") is False


# ------------------------------------------------------------------ #
# Task 16b: invite-survey.yml. Same derived-environment idiom as the
# certificate trio above -- the same gap this whole idiom exists to catch
# (task 7's workflow forwarding three of nine variables its own command
# read) applies just as much to a brand-new workflow as to an edited one.
# ------------------------------------------------------------------ #

INVITE_SURVEY_WORKFLOW = Path(".github/workflows/invite-survey.yml")


def _invite_survey_workflow() -> dict[str, Any]:
    return safe_load((ROOT / INVITE_SURVEY_WORKFLOW).read_text(encoding="utf-8"))


def test_invite_survey_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "invite_survey")
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_MATCHING_SALT",
        "RESEND_ALL",
        "CONVENER_MEETING_API_TOKEN",
        "CONVENER_FCC_CONFERENCE_ID",
        *confirmation.SMTP_ENV_VARS,
    }, (
        "the derivation itself found an unexpected set -- either "
        "invite_survey changed what it reads, or this AST walk no longer "
        "sees it correctly; investigate before trusting the carried-forward "
        "check below"
    )
    carried = _workflow_step_env_keys(
        INVITE_SURVEY_WORKFLOW, "invite", "convener-invite-survey"
    )
    missing = expected - carried
    assert not missing, (
        f"invite-survey.yml does not forward {missing} to the step that "
        "runs convener-invite-survey, which reads it directly -- task 7 shipped "
        "exactly this gap"
    )


def test_record_survey_invitation_step_carries_every_env_var_the_command_reads() -> (
    None
):
    expected = _env_vars_read(CLI_MODULE_PATH, "record_survey_invitation")
    assert expected == {"EVENT_ID"}
    carried = _workflow_step_env_keys(
        INVITE_SURVEY_WORKFLOW, "invite", "convener-record-survey-invitation"
    )
    missing = expected - carried
    assert not missing, (
        f"invite-survey.yml does not forward {missing} to the step that "
        "runs convener-record-survey-invitation, which reads it directly"
    )


def test_invite_survey_workflow_is_dispatchable_by_hand_only() -> None:
    loaded = _invite_survey_workflow()
    assert set(loaded[True]) == {"workflow_dispatch"}, (
        "invite-survey.yml must be reachable only by an operator's own "
        "decision -- never scheduled, never triggered by a push: an "
        "invitation is an outbound message to real people"
    )


def test_invite_survey_workflow_has_a_resend_all_input_defaulting_false() -> None:
    loaded = _invite_survey_workflow()
    inputs = loaded[True]["workflow_dispatch"]["inputs"]
    assert inputs["resend_all"]["type"] == "boolean"
    assert inputs["resend_all"]["default"] is False
    assert inputs["resend_all"]["required"] is False


def test_invite_survey_workflow_job_has_write_permission_and_a_timeout() -> None:
    loaded = _invite_survey_workflow()
    job = loaded["jobs"]["invite"]
    assert job.get("permissions") == {"contents": "write"}
    assert isinstance(job.get("timeout-minutes"), int)


def test_invite_survey_workflow_has_its_own_concurrency_group() -> None:
    loaded = _invite_survey_workflow()
    concurrency = loaded.get("concurrency")
    assert isinstance(concurrency, dict)
    assert concurrency.get("group") == "survey-invite-${{ inputs.event_id }}"
    assert concurrency.get("cancel-in-progress") is False


def test_invite_survey_workflow_records_only_when_something_was_sent() -> None:
    """The whole point of the two-step split (`invite_survey`'s own
    docstring): the recording step must be conditioned on the send step's
    own `record` output, never run unconditionally -- an unconditional
    record would mark an event invited even on a run that sent nothing."""
    loaded = _invite_survey_workflow()
    steps = loaded["jobs"]["invite"]["steps"]
    record_step = next(
        step for step in steps if "convener-record-survey-invitation" in step.get("run", "")
    )
    assert record_step.get("if") == "steps.invite.outputs.record == 'true'"


# ------------------------------------------------------------------ #
# I-4, branch review: match-attendance.yml is what makes
# `convener-match-attendance` reachable at all -- before this workflow existed,
# two others' own header comments told a volunteer to run it by hand, a
# command that reads EVENT_PRIVATE_KEY, which by design never touches a
# laptop. Same derived-environment idiom as the certificate trio and
# invite-survey.yml above.
# ------------------------------------------------------------------ #

MATCH_ATTENDANCE_WORKFLOW = Path(".github/workflows/match-attendance.yml")


def test_match_attendance_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(CLI_MODULE_PATH, "match_attendance")
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        "CONVENER_FCC_CONFERENCE_ID",
    }, (
        "the derivation itself found an unexpected set -- either "
        "match_attendance changed what it reads, or this AST walk no "
        "longer sees it correctly; investigate before trusting the "
        "carried-forward check below"
    )
    carried = _workflow_step_env_keys(
        MATCH_ATTENDANCE_WORKFLOW, "match", "convener-match-attendance"
    )
    missing = expected - carried
    assert not missing, (
        f"match-attendance.yml does not forward {missing} to the step "
        "that runs convener-match-attendance, which reads it directly"
    )


def test_match_attendance_workflow_is_dispatchable_by_hand_only() -> None:
    loaded = safe_load((ROOT / MATCH_ATTENDANCE_WORKFLOW).read_text(encoding="utf-8"))
    assert set(loaded[True]) == {"workflow_dispatch"}, (
        "match-attendance.yml must be reachable only by an operator's own "
        "decision, the same as the workflows that depend on it"
    )


def test_match_attendance_workflow_job_has_read_permission_and_a_timeout() -> None:
    loaded = safe_load((ROOT / MATCH_ATTENDANCE_WORKFLOW).read_text(encoding="utf-8"))
    job = loaded["jobs"]["match"]
    assert job.get("permissions") == {"contents": "read"}, (
        "match_attendance never writes to the repository -- a write "
        "permission here would be broader than this job ever needs"
    )
    assert isinstance(job.get("timeout-minutes"), int)


def test_match_attendance_workflow_has_its_own_concurrency_group() -> None:
    loaded = safe_load((ROOT / MATCH_ATTENDANCE_WORKFLOW).read_text(encoding="utf-8"))
    concurrency = loaded.get("concurrency")
    assert isinstance(concurrency, dict)
    assert concurrency.get("group") == "match-attendance-${{ inputs.event_id }}"


def test_match_attendance_workflow_uploads_the_unmatched_list_privately() -> None:
    """The only artefact naming who could not be matched, and the only
    place acceptance criterion 9's own distinction ever reaches a human --
    must be a short-retention, access-controlled build artefact, never a
    public one, the same restriction `cli.py::UNMATCHED_ATTENDANCE`'s own
    comment requires."""
    loaded = safe_load((ROOT / MATCH_ATTENDANCE_WORKFLOW).read_text(encoding="utf-8"))
    steps = loaded["jobs"]["match"]["steps"]
    upload = next(
        step
        for step in steps
        if step.get("uses", "").startswith("actions/upload-artifact")
    )
    assert upload["with"]["path"] == "unmatched-attendance.md"
    assert upload["with"]["retention-days"] == 14
    assert upload["if"] == "always()"


# ------------------------------------------------------------------ #
# R-34: the "Delete the destroyed event keys" step, executed for real
# under a stubbed `gh` on PATH -- the constraint that no test may touch
# the network, applied to shell rather than Python. The critical defect
# this reproduces (a `break` that abandons a healthy later event, and a
# failed `gh secret delete` on an already-absent secret wedging the sweep
# forever) lives entirely in this shell script; a text-only assertion on
# the YAML would not exercise it.
# ------------------------------------------------------------------ #

#: A stand-in for the real `gh` CLI, covering only the two subcommands
#: this step calls. `GH_STUB_STORE` is a newline-separated file of
#: currently-present secret names -- `secret delete` removes a present
#: name and exits 0, or exits 1 leaving the store untouched (a missing
#: name is never present to begin with, reproducing "deleting an
#: already-deleted secret is an error"). `secret list --json name --jq
#: '.[].name'` prints the store's current contents, one per line, exactly
#: the shape the real step's own listing expects. `GH_STUB_ALWAYS_FAIL`
#: (comma-joined names) forces `secret delete` to fail *and* leaves the
#: name in the store -- the genuine failure this stub can otherwise not
#: produce, since an ordinary present name always deletes cleanly.
#: `GH_STUB_FAKE_SUCCESS` (comma-joined names) makes `secret delete`
#: report success (exit 0) while leaving the name in the store untouched
#: -- an eventual-consistency lag the real API can plausibly produce, and
#: R-36's own second shape: a successful-looking delete must not be
#: trusted either, only what `secret list` confirms. `GH_STUB_LIST_FAIL`
#: ("1") makes every `secret list` call fail (non-zero exit, nothing
#: printed) -- R-36's own reproduction: a listing that cannot answer the
#: question must never be read as "the answer is no". `GH_STUB_LIST_
#: FAIL_ON_CALL` (an integer) fails only the Nth `secret list` call
#: across the whole run -- fix round 3's own reproduction, a mixed batch
#: where an earlier event's own listing succeeds and a later one's does
#: not; the call count is tracked in `$GH_STUB_STORE.listcalls` since
#: each invocation of this stub is a fresh process.
_GH_STUB = """#!/usr/bin/env bash
set -e
store="$GH_STUB_STORE"
fail_list=",${GH_STUB_ALWAYS_FAIL:-},"
fake_ok=",${GH_STUB_FAKE_SUCCESS:-},"
if [ "$1" = "secret" ] && [ "$2" = "delete" ]; then
  name="$3"
  if [ "$fail_list" != ",," ] && printf '%s' "$fail_list" | grep -qF ",$name,"; then
    exit 1
  fi
  if [ "$fake_ok" != ",," ] && printf '%s' "$fake_ok" | grep -qF ",$name,"; then
    exit 0
  fi
  if [ -f "$store" ] && grep -qxF "$name" "$store"; then
    grep -vxF "$name" "$store" > "$store.tmp" || true
    mv "$store.tmp" "$store"
    exit 0
  fi
  exit 1
elif [ "$1" = "secret" ] && [ "$2" = "list" ]; then
  count_file="$store.listcalls"
  count=0
  [ -f "$count_file" ] && count="$(cat "$count_file")"
  count=$((count + 1))
  echo "$count" > "$count_file"
  fail_on="${GH_STUB_LIST_FAIL_ON_CALL:-0}"
  if [ "${GH_STUB_LIST_FAIL:-}" = "1" ] || [ "$count" = "$fail_on" ]; then
    echo "gh: HTTP 401: Bad credentials" >&2
    exit 1
  fi
  [ -f "$store" ] && cat "$store"
  exit 0
fi
exit 1
"""


def _delete_step_script() -> str:
    loaded = safe_load((ROOT / RETENTION_WORKFLOW).read_text(encoding="utf-8"))
    for step in loaded["jobs"]["retention"]["steps"]:
        if step.get("id") == "delete":
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError("no step with id 'delete' in retention.yml::retention")


def _run_delete_step(
    tmp_path: Path,
    *,
    present_secrets: list[str],
    destroyed_ids: str,
    destroyed_secrets: str,
    always_fail: list[str] | None = None,
    fake_success: list[str] | None = None,
    list_fail: bool = False,
    list_fail_on_call: int = 0,
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh_stub = bin_dir / "gh"
    gh_stub.write_text(_GH_STUB, encoding="utf-8", newline="\n")
    gh_stub.chmod(gh_stub.stat().st_mode | stat.S_IEXEC)

    store = tmp_path / "store"
    store.write_text("".join(f"{name}\n" for name in present_secrets), encoding="utf-8")
    output_file = tmp_path / "gh_output"
    output_file.write_text("", encoding="utf-8")

    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "GH_STUB_STORE": str(store),
        "GH_STUB_ALWAYS_FAIL": ",".join(always_fail or []),
        "GH_STUB_FAKE_SUCCESS": ",".join(fake_success or []),
        "GH_STUB_LIST_FAIL": "1" if list_fail else "0",
        "GH_STUB_LIST_FAIL_ON_CALL": str(list_fail_on_call),
        "GH_TOKEN": "stub-token",
        "GITHUB_REPOSITORY": "example/example-showcase",
        "DESTROYED_IDS": destroyed_ids,
        "DESTROYED_SECRETS": destroyed_secrets,
        "GITHUB_OUTPUT": str(output_file),
    }
    assert _BASH_PATH is not None
    result = subprocess.run(  # nosec B603
        # Production runs this under GitHub's own default `run:` shell,
        # `bash -e {0}` -- no `-o pipefail` (fix round 3: verified, not
        # assumed, after `-o pipefail` masked nothing here but a second
        # assumption about the runner's own shell was exactly what let
        # `list_status=$?` read as reachable when it was not).
        [_BASH_PATH, "-e", "-c", _delete_step_script()],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    outputs: dict[str, str] = {}
    for line in output_file.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            outputs[key] = value
    return result, outputs


#: The full path, not the bare name: on Windows, a plain `["bash", ...]`
#: argv lets `CreateProcess` search the Windows system directory before
#: `PATH`, which can resolve to `System32\bash.exe` -- a WSL launcher that
#: is not the same interpreter these tests need and fails outright with
#: no WSL distribution installed. Resolving through `PATH` ourselves and
#: passing the full path sidesteps that search order entirely.
_BASH_PATH = shutil.which("bash")
_BASH_MISSING = _BASH_PATH is None


@pytest.mark.skipif(_BASH_MISSING, reason="bash is not on PATH")
def test_delete_step_deletes_every_secret_on_an_ordinary_run(tmp_path: Path) -> None:
    result, outputs = _run_delete_step(
        tmp_path,
        present_secrets=["CONVENER_EVENT_KEY_MRG_042", "CONVENER_EVENT_KEY_MRG_050"],
        destroyed_ids="mrg-042,mrg-050",
        destroyed_secrets="CONVENER_EVENT_KEY_MRG_042,CONVENER_EVENT_KEY_MRG_050",
    )
    assert result.returncode == 0, result.stderr
    assert outputs["recorded_ids"] == "mrg-042,mrg-050"


@pytest.mark.skipif(_BASH_MISSING, reason="bash is not on PATH")
def test_delete_step_records_a_secret_that_was_already_absent(tmp_path: Path) -> None:
    """Critical 1's own reproduction, the direction report concern 3 and
    `retention.yml`'s comment assumed: `gh secret delete` on a secret that
    is not there returns non-zero. The fix must converge on this anyway --
    `gh secret list` confirms the secret is absent, which is what the
    registry exists to record, regardless of the delete call's own exit
    code. A mutant that trusts the exit code instead fails this: it would
    leave `recorded_ids` empty and the step would exit 1."""
    result, outputs = _run_delete_step(
        tmp_path,
        present_secrets=[],  # already gone -- e.g. a retry after Critical 1
        destroyed_ids="mrg-042",
        destroyed_secrets="CONVENER_EVENT_KEY_MRG_042",
    )
    assert result.returncode == 0, result.stderr
    assert outputs["recorded_ids"] == "mrg-042"


@pytest.mark.skipif(_BASH_MISSING, reason="bash is not on PATH")
def test_delete_step_does_not_abandon_a_later_event_after_an_earlier_failure(
    tmp_path: Path,
) -> None:
    """Critical 1's other half: a `break` on the first failure abandoned
    every later, healthy event in the same batch. `mrg-042` fails for real
    here (`GH_STUB_ALWAYS_FAIL` -- delete fails and the secret stays
    present, the one failure this stub can produce that `gh secret list`
    does not paper over); `mrg-050` is perfectly healthy and must still be
    deleted and recorded. A `break` mutant fails this: `recorded_ids`
    would be empty and `mrg-050` would never even be attempted."""
    result, outputs = _run_delete_step(
        tmp_path,
        present_secrets=["CONVENER_EVENT_KEY_MRG_042", "CONVENER_EVENT_KEY_MRG_050"],
        destroyed_ids="mrg-042,mrg-050",
        destroyed_secrets="CONVENER_EVENT_KEY_MRG_042,CONVENER_EVENT_KEY_MRG_050",
        always_fail=["CONVENER_EVENT_KEY_MRG_042"],
    )
    assert result.returncode == 1
    assert outputs["recorded_ids"] == "mrg-050"
    assert "CONVENER_EVENT_KEY_MRG_042" in result.stdout + result.stderr


@pytest.mark.skipif(_BASH_MISSING, reason="bash is not on PATH")
def test_delete_step_treats_a_fake_success_as_a_failure(tmp_path: Path) -> None:
    """R-36's second shape: `gh secret delete` reporting success is not
    itself the answer either -- an eventual-consistency lag between the
    delete call and the list call is plausible on a real API, and this
    step's own comment says the listing is "the one question that
    actually matters". `GH_STUB_FAKE_SUCCESS` makes delete exit 0 while
    leaving the secret in the store; the listing then (correctly) still
    shows it present, so this must be recorded as a failure exactly like
    an outright failed delete, not silently trusted because the delete
    call itself looked clean."""
    result, outputs = _run_delete_step(
        tmp_path,
        present_secrets=["CONVENER_EVENT_KEY_MRG_042"],
        destroyed_ids="mrg-042",
        destroyed_secrets="CONVENER_EVENT_KEY_MRG_042",
        fake_success=["CONVENER_EVENT_KEY_MRG_042"],
    )
    assert result.returncode == 1
    assert outputs.get("recorded_ids", "") == ""
    assert "CONVENER_EVENT_KEY_MRG_042" in result.stdout + result.stderr


@pytest.mark.skipif(_BASH_MISSING, reason="bash is not on PATH")
def test_delete_step_fails_and_records_nothing_when_listing_fails(
    tmp_path: Path,
) -> None:
    """R-36's own reproduction (Critical, round 2): the listing's exit
    status was discarded and only the grep result was consulted, so a
    failed listing (an expired PAT mid-run, a 403, gh missing from PATH)
    printed nothing, grep found no match, and the id was recorded as
    destroyed -- the exact inverse of what this job exists to guarantee,
    since the secret is still live. `GH_STUB_LIST_FAIL` makes `gh secret
    list` itself exit non-zero with nothing printed; the fix must record
    nothing for this event and fail the job, never read a failed question
    as a negative answer.

    **The `::error::` annotation is asserted by name, not merely "the id
    appears somewhere" (fix round 3).** Round 2's own version of this test
    passed for the wrong reason: under production's actual shell (`bash -e
    {0}`, no `-o pipefail`), `listing="$(...)"; list_status=$?` died on the
    failed command substitution before `list_status=$?` was ever reached,
    so the branch that prints this very annotation was dead code -- and
    the assertion below, checking only that the exit code was 1 and
    `recorded_ids` was empty, could not tell that apart from the intended
    mechanism, because a script that dies mid-loop also exits non-zero
    and never reaches the line that writes `recorded_ids` at all. Pinning
    the annotation text is what distinguishes "the fix printed its own
    diagnosis and continued" from "the script silently died"."""
    result, outputs = _run_delete_step(
        tmp_path,
        present_secrets=["CONVENER_EVENT_KEY_MRG_042"],
        destroyed_ids="mrg-042",
        destroyed_secrets="CONVENER_EVENT_KEY_MRG_042",
        list_fail=True,
    )
    assert result.returncode == 1
    assert outputs.get("recorded_ids", "") == ""
    assert (
        "::error::could not confirm whether CONVENER_EVENT_KEY_MRG_042 was deleted "
        "for event mrg-042" in result.stdout
    )


@pytest.mark.skipif(_BASH_MISSING, reason="bash is not on PATH")
def test_delete_step_still_records_an_earlier_event_when_a_later_listing_fails(
    tmp_path: Path,
) -> None:
    """Fix round 3's own reproduction, and the assertion that actually
    catches the `bash -e` defect the sibling test above could not: a
    mixed batch where `mrg-042` deletes and confirms cleanly (the first
    `secret list` call) and `mrg-050`'s own listing then fails (the
    second call, `GH_STUB_LIST_FAIL_ON_CALL=2`). R-34's partial-batch
    property says a later failure must not un-record an earlier success.

    Under the dead `list_status=$?` mechanism this reproduces exactly
    what the coordinator's own verification showed: the script died
    partway through the loop -- after `mrg-042` was appended to `recorded`
    in memory, but before the `echo "recorded_ids=$recorded"` line ever
    ran -- so `recorded_ids` came out empty despite `mrg-042` having been
    both deleted and confirmed absent. This test fails under that
    mechanism (`recorded_ids` would be `""`, not `"mrg-042"`) and passes
    under the `if ! listing=...; then` fix, which reaches the `echo`
    line regardless of where in the loop a listing failed."""
    result, outputs = _run_delete_step(
        tmp_path,
        present_secrets=["CONVENER_EVENT_KEY_MRG_042", "CONVENER_EVENT_KEY_MRG_050"],
        destroyed_ids="mrg-042,mrg-050",
        destroyed_secrets="CONVENER_EVENT_KEY_MRG_042,CONVENER_EVENT_KEY_MRG_050",
        list_fail_on_call=2,
    )
    assert result.returncode == 1
    assert outputs.get("recorded_ids", "") == "mrg-042"
    assert (
        "::error::could not confirm whether CONVENER_EVENT_KEY_MRG_050 was deleted "
        "for event mrg-050" in result.stdout
    )
