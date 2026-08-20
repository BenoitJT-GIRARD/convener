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
import re
from pathlib import Path
from typing import Any

import pytest

from convener_ops import certificate, platform_fcc, signing
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

#: `os.environ.get(signing.SECRET_NAME, ...)` cannot be read as a string
#: literal by the AST walk below -- it is an attribute access, not a
#: constant -- so this maps the one dotted name `issue_certificates` and
#: `reissue_certificate` read that way onto the actual secret name it
#: resolves to, itself read from `signing.py`, never retyped by hand.
_DOTTED_ENV_NAMES: dict[tuple[str, str], str] = {
    ("signing", "SECRET_NAME"): signing.SECRET_NAME
}


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

    **What this still cannot see**, so the docstring does not claim more
    than the walk does: a call reached only through a name that is not a
    plain `ast.Name` (a method call, a call through a variable holding a
    function reference, `getattr`-style indirection), and any read inside
    a function this module imports from elsewhere -- `platform_from_env`
    is the one such case this function already knows about by name, and
    remains the only one special-cased rather than walked, since walking
    a different module's own AST is out of this function's own scope by
    design (it answers "what does `cli.py` read", not "what does
    everything `cli.py` calls read")."""
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
                if name:
                    names.add(name)
        elif isinstance(node, ast.Subscript) and _is_os_environ(node.value):
            name = _literal_env_name(node.slice)
            if name:
                names.add(name)
    if _calls_platform_from_env(func):
        names.add(platform_fcc.TOKEN_ENV)

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


#: Minor 3, fix round 3: the exact three names any of these workflows'
#: `workflow_dispatch` inputs may ever carry -- an allowlist, not the
#: one-word denylist (`"email" not in trigger.lower()`) this test used to
#: be. R-22's own docstring calls "never an address" "the one property
#: every input list in this trio must hold", but the old denylist let
#: `attendee_address`, `contact` or `who` sail straight through it
#: untouched. This repository already argues the general case in
#: `certificate.public_register`'s own docstring: an allowlist of exactly
#: what may leave, not a denylist of the one thing that must not.
_ALLOWED_CERTIFICATE_WORKFLOW_INPUTS = frozenset(
    {"event_id", "certificate_id", "conference_id"}
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
