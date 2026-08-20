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

import re
from pathlib import Path
from typing import Any

import pytest

from convener_ops.paths import repo_root
from convener_ops.yaml_safe import safe_load

ROOT = repo_root()
DEPLOY_WORKFLOW = Path(".github/workflows/deploy.yml")
VITE_CONFIG = Path("app/vite.config.ts")

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


def test_deploy_workflow_build_job_permissions_are_read_only() -> None:
    assert _build_job()["permissions"] == {"contents": "read"}, (
        "the build job pushes to example-showcase over a PAT in DEPLOY_TOKEN, "
        "not over the checkout's own GITHUB_TOKEN, so it never needs more "
        "than read access to this repo"
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


def test_publish_vitrine_builds_the_certificates_public_data() -> None:
    """The other half: the projection has to actually be regenerated, not
    only trigger-eligible."""
    assert "convener-certificates-public-data" in _publish_vitrine_build_step()


def test_publish_vitrine_push_step_copies_certificates_data_to_the_showcase() -> None:
    """Follows `events-public.json`'s own precedent exactly: built under
    `public-data/`, copied into the cloned showcase's `src/_data/`, staged
    alongside the events feed so one commit carries both."""
    script = _publish_vitrine_push_script()
    assert (
        "cp public-data/certificates-public.json /tmp/vit/src/_data/certificates.json"
        in script
    )
    assert "git add src/_data/events.json src/_data/certificates.json" in script


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


def _workflow_files() -> list[Path]:
    paths = sorted((ROOT / WORKFLOWS_DIR).glob("*.yml"))
    assert paths, (
        f"no *.yml files found under {WORKFLOWS_DIR.as_posix()} -- "
        "the glob itself is wrong, which would silently empty this scan"
    )
    return paths


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
