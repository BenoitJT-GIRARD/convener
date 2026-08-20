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


def test_deploy_workflow_has_no_pages_concurrency_group() -> None:
    workflow = _load_workflow()
    assert "concurrency" not in workflow, (
        "the `concurrency: group: pages` block only serialised deploys "
        "against the Pages environment; there is no Pages environment left "
        "to serialise against"
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
