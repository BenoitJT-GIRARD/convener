"""The app publishes to the showcase, not to GitHub Pages on this repo.

`example-cockpit` is private; GitHub Pages does not serve a private repo without
a paid plan, so the three Pages actions (`configure-pages`,
`upload-pages-artifact`, `deploy-pages`) and the `deploy` job that used them
can never succeed here. Nothing in this repository read workflow YAML before
this module, which made that a config file no test could catch drifting back
in.

Two things are asserted, and neither is the obvious one:

* Rather than running `npm run build` and grepping `app/dist/index.html`
  (slow, and this suite runs on every push), the base path is asserted
  straight from `app/vite.config.ts` — the one source Vite reads it from.
* The publish step is a hand-written shell script, the same shape as
  `publish-showcase.yml`'s own push step. It is asserted against as text
  (`in` checks on the parsed `run:` block) rather than executed, because
  running it means a real clone of a real repo, which is exactly the kind
  of network access this suite must not take on.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import os
import re
import shutil
import stat
import subprocess  # nosec B404
import sys
import textwrap
import tomllib
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest
from conftest import WorkflowYaml, workflow_event_names, workflow_triggers

import convener_ops.cli
from convener_ops.declaration import published
from convener_ops.declaration.paths import (
    DATA_DIR,
    KEYS_DIR,
    PUBLIC_DATA_DIR,
    REGISTER_PATH,
    repo_root,
)
from convener_ops.declaration.yaml_safe import safe_load
from convener_ops.journey import (
    certificate,
    confirmation,
    platform_fcc,
    registration,
    signing,
    survey_invite,
)

ROOT = repo_root()
DEPLOY_WORKFLOW = Path(".github/workflows/deploy.yml")
VITE_CONFIG = Path("app/vite.config.ts")
APP_TSX = Path("app/src/App.tsx")


#: The base path this repository publishes under: the app is served from the
#: public showcase repository, under its own `app/` subtree, not from the
#: private cockpit repo's own Pages site (which cannot exist on the free
#: plan). Derived from `instance/config.json` rather
#: than typed here, so this module pins the *shape* of the address
#: (`<published prefix>app/`) and never becomes a second statement of
#: what that prefix is.
#: Read on demand, never while this module loads.
#: `published.load` reads `instance/config.json`, a path
#: `declarations/boundary.yml` hands to the instance, and a derived repository is
#: entitled not to have it until the derivation lays an example's own file
#: there. At module scope that read took this whole module down at
#: collection, with a stack trace in place of the one failing assertion.
@cache
def _expected_base_path() -> str:
    return published.load().app_base


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
        if any("SHOWCASE_DEPLOY_TOKEN" in str(value) for value in env.values()):
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        "no step in the build job reads SHOWCASE_DEPLOY_TOKEN — "
        "the push-to-showcase step is missing or was renamed away from it"
    )


def _survey_status_step_script() -> str:
    """The `run:` block of the step that commits
    `instance/public-data/survey-status.json` back to this repository.

    Found by the file it writes rather than by its `name:`, the identical
    reasoning `_push_step_script` above gives for its own lookup -- a
    rename of the step does not silently stop this module from checking
    it.
    """
    for step in _build_job()["steps"]:
        run = step.get("run")
        if isinstance(run, str) and "instance/public-data/survey-status.json" in run:
            return run
    raise AssertionError(
        "no step in the build job writes instance/public-data/survey-status.json — "
        "the survey-status commit step is missing or was renamed away from it"
    )


def _settings_form_source() -> str:
    return (ROOT / "app" / "src" / "settings" / "form.ts").read_text(encoding="utf-8")


def _deploy_paths_ignored() -> list[str]:
    """What `deploy.yml` declines to run for.

    `on:` is read back as the boolean `True` by every YAML 1.1 loader,
    so the key is looked up both ways.
    """
    raw: dict[Any, Any] = dict(_load_workflow())
    on = raw.get(True) or raw.get("on") or {}
    push = on.get("push") or {}
    return [str(entry) for entry in (push.get("paths-ignore") or [])]


def test_the_deploy_runs_for_the_files_the_settings_screen_writes() -> None:
    """The fact the settings screen's advice rests on.

    `config/**` sat in `paths-ignore` until the published address moved
    into a file the bundle reads, and removing it is what stopped a
    changed address publishing nothing and going green. The settings
    screen tells a volunteer what saving does, so if that entry ever
    comes back the screen's answer changes with it.
    """
    ignored = _deploy_paths_ignored()
    written = [p.name for p in (ROOT / "instance").glob("*.yml")]
    written.append("config.json")
    for pattern in ignored:
        head = pattern.split("*")[0].rstrip("/")
        assert head not in ("instance", "declarations"), (
            f"deploy.yml declines to run for {pattern!r}, which covers the "
            "files the settings screen writes. app/src/settings/form.ts "
            "tells a volunteer that saving starts this workflow; that "
            "sentence is now wrong and has to change with this list."
        )
    assert written, "no settings file found to check the filter against"


def test_the_settings_form_claims_no_workflow_ignores_what_it_writes() -> None:
    """The prose half of the same rule.

    Seven sentences across four files claimed `deploy.yml` ignored the
    directory the settings screen writes into. It had stopped being true,
    nothing read the claim, and one of the seven was a string shown on
    screen telling a volunteer to run the workflow by hand.
    """
    source = _settings_form_source()
    assert "ignores config/" not in source and "ignores `config/" not in source, (
        "app/src/settings/form.ts claims a workflow ignores the directory "
        "it writes into. deploy.yml runs for those files, and a volunteer "
        "reading otherwise dispatches a run they did not need."
    )


def test_deploy_workflow_survey_status_retry_re_derives_rather_than_rebases() -> None:
    """The same defence `registration.yml`'s and
    `survey.yml`'s own retry loops use -- a rejected push is handled by
    fetching the branch tip, hard-resetting, and re-running the
    projection command, never actually *running* `git rebase`.

    `instance/public-data/survey-status.json` is a generated JSON array, the same
    shape `registrations.enc` and `survey-responses.enc` are. Reproduced
    end to end with real git: `git rebase` on two runs each rewriting an
    array's own closing lines
    returns 1 on the conflict, and `set -e` kills the step before the
    `::error::` line is ever reached -- an unexplained red with the tree
    left mid-rebase. This exact step used to run `git rebase`
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
        "uv run --frozen convener-survey-status-public-data"
        in script.split("for attempt", 1)[-1]
    ), (
        "the retry loop must re-run the projection command on every "
        "attempt, not only build it once before the loop starts"
    )
    assert "for attempt in 1 2 3; do" in script


def test_vite_config_base_path_targets_the_showcase_app_subtree() -> None:
    """`base` is no longer a literal in this file, so
    what is checked here is that it is *derived* -- from the declaration,
    through the same reader the build runs. That it resolves to
    `_expected_base_path()` is checked by actually loading all four
    configurations, in `test_published.py`: a source text agreeing with a
    value proves nothing about what a build does with it.
    """
    config = (ROOT / VITE_CONFIG).read_text(encoding="utf-8")
    assert "from './scripts/published.mjs'" in config, (
        f"{VITE_CONFIG.as_posix()} no longer reads the published address "
        "from instance/config.json; a build off this config would ship "
        "asset URLs nothing derives, at an address nothing declares."
    )
    assert "base: PUBLISHED.appBase" in config


def test_vite_config_base_no_longer_points_at_the_private_repo() -> None:
    config = (ROOT / VITE_CONFIG).read_text(encoding="utf-8")
    assert "/example-cockpit/" not in config, (
        f"{VITE_CONFIG.as_posix()} still references /example-cockpit/; a bundle "
        "built from it would 404 every asset once served from the public "
        "showcase."
    )


def test_all_islands_share_the_apps_published_base_not_a_divergent_one() -> None:
    """The path-prefix defect: `islandSignupConfig` and
    `islandVerifyConfig` used to set `base: '/app/'`, deliberately distinct
    from the main config's own published base (`_expected_base_path()`,
    above), on the reasoning that the *site* pages
    hosting these islands already addressed
    the app's assets root-relative to the site's own root. That reasoning
    assumed the site's own root-relative links already landed at wherever
    GitHub Pages resolves this project's published root to -- they did not
    (no CNAME, no custom domain), which is the identical gap
    `tools/tests/repository/test_site.py::
    test_no_built_page_emits_a_root_relative_link_without_the_prefix` now
    closes on the site's own side. Every island publishes into, and is
    addressed from, the exact same `example-showcase` `app/` subtree the main
    app does (`deploy.yml`'s single push step carries all of them,
    `islandSurveyConfig` included), so all four configs
    must read the identical value -- a stray `'/app/'` reappearing on any
    island is exactly the regression this guards. "Identical" is
    structural rather than textual: all four name one
    derived expression, and none of them names an address at all.
    """
    config = (ROOT / VITE_CONFIG).read_text(encoding="utf-8")
    # Block comments stripped first: this file's own explanatory comments
    # quote `base: PUBLISHED.appBase` by way of describing the fix, which
    # would otherwise inflate this count without a fifth real config.
    code_only = re.sub(r"/\*.*?\*/", "", config, flags=re.DOTALL)
    bases = re.findall(r"base:\s*([^,\n]+)", code_only)
    assert len(bases) == 4, (
        f"expected exactly 4 `base:` entries in {VITE_CONFIG.as_posix()} "
        "(main app, island-signup, island-verify, island-survey), found "
        f"{bases!r}"
    )
    assert set(bases) == {"PUBLISHED.appBase"}, (
        f"{VITE_CONFIG.as_posix()}'s four `base:` entries are {bases!r}, "
        "not all the one derived value -- an island publishing under a "
        "different base than the main app 404s its own fetches (event keys, "
        "the certificate register, signing keys) once served from the real, "
        "single app/ subtree they share"
    )


def test_app_no_longer_declares_a_survey_route() -> None:
    """The post-event survey moved off `App.tsx`'s own
    former `<Route path="/survey/:eventId" .../>` onto a static page's
    own island (`site/src/survey.njk`, `app/src/islands/survey/`), the
    identical move registration and
    verification made (see git history for the route this replaced). This was
    the last public route `App.tsx` carried -- with it gone, every route
    that document still declares is reached only through `Shell`, gated
    on sign-in."""
    app_tsx = (ROOT / APP_TSX).read_text(encoding="utf-8")
    assert '"/survey/:eventId"' not in app_tsx, (
        f"{APP_TSX.as_posix()} still declares a route at "
        '"/survey/:eventId" -- the post-event survey moved onto '
        "the static survey page's own island instead"
    )


def test_app_no_longer_declares_a_verify_route() -> None:
    """Certificate verification moved off `App.tsx`'s own
    `<Route path="/verify/:identifier" .../>` onto a static page's own
    island (`site/src/verify.njk`, `app/src/islands/verify/`), the same
    move registration made for its own `/signup/:eventId` (see git
    history for the route this replaced). A route left behind here would
    still technically work -- `App.tsx`'s own `<Route path="/*"
    element={<Shell />} />` catches everything else, so a stray route is
    dead code, not dead code with a live consumer -- but every certificate
    printed from now on carries `VERIFICATION_BASE`'s *new* address, and
    this pin is what would catch the old route quietly reappearing."""
    app_tsx = (ROOT / APP_TSX).read_text(encoding="utf-8")
    assert '"/verify/:identifier"' not in app_tsx, (
        f"{APP_TSX.as_posix()} still declares a route at "
        '"/verify/:identifier" -- certificate verification moved '
        "onto the static verify page's own island instead"
    )


#: `site/src/verify.njk`'s own permalink -- a fixed, static page (unlike
#: `event.njk`'s per-edition pagination), because a certificate names no
#: event this page could key a per-page address off.
VERIFY_TEMPLATE = Path("site/src/verify.njk")
VERIFY_PERMALINK = "/verify/"


def test_certificate_verification_base_matches_the_verify_page_permalink() -> None:
    """A correction of the D-14 pin `test_app_route_matches_
    certificate_verification_base` used to make (see git history): `App.tsx`
    no longer declares this route at all, so the host-and-path portion of
    `VERIFICATION_BASE` -- everything *before* the `#` -- must now match
    the static verify page's own address instead. The fragment *after* the
    `#` is a separate, and more important, property -- see
    `test_verification_url_carries_the_token_after_the_fragment_not_before_it`
    in `test_certificate.py` for that half, unchanged by this move."""
    verify_njk = (ROOT / VERIFY_TEMPLATE).read_text(encoding="utf-8")
    assert f'permalink: "{VERIFY_PERMALINK}"' in verify_njk, (
        f"{VERIFY_TEMPLATE.as_posix()} does not declare the permalink "
        f"{VERIFY_PERMALINK!r} this pin assumes -- update both together"
    )
    host_and_path = certificate.VERIFICATION_BASE.split("#", 1)[0]
    assert host_and_path.endswith(VERIFY_PERMALINK), (
        f"certificate.VERIFICATION_BASE ({certificate.VERIFICATION_BASE!r}) "
        f"does not carry the verify page's own address ({VERIFY_PERMALINK!r}) "
        "before its fragment -- every printed QR code would 404 once served"
    )


def test_certificate_verification_base_no_longer_targets_the_app_subtree() -> None:
    """Same gap `test_registration_signup_base_no_longer_targets_the_app_
    subtree` guards for `SIGNUP_BASE`, applied here: verification moved
    off the app's own route onto the static verify page
    above, so a published certificate's address should no longer carry the
    app's own asset subtree."""
    assert _expected_base_path() not in certificate.VERIFICATION_BASE, (
        f"certificate.VERIFICATION_BASE still carries {_expected_base_path()!r} "
        "-- verification moved off the app's own route onto the "
        "verify page; every printed certificate should target that page "
        "instead"
    )


#: `site/src/survey.njk`'s own permalink expression -- D-19, `event_id` IS
#: `edition_code` lower-cased, nothing else names an event, the identical
#: rule `EVENT_PERMALINK` below already applies. Read from the template's
#: own front matter rather than restated as a second literal, so a future
#: change to that permalink fails this pin instead of quietly leaving
#: `survey_invite.SURVEY_BASE` pointing at an address the site no longer
#: serves.
SURVEY_TEMPLATE = Path("site/src/survey.njk")
SURVEY_PERMALINK = "/survey/{{ event.id | lower }}/"


def test_survey_base_matches_the_survey_page_permalink() -> None:
    """A correction of the D-14 pin `test_survey_base_
    matches_app_tsxs_own_survey_route` used to make (see git history):
    `App.tsx` no longer declares a survey route at all -- the post-event
    survey moved off it entirely, the same D-18 move registration made
    -- so the address `survey_invite.SURVEY_BASE` must now
    match is the static survey page's own, exactly the way
    `test_registration_signup_base_matches_the_event_page_permalink`
    already holds `registration.SIGNUP_BASE` to `event.njk`'s."""
    survey_njk = (ROOT / SURVEY_TEMPLATE).read_text(encoding="utf-8")
    assert f'permalink: "{SURVEY_PERMALINK}"' in survey_njk, (
        f"{SURVEY_TEMPLATE.as_posix()} does not declare the permalink "
        f"{SURVEY_PERMALINK!r} this pin assumes -- update both together"
    )
    prefix = SURVEY_PERMALINK.split("{{", 1)[0]  # "/survey/"
    assert survey_invite.SURVEY_BASE.endswith(prefix), (
        f"survey_invite.SURVEY_BASE ({survey_invite.SURVEY_BASE!r}) does "
        f"not end with the survey page's own address prefix ({prefix!r})"
    )
    assert survey_invite.survey_url("mrg-042") == f"{survey_invite.SURVEY_BASE}mrg-042/"


def test_survey_base_no_longer_targets_the_app_subtree() -> None:
    """Same gap `test_certificate_verification_base_no_longer_targets_the_
    app_subtree` and `test_registration_signup_base_no_longer_targets_
    the_app_subtree` guard for their own bases, applied here now that the
    survey has the identical shape registration's own base already has: a
    published survey link that still carried `_expected_base_path()` would
    point at the now-deleted `App.tsx` route's own asset
    subtree, not at the survey page that replaced it."""
    assert _expected_base_path() not in survey_invite.SURVEY_BASE, (
        f"survey_invite.SURVEY_BASE still carries {_expected_base_path()!r} -- "
        "the survey moved off the app's own route onto the survey "
        "page; every survey invitation link should target that page instead"
    )


#: `site/src/event.njk`'s own permalink expression -- D-19, `event_id` IS
#: `edition_code` lower-cased, nothing else names an event. Read from the
#: template's own front matter rather than restated as a second literal,
#: so a future change to that permalink fails this pin instead of quietly
#: leaving `registration.SIGNUP_BASE` pointing at an address the site no
#: longer serves.
EVENT_TEMPLATE = Path("site/src/event.njk")
EVENT_PERMALINK = "/events/{{ event.id | lower }}/"


def test_registration_signup_base_matches_the_event_page_permalink() -> None:
    """A correction found on review: `registration.
    SIGNUP_BASE` used to be a `HashRouter` fragment pinned against
    `App.tsx`'s own `path="/signup/:eventId"` route
    (`test_app_route_matches_certificate_verification_base` still makes
    that same pin for `/verify/:identifier`). Registration left that route
    entirely for an island mounted on the public event page (D-18), so the
    address it must now match is that page's own -- `event.njk`'s
    permalink -- not a route in an application it no longer lives in."""
    event_njk = (ROOT / EVENT_TEMPLATE).read_text(encoding="utf-8")
    assert f'permalink: "{EVENT_PERMALINK}"' in event_njk, (
        f"{EVENT_TEMPLATE.as_posix()} does not declare the permalink "
        f"{EVENT_PERMALINK!r} this pin assumes -- update both together"
    )
    prefix = EVENT_PERMALINK.split("{{", 1)[0]  # "/events/"
    assert registration.SIGNUP_BASE.endswith(prefix), (
        f"registration.SIGNUP_BASE ({registration.SIGNUP_BASE!r}) does not "
        f"end with the event page's own address prefix ({prefix!r})"
    )
    assert registration.signup_url("mrg-042") == f"{registration.SIGNUP_BASE}mrg-042/"


def test_registration_signup_base_no_longer_targets_the_app_subtree() -> None:
    """Same gap `test_certificate_verification_base_targets_the_showcase_
    app_subtree` and `test_survey_base_targets_the_showcase_app_subtree`
    guard for their own bases, inverted for this one: unlike verification
    and the survey, which still live on `App.tsx` routes, a published
    signup link that still carried `_expected_base_path()` would
    point at the now-deleted `/signup/:eventId` route's own asset
    subtree, not at the event page that replaced it."""
    assert _expected_base_path() not in registration.SIGNUP_BASE, (
        f"registration.SIGNUP_BASE still carries {_expected_base_path()!r} -- "
        "registration moved off the app's own route onto the event "
        "page; every published signup link should target that page instead"
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
    this workflow and `publish-showcase.yml`, which write disjoint subtrees and
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


def test_deploy_workflow_concurrency_is_not_shared_with_publish_showcase() -> None:
    """`publish-showcase.yml` writes a disjoint subtree of example-showcase
    and its overlapping pushes are both legitimate -- the retry-with-rebase
    loop already handles that case more cheaply. Grouping the two workflows
    *together* would serialise a job that does not need to wait.

    That is the whole claim, and this test used to assert something wider
    than it: that `publish-showcase.yml` carried no concurrency block at
    all. The two are not the same, and the difference was measured -- with
    no group of its own, that workflow ran thirty times for one volunteer's
    runbook session and cost 51 minutes, where `deploy.yml`, cancelling its
    own superseded runs, cost 10 across 32. Worse, two overlapping showcase
    runs race to push a *whole built site*, which is exactly the case
    `test_deploy_workflow_cancels_stale_runs_of_itself` cancels for: the
    loser's rebase can replay cleanly and let the older build overwrite the
    newer.

    So it now has a group -- its own. What this test holds is the thing the
    docstring above always meant: not the same group as deploy's.
    """
    publish_showcase = safe_load(
        (ROOT / ".github/workflows/publish-showcase.yml").read_text(encoding="utf-8")
    )
    theirs = publish_showcase.get("concurrency", {}).get("group")
    ours = _load_workflow()["concurrency"]["group"]

    assert theirs, (
        "publish-showcase.yml has no concurrency group -- two overlapping "
        "runs each push a whole built site, and the loser's rebase can "
        "replay cleanly with the older build overwriting the newer"
    )
    assert theirs != ours, (
        f"publish-showcase.yml and deploy.yml share the group {ours!r} -- "
        "they write disjoint subtrees, their overlapping pushes are both "
        "legitimate, and the retry-with-rebase loop already reconciles "
        "them, so serialising one behind the other buys nothing"
    )


def test_deploy_workflow_build_job_permissions_allow_committing_survey_status() -> None:
    """`permissions.contents` moved from `read` to
    `write` when the "Commit survey status" step was added -- unlike the
    push to example-showcase (a separate repository, authenticated over a PAT
    in `DEPLOY_TOKEN`, never the checkout's own token), that step commits
    `instance/public-data/survey-status.json` back to *this* repository using the
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
        "a missing SHOWCASE_DEPLOY_TOKEN must be a normal, silent no-op "
        "(decision D-13), not a failed job"
    )


def test_deploy_workflow_push_step_only_touches_the_app_subtree() -> None:
    script = _push_step_script()
    assert "git add --force app" in script, (
        "the push step must stage only the target repo's app/ subtree, the "
        "same discipline publish-showcase.yml uses for the site's own "
        "root-level files -- and with --force, since `git add` still "
        "honours the target repository's own .gitignore"
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
        "guard publish-showcase.yml already applies"
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
    """deploy.yml's own 'Build public
    data' step was pinned by nothing, even though this module already
    carries fourteen assertions about deploy.yml. Deleting the step left
    the suite green while certificates.json -- the file the verification
    page actually fetches -- shipped permanently empty. (This same step
    also once existed, pinned, in publish-showcase.yml;
    that copy is gone now that this one is the only writer -- see
    test_publish_showcase_no_longer_builds_the_certificates_public_data.)"""
    assert "convener-certificates-public-data" in _deploy_build_public_data_step(), (
        "deploy.yml's 'Build public data' step no longer runs "
        "convener-certificates-public-data -- app/public/certificates.json "
        "(and therefore app/dist/certificates.json) would ship empty "
        "even with real certificates on record"
    )


def test_deploy_workflow_builds_public_data_before_the_npm_build() -> None:
    """The step above has to run *before* `npm run build`: vite's own
    `prebuild` script is what runs `scripts/copy-certificates.mjs`, which
    reads `instance/public-data/certificates-public.json` -- generated by the step
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
        "instance/public-data/certificates-public.json that does not exist yet"
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
    """The same reachability requirement the step above has for
    `certificates-public-data`: deleting this step would
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
    `instance/public-data/survey-status.json` -- generated by this step -- into
    `app/public/`."""
    names = [step.get("name") for step in _build_job()["steps"]]
    assert "Build survey status" in names, (
        "see test_deploy_workflow_builds_the_survey_status_public_data"
    )
    assert names.index("Build survey status") < names.index("Build"), (
        "'Build survey status' must run before 'Build' (npm run build), or "
        "copy-survey-status.mjs's own prebuild step reads a "
        "instance/public-data/survey-status.json that does not exist yet"
    )


# ------------------------------------------------------------------ #
# publish-showcase.yml: the certificate register's public projection.
# There was a time when a revocation -- a change to
# instance/data/events/<id>/certificates.yml -- did not even fire this workflow,
# and the file it would have built was never copied to the showcase, so
# the register being what settles a certificate's state had no observable
# effect on any verifier. Text assertions on the parsed `run:` block, the
# same idiom test_notify.py uses for notify.yml, because running the
# script means a
# real clone of a real repository -- exactly the network access this
# suite must not take on (see this module's own docstring).
# ------------------------------------------------------------------ #

PUBLISH_SHOWCASE_WORKFLOW = Path(".github/workflows/publish-showcase.yml")


def _publish_showcase_workflow() -> dict[str, Any]:
    loaded = safe_load((ROOT / PUBLISH_SHOWCASE_WORKFLOW).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _publish_showcase_build_step() -> str:
    job = _publish_showcase_workflow()["jobs"]["publish"]
    for step in job["steps"]:
        if step.get("name") == "Build public data":
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        "publish-showcase.yml has no 'Build public data' step -- renamed "
        "away from the name this test looks for"
    )


def _publish_showcase_push_script() -> str:
    job = _publish_showcase_workflow()["jobs"]["publish"]
    for step in job["steps"]:
        env = step.get("env", {})
        if any("SHOWCASE_DEPLOY_TOKEN" in str(value) for value in env.values()):
            run = step["run"]
            assert isinstance(run, str)
            return run
    raise AssertionError(
        "no step in the publish job reads SHOWCASE_DEPLOY_TOKEN -- the "
        "push-to-showcase step is missing or was renamed away from it"
    )


def test_publish_showcase_paths_trigger_includes_the_certificate_register() -> None:
    """Half the original defect: a revocation is a change to
    `instance/data/events/<id>/certificates.yml`, and the old `paths:` trigger
    (`instance/data/speakers.yml`, `tools/**`) would not even fire this workflow
    for one.

    Read as raw text, not through `safe_load`: PyYAML's YAML-1.1 bool
    resolver reads a bare `on:` key as the boolean `True`, not the string
    `"on"` -- a real gotcha, not a reason to trust this file less than
    `notify.yml`'s own text assertions already do (test_notify.py's own
    idiom, followed here for exactly this reason)."""
    text = (ROOT / PUBLISH_SHOWCASE_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "'instance/data/events/*/certificates.yml'" in trigger


def test_publish_showcase_no_longer_builds_the_certificates_public_data() -> None:
    """This step used to also run
    `convener-certificates-public-data`, to feed the push step's own (equally
    removed) copy into the showcase's `src/_data/certificates.json` -- a
    file no Eleventy template there ever read. Regenerating it here with
    nothing left to consume the output would be pure waste; the register
    a verifier actually reads is built by deploy.yml instead (see that
    workflow's own 'Build public data' step and
    test_deploy_workflow_builds_the_certificates_public_data, above)."""
    assert "convener-certificates-public-data" not in _publish_showcase_build_step(), (
        "publish-showcase.yml still builds the certificates projection "
        "though nothing here writes it anywhere any more"
    )


def test_publish_showcase_push_step_no_longer_copies_certificates_data() -> None:
    """Confirmed independently, at
    at the address `instance/config.json` declares, and verified
    against the showcase checkout itself, that no Eleventy template reads
    `src/_data/certificates.json` -- `grep -rn certificates src/` there is
    empty. The write survived three fix rounds because it made the three
    certificate workflows *look* like they refreshed the public register,
    which was the root cause of a real defect; removing it is the other
    half of that fix."""
    script = _publish_showcase_push_script()
    assert "certificates.json" not in script, (
        "publish-showcase.yml's push step still mentions certificates.json "
        "-- the dead write this test exists to keep gone"
    )


def test_publish_showcase_workflow_permissions_are_read_only() -> None:
    job = _publish_showcase_workflow()["jobs"]["publish"]
    assert job["permissions"] == {"contents": "read"}


# ------------------------------------------------------------------ #
# publish-showcase.yml: the showcase's own templates
# moved from `example-showcase` into this repository's `site/` (D-15). This job
# now builds the whole site and pushes the built output to the showcase's
# root, rather than copying one generated data file into a checkout of a
# separate Eleventy project living there.
# ------------------------------------------------------------------ #


def test_publish_showcase_paths_trigger_includes_the_site_templates() -> None:
    """A change under `site/` has no effect on `events-public.json`, so
    without this the old `paths:` trigger (data + `tools/**`) would never
    rebuild or republish the site at all -- the same gap closed above for
    `certificates.yml`."""
    text = (ROOT / PUBLISH_SHOWCASE_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "'site/**'" in trigger


def test_publish_showcase_refreshes_site_data_before_building() -> None:
    """`site/src/_data/events.json` is committed only as a build fixture
    (see site/README.md); this step overwrites it from the file 'Build
    public data' just generated, so the build that follows always reflects
    current private data, not whatever a contributor last committed."""
    job = _publish_showcase_workflow()["jobs"]["publish"]
    names = [step.get("name") for step in job["steps"]]
    assert "Refresh site data" in names
    assert names.index("Refresh site data") > names.index("Build public data"), (
        "the site data must be refreshed after the public data projection "
        "runs, or it copies last run's file"
    )
    for step in job["steps"]:
        if step.get("name") == "Refresh site data":
            assert "instance/public-data/events-public.json" in step["run"]
            assert "site/src/_data/events.json" in step["run"]


def test_publish_showcase_builds_the_site_before_pushing() -> None:
    job = _publish_showcase_workflow()["jobs"]["publish"]
    names = [step.get("name") for step in job["steps"]]
    assert "Install site" in names and "Build site" in names
    assert names.index("Refresh site data") < names.index("Build site"), (
        "the site must build from the refreshed data, not the committed fixture"
    )
    assert names.index("Build site") < names.index(
        "Push to the published repository"
    ), (
        "the build must run before the push step, or it publishes "
        "whatever site/_site last held"
    )


def test_publish_showcase_push_step_only_touches_the_root_site_files() -> None:
    """The disjoint-subtree argument the retry loop relies on: this step
    must never remove or restage `app/`, deploy.yml's own subtree of the
    same repository."""
    script = _publish_showcase_push_script()
    assert "! -name 'app'" in script, (
        "the push step's wipe must exclude app/ -- deploy.yml's own "
        "disjoint subtree -- or a site publish would delete the deployed "
        "application"
    )
    assert "rm -rf /tmp/vit/app" not in script
    assert "git add --force -A" in script, (
        "the built site is a whole-tree replacement (new pages appear "
        "without editing this step), staged in full, not one named "
        "file"
    )


def test_publish_showcase_push_step_refuses_to_publish_an_empty_build() -> None:
    """D-25: Eleventy exits 0 on 'Wrote 0 files' -- a wrong
    dir.input, a template error that skips every page, or any config change
    that makes the build emit nothing all 'succeed' as far as the 'Build
    site' step is concerned. Without a guard, the wipe below would then
    remove the published site and commit an empty publication over a
    working one -- D-25's own "a control that cannot fail loudly is not a
    control", except here the silent success is destructive rather than
    merely useless."""
    script = _publish_showcase_push_script()
    guard_at = script.find('if [ ! -f "$SITE_OUTPUT/index.html" ]')
    count_at = script.find("site_file_count=")
    wipe_at = script.find("find /tmp/vit")
    assert guard_at != -1, (
        "no guard checks that $SITE_OUTPUT/index.html exists -- a build "
        "that silently wrote nothing would still be published"
    )
    assert count_at != -1, (
        "no file-count floor beside the index.html check -- a build that "
        "wrote only one or two files (also wrong, with this many pages) "
        "would still be published"
    )
    assert -1 < guard_at < wipe_at and -1 < count_at < wipe_at, (
        "both emptiness guards must run before the wipe starts -- checked "
        "after, the wipe has already begun removing what a failed check "
        "could no longer replace"
    )
    guard_block = script[guard_at : script.find("fi", guard_at)]
    assert "exit 1" in guard_block, (
        "the index.html guard does not exit 1 -- a missing index.html "
        "must fail the step, not merely be noticed"
    )


def test_publish_showcase_push_step_clears_stale_files_before_copying() -> None:
    script = _publish_showcase_push_script()
    wipe_at = script.find("find /tmp/vit")
    copy_at = script.find("cp -r")
    assert wipe_at != -1 and copy_at != -1 and wipe_at < copy_at, (
        "a page removed from site/ must disappear from the publication "
        "too -- the wipe has to happen before the fresh build is copied in"
    )


def test_publish_showcase_push_step_retry_re_derives_rather_than_rebases() -> None:
    """The same defence deploy.yml's own 'Commit survey status' step uses
    (test_deploy_workflow_survey_status_retry_re_derives_rather_than_
    rebases, above), for the identical reason: this commit is a wholesale
    rewrite of generated files -- built HTML, a stylesheet, binary fonts --
    not an append. Replaying a rebase's diff over a full-file rewrite is
    exactly where it conflicts instead of applying; re-deriving discards
    the local commit and reproduces the identical output against whatever
    landed on main in the meantime."""
    script = _publish_showcase_push_script()
    commands = [
        line for line in script.splitlines() if not line.strip().startswith("#")
    ]
    assert not any("git rebase" in line for line in commands)
    assert not any("git pull" in line for line in commands)
    assert "git fetch origin main" in script
    assert "git reset --hard origin/main" in script
    retry_block = script.split("for attempt in 1 2 3; do", 1)[-1]
    assert "refresh_published_site" in retry_block, (
        "the retry must re-copy the already-built site over the freshly "
        "reset tree on every attempt, not only stage whatever survived "
        "the reset"
    )
    assert "git commit" in retry_block


def test_publish_showcase_site_ships_nojekyll() -> None:
    """The consequence of moving the templates here: the showcase's root is a full site
    (`index.html`, `style.css`, `fonts/`, `app/`), exactly what its
    already-active GitHub Pages setting ('branch main, folder root')
    serves -- but GitHub's default Jekyll processing swallows anything at
    that root it does not recognise, which is what served the README
    instead of the site until now. `.nojekyll` stops that. Sourced from
    `site/src/.nojekyll` and passed through by `site/.eleventy.js`, not
    `touch`-ed by this workflow, so the published site stays reproducible
    from `site/` alone."""
    assert (ROOT / "site/src/.nojekyll").exists(), (
        "site/src/.nojekyll is missing -- the published root would carry "
        "no .nojekyll marker, and GitHub's default Jekyll processing "
        "would swallow the site"
    )
    eleventy_config = (ROOT / "site/.eleventy.js").read_text(encoding="utf-8")
    assert "addPassthroughCopy('src/.nojekyll')" in eleventy_config, (
        "site/.eleventy.js no longer passes .nojekyll through to _site/ -- "
        "a build would silently drop it from the publication"
    )


# ------------------------------------------------------------------ #
# Commit authors: an address on a domain this project administers
# ------------------------------------------------------------------ #

#: Criterion 8 is universal -- no commit author anywhere may carry a domain
#: this project does not administer -- so this scans every workflow file
#: rather than naming the ones known to commit today. A hardcoded list is
#: what let `deploy.yml` through the first time: it copied
#: `publish-showcase.yml`'s push step, including its stale address on
#: this organisation's own domain, and the list here named only
#: `candidate-form.yml` and `publish-showcase.yml`, so nothing caught it.
#: A scan covers a workflow nobody has written yet, which a list never can.
WORKFLOWS_DIR = Path(".github/workflows")

#: The check used to look for one
#: syntax only -- `user\.email\s+"..."`, a double-quoted literal directly
#: after `user.email` -- because that is the shape the defect it was built
#: to catch happened to take (`deploy.yml` copying `publish-showcase.yml`'s
#: push step, stale off-domain address and all). An unquoted
#: address, a single-quoted one, an identity set through an
#: `actions/github-script` object literal instead of `git config`, or one
#: assigned through a `GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_EMAIL` environment
#: variable would all have read back zero matches and passed unnoticed --
#: the same shape of failure as the iCalendar leak guard that never saw
#: line folding.
#:
#: Whatever sets a commit's author, the address itself is written down
#: somewhere as text in the workflow that sets it -- `git config`'s
#: argument, an `env:` value, or a `github-script` field name are all just
#: different surroundings for the same address. So this reads by the
#: address's own shape, not by the syntax around it, and it no longer
#: matters which of those surroundings a future workflow chooses.
_EMAIL_SHAPE_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

#: The only domain a commit author here may use: a `users.noreply.github.com`
#: address claims nothing beyond what GitHub itself already vouches for.
_ALLOWED_EMAIL_DOMAIN = "users.noreply.github.com"


def _commit_emails(text: str) -> list[str]:
    """Every email-shaped string in `text`, in the order it appears."""
    return _EMAIL_SHAPE_RE.findall(text)


def _names_the_local_part(text: str, local: str) -> bool:
    """Whether `local` -- the part of a commit-author address before its
    `@` -- appears in `text` as its own token at least once *beyond* the
    address itself.

    Reads by shape for the same reason `_commit_emails` does: the token
    naming an automated identity might be `user.name "local"`, a
    `GIT_AUTHOR_NAME`/`GIT_COMMITTER_NAME` environment value, an
    `actions/github-script` `name:` field, or nothing more structured than
    a bare word -- all of them put `local` down as a standalone token, so a
    plain word-boundary count -- at least one occurrence beyond the address
    match itself -- catches every one of those shapes without caring which
    it is.
    """
    return len(re.findall(rf"\b{re.escape(local)}\b", text)) >= 2


def _workflow_files_in(directory: Path) -> list[Path]:
    """`.yml` and `.yaml` both, sorted together -- GitHub Actions runs
    either extension under `.github/workflows/` (every file in this
    repository today happens to be `.yml`, but nothing about that is
    enforced anywhere, and a sweep that only globbed `.yml` would have
    silently had nothing at all to say about a `.yaml` file someone added
    -- the third way this sweep could be evaded). A plain `list` directory
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
    """The third sweep evasion, proven with a probe
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


def _assert_no_foreign_domain(workflow_name: str, text: str) -> None:
    for email in _commit_emails(text):
        assert email.endswith(f"@{_ALLOWED_EMAIL_DOMAIN}"), (
            f"{workflow_name} carries the address {email!r}, not on "
            f"{_ALLOWED_EMAIL_DOMAIN} -- a domain this project does not "
            "administer (criterion 8)"
        )


def _assert_every_address_is_named(workflow_name: str, text: str) -> None:
    for email in _commit_emails(text):
        local = email.split("@", 1)[0]
        assert _names_the_local_part(text, local), (
            f"{workflow_name} carries the address {email!r} without a "
            f"matching name for {local!r} anywhere in the file"
        )


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_automated_commit_author_is_not_on_a_domain_we_do_not_administer(
    workflow: Path,
) -> None:
    _assert_no_foreign_domain(workflow.name, workflow.read_text(encoding="utf-8"))


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_automated_commit_identity_pairs_a_name_with_its_address(
    workflow: Path,
) -> None:
    """Every commit-author address a workflow carries has a matching name
    naming the same identity, so an automated commit reads as a
    recognisable bot rather than a bare, unexplained address -- whatever
    syntax set the address (see `_commit_emails`'s own comment)."""
    _assert_every_address_is_named(workflow.name, workflow.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ #
# Proven by name: five shapes the
# previous check -- `user\.email\s+"..."`, a double-quoted literal directly
# after the literal text `user.email` -- would have let a foreign-domain
# commit author through in without either test above ever seeing it. Each
# is run against the real assertion the parametrized tests above call
# (`_assert_no_foreign_domain`), not a reimplementation of it, so a
# regression in the checker itself fails these too, exactly the way
# `test_rebasing_on_a_rejected_push_can_lose_an_entry` proves the rebase
# defect by running the real re-derive helper instead of describing what a
# rebase would do.
# ------------------------------------------------------------------ #

_FOREIGN_ADDRESS = "publisher@example.invalid"

#: Escaped once, reused everywhere below: the address's domain contains a
#: literal `.`, a regex metacharacter `pytest.raises(match=...)` would
#: otherwise interpret rather than match.
_FOREIGN_DOMAIN_PATTERN = re.escape("example.invalid")


def test_evasion_1_unquoted_address_is_still_caught() -> None:
    """No quotes at all -- `git config user.email` accepts a bare token as
    happily as a quoted one; the old regex required a `"` right after the
    key and found nothing here."""
    text = f"run: git config user.email {_FOREIGN_ADDRESS}\n"
    with pytest.raises(AssertionError, match=_FOREIGN_DOMAIN_PATTERN):
        _assert_no_foreign_domain("probe.yml", text)


def test_evasion_2_single_quoted_address_is_still_caught() -> None:
    """Single quotes -- valid shell, invalid to a pattern anchored on `"`."""
    text = f"run: git config user.email '{_FOREIGN_ADDRESS}'\n"
    with pytest.raises(AssertionError, match=_FOREIGN_DOMAIN_PATTERN):
        _assert_no_foreign_domain("probe.yml", text)


def test_evasion_3_identity_via_github_script_is_still_caught() -> None:
    """No `git config` at all -- `actions/github-script` sets the commit
    author through the REST API's own `author`/`committer` object, entirely
    outside the `user.email`/`user.name` vocabulary the old regex looked
    for."""
    text = f"""
    - uses: actions/github-script@0123456789abcdef0123456789abcdef01234567
      with:
        script: |
          await github.rest.git.createCommit({{
            owner, repo, message: 'automated',
            author: {{ name: 'convener-publisher', email: '{_FOREIGN_ADDRESS}' }},
          }});
    """
    with pytest.raises(AssertionError, match=_FOREIGN_DOMAIN_PATTERN):
        _assert_no_foreign_domain("probe.yml", text)


def test_evasion_4_identity_via_environment_variable_is_still_caught() -> None:
    """Set through `env:` (`GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_EMAIL`, the
    environment variables `git` itself reads) rather than through
    `git config` -- the address never appears next to the literal text
    `user.email` at all."""
    text = f"""
    env:
      GIT_AUTHOR_EMAIL: {_FOREIGN_ADDRESS}
      GIT_AUTHOR_NAME: convener-publisher
    run: git commit -am "automated"
    """
    with pytest.raises(AssertionError, match=_FOREIGN_DOMAIN_PATTERN):
        _assert_no_foreign_domain("probe.yml", text)


def test_evasion_5_dot_yaml_workflow_is_still_swept(tmp_path: Path) -> None:
    """Not a parsing evasion but a discovery one: a smarter regex over a
    file the sweep never opens protects nothing. `_workflow_files_in`
    already globs `.yaml` (fixed independently, for sweep evasion 3 --
    `test_the_workflow_sweep_globs_yaml_files_too_not_only_yml`), so this
    closes entry 5 end to end by proving a `.yaml` file both reaches the
    sweep and still fails the real check once it does."""
    workflow = tmp_path / "probe.yaml"
    workflow.write_text(
        f'run: git config user.email "{_FOREIGN_ADDRESS}"\n', encoding="utf-8"
    )

    assert workflow in _workflow_files_in(tmp_path)
    with pytest.raises(AssertionError, match=_FOREIGN_DOMAIN_PATTERN):
        _assert_no_foreign_domain(workflow.name, workflow.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ #
# No repo-wide lint enforces SHA pinning
# or timeout-minutes. Deleting timeout-minutes from survey.yml, or
# swapping a pinned checkout SHA for actions/checkout@v7, left everything
# green. Both mutations were real before these checks existed --
# confirmed against this same `_workflow_files()` sweep. Text-scanned,
# the same idiom every other scan in this module uses, never parsed and
# executed.
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
    both evasions an earlier version of this check missed."""
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
    """The second sweep evasion, proven with a probe
    workflow: an earlier version of this check counted every
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
    """The first sweep evasion, proven with a probe
    workflow: an earlier version of this check matched
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

    Rewritten from a text-scanned line count (which
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
# `queue: max` turned out not to be a valid `concurrency`
# key at all (`actionlint`, 2026-08-24 -- see quality.yml). Once dropped,
# what a `group` plus `cancel-in-progress: false` leaves behind cancels a
# *waiting* run rather than queuing it -- a lost submission, not a delayed
# one, for a workflow whose every run carries one. Five workflows also
# rebased a local commit onto a rejected push instead of re-deriving
# against the refreshed tip, which registration.yml's own retry-loop
# comment already named as the way a JSON array's own closing lines get
# corrupted by a rebase conflict. Both checks below are scanned
# structurally, over every workflow this repository has, so a sixth one
# added later is caught the same way rather than needing its name added to
# a list here.
# ------------------------------------------------------------------ #


def _all_run_scripts(workflow: Path) -> list[tuple[str, str, str]]:
    """`(job id, step name, run: script)` for every step in `workflow`
    that has a `run:` key -- `uses:`-only steps carry nothing to scan."""
    loaded = safe_load(workflow.read_text(encoding="utf-8"))
    jobs = loaded.get("jobs") if isinstance(loaded, dict) else None
    found: list[tuple[str, str, str]] = []
    if not isinstance(jobs, dict):
        return found
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps", []):
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if isinstance(run, str):
                found.append((job_id, step.get("name", "<unnamed>"), run))
    return found


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_no_run_script_rebases_a_local_commit_on_a_rejected_push(
    workflow: Path,
) -> None:
    """Closes the class this repository fixed five instances of
    (candidate-form.yml, deploy.yml, derive-decision-register.yml, sweep.yml,
    visuals-production.yml): a retry loop that rebases a local commit onto
    a rejected push, rather than fetching the refreshed tip, hard-resetting
    and re-running the handler against it (registration.yml's and
    survey.yml's own shape, which every one of those five now follows
    too).

    Scanned on each step's parsed `run:` string, over uncommented lines
    only -- `git pull --rebase` named in an explanatory comment (as
    registration.yml's and survey.yml's own comments both still do, to say
    why they do *not* use it) must never trip this, and parsing the YAML
    structurally rather than grepping the raw file text is what keeps a
    `#`-prefixed line invisible here the same way it is to `set -e`."""
    for job_id, step_name, run in _all_run_scripts(workflow):
        commands = [
            line for line in run.splitlines() if not line.strip().startswith("#")
        ]
        assert not any("git rebase" in line for line in commands), (
            f"{workflow.name}::{job_id} ({step_name}) rebases a local "
            "commit on a rejected push -- re-derive instead: fetch, "
            "reset --hard, re-run the handler"
        )
        assert not any("git pull" in line for line in commands), (
            f"{workflow.name}::{job_id} ({step_name}) calls `git pull`, "
            "which defaults to a merge or rebase, never the fetch-and-"
            "reset-hard re-derive shape this repository standardises on "
            "for a shared write"
        )


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_a_repository_dispatch_workflow_declares_no_concurrency_group(
    workflow: Path,
) -> None:
    """Closed as a property rather than
    a name list: a workflow triggered by `repository_dispatch` carries one
    externally-submitted payload per run -- a registration, a survey
    response, a proposal -- that only that one dispatch will ever deliver.
    A `group` plus `cancel-in-progress: false` lets exactly one run wait
    behind the one in progress and *cancels* any further arrival, and a
    cancelled run never starts, so the retry loop inside it can never save
    what it was carrying. A workflow triggered by `push`, `schedule` or
    `workflow_dispatch` instead regenerates its own output from this
    repository's own state, so a superseded run really is replaceable, and
    keeps whatever `concurrency:` block it declares.

    Derived from the trigger actually declared, not from
    `{"registration.yml", "survey.yml", "candidate-form.yml"}` written out
    by hand -- a sixth `repository_dispatch` workflow added next month is
    caught by this test the same way those three were, without anyone
    remembering to add its name anywhere."""
    loaded = safe_load(workflow.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    if "repository_dispatch" not in workflow_event_names(loaded):
        pytest.skip(f"{workflow.name} is not repository_dispatch-triggered")
    assert "concurrency" not in loaded, (
        f"{workflow.name} is dispatched externally -- one submission per "
        "run -- and declares a concurrency group; grouping cancels a "
        "waiting run rather than queuing it, "
        "which drops exactly the data this workflow exists to keep"
    )


def test_the_externally_dispatched_sweep_actually_matches_something() -> None:
    """The guard above skips every workflow that is not
    `repository_dispatch`-triggered, which is the honest thing to do per
    file -- but a parametrised skip degrades silently. If
    `workflow_event_names` ever stopped recognising that trigger (a
    refactor, a change in how the `on:` block is written, a bug), all 31
    cases would skip and the suite would still report green: a control
    that cannot fail, which is the shape this repository has now caught a
    dozen times.

    So the set is asserted non-empty here, separately, and named. This test
    fails loudly the day the detection breaks, while the guard above keeps
    reporting per file."""
    dispatched = sorted(
        workflow.name
        for workflow in _workflow_files()
        if "repository_dispatch"
        in workflow_event_names(safe_load(workflow.read_text(encoding="utf-8")) or {})
    )
    assert dispatched, (
        "no workflow was detected as repository_dispatch-triggered, so the "
        "concurrency guard above skipped every case and proved nothing -- "
        "either every externally dispatched workflow really is gone, or "
        "`workflow_event_names` has stopped recognising the trigger"
    )


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603, B607
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _local_repo_pair(tmp_path: Path) -> tuple[Path, Path]:
    """A bare `origin`, seeded with one committed `shared.json: []`, and
    two independent clones of it (`a`, `b`) -- stand-ins for two workflow
    runs' own checkouts, started far enough apart that one has already
    pushed by the time the other tries to. Everything lives on local disk;
    the "remote" is a bare repo under `tmp_path`, never a network call."""
    origin = tmp_path / "origin.git"
    assert (
        _run_git(
            ["init", "--bare", "-q", "-b", "main", str(origin)], tmp_path
        ).returncode
        == 0
    )

    seed = tmp_path / "seed"
    seed.mkdir()
    assert _run_git(["init", "-q", "-b", "main"], seed).returncode == 0
    _run_git(["config", "user.email", "seed@users.noreply.github.com"], seed)
    _run_git(["config", "user.name", "seed"], seed)
    (seed / "shared.json").write_text("[]\n", encoding="utf-8")
    _run_git(["add", "shared.json"], seed)
    assert _run_git(["commit", "-q", "-m", "seed"], seed).returncode == 0
    assert _run_git(["remote", "add", "origin", str(origin)], seed).returncode == 0
    assert _run_git(["push", "-q", "origin", "main"], seed).returncode == 0

    clone_a, clone_b = tmp_path / "a", tmp_path / "b"
    for clone in (clone_a, clone_b):
        assert (
            _run_git(["clone", "-q", str(origin), str(clone)], tmp_path).returncode == 0
        )
        _run_git(["config", "user.email", "handler@users.noreply.github.com"], clone)
        _run_git(["config", "user.name", "handler"], clone)
    return clone_a, clone_b


def _append_entry(clone: Path, entry: str) -> None:
    """Stands in for a workflow's own handler (`convener-handle-registration`,
    `convener-handle-proposal`): read the current
    array, append one more entry, write it back -- the exact "one array,
    two concurrent writers" shape registration.yml's own retry-loop
    comment names as what a rebase corrupts."""
    path = clone / "shared.json"
    entries = json.loads(path.read_text(encoding="utf-8"))
    if entry not in entries:
        entries.append(entry)
    path.write_text(json.dumps(entries) + "\n", encoding="utf-8")


def test_re_deriving_on_a_rejected_push_loses_no_entry(tmp_path: Path) -> None:
    """Provoked, not assumed. `a` pushes its own entry first; `b`'s
    checkout is now stale, so appending its own entry and pushing is
    rejected as a non-fast-forward -- the collision this repository's real
    workflows face on every burst of concurrent public submissions.
    Re-deriving (fetch, reset --hard, re-run the handler against the
    refreshed file, recommit, retry) is exactly registration.yml's and
    survey.yml's own retry loop, and candidate-form.yml's, deploy.yml's,
    derive-decision-register.yml's, sweep.yml's and visuals-production.yml's too. Both
    entries must survive."""
    clone_a, clone_b = _local_repo_pair(tmp_path)

    _append_entry(clone_a, "run-a")
    _run_git(["add", "shared.json"], clone_a)
    _run_git(["commit", "-q", "-m", "run a"], clone_a)
    assert _run_git(["push", "origin", "main"], clone_a).returncode == 0

    _append_entry(clone_b, "run-b")
    _run_git(["add", "shared.json"], clone_b)
    _run_git(["commit", "-q", "-m", "run b"], clone_b)
    first_attempt = _run_git(["push", "origin", "main"], clone_b)
    assert first_attempt.returncode != 0, (
        "the setup is wrong if b's first push is not rejected -- "
        "there is no collision here to re-derive against"
    )

    # The re-derive loop itself -- fetch, reset --hard, re-run the
    # handler, recommit, retry -- never `git pull --rebase`.
    assert _run_git(["fetch", "-q", "origin", "main"], clone_b).returncode == 0
    assert _run_git(["reset", "-q", "--hard", "origin/main"], clone_b).returncode == 0
    _append_entry(clone_b, "run-b")
    _run_git(["add", "shared.json"], clone_b)
    _run_git(["commit", "-q", "-m", "run b"], clone_b)
    assert _run_git(["push", "origin", "main"], clone_b).returncode == 0

    _run_git(["fetch", "-q", "origin", "main"], clone_a)
    shown = _run_git(["show", "origin/main:shared.json"], clone_a)
    assert shown.returncode == 0, shown.stderr
    final = json.loads(shown.stdout)
    assert set(final) == {"run-a", "run-b"}, (
        f"re-deriving lost an entry: {final!r} -- both concurrent writes "
        "must survive a collision"
    )


def test_rebasing_on_a_rejected_push_can_lose_an_entry(tmp_path: Path) -> None:
    """The mutation this claim has to show, not merely
    describe: restore the pattern this repository removed -- `git pull --rebase`
    (here, its two constituent commands, to inspect the conflict rather
    than let a plumbing wrapper hide it) instead of fetch-and-reset-hard --
    against the identical collision the previous test proves re-deriving
    survives, and watch it fail instead. Both runs append to the *same*
    JSON array, so both diffs touch its own closing line -- exactly the
    shape registration.yml's own retry-loop comment names as `git
    rebase`'s failure mode."""
    clone_a, clone_b = _local_repo_pair(tmp_path)

    _append_entry(clone_a, "run-a")
    _run_git(["add", "shared.json"], clone_a)
    _run_git(["commit", "-q", "-m", "run a"], clone_a)
    assert _run_git(["push", "origin", "main"], clone_a).returncode == 0

    _append_entry(clone_b, "run-b")
    _run_git(["add", "shared.json"], clone_b)
    _run_git(["commit", "-q", "-m", "run b"], clone_b)
    assert _run_git(["push", "origin", "main"], clone_b).returncode != 0

    assert _run_git(["fetch", "-q", "origin", "main"], clone_b).returncode == 0
    rebased = _run_git(["rebase", "origin/main"], clone_b)
    assert rebased.returncode != 0, (
        "expected the rebase to conflict on shared.json's own line -- if "
        "it did not, this probe no longer reproduces the collision "
        "registration.yml's own comment describes"
    )
    # Left mid-rebase on the conflict -- exactly the state registration.
    # yml's own comment names: a `set -e` step would stop here, before its
    # own `::error::` line, having neither pushed nor reported why. b's
    # own entry never reaches origin.
    _run_git(["rebase", "--abort"], clone_b)
    shown = _run_git(["show", "origin/main:shared.json"], clone_a)
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout) == ["run-a"], (
        "run-b never reached origin -- confirming the loss the rebase "
        "pattern produces, which is exactly why it was removed"
    )


# ------------------------------------------------------------------ #
# issue-certificates.yml / reissue-certificate.yml / revoke-certificate.yml
# The finding these three exist because of:
# `certificate.issue` had a tested, correct implementation and no caller
# anywhere in this repository, because no workflow ever set
# CONVENER_SIGNING_KEY in a step that ran it. **The check below is the single
# most important one here**: a workflow once shipped forwarding
# three of the nine environment variables its own command read, its whole
# suite stayed green, and the gap went unnoticed until a human read the
# workflow file directly, not a test failure. Derived from each command's
# own source (`ast`, the same tool this project's import-graph test in
# test_notify.py already uses to read a module rather than trust a
# docstring) rather than a hand-typed list -- a hand-copied list is the
# same defect one layer up, and would not have caught that bug
# either, since a list copied *from the workflow* reproduces exactly the
# workflow's own mistake.
# ------------------------------------------------------------------ #


def _cli_source(command: str) -> Path:
    """Where the command named `command` is written, derived rather than
    listed: `convener_ops.cli` re-exports exactly the names
    `tools/pyproject.toml` declares, and each one carries the module it
    was defined in. A command moved from one module of `convener_ops/cli/`
    to another moves this answer with it, which is the whole reason the
    path is not typed out here."""
    module = sys.modules[getattr(convener_ops.cli, command).__module__]
    assert module.__file__ is not None
    return Path(module.__file__).resolve().relative_to(ROOT)


def _cli_module(command: str) -> ModuleType:
    """The module `command` is written in, for resolving a constant it
    names."""
    return sys.modules[getattr(convener_ops.cli, command).__module__]


ISSUE_CERTIFICATES_WORKFLOW = Path(".github/workflows/issue-certificates.yml")
REISSUE_CERTIFICATE_WORKFLOW = Path(".github/workflows/reissue-certificate.yml")
REVOKE_CERTIFICATE_WORKFLOW = Path(".github/workflows/revoke-certificate.yml")
#: The delivery step issue-certificates.yml runs after issuance,
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

#: Excluded from `_env_vars_read`'s own result:
#: `_write_github_output` reads `GITHUB_OUTPUT`
#: (`cli/journey/certificate.py::issue_certificates` reaches it through that shared
#: helper), but this is not a secret or an input a workflow author ever forwards through
#: a step's own `env:` block -- the runner already sets it, unconditionally,
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
    """The analogue of `_calls_platform_from_env` above: `cli/`
    calls `delivery.deliver(message, os.environ)` (a module-qualified
    attribute call, `confirmation.deliver`'s own calling convention --
    `cli/` imports `delivery` as a module, never a bare name), which
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
    """The analogue of `_calls_delivery_deliver` above:
    `cli/journey/survey.py::invite_survey` calls `confirmation.deliver(message,
    os.environ)` directly -- there is no dedicated transport for a survey invitation to
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


def _helper_sources(path: Path) -> dict[str, Path]:
    """Every function a plain, undotted call inside `path`'s own module can
    reach, and the file each is written in -- the universe
    `_env_vars_read`'s recursion (below) is allowed to walk into.

    Two kinds, and the second is the one that was missing. A function the
    module defines itself resolves to `path`. A function the module
    imports by name from another module of `convener_ops.cli`
    (`from convener_ops.cli.journey.event import conference_ids_from_env`)
    is called exactly the same way -- an undotted `ast.Name` -- and reads
    exactly the same environment, so it resolves to the file it is defined
    in. Stopping at the module's own `def`s was correct while every
    command and every helper it used sat in one file; the day the commands
    were split into `convener_ops/cli/`, that walk lost
    `CONVENER_FCC_CONFERENCE_ID` and `RESEND_ALL` from five commands at
    once. It failed loudly rather than silently, because the sets it
    derives are compared against what the workflows actually forward --
    which is the only reason this is a paragraph and not a leak.

    **`convener_ops.cli` and no further**, which is the same boundary the
    single file used to draw. `repo_root` is imported by every command and
    reads `CONVENER_REPO_ROOT`, a development override no workflow ever
    forwards; following an import out of the command line would put it,
    and every other read a called module happens to make, into the set a
    workflow is then required to carry.

    A dotted call (`module.function(...)`) is deliberately still out of
    reach; the three that matter are named one by one below."""
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    found: dict[str, Path] = {
        node.name: path for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ImportFrom) and node.module):
            continue
        if not node.module.startswith("convener_ops.cli"):
            continue
        origin = Path("tools") / Path(node.module.replace(".", "/"))
        for candidate in (origin.with_suffix(".py"), origin / "__init__.py"):
            if (ROOT / candidate).is_file():
                defined = {
                    inner.name
                    for inner in ast.walk(
                        ast.parse((ROOT / candidate).read_text(encoding="utf-8"))
                    )
                    if isinstance(inner, ast.FunctionDef)
                }
                for alias in node.names:
                    if alias.asname is None and alias.name in defined:
                        found.setdefault(alias.name, candidate)
                break
    return found


def _env_vars_read(
    path: Path,
    function_name: str,
    *,
    _seen: frozenset[tuple[str, str]] = frozenset(),
) -> set[str]:
    """Every environment variable `function_name` (defined in `path`)
    reads directly (`os.environ.get(...)` or `os.environ[...]`), plus --
    derived, not hand-typed -- `platform_fcc.TOKEN_ENV` whenever the
    function hands `os.environ` whole to `platform_from_env` (
    `platform_from_env`'s own body is never walked; only the fact that
    this function calls it at all, which is what actually determines
    whether the read happens).

    **Recurses into this module's own helper functions.**
    The first version of this walk covered only
    `function_name`'s own body, which made it blind to a read moved out
    of that body and into a private helper -- exactly what
    `cli/journey/event.py::conference_ids_from_env` is, this same round: without this
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

    Also derived, not hand-typed: `confirmation.SMTP_ENV_VARS`
    whenever the function calls `delivery.deliver` -- `_calls_delivery_deliver`,
    below, the second special case this walk knows about by name, for the
    identical reason `platform_from_env` needed one: `delivery.deliver`
    hands `os.environ` on to `confirmation.smtp_config_from_env`, a read
    genuinely inside a different module's own AST. There is a third,
    identical case, `_calls_confirmation_deliver`:
    `cli/journey/survey.py::invite_survey` calls `confirmation.deliver` directly, rather
    than through `delivery.deliver`'s own indirection, so the same read needs its own
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
    function's own scope by design (it answers "what does `cli/` read",
    not "what does everything `cli/` calls read")."""
    if (path.as_posix(), function_name) in _seen:
        return set()
    func = _function_node(path, function_name)
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            callee = node.func
            is_os_environ_get = (
                isinstance(callee, ast.Attribute)
                and callee.attr == "get"
                and _is_os_environ(callee.value)
            )
            # `env_flag_is_true(name)` reads
            # `os.environ.get(name, ...)` one level down, through its own
            # parameter -- invisible to the recursion below, which only
            # ever sees a literal passed directly to `os.environ.get`
            # itself, never one threaded through a second function's own
            # argument. The literal lives at the *call site* here, not
            # inside the helper's body, so it is read directly off this
            # call rather than by walking into `env_flag_is_true` at all.
            is_env_flag_is_true = (
                isinstance(callee, ast.Name) and callee.id == "env_flag_is_true"
            )
            if (is_os_environ_get or is_env_flag_is_true) and node.args:
                name = _literal_env_name(node.args[0])
                if name and name not in _RUNNER_PROVIDED_ENV_VARS:
                    names.add(name)
            # `given.value(option, name)` is the same shape as
            # `env_flag_is_true` above and needs the same case for the
            # same reason -- the read is one level down, inside
            # `cli/given.py`, through that function's own parameter -- with
            # one difference: the literal is its *second* argument, because
            # the first is the option an operator may have typed instead.
            # Missing it would make a command that moved a value from a
            # bare `os.environ.get` into an option silently drop out of the
            # set this derives, and the workflow check below would go on
            # passing while forwarding nothing.
            is_given_value = (
                isinstance(callee, ast.Attribute)
                and callee.attr == "value"
                and isinstance(callee.value, ast.Name)
                and callee.value.id == "given"
            )
            if is_given_value and len(node.args) > 1:
                name = _literal_env_name(node.args[1])
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

    seen = _seen | {(path.as_posix(), function_name)}
    reachable = _helper_sources(path)
    called = {
        node.func.id
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for helper in sorted(called & reachable.keys()):
        names |= _env_vars_read(reachable[helper], helper, _seen=seen)
    return names


def _last_path_component(
    expr: ast.expr,
    assigned: dict[str, ast.expr],
    module: ModuleType,
    _seen: frozenset[str] = frozenset(),
) -> str | None:
    """The trailing literal component of a `Path(...) / a / b / c`-style
    chain -- either a string constant (`"registrations.enc"`) or a
    module-level constant the command's own module imports by name
    (`ENCRYPTED_ATTENDANCE_FILENAME`), resolved against the real module
    rather than retyped. Recurses through `assigned` for a variable built
    in an earlier statement (`enc_path = root / rel_path`, `rel_path = ...`),
    the same "follow the assignment, do not hand-type the answer" idiom
    `_env_vars_read` already uses for environment variables."""
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return _last_path_component(expr.right, assigned, module, _seen)
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.Call):
        # Path("data") -- the innermost call in a chain; only reachable
        # when a chain has no `/` component after it, which none of this
        # module's own path-building does today, but this keeps the walk
        # from silently returning None for it if that ever changes.
        if expr.args:
            return _last_path_component(expr.args[-1], assigned, module, _seen)
        return None
    if isinstance(expr, ast.Name):
        if hasattr(module, expr.id):
            value = getattr(module, expr.id)
            if isinstance(value, str):
                return value
        if expr.id in assigned and expr.id not in _seen:
            return _last_path_component(
                assigned[expr.id], assigned, module, _seen | {expr.id}
            )
    return None


def _module_of(path: Path) -> ModuleType:
    """The imported module a repository-relative source path names."""
    dotted = path.with_suffix("").as_posix().removeprefix("tools/").replace("/", ".")
    return importlib.import_module(dotted.removesuffix(".__init__"))


def _files_written(path: Path, function_name: str) -> set[str]:
    """The filename (final path component) of every `<var>.write_text(...)`
    call inside `function_name`, derived from the assignment that built
    `<var>` -- not a hand-typed list, which is exactly the shape that let
    a real defect through: a fix that adds a second `write_text` call inside
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
                component = _last_path_component(expr, assigned, _module_of(path))
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
    expected = _env_vars_read(_cli_source("issue_certificates"), "issue_certificates")
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_SIGNING_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        # Read inside `_conference_ids_from_env`,
        # a helper `issue_certificates` calls -- present here only because
        # `_env_vars_read` recurses into it.
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
        "a workflow shipped with exactly this gap once"
    )


def test_reissue_certificate_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(_cli_source("reissue_certificate"), "reissue_certificate")
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_SIGNING_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        "CERTIFICATE_ID",
        # See
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
    expected = _env_vars_read(_cli_source("revoke_certificate"), "revoke_certificate")
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
# The same check above, for the two delivery jobs:
# the delivery step issue-certificates.yml runs after issuance, and the
# standalone deliver-certificate.yml resend keyed by CERTIFICATE_ID.
# Both must forward every environment variable
# their command reads, including all five CONVENER_SMTP_* secrets -- a
# workflow once shipped passing three of nine and its whole suite stayed
# green, so the derived-environment test covers
# the new jobs rather than restating a hand-copied list.
# ------------------------------------------------------------------ #


def test_issue_certificates_delivery_step_carries_every_env_var_it_reads() -> None:
    expected = _env_vars_read(
        _cli_source("deliver_certificates"), "deliver_certificates"
    )
    assert expected == {
        "EVENT_ID",
        "EVENT_PRIVATE_KEY",
        "CONVENER_SIGNING_KEY",
        "CONVENER_MATCHING_SALT",
        "CONVENER_MEETING_API_TOKEN",
        "CONVENER_FCC_CONFERENCE_ID",
        # The identifier hand-off from the issuance
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
        "directly -- a workflow shipped with exactly this gap once"
    )


def test_deliver_certificate_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(_cli_source("deliver_certificate"), "deliver_certificate")
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


#: The exact names any of these workflows'
#: `workflow_dispatch` inputs may ever carry -- an allowlist, not the
#: one-word denylist (`"email" not in trigger.lower()`) this test used to
#: be. "Never an address" is the one property
#: every input list in this trio must hold, and the old denylist let
#: `attendee_address`, `contact` or `who` sail straight through it
#: untouched. This repository already argues the general case in
#: `certificate.public_register`'s own docstring: an allowlist of exactly
#: what may leave, not a denylist of the one thing that must not.
#: `resend_all` joined this set with
#: `issue-certificates.yml`'s own delivery step: a boolean, never
#: personal data, so the property still holds.
_ALLOWED_CERTIFICATE_WORKFLOW_INPUTS = frozenset(
    {"event_id", "certificate_id", "conference_id", "resend_all"}
)

#: Matches a `workflow_dispatch` input's own name -- a key indented
#: exactly six spaces under `on: / workflow_dispatch: / inputs:` in every
#: workflow file this repository writes by hand (verified against all
#: three below, and against recording.yml's own `conference_id`).
_WORKFLOW_DISPATCH_INPUT_NAME_RE = re.compile(r"^ {6}([A-Za-z_][A-Za-z0-9_]*):$", re.M)


def test_certificate_workflows_accept_only_the_allowlisted_inputs() -> None:
    """The one property every input list in this trio must hold. A
    scan over the raw `on:` trigger block's own text, the same "read
    around `on:` as raw text" idiom
    `test_publish_showcase_paths_trigger_includes_the_certificate_register`
    already uses -- PyYAML's YAML-1.1 bool resolver reads a bare `on:` key
    as `True`, not `"on"`, so `safe_load` would silently drop this
    section's own key if it were relied on here instead."""
    for workflow_path in (
        ISSUE_CERTIFICATES_WORKFLOW,
        REISSUE_CERTIFICATE_WORKFLOW,
        REVOKE_CERTIFICATE_WORKFLOW,
        # The same property applies to the resend
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
            f"{sorted(_ALLOWED_CERTIFICATE_WORKFLOW_INPUTS)} -- these "
            "require an identifier, never an address, and an allowlist "
            "is what actually enforces that, not a denylist of the one "
            "word 'email'"
        )


# ------------------------------------------------------------------ #
# D-24 -- an operator command
# names a thing, never a person -- applies to every workflow_dispatch
# input in the repository, not only the certificate trio above. A review
# found exactly the gap `test_certificate_workflows_accept_only_the_
# allowlisted_inputs`'s own docstring already names as the reason an
# allowlist beats a denylist: `erase-registration.yml` and
# `resend-confirmation.yml` both took a bare `email` input, which GitHub
# renders and retains on the run's own page for as long as the run's
# history exists -- so the erasure command was manufacturing a fresh,
# permanent, plaintext copy of the exact address it exists to erase.
#
# Repository-wide, an allowlist of every legitimate input name is not
# viable -- a future workflow may legitimately need a new identifier this
# module has never seen -- so this closes the *class* the other way: a
# denylist of the person-shaped word *parts* an input name's own
# underscore-separated tokens must never contain. `certificate_id`,
# `conference_id`, `encrypted_identifier` and `matching_code` all clear
# it; `email`, `attendee_address`, `contact` and `first_name` all trip it,
# whatever workflow they turn up in next.
# ------------------------------------------------------------------ #

#: Every token a workflow_dispatch input's own name, split on `_`, must
#: never contain -- each one names a person-shaped fact rather than a
#: record. Deliberately word *parts*, not whole names: `attendee_address`
#: splits to `{"attendee", "address"}`, `contact_email` to `{"contact",
#: "email"}`, `first_name` to `{"first", "name"}` -- every one caught by a
#: single token here, without hand-listing every compound name a future
#: workflow might spell it with.
_PERSON_LIKE_INPUT_TOKENS = frozenset(
    {
        "email",
        "mail",
        "address",
        "name",
        "phone",
        "surname",
        "firstname",
        "lastname",
        "contact",
        "who",
        "institution",
    }
)


def _workflow_dispatch_input_names(workflow: Path) -> set[str]:
    text = workflow.read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    return set(_WORKFLOW_DISPATCH_INPUT_NAME_RE.findall(trigger))


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_no_workflow_dispatch_input_looks_like_a_person(workflow: Path) -> None:
    """D-24, repository-wide: closes the class a review found one instance of.
    Every workflow_dispatch input's own name is split on `_`; none of its
    tokens may be a person-shaped word from `_PERSON_LIKE_INPUT_TOKENS`.
    A thirtieth workflow that adds `attendee_address`, `contact_email` or
    `first_name` fails this the moment it is written, by name, rather than
    waiting for a reviewer to find it by hand."""
    for name in _workflow_dispatch_input_names(workflow):
        tokens = set(name.lower().split("_"))
        offending = tokens & _PERSON_LIKE_INPUT_TOKENS
        assert not offending, (
            f"{workflow.name}: workflow_dispatch input {name!r} carries "
            f"{sorted(offending)} -- an operator command names a record, "
            "never a person (D-24); GitHub renders and retains a "
            "dispatch input's own value on the run page for as long as "
            "the run exists"
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
    # `actions: write` joined `contents: write`
    # in all three jobs -- each now dispatches publish-showcase.yml as its
    # own last step once it has actually committed something, which needs
    # that permission (`workflow_dispatch` is the documented exception to
    # GitHub's recursion guard, so no new secret is needed).
    assert job_data.get("permissions") == {
        "contents": "write",
        "actions": "write",
    }, (
        f"{workflow_path.as_posix()}::{job} commits a change to "
        "certificates.yml (needs contents: write) and dispatches "
        "publish-showcase.yml afterwards (needs actions: write)"
    )
    assert isinstance(job_data.get("timeout-minutes"), int), (
        f"{workflow_path.as_posix()}::{job} has no timeout-minutes"
    )


# ------------------------------------------------------------------ #
# GitHub does not start a new workflow run from
# an event triggered by a job's own GITHUB_TOKEN (the recursion guard),
# so a push made by any of the three certificate workflows -- or by
# sweep.yml -- could never fire publish-showcase.yml's own `push`-triggered
# `paths:` trigger, however carefully that trigger was worded.
# Each of those four jobs now dispatches publish-showcase.yml directly,
# with `gh workflow run`, as its own last step -- `workflow_dispatch` is
# the one documented exception to the recursion guard. Text assertions on
# the parsed `run:` block, the same idiom this module already uses
# throughout (see this module's own docstring for why: running the script
# means a real `gh` call, exactly the kind of network access this suite
# must not take on).
# ------------------------------------------------------------------ #

PUBLISH_SHOWCASE_DISPATCH = "gh workflow run publish-showcase.yml"
#: The nightly sweep and the board digest are
#: one workflow now (`sweep-and-notify.yml`), and the sweep is the first
#: step of its `daily` job rather than a file and a cron of its own. The
#: dispatch this constant's own tests below follow is unchanged, and so is
#: the reason it exists.
SWEEP_WORKFLOW = Path(".github/workflows/sweep-and-notify.yml")
SWEEP_JOB = "daily"


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
def test_certificate_workflow_dispatches_deploy_only_after_a_real_push(
    workflow_path: Path, job: str, run_contains: str
) -> None:
    """The mutation this pins directly: "make the
    publication dispatch step unconditional, or delete it. A test must
    fail." Two halves, both required: the dispatch must be reachable once
    a push genuinely succeeds, and must not be reachable on the "nothing
    to commit" branch, where nothing was ever pushed for a publication to
    reflect.

    This used to assert the identical shape
    for `publish-showcase.yml`, dispatched here unconditionally alongside
    deploy.yml. That dispatch is gone now (dead motion -- see
    `test_certificate_register_workflows_no_longer_dispatch_publish_showcase`),
    so this test follows the one dispatch that remains and still matters:
    deploy.yml, the file a verification page actually depends on."""
    script = _job_step_script(workflow_path, job, run_contains)

    pushed = _guarded_block(script, "if git push; then")
    assert DEPLOY_DISPATCH in pushed, (
        f"{workflow_path.as_posix()}::{job} does not dispatch deploy.yml "
        "once a change is genuinely pushed -- a revocation, issuance or "
        "correction would otherwise reach nobody"
    )

    unchanged = _guarded_block(script, "if git diff --staged --quiet; then")
    assert DEPLOY_DISPATCH not in unchanged, (
        f"{workflow_path.as_posix()}::{job} dispatches deploy.yml even "
        "when nothing changed this run -- the dispatch step must be "
        "conditional on a real push, not unconditional"
    )


def test_sweep_workflow_dispatches_publish_showcase_only_after_a_real_push() -> None:
    """The same fix, and the same two-halves guard, for the sweep -- a
    re-read found the identical suppression there: `events-public.json`
    had never been republished after a nightly sweep,
    since the sweep also pushes `instance/data/speakers.yml` with GITHUB_TOKEN.

    Merging the sweep into
    `sweep-and-notify.yml` makes this test matter *more*, not
    less: the merged workflow's own `push:` trigger names
    `instance/data/speakers.yml`, the exact file the sweep commits, so a reader
    could easily conclude the publication now happens by itself. It does
    not -- the recursion guard is why this dispatch exists, and it is
    unchanged by the merge."""
    script = _job_step_script(SWEEP_WORKFLOW, SWEEP_JOB, "git commit -m")

    pushed = _guarded_block(script, "if git push; then")
    assert PUBLISH_SHOWCASE_DISPATCH in pushed, (
        "the sweep does not dispatch publish-showcase.yml once a change is "
        "genuinely pushed -- events-public.json would never be republished "
        "after a sweep"
    )

    unchanged = _guarded_block(script, "if git diff --staged --quiet; then")
    assert PUBLISH_SHOWCASE_DISPATCH not in unchanged, (
        "the sweep dispatches publish-showcase.yml even when nothing changed this run"
    )


# ------------------------------------------------------------------ #
# Dispatching publish-showcase.yml alone
# was never enough for a workflow that changes the certificate register --
# that workflow rebuilt src/_data/certificates.json in the showcase,
# which nothing there ever served (that write is gone). The file
# `src/verify/register.ts` actually fetches is only rebuilt by
# deploy.yml's own "Build public data" step, and nothing dispatched it:
# `grep -rn "gh workflow run" .github/workflows/` returned four hits, all
# four naming publish-showcase.yml, none naming deploy.yml. This had
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

#: This used to require a quoted
#: `git add "path"` (`r'git add ["\'][^\n"\']*certificates\.yml'`) --
#: an unquoted `git add instance/data/events/*/certificates.yml`, the ordinary
#: shape for a glob (quoting it would stop the shell from expanding it),
#: escaped the scan silently. `_register_writing_jobs` below found no
#: workflow job at all for that mutation, and the mutation was
#: reproducible: adding a job whose `run:` staged the register with an
#: unquoted glob passed `_register_writing_jobs`'s own "no workflow job
#: stages a change to certificates.yml" sanity assertion as if the
#: register were unwritten, then silently skipped every dispatch check
#: below it -- exactly the rot vector this phase's own history (Critical
#: 1's docstring, above: "four rounds in a row") already warns about.
#: No longer anchored on a leading quote: matches `git add` followed by
#: any run of non-whitespace characters that contains `certificates.yml`,
#: quoted or not.
_CERTIFICATES_STAGED_RE = re.compile(r"git add\s+\S*certificates\.yml\S*")


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
    "run_line",
    [
        'git add "instance/data/events/$EVENT_ID/certificates.yml"',
        "git add 'instance/data/events/$EVENT_ID/certificates.yml'",
        # Carried item 3: the unquoted shape a glob actually needs --
        # quoting `*` would stop the shell expanding it -- used to escape
        # `_CERTIFICATES_STAGED_RE` entirely.
        "git add instance/data/events/*/certificates.yml",
        "git add instance/data/events/mrg-042/certificates.yml",
    ],
)
def test_certificates_staged_re_matches_quoted_and_unquoted_git_add(
    run_line: str,
) -> None:
    assert _CERTIFICATES_STAGED_RE.search(run_line), (
        f"_CERTIFICATES_STAGED_RE does not match {run_line!r} -- a workflow "
        "staging the register this way would escape every dispatch check "
        "below it silently"
    )


@pytest.mark.parametrize(
    "workflow_path,job",
    _register_writing_jobs(),
    ids=lambda value: value if isinstance(value, str) else value.name,
)
def test_workflow_that_writes_the_certificate_register_dispatches_deploy(
    workflow_path: Path, job: str
) -> None:
    """A workflow that changes `certificates.yml` and pushes with
    GITHUB_TOKEN must dispatch deploy.yml once that push genuinely lands,
    or it does not count: deploy.yml is what rebuilds
    app/dist/certificates.json, the file a verification page actually
    fetches.

    This used to also require
    publish-showcase.yml dispatched in the same guard. That requirement is
    gone on purpose, not merely relaxed -- see
    `test_certificate_register_workflows_no_longer_dispatch_publish_showcase`
    just below, which pins the opposite: none of these jobs dispatch it
    any more, because nothing a certificate change writes ever touches
    `instance/data/speakers.yml`, the only input that dispatch ever did anything
    with."""
    loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    run = next(
        step["run"]
        for step in loaded["jobs"][job]["steps"]
        if isinstance(step.get("run"), str)
        and _CERTIFICATES_STAGED_RE.search(step["run"])
    )
    pushed = _guarded_block(run, "if git push; then")
    assert DEPLOY_DISPATCH in pushed, (
        f"{workflow_path.as_posix()}::{job} changes the certificate "
        "register and pushes it, but does not dispatch deploy.yml -- the "
        "file src/verify/register.ts actually fetches would never be "
        "rebuilt"
    )


@pytest.mark.parametrize(
    "workflow_path,job",
    _register_writing_jobs(),
    ids=lambda value: value if isinstance(value, str) else value.name,
)
def test_certificate_register_workflows_no_longer_dispatch_publish_showcase(
    workflow_path: Path, job: str
) -> None:
    """Dispatching publish-showcase.yml
    alongside deploy.yml was dead motion for every workflow that only
    ever changes `certificates.yml` -- that dispatch's own job never
    touches anything but `instance/data/speakers.yml`, so a certificate-only push
    always found nothing changed there and exited as a no-op. Removed
    from `issue-certificates.yml`, `reissue-certificate.yml` and
    `revoke-certificate.yml`; pinned here so it cannot quietly come back
    (`sweep.yml`, which genuinely can change `instance/data/speakers.yml`, is not
    one of these jobs and keeps its own dispatch)."""
    loaded = safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    run = next(
        step["run"]
        for step in loaded["jobs"][job]["steps"]
        if isinstance(step.get("run"), str)
        and _CERTIFICATES_STAGED_RE.search(step["run"])
    )
    assert PUBLISH_SHOWCASE_DISPATCH not in run, (
        f"{workflow_path.as_posix()}::{job} dispatches publish-showcase.yml "
        "for a certificate-only change -- dead motion, carried item 4"
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
    itself would fail every time, silently defeating the fix
    from inside the one step meant to carry it out."""
    carried = _workflow_step_env_keys(workflow_path, job, run_contains)
    assert "GH_TOKEN" in carried, (
        f"{workflow_path.as_posix()}::{job} calls gh workflow run without "
        "GH_TOKEN in its own env -- the dispatch call would fail to "
        "authenticate"
    )


def test_publish_showcase_workflow_dispatch_is_enabled() -> None:
    """The `paths:` trigger alone is
    unreachable from any of the four jobs that write the paths it names,
    since all four commit with their own GITHUB_TOKEN (the recursion
    guard) -- `workflow_dispatch` is what each of those jobs' own
    dispatch step (above) actually calls."""
    text = (ROOT / PUBLISH_SHOWCASE_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "workflow_dispatch:" in trigger, (
        "publish-showcase.yml has no workflow_dispatch trigger -- nothing "
        "could ever call `gh workflow run publish-showcase.yml`"
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
    """A dispatched job that writes nothing
    still exits 0 (D-13 still holds -- this is not turned into a
    failure), but a `::warning::` annotation is what stops "it worked" and
    "it skipped" from looking identical on the run's own summary page,
    which matters most for `declarations/integrations.yml`'s own
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
# it never writes certificates.yml (delivery is not a register state)
# and never commits anything.
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
    """Two concurrent dispatches for the *same*
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
# The issue step hands its own freshly-issued
# identifiers to the delivery step, which restricts itself to that set by
# default, and a transient delivery failure must not mask that
# the certificates were already committed and pushed.
# ------------------------------------------------------------------ #


def _issue_certificates_workflow() -> WorkflowYaml:
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
    """A transient failure re-fetching attendance in
    this step must not mark the whole run red after the certificates were
    already committed and pushed by the step before it."""
    loaded = _issue_certificates_workflow()
    steps = loaded["jobs"]["issue"]["steps"]
    delivery_step = next(
        step for step in steps if "convener-deliver-certificates" in step.get("run", "")
    )
    assert delivery_step.get("continue-on-error") is True


def test_issue_certificates_workflow_has_a_resend_all_input_defaulting_false() -> None:
    loaded = _issue_certificates_workflow()
    inputs = workflow_triggers(loaded)["workflow_dispatch"]["inputs"]
    assert inputs["resend_all"]["type"] == "boolean"
    assert inputs["resend_all"]["default"] is False
    assert inputs["resend_all"]["required"] is False


# ------------------------------------------------------------------ #
# The widened AST walk
# (`_calls_confirmation_deliver`) surfaced a pre-existing gap that
# predates this whole task -- `_send_confirmation`
# (`cli/journey/registration.py::_send_confirmation`) resolves the room link through
# `platform_from_env`, which reads `CONVENER_MEETING_API_TOKEN`, and neither workflow
# that reaches it forwarded it. Benign today (the confirmation falls back to the manual
# `zoom_link` rather than failing), but the same class of defect this whole derived-
# environment idiom exists to catch, so it is asserted here now that the
# walk can see it at all.
# ------------------------------------------------------------------ #

REGISTRATION_WORKFLOW = Path(".github/workflows/registration.yml")
RESEND_CONFIRMATION_WORKFLOW = Path(".github/workflows/resend-confirmation.yml")


def test_registration_workflow_send_step_carries_every_env_var_the_command_reads() -> (
    None
):
    expected = _env_vars_read(_cli_source("send_confirmation"), "send_confirmation")
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
    expected = _env_vars_read(_cli_source("resend_confirmation"), "resend_confirmation")
    assert expected == {
        "EVENT_ID",
        "EMAIL_ENVELOPE",
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
# retention.yml and erase-registration.yml. Same derived-
# environment idiom as the certificate trio above -- the whole reason it
# exists (this section's own header comment) is a workflow that forwards
# three of nine environment variables its own command reads while its
# test suite stays green; a hand-typed list here would reproduce exactly
# that gap rather than catch it.
# ------------------------------------------------------------------ #

RETENTION_WORKFLOW = Path(".github/workflows/retention.yml")
ERASE_REGISTRATION_WORKFLOW = Path(".github/workflows/erase-registration.yml")


def test_retention_sweep_step_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(_cli_source("retention_sweep"), "retention_sweep")
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
        "convener-retention-sweep, which reads it directly -- the "
        "fail-outright rule would go unenforced in production"
    )


def test_record_destructions_step_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(_cli_source("record_destructions"), "record_destructions")
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
    expected = _env_vars_read(_cli_source("erase_registration"), "erase_registration")
    assert expected == {
        "EVENT_ID",
        "MATCHING_CODE",
        "EMAIL_ENVELOPE",
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
    """`convener-erase-registration` rewrites two files when the
    erased person has attendance rows, and
    `erase-registration.yml` staged only one -- the rewritten attendance
    export died with the runner while the job's own log claimed it was
    committed. `_files_written` derives the set from the command's own
    source rather than a hand-typed list, which is how the gap survived
    every review of the two halves separately; a future third file this
    command starts writing needs no matching edit here to stay caught."""
    written = _files_written(_cli_source("erase_registration"), "erase_registration")
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
    """A retention job that only runs when somebody remembers is
    the failure this exists to prevent -- scheduled, with
    workflow_dispatch for a manual run, the same pairing sweep.yml already
    uses for its own daily job."""
    text = (ROOT / RETENTION_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "schedule:" in trigger
    assert "cron:" in trigger
    assert "workflow_dispatch:" in trigger


def test_erase_registration_workflow_is_dispatchable_by_hand() -> None:
    """The same check `test_deliver_certificate_workflow_is_dispatchable_
    by_hand` already makes for the resend path: a command
    nothing invokes is not delivered work."""
    text = (ROOT / ERASE_REGISTRATION_WORKFLOW).read_text(encoding="utf-8")
    trigger = text.split("jobs:")[0]
    assert "workflow_dispatch:" in trigger


def test_retention_workflow_job_has_write_permission_and_a_timeout() -> None:
    loaded = safe_load((ROOT / RETENTION_WORKFLOW).read_text(encoding="utf-8"))
    job = loaded["jobs"]["retention"]
    # `actions: write` joined `contents:
    # write` -- the same pairing the three certificate workflows and
    # sweep.yml already carry, for the identical recursion-guard reason.
    assert job.get("permissions") == {"contents": "write", "actions": "write"}
    assert isinstance(job.get("timeout-minutes"), int)


def test_retention_workflow_dispatches_both_publish_targets_after_a_real_push() -> None:
    """`record_destructions` deletes a
    destroyed event's `instance/keys/events/<id>.pub` and this job pushes that
    deletion with `GITHUB_TOKEN`, the recursion guard `publish-showcase.
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
    assert PUBLISH_SHOWCASE_DISPATCH in pushed, (
        "retention.yml changes instance/keys/events and the destruction registry "
        "and pushes it, but does not dispatch publish-showcase.yml"
    )
    assert DEPLOY_DISPATCH in pushed, (
        "retention.yml changes instance/keys/events and the destruction registry "
        "and pushes it, but does not dispatch deploy.yml -- a destroyed "
        "event's public key would keep being served from the deployed "
        "app bundle"
    )

    unchanged = _guarded_block(script, "if git diff --staged --quiet; then")
    assert PUBLISH_SHOWCASE_DISPATCH not in unchanged, (
        "retention.yml dispatches publish-showcase.yml even when nothing "
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
    """Every other writing dispatch workflow has one; this
    one shares registration.yml's own group name deliberately, since both
    workflows write the same `registrations.enc`."""
    loaded = safe_load((ROOT / ERASE_REGISTRATION_WORKFLOW).read_text(encoding="utf-8"))
    concurrency = loaded.get("concurrency")
    assert isinstance(concurrency, dict)
    assert concurrency.get("group") == "registration-${{ inputs.event_id }}"
    assert concurrency.get("cancel-in-progress") is False


# ------------------------------------------------------------------ #
# invite-survey.yml. Same derived-environment idiom as the
# certificate trio above -- the same gap this whole idiom exists to catch
# (a workflow forwarding three of nine variables its own command
# read) applies just as much to a brand-new workflow as to an edited one.
# ------------------------------------------------------------------ #

INVITE_SURVEY_WORKFLOW = Path(".github/workflows/invite-survey.yml")


def _invite_survey_workflow() -> WorkflowYaml:
    loaded = safe_load((ROOT / INVITE_SURVEY_WORKFLOW).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), (
        f"{INVITE_SURVEY_WORKFLOW.name} does not parse as a mapping -- a "
        "workflow file that is a list or a scalar is not a workflow at all"
    )
    return loaded


def test_invite_survey_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(_cli_source("invite_survey"), "invite_survey")
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
        "runs convener-invite-survey, which reads it directly -- a workflow "
        "shipped with exactly this gap once"
    )


def test_record_survey_invitation_step_carries_every_env_var_the_command_reads() -> (
    None
):
    expected = _env_vars_read(
        _cli_source("record_survey_invitation"), "record_survey_invitation"
    )
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
    assert set(workflow_triggers(loaded)) == {"workflow_dispatch"}, (
        "invite-survey.yml must be reachable only by an operator's own "
        "decision -- never scheduled, never triggered by a push: an "
        "invitation is an outbound message to real people"
    )


def test_invite_survey_workflow_has_a_resend_all_input_defaulting_false() -> None:
    loaded = _invite_survey_workflow()
    inputs = workflow_triggers(loaded)["workflow_dispatch"]["inputs"]
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
        step
        for step in steps
        if "convener-record-survey-invitation" in step.get("run", "")
    )
    assert record_step.get("if") == "steps.invite.outputs.record == 'true'"


# ------------------------------------------------------------------ #
# match-attendance.yml is what makes
# `convener-match-attendance` reachable at all -- before this workflow existed,
# two others' own header comments told a volunteer to run it by hand, a
# command that reads EVENT_PRIVATE_KEY, which by design never touches a
# laptop. Same derived-environment idiom as the certificate trio and
# invite-survey.yml above.
# ------------------------------------------------------------------ #

MATCH_ATTENDANCE_WORKFLOW = Path(".github/workflows/match-attendance.yml")


def test_match_attendance_workflow_carries_every_env_var_the_command_reads() -> None:
    expected = _env_vars_read(_cli_source("match_attendance"), "match_attendance")
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
    assert set(workflow_triggers(loaded)) == {"workflow_dispatch"}, (
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
    place the unmatched/unreachable distinction ever reaches a human --
    must be a short-retention, access-controlled build artefact, never a
    public one, the same restriction `cli/journey/attendance.py::UNMATCHED_ATTENDANCE`'s
    own comment requires."""
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
# The "Delete the destroyed event keys" step, executed for real
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
#: the second shape of the same defect: a successful-looking delete must
#: not be trusted either, only what `secret list` confirms.
#: `GH_STUB_LIST_FAIL` ("1") makes every `secret list` call fail
#: (non-zero exit, nothing printed) -- the reproduction of a listing that
#: cannot answer the question being read as "the answer is no".
#: `GH_STUB_LIST_FAIL_ON_CALL` (an integer) fails only the Nth `secret
#: list` call across the whole run -- a mixed batch
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
        # `bash -e {0}` -- no `-o pipefail` (verified, not
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
    """The reproduction of the defect, in the direction
    `retention.yml`'s comment assumed: `gh secret delete` on a secret that
    is not there returns non-zero. The fix must converge on this anyway --
    `gh secret list` confirms the secret is absent, which is what the
    registry exists to record, regardless of the delete call's own exit
    code. A mutant that trusts the exit code instead fails this: it would
    leave `recorded_ids` empty and the step would exit 1."""
    result, outputs = _run_delete_step(
        tmp_path,
        present_secrets=[],  # already gone -- e.g. a retry after a failure
        destroyed_ids="mrg-042",
        destroyed_secrets="CONVENER_EVENT_KEY_MRG_042",
    )
    assert result.returncode == 0, result.stderr
    assert outputs["recorded_ids"] == "mrg-042"


@pytest.mark.skipif(_BASH_MISSING, reason="bash is not on PATH")
def test_delete_step_does_not_abandon_a_later_event_after_an_earlier_failure(
    tmp_path: Path,
) -> None:
    """The other half: a `break` on the first failure abandoned
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
    """The second shape: `gh secret delete` reporting success is not
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
    """The reproduction: the listing's exit
    status was discarded and only the grep result was consulted, so a
    failed listing (an expired PAT mid-run, a 403, gh missing from PATH)
    printed nothing, grep found no match, and the id was recorded as
    destroyed -- the exact inverse of what this job exists to guarantee,
    since the secret is still live. `GH_STUB_LIST_FAIL` makes `gh secret
    list` itself exit non-zero with nothing printed; the fix must record
    nothing for this event and fail the job, never read a failed question
    as a negative answer.

    **The `::error::` annotation is asserted by name, not merely "the id
    appears somewhere".** An earlier version of this test
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
    """The reproduction, and the assertion that actually
    catches the `bash -e` defect the sibling test above could not: a
    mixed batch where `mrg-042` deletes and confirms cleanly (the first
    `secret list` call) and `mrg-050`'s own listing then fails (the
    second call, `GH_STUB_LIST_FAIL_ON_CALL=2`). The partial-batch
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


# ------------------------------------------------------------------ #
# GitHub Actions' own workflow
# parser does not support YAML anchors (`&name`) or aliases (`*name`) -- a
# long-standing, documented limitation of that parser, not a version
# question. `visuals.yml` used to bind `push.paths` and `pull_request.
# paths` with exactly that (`&visual_paths`/`*visual_paths`); PyYAML
# expands them without complaint (every `safe_load`/`yaml.safe_load` call
# in this project's own test suite would have too), which is exactly why
# that version parsed clean in every local check and would still have
# failed to *trigger* the very first time this workflow ran for real -- no
# workflow in this repository has ever executed, which is confirmed rather
# than assumed. visuals.yml's own fix is two hand-written copies, bound by
# tools/tests/repository/test_visuals_workflow.py::
# test_the_two_path_filters_are_identical_lists. The sweep below closes
# the class, not just that one instance: an anchor anywhere in
# `.github/workflows/` has the identical consequence, and this file
# already has the sweep infrastructure (`_workflow_files()`) other
# repo-wide checks above use.
#
# Read as raw text, never through `safe_load`/`yaml.safe_load`: an anchor
# or alias is invisible once a YAML loader has resolved it, which is
# precisely the trap that let visuals.yml's own pair through undetected.
# ------------------------------------------------------------------ #


def _strip_yaml_line_comment(line: str) -> str:
    """`line` with everything from an unquoted `#` onward removed.

    Quote-aware -- a `#` inside `'...'` or `"..."` does not start a
    comment -- so a real value (a hex colour, a shell string) is never
    truncated by mistake. This is a plain line-scanner, not a YAML parse:
    the whole point of this sweep is to see the anchor/alias syntax
    itself, which a real parse would already have resolved away.
    """
    result: list[str] = []
    in_single = False
    in_double = False
    for char in line:
        if char == "'" and not in_double:
            in_single = not in_single
            result.append(char)
        elif char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
        elif char == "#" and not in_single and not in_double:
            break
        else:
            result.append(char)
    return "".join(result)


#: A `&name` anchor or `*name` alias in real YAML node position:
#: immediately after a mapping colon or a sequence dash, separated only by
#: inline spaces/tabs -- never a newline, so a dash-terminated line
#: followed by a blank line and then an unrelated line starting with `*`
#: can never bridge into a false match. Deliberately *not* "any `&`/`*`
#: anywhere": this project's own workflow comments already write
#: `*emphasis*` in prose, a heredoc'd `run:` script can contain a markdown
#: bullet list (see preview.yml's own README.txt heredoc), a bare `&&` is
#: ordinary shell, and `**`/`*.yml`/`* * * * *` are ordinary glob and cron
#: syntax -- none of those has an identifier character immediately after a
#: single `&` or `*` in real node position, so none of them matches this.
_YAML_NODE_RE = re.compile(r"(?::|-)[ \t]+([&*])([A-Za-z0-9_][A-Za-z0-9_-]*)")


def _yaml_anchors_and_aliases(text: str) -> list[tuple[int, str, str]]:
    """`(line number, '&' or '*', name)` for every anchor/alias `text`
    declares in real YAML node position. Scanned line by line -- both to
    keep `_YAML_NODE_RE` from spanning a line break, and so a match can be
    reported with the line number a human would look at."""
    hits: list[tuple[int, str, str]] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_yaml_line_comment(raw_line)
        for match in _YAML_NODE_RE.finditer(line):
            hits.append((lineno, match.group(1), match.group(2)))
    return hits


def test_yaml_node_detector_finds_a_real_anchor_and_alias() -> None:
    """Positive control: proves `_yaml_anchors_and_aliases` actually
    detects the shape it exists to catch -- visuals.yml's own former
    `&visual_paths`/`*visual_paths` pair, reduced to a minimal probe --
    before the sweep below is trusted to report an absence of it across
    every real workflow file."""
    probe = "paths: &visual_paths\n  - 'a'\nother:\n  paths: *visual_paths\n"
    hits = _yaml_anchors_and_aliases(probe)
    assert (1, "&", "visual_paths") in hits
    assert (4, "*", "visual_paths") in hits


#: Each probe is a real shape already present somewhere in this
#: repository's own workflow comments or scripts (see `_YAML_NODE_RE`'s
#: own docstring) -- the sweep below is only useful if it can tell a real
#: anchor/alias apart from every one of these.
_ORDINARY_YAML_PROBES: list[tuple[str, str]] = [
    (
        "run: |\n  echo *this* is emphasis, not YAML\n",
        "markdown emphasis inside a run: script",
    ),
    ("run: |\n  cmd1 && cmd2\n", "a shell && inside a run: script"),
    (
        "paths:\n  - 'assets/fonts/**'\n  - 'tools/visuals/**'\n",
        "double-star glob path filters",
    ),
    ("schedule:\n  - cron: '0 6 * * *'\n", "a cron schedule"),
    (
        "run: |\n  cat <<EOF\n  * bullet one\n  * bullet two\n  EOF\n",
        "a heredoc'd markdown bullet list",
    ),
]


@pytest.mark.parametrize(
    ("probe", "description"),
    _ORDINARY_YAML_PROBES,
    ids=[description for _, description in _ORDINARY_YAML_PROBES],
)
def test_yaml_node_detector_does_not_flag_ordinary_syntax(
    probe: str, description: str
) -> None:
    assert _yaml_anchors_and_aliases(probe) == [], (
        f"{description!r} was misread as a YAML anchor or alias: {probe!r}"
    )


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_no_workflow_uses_a_yaml_anchor_or_alias(workflow: Path) -> None:
    """GitHub Actions' own workflow parser does not support YAML anchors or
    aliases -- a documented, long-standing limitation of that parser, not
    a version question. `yaml.safe_load`/`safe_load` (used everywhere else
    in this module) expand them without complaint, which is exactly why
    visuals.yml's own former `&visual_paths`/`*visual_paths` passed every
    check that reads the parsed document and would still have failed to
    *trigger* on the first real push (no workflow in this repository has
    ever executed). See `.github/workflows/visuals.yml`'s own
    `push.paths`/`pull_request.paths` comments for what replaced it, and
    `tools/tests/repository/test_visuals_workflow.py::
    test_the_two_path_filters_are_identical_lists` for what keeps those
    two hand-written copies from drifting apart."""
    text = workflow.read_text(encoding="utf-8")
    hits = _yaml_anchors_and_aliases(text)
    assert hits == [], (
        f"{workflow.name} uses a YAML anchor or alias GitHub Actions' own "
        f"parser cannot read: {hits} -- write the value out in full at "
        "each place it is needed instead, bound by a test if more than "
        "one copy must stay in sync (see visuals.yml's own path filter "
        "for the pattern)"
    )


# ------------------------------------------------------------------ #
# secret-workflow-monitor.yml: closes the class, not the instance. A
# hand-maintained `workflows:` list drifts the moment somebody adds a
# workflow carrying a new secret and does not think to also edit this
# unrelated file. The tests below derive the *expected* list structurally
# -- from the same `secrets.`/`secrets[...]` reference every job's own
# `env:`/`with:` values already carry -- and assert it against what the
# monitor actually watches, in both directions, so an addition on either
# side without the other fails here, by name, rather than the monitor
# silently watching nothing for a secret it was never told about.
# ------------------------------------------------------------------ #

SECRET_WORKFLOW_MONITOR = WORKFLOWS_DIR / "secret-workflow-monitor.yml"

#: A `secrets.NAME` or dynamic `secrets[...]` reference, the same shape
#: a supply-chain review scanned for. Matched against
#: parsed YAML *values* (never the raw file text) below, specifically so a
#: mention inside a `#` comment -- `safe_load` discards comments entirely
#: -- can never be mistaken for a real reference; see
#: `test_a_commented_out_secret_reference_is_not_detected` for the
#: regression this exists to guard.
_SECRETS_REFERENCE_RE = re.compile(r"secrets\.[A-Za-z0-9_]+|secrets\[[^\]]+\]")

#: The one secret reference that does not count. No job in this repository
#: uses this literal form today (the default token is read as
#: `github.token`, never `secrets.GITHUB_TOKEN` -- confirmed by
#: `test_every_job_declares_a_timeout`'s own sweep finding nothing of the
#: kind), but the definition this test enforces is "declares a secret
#: *beyond* GITHUB_TOKEN", so the one name that is not "beyond" it is
#: excluded by name rather than by accident.
_GITHUB_TOKEN_REFERENCE = "secrets.GITHUB_TOKEN"


def _secret_references(value: Any) -> set[str]:
    """Every `secrets.*`/`secrets[...]` reference found in any string
    reachable from `value` -- a parsed YAML node, recursed through dicts
    and lists. Never reads a raw file: comments are already gone by the
    time `safe_load` produces `value`, which is the whole point."""
    found: set[str] = set()
    if isinstance(value, str):
        found.update(_SECRETS_REFERENCE_RE.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            found.update(_secret_references(v))
    elif isinstance(value, list):
        for v in value:
            found.update(_secret_references(v))
    return found


def test_secret_reference_scanner_finds_a_dotted_reference() -> None:
    """Positive control for `_secret_references`."""
    probe = safe_load(
        "jobs:\n  a:\n    steps:\n      - env:\n"
        "          K: ${{ secrets.CONVENER_SIGNING_KEY }}\n"
    )
    assert _secret_references(probe["jobs"]) == {"secrets.CONVENER_SIGNING_KEY"}


def test_secret_reference_scanner_finds_a_dynamic_reference() -> None:
    """The certificate/registration/survey workflows resolve an event's own
    key through `secrets[steps.resolve.outputs.secret_name]`, never a
    literal dotted name -- `_secret_references` must see this form too."""
    probe = safe_load(
        "jobs:\n  a:\n    steps:\n      - env:\n"
        "          K: ${{ secrets[steps.resolve.outputs.secret_name] }}\n"
    )
    assert _secret_references(probe["jobs"]) == {
        "secrets[steps.resolve.outputs.secret_name]"
    }


def test_secret_reference_scanner_finds_nothing_in_a_workflow_with_no_secret() -> None:
    probe = safe_load("jobs:\n  a:\n    steps:\n      - run: echo hi\n")
    assert _secret_references(probe["jobs"]) == set()


def test_a_commented_out_secret_reference_is_not_detected() -> None:
    """The same evasion class `test_a_commented_out_timeout_does_not_
    satisfy_the_job_level_requirement` guards against, applied here: a
    `# secrets.CONVENER_SIGNING_KEY` mentioned only in prose must never make a
    workflow look secret-bearing. Parsing YAML rather than scanning raw
    text is what makes this true by construction -- `safe_load` never sees
    a comment at all -- so this is a regression guard on the *approach*,
    not merely one more case."""
    probe = safe_load(
        "jobs:\n  a:\n    steps:\n"
        "      # reads secrets.CONVENER_SIGNING_KEY further down in a sibling"
        " workflow\n"
        "      - run: echo hi\n"
    )
    assert _secret_references(probe["jobs"]) == set()


def _declares_a_secret_beyond_github_token(workflow: Path) -> bool:
    """Whether any job in `workflow` references a secret other than
    `GITHUB_TOKEN` -- the honest definition of "sensitive" this monitor
    uses: not a hand-picked severity judgement, a structural fact about
    the file."""
    data = safe_load(workflow.read_text(encoding="utf-8"))
    jobs = data.get("jobs", {}) if isinstance(data, dict) else {}
    refs = _secret_references(jobs)
    return any(ref != _GITHUB_TOKEN_REFERENCE for ref in refs)


def _secret_bearing_workflow_names(directory: Path, *, exclude: Path) -> set[str]:
    """The `name:` of every workflow under `directory` that declares a
    secret beyond `GITHUB_TOKEN`, excluding `exclude` -- the monitor's own
    file must never be asked to watch itself; see
    `test_the_monitor_would_otherwise_qualify_to_watch_itself` for why the
    exclusion is deliberate rather than an oversight this function hides."""
    names: set[str] = set()
    for path in _workflow_files_in(directory):
        if path == exclude:
            continue
        if not _declares_a_secret_beyond_github_token(path):
            continue
        data = safe_load(path.read_text(encoding="utf-8"))
        name = data.get("name") if isinstance(data, dict) else None
        assert isinstance(name, str) and name, (
            f"{path.name} declares a secret beyond GITHUB_TOKEN but has no "
            "`name:` -- workflow_run.workflows matches by name, never by "
            "filename, so an unnamed workflow could never be watched"
        )
        names.add(name)
    return names


def test_the_secret_workflow_monitor_watches_every_secret_bearing_workflow() -> None:
    """The class-closing assertion. A workflow added later that declares
    any secret beyond `GITHUB_TOKEN` and is not also added to
    `secret-workflow-monitor.yml`'s own `workflows:` list fails this test
    by name -- see `test_a_workflow_with_a_new_secret_is_flagged_as_
    unwatched` for the same check exercised against a synthetic addition,
    proving it actually fails rather than only asserting it should."""
    expected = _secret_bearing_workflow_names(
        ROOT / WORKFLOWS_DIR, exclude=ROOT / SECRET_WORKFLOW_MONITOR
    )
    monitor = safe_load((ROOT / SECRET_WORKFLOW_MONITOR).read_text(encoding="utf-8"))
    watched = set(workflow_triggers(monitor)["workflow_run"]["workflows"])

    missing = expected - watched
    extra = watched - expected
    assert not missing, (
        "declares a secret beyond GITHUB_TOKEN but secret-workflow-monitor.yml "
        f"does not watch it: {sorted(missing)}"
    )
    assert not extra, (
        "secret-workflow-monitor.yml watches a workflow that declares no "
        f"secret beyond GITHUB_TOKEN: {sorted(extra)} -- either it lost its "
        "only sensitive secret and should be removed from the list, or the "
        "list carries a name that no longer matches any workflow's own "
        "`name:`"
    )


def test_a_workflow_with_a_new_secret_is_flagged_as_unwatched(tmp_path: Path) -> None:
    """Mutation proof for the test above, against a synthetic directory so
    the real `secret-workflow-monitor.yml` is never touched to prove it.
    A stale monitor (watching only `Existing`) and a freshly added
    workflow (`New`, carrying a secret) reproduce exactly the drift the
    class-closing test exists to catch: `New` must come back in `missing`.
    """
    (tmp_path / "existing.yml").write_text(
        "name: Existing\njobs:\n  a:\n    steps:\n"
        "      - env:\n          K: ${{ secrets.CONVENER_SIGNING_KEY }}\n",
        encoding="utf-8",
    )
    (tmp_path / "new.yml").write_text(
        "name: New\njobs:\n  a:\n    steps:\n"
        "      - env:\n          K: ${{ secrets.CONVENER_SMTP_PASSWORD }}\n",
        encoding="utf-8",
    )
    monitor_path = tmp_path / "secret-workflow-monitor.yml"
    monitor_path.write_text(
        "name: Monitor secret-bearing workflow runs\n"
        "on:\n  workflow_run:\n    workflows: [Existing]\n    types: [requested]\n",
        encoding="utf-8",
    )

    expected = _secret_bearing_workflow_names(tmp_path, exclude=monitor_path)
    monitor = safe_load(monitor_path.read_text(encoding="utf-8"))
    watched = set(workflow_triggers(monitor)["workflow_run"]["workflows"])

    assert expected - watched == {"New"}


def test_a_workflow_that_lost_its_secret_is_flagged_as_over_watched(
    tmp_path: Path,
) -> None:
    """The other direction of the same mutation: a workflow the monitor
    still lists after every secret was removed from it must be reported
    too, not silently tolerated as a harmless extra -- a stale entry is
    exactly how the list stops being trustworthy evidence of what is
    actually secret-bearing."""
    (tmp_path / "retired.yml").write_text(
        "name: Retired\njobs:\n  a:\n    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    monitor_path = tmp_path / "secret-workflow-monitor.yml"
    monitor_path.write_text(
        "name: Monitor secret-bearing workflow runs\n"
        "on:\n  workflow_run:\n    workflows: [Retired]\n    types: [requested]\n",
        encoding="utf-8",
    )

    expected = _secret_bearing_workflow_names(tmp_path, exclude=monitor_path)
    monitor = safe_load(monitor_path.read_text(encoding="utf-8"))
    watched = set(workflow_triggers(monitor)["workflow_run"]["workflows"])

    assert watched - expected == {"Retired"}


def test_the_monitor_would_otherwise_qualify_to_watch_itself() -> None:
    """`secret-workflow-monitor.yml` itself references `secrets.
    CONVENER_NOTIFY_THREAD` and `secrets.CONVENER_NOTIFY_MENTION` to post its own
    alert, so `_declares_a_secret_beyond_github_token` reads `True` for
    it -- it would qualify for its own watch list by the same rule every
    other workflow is held to. The `exclude=` parameter in
    `_secret_bearing_workflow_names` is what keeps it out, deliberately:
    `workflow_run` re-triggering on its own completed run would be a
    self-loop, not a protection. This test pins that the exclusion is
    doing real work, not guarding against a case that could never arise."""
    assert _declares_a_secret_beyond_github_token(ROOT / SECRET_WORKFLOW_MONITOR)
    monitor = safe_load((ROOT / SECRET_WORKFLOW_MONITOR).read_text(encoding="utf-8"))
    own_name = monitor["name"]
    watched = set(workflow_triggers(monitor)["workflow_run"]["workflows"])
    assert own_name not in watched


def test_the_secret_workflow_monitor_fires_on_request_not_completion() -> None:
    """`types: [requested]`, not `completed` -- see the workflow's own
    header comment for why: an alert that can only confirm a run already
    finished is not detection close enough behind the run to matter."""
    monitor = safe_load((ROOT / SECRET_WORKFLOW_MONITOR).read_text(encoding="utf-8"))
    assert workflow_triggers(monitor)["workflow_run"]["types"] == ["requested"]


def test_the_secret_workflow_monitor_declares_no_yaml_anchor() -> None:
    """Redundant with the repo-wide sweep above once this file exists and
    is discovered by `_workflow_files()` -- kept as an explicit,
    independent check on this exact file so a reader of this test module
    does not have to trust that the generic sweep really does cover a file
    added after it was written."""
    text = (ROOT / SECRET_WORKFLOW_MONITOR).read_text(encoding="utf-8")
    assert _yaml_anchors_and_aliases(text) == []


# ------------------------------------------------------------------ #
# The anchor/alias sweep above is one instance of a wider
# class -- nothing before it checked a workflow against GitHub's own
# workflow schema at all. Every check in this module, including that
# sweep, reads workflow YAML through PyYAML (`safe_load`) or as plain
# text; both accept a document GitHub's own parser refuses. This project
# found that out the hard way with a YAML anchor that would have kept
# visuals.yml from ever triggering, discovered by reading the file, not
# by a tool.
#
# `.github/workflows/quality.yml`'s own `workflow-schema` job now runs
# `actionlint` -- a real implementation of GitHub's workflow schema -- as
# a CI step, not a test: it downloads a pinned release, reaching the
# network the same way `npm audit`/`pip-audit`/`cspell` already do
# elsewhere in this same chain, which this suite must never do. This test
# pins that the step exists and is wired correctly, without ever running
# the tool itself -- the same "pin the step, let CI run the tool for real"
# split test_dependency_audit_workflow.py already uses for `npm audit`.
# ------------------------------------------------------------------ #

QUALITY_WORKFLOW = Path(".github/workflows/quality.yml")

#: The exact release this project has verified against a real, network-
#: reaching run: pinned so a silent bump to
#: "latest" -- which could change what a future run reports without any
#: diff in this repository explaining why -- fails this test instead.
_ACTIONLINT_VERSION = "1.7.12"


def test_quality_workflow_validates_workflows_against_github_actions_schema() -> None:
    data = safe_load((ROOT / QUALITY_WORKFLOW).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    job = data["jobs"].get("workflow-schema")
    assert isinstance(job, dict), (
        "quality.yml has no workflow-schema job -- GitHub's own workflow "
        "schema is no longer validated in this chain at all"
    )
    assert job.get("permissions") == {"contents": "read"}
    assert isinstance(job.get("timeout-minutes"), int)
    scripts = " ".join(
        step["run"] for step in job["steps"] if isinstance(step.get("run"), str)
    )
    assert "download-actionlint.bash" in scripts, (
        "workflow-schema no longer installs actionlint from its own release page"
    )
    assert _ACTIONLINT_VERSION in scripts, (
        "workflow-schema installs actionlint without pinning it to the "
        "version this project has actually verified"
    )
    assert "actionlint" in scripts.split("download-actionlint.bash", 1)[1], (
        "workflow-schema installs actionlint but never runs it"
    )


def test_quality_workflow_has_no_third_party_action_to_sha_pin_in_the_new_job() -> None:
    """`workflow-schema` reaches the network through a pinned release
    download in a `run:` step, the same shape `npm audit`/`pip-audit`/
    `cspell` already use elsewhere in this chain -- never through a
    third-party `uses:` action, which the SHA-pin sweep
    (`test_every_action_reference_is_pinned_to_a_full_commit_sha`) would
    otherwise have to hold to the same standard as every other action in
    this repository. This pins that choice: only the shared
    `actions/checkout` step should appear here."""
    data = safe_load((ROOT / QUALITY_WORKFLOW).read_text(encoding="utf-8"))
    job = data["jobs"]["workflow-schema"]
    uses = [step["uses"] for step in job["steps"] if "uses" in step]
    assert all(use.startswith("actions/checkout@") for use in uses)


# ------------------------------------------------------------------ #
# The secret monitor's job guard: it must ask
# the *fact*, and never a proxy for it.
#
# The distinction this section exists to hold is one word wide, and
# getting it wrong costs either a control or half the repository's
# compute budget -- both of which have now actually happened here.
#
# **A proxy is refused.** A guard on the triggering run's *event name*
# ("skip `push` too", "run only for `workflow_dispatch`") is a statement
# about the nineteen *watched* files -- that none of them has a `push:`
# trigger outside `branches: [main]`. The platform promises nothing of
# the sort. The day one of those files loses its branch filter, such a
# guard goes quietly false exactly where it had started to matter.
#
# **The fact is required.** `github.event.workflow_run.head_branch` is
# the branch the run was actually requested against, reported by the
# platform for the run in hand. It is the same value
# `dispatch_alert.alert_message` decides on -- that function returns
# `None` exactly when it equals `MAIN_BRANCH` -- so a guard on it can
# skip only runs the function would have passed over in silence anyway.
# There is no watched-file property in it to come apart.
#
# The earlier version of this section pinned "no clause beyond the two
# event comparisons", which reads as caution and was not: it generalised
# a correct argument about *event-name* proxies into a ban on the one
# term that is not a proxy. The monitor consequently started a full
# Python toolchain on every push to answer a question already in the
# payload -- measured at 465 of 874 minutes on the derived instance over
# 400 runs, 53% of everything, with 56 runs failing on their own
# five-minute ceiling before the account's included minutes ran out. The
# tests below hold the distinction itself, so neither failure can come
# back: the guard must read the branch, and must not narrow on the event.
# ------------------------------------------------------------------ #

#: A comparison of the *triggering run's* own event against a literal --
#: `github.event.workflow_run.event`, never `github.event_name`, which on
#: this workflow is always the constant `workflow_run`. Finding one of
#: these in the guard is the failure, not the requirement.
_TRIGGERING_EVENT_TEST_RE = re.compile(
    r"github\.event\.workflow_run\.event\s*(==|!=)\s*'([a-z_]+)'"
)

#: The comparison the guard must be made of: the triggering run's own
#: branch against a literal. The operator is captured because its
#: direction is a safety property -- see the test below.
_HEAD_BRANCH_TEST_RE = re.compile(
    r"github\.event\.workflow_run\.head_branch\s*(==|!=)\s*'([A-Za-z0-9._/-]+)'"
)


def _guard_event_tests(guard: str) -> tuple[set[str], set[str], str]:
    """`(operators, event names, whatever is left)` for a job-level `if:`.

    The leftover is what makes this useful: an added `||`, a second
    context, or any other term stays behind once the comparisons are
    removed, so a guard cannot pass merely by having a right-looking
    term among several.
    """
    found = _TRIGGERING_EVENT_TEST_RE.findall(guard)
    leftover = _TRIGGERING_EVENT_TEST_RE.sub("", guard).replace("&&", "")
    return (
        {operator for operator, _ in found},
        {event for _, event in found},
        " ".join(leftover.split()),
    )


def _guard_branch_tests(guard: str) -> tuple[set[str], set[str], str]:
    """`(operators, branch names, whatever is left)`, the same shape."""
    found = _HEAD_BRANCH_TEST_RE.findall(guard)
    leftover = _HEAD_BRANCH_TEST_RE.sub("", guard).replace("&&", "")
    return (
        {operator for operator, _ in found},
        {branch for _, branch in found},
        " ".join(leftover.split()),
    )


def test_the_guard_reader_tells_the_fact_from_the_proxy() -> None:
    """Positive control, on probes rather than on the real file: the two
    readers have to tell apart the guard that asks the branch, the
    guards that narrow on the event name, and a guard that does both --
    or they prove nothing about the real one."""
    fact = "github.event.workflow_run.head_branch != 'main'"
    assert _guard_branch_tests(fact) == ({"!="}, {"main"}, "")
    assert _guard_event_tests(fact)[1] == set(), "no event comparison here"

    proxy = (
        "github.event.workflow_run.event != 'schedule' && "
        "github.event.workflow_run.event != 'repository_dispatch'"
    )
    assert _guard_event_tests(proxy) == (
        {"!="},
        {"schedule", "repository_dispatch"},
        "",
    )
    assert _guard_branch_tests(proxy)[1] == set(), "no branch comparison here"

    widest = "github.event.workflow_run.event == 'workflow_dispatch'"
    assert _guard_event_tests(widest) == ({"=="}, {"workflow_dispatch"}, "")

    both = f"{proxy} && {fact}"
    assert _guard_event_tests(both)[1] == {"schedule", "repository_dispatch"}
    assert _guard_branch_tests(both)[1] == {"main"}

    inverted = "github.event.workflow_run.head_branch == 'main'"
    assert _guard_branch_tests(inverted)[0] == {"=="}, (
        "the reader has to report the operator, because an inverted "
        "comparison is the one mutation that reverses this guard's "
        "meaning while keeping every other property it is checked for"
    )


def test_the_monitor_guards_on_the_branch_the_alert_decides_on() -> None:
    """The guard is the alert's own condition, hoisted into an expression
    the platform evaluates for free.

    A skipped job starts no runner and is billed nothing, so on `main`
    this control now costs what it is worth -- and off `main`, which is
    the only case `alert_message` ever speaks in, it runs exactly as it
    did.
    """
    monitor = safe_load((ROOT / SECRET_WORKFLOW_MONITOR).read_text(encoding="utf-8"))
    guard = monitor["jobs"]["monitor"]["if"]
    assert isinstance(guard, str) and guard, (
        "secret-workflow-monitor.yml's own job carries no `if:` at all -- "
        "the guard was reverted, and the monitor is starting a runner on "
        "every run of all twenty watched workflows to answer a question "
        "that is already in the event payload"
    )

    operators, branches, leftover = _guard_branch_tests(guard)
    assert branches, (
        "the monitor's job guard does not test "
        "`github.event.workflow_run.head_branch` at all -- that value is "
        "the branch the triggering run was requested against, and it is "
        "the only term in this guard that is the fact rather than a "
        "proxy for it"
    )
    assert operators == {"!="}, (
        f"the guard compares the branch with {sorted(operators)} -- it "
        "must be `!=`, so that a run whose branch is *absent* (GitHub "
        "omits `head_branch` once a branch is deleted) compares unequal, "
        "runs the job, and is reported. An `==` test, however it is "
        "negated further out, makes the unknown case read as safe"
    )
    assert leftover == "", (
        f"the guard carries a term beyond the branch comparison: {leftover!r}"
    )
    assert "||" not in guard, (
        "the guard joins its terms with `||`, so a run only has to fail "
        "one of them to be watched -- every term here must hold"
    )

    _, events, _ = _guard_event_tests(guard)
    assert events == set(), (
        f"the guard narrows on the triggering event name {sorted(events)} "
        "-- that is a statement about the *watched* workflows keeping "
        "their `branches: [main]`, which the platform does not promise. "
        "The branch comparison above already skips every run this "
        "monitor has nothing to say about, including the scheduled and "
        "dispatched ones, so an event test can now only subtract "
        "detection"
    )


def test_the_branch_the_guard_names_is_the_branch_the_alert_is_silent_for() -> None:
    """The one literal, in two files.

    `alert_message` returns `None` exactly when `head_branch ==
    MAIN_BRANCH`; the guard skips the job exactly when the same value
    equals its own literal. If those two ever name different branches,
    the guard stops being the function's own condition and starts being
    a second opinion about it -- silently dropping the runs the function
    would have reported.
    """
    from convener_ops.governance import dispatch_alert

    monitor = safe_load((ROOT / SECRET_WORKFLOW_MONITOR).read_text(encoding="utf-8"))
    _, branches, _ = _guard_branch_tests(monitor["jobs"]["monitor"]["if"])

    assert branches == {dispatch_alert.MAIN_BRANCH}, (
        f"secret-workflow-monitor.yml's guard skips {sorted(branches)} but "
        f"dispatch_alert.MAIN_BRANCH is {dispatch_alert.MAIN_BRANCH!r} -- "
        "the guard must name the branch the alert itself is silent for"
    )


def test_the_alert_is_silent_for_exactly_the_branch_the_guard_skips() -> None:
    """The other direction, executed rather than read: the guard is only
    safe because `alert_message` has nothing to say for that branch and
    something to say for every other. This runs the function, so a change
    to *it* -- an added reason to speak on `main`, a widened silence --
    fails here rather than in production."""
    from convener_ops.governance import dispatch_alert

    common = {
        "workflow_name": "Mint event keys",
        "run_event": "push",
        "run_url": "https://example.invalid/run/1",
        "actor": "somebody",
    }

    assert (
        dispatch_alert.alert_message(head_branch=dispatch_alert.MAIN_BRANCH, **common)
        is None
    ), "the guard skips this branch on the strength of this silence"

    for branch in ("a-side-branch", "release/1.0", ""):
        assert dispatch_alert.alert_message(head_branch=branch, **common) is not None, (
            f"alert_message says nothing for {branch!r}, which the job "
            "guard lets through -- the guard is not the bottleneck here, "
            "so a silence added to the function is a detection lost with "
            "nothing in the workflow to notice"
        )

    assert dispatch_alert.alert_message(head_branch=None, **common) is not None, (
        "an absent branch must be reported -- it is the case the guard's "
        "own `!=` is written to let through"
    )


# ------------------------------------------------------------------ #
# A superseded run is cancelled, and a push to
# `main` is not.
#
# The trap this closes is one line wide. `group: ${{ github.ref }}` reads
# like the obvious way to say "one run per branch", and it is -- for a
# pull request. For a push to `main` it means every push shares one
# group, so `cancel-in-progress: true` lets the next push kill the checks
# on the commit before it, and that commit reaches production having been
# verified by nothing. Nothing turns red; the run just says "cancelled".
# D-25, and this repository has recorded that shape of failure thirteen
# times.
#
# So the expression is not asserted by its text but *evaluated*, against
# the contexts GitHub would supply, and what is asserted is the property:
# two runs of the same workflow on a push to `main` land in two different
# groups, two runs on the same pull-request branch land in one.
# ------------------------------------------------------------------ #

#: One `${{ ... }}` placeholder. Deliberately not a general expression
#: parser: the only forms this repository's concurrency groups use are a
#: context lookup and a `||` fallback chain of them, and `_render_group`
#: below refuses anything else rather than guessing at it.
_PLACEHOLDER_RE = re.compile(r"\$\{\{([^}]*)\}\}")

#: A `github.*` context lookup, the only operand `_render_group` accepts.
_CONTEXT_LOOKUP_RE = re.compile(r"github\.[a-z_]+(?:\.[a-z_]+)*")


def _render_group(expression: str, context: dict[str, str]) -> str:
    """`expression` with every `${{ ... }}` replaced the way GitHub would.

    Two shapes only -- a bare context lookup, and lookups joined by `||`,
    where an unset or empty context value is falsy and the chain yields
    the first truthy one (the empty string if there is none). Anything
    else raises, so a group expression that grew a function call or a
    comparison fails here loudly instead of being quietly mis-evaluated
    into a passing result.
    """

    def one(match: re.Match[str]) -> str:
        for operand in (part.strip() for part in match.group(1).split("||")):
            assert _CONTEXT_LOOKUP_RE.fullmatch(operand), (
                f"{operand!r} is not a plain `github.*` context lookup -- "
                "this evaluator understands lookups and `||` fallbacks "
                "between them, and refuses to guess at anything else"
            )
            value = context.get(operand, "")
            if value:
                return value
        return ""

    return _PLACEHOLDER_RE.sub(one, expression)


def _push_context(workflow_name: str, run_id: str) -> dict[str, str]:
    """A push to `main`. `github.head_ref` is empty for every event that
    is not a pull request -- GitHub's own documented behaviour, and the
    hinge the whole expression turns on."""
    return {
        "github.workflow": workflow_name,
        "github.head_ref": "",
        "github.ref": "refs/heads/main",
        "github.run_id": run_id,
    }


def _pull_request_context(
    workflow_name: str, branch: str, run_id: str
) -> dict[str, str]:
    return {
        "github.workflow": workflow_name,
        "github.head_ref": branch,
        "github.ref": "refs/pull/7/merge",
        "github.run_id": run_id,
    }


def test_the_group_evaluator_reproduces_the_trap_it_exists_to_catch() -> None:
    """Positive control. `${{ github.ref }}` -- the shorthand this change
    had to avoid -- must come back *identical* for two different pushes to
    `main`, which is exactly what would let the second cancel the first.
    An evaluator that could not show that could not be trusted to show
    the real expression avoiding it."""
    naive = "${{ github.ref }}"
    assert _render_group(naive, _push_context("Quality", "1")) == _render_group(
        naive, _push_context("Quality", "2")
    )

    chosen = "${{ github.workflow }}-${{ github.head_ref || github.run_id }}"
    assert _render_group(chosen, _push_context("Quality", "1")) != _render_group(
        chosen, _push_context("Quality", "2")
    )


def _pull_request_workflows() -> list[Path]:
    """Every workflow that runs on a pull request -- derived from the
    trigger each file declares, never a list of names. Counting by hand
    gives five; there are six, because `visuals.yml` runs on pull requests
    too and pays a real browser download to render a commit already
    superseded."""
    return [
        workflow
        for workflow in _workflow_files()
        if "pull_request"
        in workflow_event_names(safe_load(workflow.read_text(encoding="utf-8")) or {})
    ]


def test_the_pull_request_sweep_actually_matches_something() -> None:
    """The same guard `test_the_externally_dispatched_sweep_actually_
    matches_something` puts on its own sweep: a parametrisation that
    silently found nothing would report green while checking nothing."""
    found = [workflow.name for workflow in _pull_request_workflows()]
    assert len(found) >= 6, (
        f"only {found} were detected as pull-request-triggered -- either "
        "they really are gone, or `workflow_event_names` has stopped "
        "recognising the trigger"
    )


@pytest.mark.parametrize("workflow", _pull_request_workflows(), ids=lambda p: p.name)
def test_a_workflow_that_runs_on_pull_requests_cancels_what_a_newer_push_replaced(
    workflow: Path,
) -> None:
    """Two pushes to the same pull-request branch share one group, so the
    older run is cancelled: the commit it was checking is not the one
    that will be merged."""
    loaded = safe_load(workflow.read_text(encoding="utf-8"))
    concurrency = loaded.get("concurrency")
    assert isinstance(concurrency, dict), (
        f"{workflow.name} runs on pull requests and declares no "
        "concurrency group -- every push to a branch under review starts a "
        "full chain of checks on a commit the next push replaces"
    )
    assert concurrency.get("cancel-in-progress") is True, (
        f"{workflow.name} declares a group but does not cancel, so a "
        "superseded run is queued rather than dropped -- the minutes are "
        "spent either way"
    )

    group = concurrency["group"]
    name = str(loaded["name"])
    first = _render_group(group, _pull_request_context(name, "feature-x", "2001"))
    second = _render_group(group, _pull_request_context(name, "feature-x", "2002"))
    assert first == second, (
        f"{workflow.name}'s group is not stable across two runs of the "
        f"same pull-request branch ({first!r} then {second!r}), so a newer "
        "push cancels nothing"
    )

    other_branch = _render_group(
        group, _pull_request_context(name, "feature-y", "2003")
    )
    assert other_branch != first, (
        f"{workflow.name} puts two different pull-request branches in one "
        "group -- opening a second pull request would cancel the checks on "
        "the first"
    )


@pytest.mark.parametrize("workflow", _pull_request_workflows(), ids=lambda p: p.name)
def test_a_push_outside_a_pull_request_can_never_be_cancelled(
    workflow: Path,
) -> None:
    """The half that is not about minutes at all.

    Every commit that reaches `main` is verified for itself, so no push to
    `main` may ever be cancelled by a later one -- and the same holds for
    a scheduled or hand-dispatched run, which nothing supersedes either.
    Evaluated, not read: the group these workflows use falls back to
    `github.run_id` whenever `github.head_ref` is empty, and
    `github.run_id` is unique per run, so no two such runs can share a
    group and `cancel-in-progress` has nothing to act on.
    """
    loaded = safe_load(workflow.read_text(encoding="utf-8"))
    group = loaded["concurrency"]["group"]
    name = str(loaded["name"])

    first = _render_group(group, _push_context(name, "1001"))
    second = _render_group(group, _push_context(name, "1002"))
    assert first != second, (
        f"{workflow.name} puts two pushes to main in the same concurrency "
        f"group ({first!r}) while cancelling in progress -- a second push "
        "would cancel the checks on the commit before it, and that commit "
        "would reach production verified by nothing, with no red anywhere "
        "(D-25)"
    )

    pull_request = _render_group(
        group, _pull_request_context(name, "feature-x", "1003")
    )
    assert pull_request != first, (
        f"{workflow.name} puts a push to main and a pull-request run in "
        "the same group -- opening a pull request would cancel main's own "
        "checks"
    )


def test_two_workflows_never_share_a_concurrency_group() -> None:
    """Concurrency groups are repository-wide, not per workflow: without
    something workflow-specific in the key, the six blocks above would
    cancel *each other* on the same branch, and five of the six checks on
    a pull request would simply stop happening. `github.workflow` is what
    keeps them apart -- the same reason deploy.yml's own group already
    carries it."""
    rendered: dict[str, str] = {}
    for workflow in _pull_request_workflows():
        loaded = safe_load(workflow.read_text(encoding="utf-8"))
        rendered[workflow.name] = _render_group(
            loaded["concurrency"]["group"],
            _pull_request_context(str(loaded["name"]), "feature-x", "2001"),
        )
    assert len(set(rendered.values())) == len(rendered), (
        f"two pull-request workflows render the same group: {rendered}"
    )


# ------------------------------------------------------------------ #
# The two narrowed triggers that nothing held.
#
# Four trigger changes were made at once. The monitor's event guard
# and branch-scoped cancellation are pinned above. The other two were
# pinned by nothing at all, and that gap was recorded rather than
# fixed for a while. This section closes it. Neither
# block below touches a workflow file: both workflows are correct, they
# were merely unguarded.
#
# The branch filter (`validate-data.yml`'s `push: branches: [main]`) is the
# smaller one. The ignore list is the one that can fail silently, and the reason
# is worth stating precisely, because it is *not* the reason
# `paths-ignore:` was chosen over `paths:`.
#
# That choice is about the filter's *direction*, and it is right: a path
# left out of a `paths-ignore:` list merely runs the workflow when it did
# not strictly have to, while a path left out of a `paths:` list
# publishes a stale bundle in silence (D-25). But the direction protects
# only the consequence of *forgetting* an entry. It says nothing about
# the entries that are there. Each one is an assertion -- "nothing under
# this path can reach the deployed bundle" -- and the day something under
# `config/` or `site/` becomes an input to that bundle, `deploy.yml`
# stops firing for changes to it, with nothing red anywhere. That is the
# D-25 failure the direction was chosen to avoid, reintroduced through
# the list's contents rather than through its direction.
#
# So what is pinned below is the *relationship*, not the list. "The list
# still holds these ten strings" would detect an edit and nothing else --
# and it would pass, green, on the exact day the bundle started reading
# `config/`. What is asserted instead is that every path the list ignores
# really is unreachable from the deploy build, with the build's inputs
# *derived* from what produces it: `app/package.json`'s own copy scripts,
# `app/src/content/registry.ts`'s publication allowlist, and the `tools/`
# commands `deploy.yml` itself runs.
# ------------------------------------------------------------------ #

#: The repository's default branch. GitHub starts `schedule:` and
#: `repository_dispatch:` only from it, a pull request is merged into it,
#: and it is the one branch a `push:` trigger in this repository is meant
#: to fire on -- see `secret-workflow-monitor.yml`'s own head-branch
#: question, which turns on the same fact.
DEFAULT_BRANCH = "main"


# ------------------------------------------------------------------ #
# The branch filter: a push to a branch under review must not run the same
# checks twice.
#
# Pinned as that property, not as the line that implements it. Without a
# branch filter, a push to a branch with an open pull request matches
# `push:` *and* `pull_request:` -- the same job, on the same commit, over
# the same tree, running the same command, where the second run can only
# ever agree with the first. Five workflows here declare both events; the
# sweep below finds them from their own triggers rather than naming them,
# so a sixth is covered the day it is written.
# ------------------------------------------------------------------ #


def _push_trigger_branches(push: Any) -> frozenset[str] | None:
    """Every branch a workflow whose `on: push:` block is `push` starts
    for -- or `None` when it starts for all of them.

    This was lifted out of `_push_trigger_fires_on` below, which now
    asks it about a single branch. Two questions, one reader: a second
    parser of GitHub's branch-filter syntax living beside this one is
    exactly the drift these tests exist to remove.

    Two shapes only -- no options at all (`push:` alone, which matches
    every branch) and a `branches:` list of plain branch names -- and
    anything else raises rather than being guessed at, the same
    discipline `_render_group` above applies to a concurrency expression.
    Three refusals in particular:

    * a wildcard pattern, because GitHub's own glob syntax is not
      `fnmatch`'s (`*` does not cross a `/` there, `**` does), no branch
      filter in this repository uses one today, and a filter that quietly
      meant something slightly different from what this reader thought is
      exactly the silence these tests exist to remove;
    * `branches-ignore:`, because this reader evaluates `branches:` and
      would report the wrong answer for the other form;
    * `tags:` and `tags-ignore:`, because there the plausible answer is
      the *permissive* one. A `push:` block carrying only tag filters
      starts for no branch at all, so a reader that guessed would answer
      "this fires on nothing" -- the answer that waves a queue write
      through -- about the one shape it was never written for. Refusing
      fails loudly instead, which is the direction to fail in.

    `paths:` is deliberately not consulted. The properties asked of this
    reader are the stronger one -- this trigger must not fire for a
    non-default branch at all -- so whether two path filters happen to
    agree on a given commit never enters into it.
    """
    if push is None:
        return None
    assert isinstance(push, dict), (
        f"this workflow's `push:` trigger is {push!r}, not a mapping of "
        "options -- this reader understands `push:` with no options and "
        "`push:` with a `branches:` list, and refuses to guess at "
        "anything else"
    )
    assert "branches-ignore" not in push, (
        "this workflow filters its `push:` trigger with "
        "`branches-ignore:` -- this reader only evaluates `branches:`, "
        "and would silently report the wrong answer for the other form"
    )
    assert not {"tags", "tags-ignore"} & set(push), (
        "this workflow filters its `push:` trigger by tag -- this reader "
        "evaluates branch filters only, and the answer it would invent "
        "for a tag filter is the permissive one, so it refuses instead"
    )
    patterns = push.get("branches")
    if patterns is None:
        return None
    assert isinstance(patterns, list) and patterns, (
        f"`push: branches:` is {patterns!r}, not a non-empty list of branch names"
    )
    names = [str(pattern) for pattern in patterns]
    for name in names:
        assert not any(character in name for character in "*?[!+"), (
            f"the branch filter {name!r} carries a glob pattern -- "
            "GitHub's filter syntax is not `fnmatch`'s, so this reader "
            "refuses to evaluate it rather than answer plausibly and "
            "wrongly"
        )
    return frozenset(names)


def _push_trigger_fires_on(push: Any, branch: str) -> bool:
    """Whether GitHub would start a workflow whose `on: push:` block is
    `push` for a push to `branch`.

    One question put to `_push_trigger_branches` above, which does all of
    the reading and all of the refusing.
    """
    branches = _push_trigger_branches(push)
    return branches is None or branch in branches


def test_the_branch_filter_reader_sees_an_unfiltered_push_for_what_it_is() -> None:
    """Positive control, on probes rather than on the real files: the
    reader has to tell an unfiltered `push:` apart from a filtered one,
    or it proves nothing about either.

    The first two shapes are the before and after of the narrowing itself --
    `push:` carrying only a `paths:` list fires on every branch, which is
    the double run; the same block with `branches: [main]` added does
    not.
    """
    unfiltered = {"paths": ["instance/data/**.yml"]}
    assert _push_trigger_fires_on(unfiltered, "feature-x") is True
    assert _push_trigger_fires_on(unfiltered, DEFAULT_BRANCH) is True

    filtered = {"branches": [DEFAULT_BRANCH], "paths": ["instance/data/**.yml"]}
    assert _push_trigger_fires_on(filtered, "feature-x") is False
    assert _push_trigger_fires_on(filtered, DEFAULT_BRANCH) is True

    assert _push_trigger_fires_on(None, "feature-x") is True


def _workflows_triggered_by_both_push_and_pull_request() -> list[Path]:
    """Every workflow that declares both events -- derived from each
    file's own trigger block, never a list of names, the same shape
    `_pull_request_workflows` above uses. A workflow that declares only
    one of the two cannot run twice on one commit and is not this
    property's business."""
    found: list[Path] = []
    for workflow in _workflow_files():
        events = workflow_event_names(
            safe_load(workflow.read_text(encoding="utf-8")) or {}
        )
        if {"push", "pull_request"} <= events:
            found.append(workflow)
    return found


def test_the_double_run_sweep_actually_matches_something() -> None:
    """The same guard every other sweep in this module carries: a
    parametrisation that silently found nothing would report green while
    checking nothing at all."""
    found = [
        workflow.name
        for workflow in _workflows_triggered_by_both_push_and_pull_request()
    ]
    assert "validate-data.yml" in found, (
        f"validate-data.yml is not among the workflows detected as "
        f"declaring both `push` and `pull_request` ({found}) -- either "
        "its trigger changed, or `workflow_event_names` has stopped "
        "recognising one of the two events, and the narrowing is then held "
        "by nothing again"
    )
    assert len(found) >= 5, (
        f"only {found} were detected as declaring both events -- five did "
        "when this was written, so either they really are gone or the "
        "sweep has stopped seeing them"
    )


@pytest.mark.parametrize(
    "workflow",
    _workflows_triggered_by_both_push_and_pull_request(),
    ids=lambda p: p.name,
)
def test_a_push_to_a_branch_under_review_does_not_run_the_same_checks_twice(
    workflow: Path,
) -> None:
    """The branch narrowing, pinned as its property.

    A branch with an open pull request receives pushes. Each one matches
    `pull_request:` already; if it also matches `push:`, the workflow
    runs twice on the same commit, over the same tree, with the same
    command, and the second run can only ever agree with the first. So
    the `push:` half must not fire for a branch that is not the default
    one.
    """
    triggers = workflow_triggers(safe_load(workflow.read_text(encoding="utf-8")))
    assert not _push_trigger_fires_on(triggers["push"], "feature-x"), (
        f"{workflow.name}'s `push:` trigger fires on a branch that is not "
        f"{DEFAULT_BRANCH!r}, and the workflow also runs on "
        "`pull_request:` -- so every push to a branch under review starts "
        "this whole workflow twice on one commit, and the second run can "
        "only agree with the first"
    )


@pytest.mark.parametrize(
    "workflow",
    _workflows_triggered_by_both_push_and_pull_request(),
    ids=lambda p: p.name,
)
def test_narrowing_the_push_trigger_left_the_default_branch_covered(
    workflow: Path,
) -> None:
    """The other half, and the reason the test above is not simply
    "declare no `push:` at all".

    The `push:` half is what checks a commit that reaches production
    without ever having been in a pull request -- a workflow's own
    dispatch, a direct push, a merge queue. A branch filter narrowed one
    step further (to a branch that does not exist, or to none) would
    satisfy the property above perfectly while deleting that coverage in
    silence.
    """
    triggers = workflow_triggers(safe_load(workflow.read_text(encoding="utf-8")))
    assert _push_trigger_fires_on(triggers["push"], DEFAULT_BRANCH), (
        f"{workflow.name} no longer runs on a push to {DEFAULT_BRANCH!r} "
        "-- this trigger was narrowed to the default branch, not "
        "away from it, and a commit reaching production is checked by "
        "this `push:` half or by nothing"
    )


# ------------------------------------------------------------------ #
# The ignore list: every path `deploy.yml` ignores really is unreachable
# from the bundle it deploys.
#
# The build's inputs are derived, never listed. Three readers, one per
# mechanism by which a repository path becomes an input to this build:
#
#   1. `_repository_paths_reached_from` -- a file under `app/` that names
#      a path outside `app/`. Every copy script `package.json`'s own
#      `prebuild` runs works this way (`resolve(ROOT, keysDir(),
#      'events')`), and so would an app source file importing across the
#      boundary. The instance's own paths reach those scripts through
#      `app/scripts/instance-paths.mjs`, which reads them from
#      `declarations/boundary.yml`; `_JS_INSTANCE_PATHS` below reads the same
#      declaration through `convener_ops.declaration.paths` and resolves each name to
#      the path it stands for.
#   2. `_published_handbook_paths` -- the one input directory whose
#      contents are filtered rather than copied wholesale. `docs/` is
#      reached by `copy-handbook.mjs`, but only the pages
#      `app/src/content/registry.ts` names actually ship, so the set of
#      inputs under that directory is the registry's answer, not the
#      directory listing.
#   3. `_repository_paths_in_source` -- the `tools/` commands `deploy.yml`
#      runs, read from the entry point each `uv run --frozen convener-...` names in
#      `tools/pyproject.toml` and parsed for the `repo_root() / ...`
#      paths each one builds.
#
# WHAT THIS DOES NOT COVER, stated rather than glossed:
#
#   * A path reached through a *variable* rather than a literal --
#     `resolve(ROOT, someName)` on the JavaScript side, `root / name` on
#     the Python side. One level of constant folding is done (a `const`
#     bound to a `resolve(__dirname, ...)`, a local bound to
#     `repo_root() / ...`); nothing beyond that is followed.
#   * On the Python side, only the *entry function itself* is read, not
#     the helpers it calls. Every path `deploy.yml`'s three commands
#     build is constructed in the entry function today; one moved into a
#     helper would leave this reader's sight. `tools/` and `instance/data/` stay
#     covered regardless (they are inputs by other routes below), but a
#     *fourth* directory a command started reading from a helper would
#     not be seen.
#   * An input reached by an npm dependency's own configuration rather
#     than by this repository's source -- a bundler alias, or a Tailwind
#     `@source` glob pointing outside `app/`. The config files beside
#     `vite.config.ts` *are* scanned, so a literal there is seen; a path
#     assembled inside a dependency is not. Tailwind's own configuration
#     is `src/index.css` since v4, which sits inside `src/` and is
#     scanned with the rest of it.
#   * `app/tests/**` and `app/public/**` are not scanned: neither is
#     compiled into the bundle (`public/` is written by the copy scripts,
#     not read by them). A build that started reading a repository path
#     from a test helper would not be seen -- and would not reach the
#     bundle either.
#   * Runtime reads. `paths-ignore:` is about what changing a file does
#     to the *build*; a page fetching a URL at runtime is a different
#     question, answered elsewhere.
#
# What that adds up to: this is a strong detector of the mechanisms this
# build actually uses to reach outside `app/`, not a proof of
# unreachability. It fails in the safe direction -- a directory whose
# filter it cannot derive is treated as read whole, which raises a false
# alarm for a human rather than passing quietly.
# ------------------------------------------------------------------ #

#: A `/* ... */` block comment. Stripped before anything is extracted:
#: this repository's source carries long explanatory headers, and
#: `app/vite.config.ts`'s own comments name `site/src/style.css` several
#: times over without the build ever reading it.
_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)

#: A `//` line comment. The lookbehind keeps `https://` and a `//` inside
#: a quoted path from being read as the start of one.
_JS_LINE_COMMENT_RE = re.compile(r"(?m)(?<![:'\"\w])//[^\n]*")

#: One single- or double-quoted string literal, on one line.
_JS_STRING_RE = re.compile(r"'([^'\n]*)'|\"([^\"\n]*)\"")

#: The argument list of a `resolve(...)`/`join(...)` call: path segments,
#: each either a literal or an argument-less call. That second shape is
#: how a copy script names an instance path --
#: `resolve(ROOT, keysDir(), 'events')`, `app/scripts/instance-paths.mjs`
#: -- and `_JS_INSTANCE_PATHS` below is what it resolves to.
_JS_PATH_ARGUMENTS = r"(?:[^()]|\b[A-Za-z_$][\w$]*\(\))*"

#: A `resolve(...)`/`join(...)` call -- the shape every copy script under
#: `app/scripts/` uses to reach out of `app/`, one path segment per
#: argument.
_JS_PATH_CALL_RE = re.compile(rf"\b(?:resolve|join)\(({_JS_PATH_ARGUMENTS})\)")

#: `const NAME = resolve(...)`, so a path assembled in two steps (a repo
#: root bound once, then joined) is followed one level.
_JS_PATH_BINDING_RE = re.compile(
    rf"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*(?:resolve|join)\(({_JS_PATH_ARGUMENTS})\)"
)

#: The names `app/scripts/instance-paths.mjs` gives the paths
#: `declarations/boundary.yml` hands to the instance, against the same paths as
#: `convener_ops.declaration.paths` reads them. Both sides answer from that one
#: declaration, so a copy script that reaches `instance/keys/` through `keysDir()`
#: is read here as reaching `instance/keys/`.
_JS_INSTANCE_PATHS: Final = {
    "dataDir": DATA_DIR,
    "keysDir": KEYS_DIR,
    "publicDataDir": PUBLIC_DATA_DIR,
    "registerPath": REGISTER_PATH,
}

#: An argument-less call, which is the form each of those names takes.
_JS_NAMED_PATH_RE = re.compile(r"([A-Za-z_$][\w$]*)\(\)")

#: `uv run --frozen convener-something` inside one of `deploy.yml`'s own `run:` blocks.
_UV_RUN_RE = re.compile(r"\buv run --frozen (convener-[a-z0-9-]+)")

#: The files under `app/` that the deploy build compiles or executes.
#: `tests/` and `public/` are deliberately absent -- see this section's
#: own header for why, and for what that costs.
_APP_BUILD_TREES = ("scripts", "src")
_APP_BUILD_FILES = (
    "package.json",
    "index.html",
    "vite.config.ts",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
)


def _strip_js_comments(text: str) -> str:
    return _JS_LINE_COMMENT_RE.sub("", _JS_BLOCK_COMMENT_RE.sub("", text))


def _js_string_literal(token: str) -> str | None:
    stripped = token.strip()
    named = _JS_NAMED_PATH_RE.fullmatch(stripped)
    if named is not None:
        declared = _JS_INSTANCE_PATHS.get(named.group(1))
        return None if declared is None else declared.as_posix()
    match = _JS_STRING_RE.fullmatch(stripped)
    if match is None:
        return None
    single, double = match.group(1), match.group(2)
    return single if single is not None else double


def _joined_path(
    here: Path, arguments: list[str], bases: dict[str, Path]
) -> Path | None:
    """The path a `resolve(...)`/`join(...)` argument list denotes, or
    `None` when its first argument is not a base this reader knows.

    Segments are consumed until the first argument that is not a string
    literal, so `resolve(__dirname, '..', '..', name)` yields the
    repository root rather than a guess at what `name` holds -- the safe
    direction: a wider input, never a narrower one.
    """
    if not arguments:
        return None
    head = arguments[0].strip()
    if head == "__dirname":
        base = here
    elif head in bases:
        base = bases[head]
    else:
        return None
    for token in arguments[1:]:
        segment = _js_string_literal(token)
        if segment is None:
            break
        base = base / segment
    return base.resolve()


def _repository_paths_reached_from(
    source: str, here: Path, *, root: Path, inside: Path
) -> set[str]:
    """Every path outside `inside` that `source` -- a file sitting in
    `here` -- names, as paths relative to `root`.

    A plain `root`/`inside`/`here` argument rather than the real
    repository baked in, so the probe test below can exercise this exact
    reader against a temporary tree instead of against `app/` -- the same
    reason `_workflow_files_in` above takes a directory.
    """
    text = _strip_js_comments(source)
    bases: dict[str, Path] = {}
    for match in _JS_PATH_BINDING_RE.finditer(text):
        bound = _joined_path(here, match.group(2).split(","), bases)
        if bound is not None:
            bases[match.group(1)] = bound

    absolute: set[Path] = set()
    for match in _JS_PATH_CALL_RE.finditer(text):
        joined = _joined_path(here, match.group(1).split(","), bases)
        if joined is not None:
            absolute.add(joined)
    # The catch-all, for every shape that is not a segment list: any
    # literal that climbs at all, resolved against the file that holds
    # it. This is what would see `import '../../services/relay.mjs'`, or
    # a stylesheet's own `url('../../fonts/x.woff2')`.
    for match in _JS_STRING_RE.finditer(text):
        single, double = match.group(1), match.group(2)
        literal = single if single is not None else double
        if literal and "../" in literal:
            absolute.add((here / literal).resolve())

    reached: set[str] = set()
    for candidate in absolute:
        if candidate == inside or inside in candidate.parents:
            continue
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if relative == Path("."):
            continue
        reached.add(relative.as_posix())
    return reached


def test_the_input_reader_sees_a_new_repository_input_for_what_it_is(
    tmp_path: Path,
) -> None:
    """Positive control, on a probe tree rather than on the real `app/`:
    the reader has to *see* a path under `config/`, `site/` or
    `services/` becoming an input, or its silence about the real build
    means nothing.

    Each probe is one of the three shapes a copy script could plausibly
    take, plus the decoy that made this reader strip comments in the
    first place: `app/vite.config.ts` names `site/src/style.css` in its
    own prose more than once, and a reader that counted that would fail
    on a correct repository -- the fastest way for a test like this to be
    deleted rather than believed.
    """
    here = tmp_path / "app" / "scripts"
    here.mkdir(parents=True)
    inside = tmp_path / "app"

    def reached(source: str, where: Path = here) -> set[str]:
        return _repository_paths_reached_from(
            source, where, root=tmp_path, inside=inside
        )

    segments = "const SRC = resolve(__dirname, '..', '..', 'declarations', 'x.yml');"
    assert reached(segments) == {"declarations/x.yml"}

    two_step = (
        "const ROOT = resolve(__dirname, '..', '..');\n"
        "const SRC = resolve(ROOT, 'site', 'tokens.css');\n"
    )
    assert reached(two_step) == {"site/tokens.css"}

    imported = "import { relay } from '../../services/signup-relay/api.mjs';"
    assert reached(imported) == {"services/signup-relay/api.mjs"}

    named = (
        "const ROOT = resolve(__dirname, '..', '..');\n"
        "const SRC = resolve(ROOT, keysDir(), 'events');\n"
    )
    assert reached(named) == {f"{KEYS_DIR.as_posix()}/events"}, (
        "a copy script reaching an instance path through the name "
        "`app/scripts/instance-paths.mjs` gives it was not read as an "
        "input -- the four copy scripts all reach out of `app/` that way"
    )

    decoy = (
        "/* styled by `site/src/style.css`, which the event page already\n"
        " * loads -- see ../../site for the whole story. */\n"
        "import { x } from './local.mjs';\n"
    )
    assert reached(decoy) == set(), (
        "a path named only in a comment was read as a build input -- this "
        "reader would then fail on a correct repository, which is how a "
        "test like this one gets deleted instead of believed"
    )

    stays_inside = "import { encrypt } from '../../signup/encrypt';"
    assert reached(stays_inside, inside / "src" / "islands" / "signup") == set(), (
        "a relative import that never leaves `app/` was counted as a "
        "repository input -- `app/src/islands/` is full of them"
    )


def _app_build_sources() -> list[Path]:
    """Every file under `app/` the deploy build compiles or executes."""
    files = [ROOT / "app" / name for name in _APP_BUILD_FILES]
    for tree in _APP_BUILD_TREES:
        files.extend(
            sorted(path for path in (ROOT / "app" / tree).rglob("*") if path.is_file())
        )
    present = [path for path in files if path.is_file()]
    assert len(present) > 50, (
        f"only {len(present)} files were found under app/ to scan for "
        "build inputs -- the tree moved, and this whole check would then "
        "pass by having nothing to look at"
    )
    return present


def _slice_between(source: str, start: str, end: str) -> str:
    """The text strictly between `start`'s first occurrence and the next
    `end` after it -- the same isolation
    `app/scripts/handbook-registry.mjs` performs on this exact file, so a
    decoy path in a *different* export, or in the prose around it, is
    never even looked at."""
    opened = source.find(start)
    if opened == -1:
        return ""
    closed = source.find(end, opened + len(start))
    if closed == -1:
        return ""
    return source[opened + len(start) : closed]


def _published_handbook_paths() -> set[str]:
    """Every file under `docs/` that actually reaches the bundle, as
    repository-relative paths.

    `copy-handbook.mjs` reaches `docs/` as a whole, but publishes only
    what `app/src/content/registry.ts` names -- `CONTENT_REGISTRY`'s own
    `file:` values and the `PUBLIC_ASSETS` array beside them. That filter
    is what makes `docs/` an input in full while only some of its pages
    reach the bundle, and it is the only thing that decides which.

    Read from the registry's own source text with the two markers and the
    two expressions `handbook-registry.mjs::publishedPaths` uses, because
    that is what actually decides what ships.
    `app/tests/scripts/copy-handbook.test.ts` pins the JavaScript half against the
    real imported `CONTENT_REGISTRY` on every run; this is the same
    allowlist, read the same way, on the Python side.
    """
    source = (ROOT / "app" / "src" / "content" / "registry.ts").read_text(
        encoding="utf-8"
    )
    registry = _strip_js_comments(
        _slice_between(source, "export const CONTENT_REGISTRY", "\n};")
    )
    assets = _strip_js_comments(
        _slice_between(source, "export const PUBLIC_ASSETS", "\n];")
    )
    published = {
        match.group(1) for match in re.finditer(r"\bfile:\s*'([^']+)'", registry)
    }
    published |= {match.group(1) for match in re.finditer(r"'([^']+)'", assets)}
    assert len(published) > 50, (
        f"only {len(published)} handbook paths were read out of "
        "registry.ts -- the two markers no longer isolate the literals, "
        "and `docs/` would then look far narrower an input than it is"
    )
    return {f"docs/{path}" for path in sorted(published)}


def test_every_published_handbook_path_really_exists_under_docs() -> None:
    """The registry reader's own non-vacuity check: a parse that returned
    plausible-looking rubbish would still be a set of strings, and every
    comparison below would still run. Each path must be a real file --
    which is also what `copy-handbook.mjs` itself requires (a registered
    page missing on disk throws from `cp` rather than being skipped)."""
    missing = [
        path
        for path in sorted(_published_handbook_paths())
        if not (ROOT / path).is_file()
    ]
    assert not missing, (
        f"registry.ts names handbook pages that do not exist: {missing} -- "
        "either the parse above is picking up strings that are not file "
        "paths, or the build is registering a page it cannot copy"
    )


def _deploy_entry_points() -> list[tuple[str, Callable[[], int]]]:
    """Every `uv run --frozen convener-...` command `deploy.yml` runs, resolved through
    `tools/pyproject.toml`'s own `[project.scripts]` table to the function
    that command actually executes."""
    scripts = tomllib.loads(
        (ROOT / "tools" / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["scripts"]
    workflow = (ROOT / DEPLOY_WORKFLOW).read_text(encoding="utf-8")
    resolved: list[tuple[str, Callable[[], int]]] = []
    for command in sorted(set(_UV_RUN_RE.findall(workflow))):
        assert command in scripts, (
            f"deploy.yml runs `uv run --frozen {command}`, which "
            "tools/pyproject.toml declares no entry point for -- the "
            "workflow would fail at that step"
        )
        module_name, _, function_name = str(scripts[command]).partition(":")
        function: Callable[[], int] = getattr(
            importlib.import_module(module_name), function_name
        )
        resolved.append((command, function))
    assert resolved, (
        "no `uv run --frozen convener-...` command was found in deploy.yml -- "
        "the Python half of the input derivation would then be empty and this "
        "whole check would quietly narrow"
    )
    return resolved


def _repository_paths_in_source(source: str, module: ModuleType) -> set[str]:
    """Every `repo_root() / ...` path built in `source`, relative to the
    repository root.

    Only maximal `/` chains are reported: `root / "instance" / "public-data" /
    "survey-status.json"` yields the file, and the `root / "instance" / "public-data"`
    inside it is reported separately only where the source itself binds
    it to a name. A segment that is a module-level constant
    (`EVENTS_DIR`) is resolved through `module`; a segment this reader
    cannot resolve stops the chain there, yielding the enclosing
    directory rather than a guess -- again the safe direction, a wider
    input rather than a narrower one.
    """
    tree = ast.parse(source)
    ordered = sorted(
        ast.walk(tree),
        key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
    )
    divisions = [
        node
        for node in ordered
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
    ]
    nested = {id(node.left) for node in divisions}
    rooted: dict[str, list[str]] = {}
    found: set[str] = set()

    def literal_segments(node: ast.expr) -> list[str] | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.Name):
            value = getattr(module, node.id, None)
            if isinstance(value, str | Path):
                return Path(value).as_posix().split("/")
        return None

    def segments(node: ast.expr) -> list[str] | None:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "repo_root"
        ):
            return []
        if isinstance(node, ast.Name) and node.id in rooted:
            return list(rooted[node.id])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left = segments(node.left)
            if left is None:
                return None
            right = literal_segments(node.right)
            if right is None:
                return None
            return left + right
        return None

    for node in ordered:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            bound = segments(node.value)
            if bound is not None:
                rooted[node.targets[0].id] = bound
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and id(node) not in nested
        ):
            built = segments(node)
            if built:
                found.add("/".join(built))
    return found


def test_the_python_input_reader_sees_a_command_reading_a_new_directory() -> None:
    """Positive control for the third reader, on a probe source rather
    than on the real commands.

    `declarations/integrations.yml` is not an idle example: `convener_ops.cli`
    already reads exactly that file, from `check_config` -- a command
    `deploy.yml` does not run, which is precisely why `config/**` may sit
    in the ignore list today. The day one of the three commands it *does*
    run starts reading it, this reader is what notices."""
    probe = textwrap.dedent(
        """
        def probe() -> int:
            root = repo_root()
            declaration = root / "declarations" / "integrations.yml"
            events = root / EVENTS_DIR
            return 0
        """
    )
    found = _repository_paths_in_source(probe, _cli_module("certificates_public_data"))
    assert "declarations/integrations.yml" in found, (
        f"a command reading declarations/integrations.yml went unseen: {found}"
    )
    assert "instance/data/events" in found, (
        "a path segment held in a module constant went unresolved: "
        f"{found} -- `EVENTS_DIR` is how `certificates_public_data` names "
        "the directory it reads, so losing that resolution loses `instance/data/` "
        "from the derived inputs"
    )


def _bundle_inputs() -> set[str]:
    """Every repository path the deploy build reads, as repository-
    relative paths where each stands for itself and everything beneath
    it.

    `docs/` is the one directory reached wholesale and published
    selectively, so it is replaced by the pages `registry.ts` names. That
    substitution is guarded: if any file other than `copy-handbook.mjs`
    ever reaches `docs/`, the filter no longer describes what happens to
    that directory and this fails rather than quietly keeping the
    narrower answer.
    """
    inputs: set[str] = set()
    docs_readers: set[str] = set()
    for source in _app_build_sources():
        for reached in _repository_paths_reached_from(
            source.read_text(encoding="utf-8"),
            source.parent,
            root=ROOT,
            inside=ROOT / "app",
        ):
            if reached == "docs":
                docs_readers.add(source.relative_to(ROOT).as_posix())
            else:
                inputs.add(reached)

    assert docs_readers == {"app/scripts/copy-handbook.mjs"}, (
        f"`docs/` is reached by {sorted(docs_readers)} -- this check knows "
        "one filter over that directory, `copy-handbook.mjs`'s own "
        "registry allowlist, and that filter is what decides which of its "
        "pages are inputs at all. A second reader of `docs/`, or none at "
        "all, means the substitution below no longer describes the build"
    )
    inputs |= _published_handbook_paths()

    for _, function in _deploy_entry_points():
        inputs |= _repository_paths_in_source(
            textwrap.dedent(inspect.getsource(function)),
            sys.modules[function.__module__],
        )

    # The directories the job itself works in: it runs `npm` in one and
    # `uv run` in the other, so the whole of each is an input to what
    # those commands do.
    workflow = safe_load((ROOT / DEPLOY_WORKFLOW).read_text(encoding="utf-8"))
    for step in workflow["jobs"]["build"]["steps"]:
        directory = step.get("working-directory")
        if directory:
            inputs.add(str(directory).strip("/"))
    return inputs


def test_the_bundle_input_sweep_finds_every_source_the_build_actually_reads() -> None:
    """Non-vacuity, and the sharpest form of it available here: the
    derived set is checked against what `deploy.yml`'s own header comment
    *claims* the build reads. The comment and the derivation are written
    from opposite ends -- one by hand, one out of `package.json`,
    `registry.ts` and `pyproject.toml` -- so agreement between them is
    worth something, and a derivation that quietly stopped finding
    anything could not fake it."""
    inputs = _bundle_inputs()
    for expected in (
        "assets/fonts",
        "instance/keys/events",
        "instance/keys/signing",
        "instance/public-data/certificates-public.json",
        "instance/public-data/survey-status.json",
        "instance/data/speakers.yml",
        "instance/data/config.yml",
        "instance/data/events",
        "app",
        "tools",
    ):
        assert expected in inputs, (
            f"{expected!r} is a documented input of the deploy build and "
            f"the derivation did not find it -- one of the three readers "
            "has stopped seeing its own mechanism, and every assertion "
            "below then checks less than it claims"
        )
    handbook = {path for path in inputs if path.startswith("docs/")}
    assert len(handbook) > 50, (
        f"only {len(handbook)} handbook pages were derived as inputs -- "
        "`docs/` is reached wholesale and filtered by the registry, and a "
        "filter that came back near-empty would make every `docs/...` "
        "comparison below vacuous"
    )


def _deploy_paths_ignore() -> list[str]:
    workflow = safe_load((ROOT / DEPLOY_WORKFLOW).read_text(encoding="utf-8"))
    ignored = workflow_triggers(workflow)["push"]["paths-ignore"]
    assert isinstance(ignored, list) and ignored, (
        f"deploy.yml's `push: paths-ignore:` is {ignored!r} -- the filter "
        "was reverted, or changed direction to `paths:`, which "
        "is the D-25 shape this workflow refuses (see its own header)"
    )
    return [str(entry) for entry in ignored]


def _ignored_subtree(entry: str) -> str:
    """The repository path one `paths-ignore:` entry covers, as a subtree
    root.

    Two shapes only -- `some/where/**` and a plain path carrying no
    wildcard at all -- and anything else raises rather than being guessed
    at. A pattern this reader mis-read would report a clean result about
    a filter that means something else, which is the whole failure mode
    being closed here.
    """
    stem = entry[: -len("/**")] if entry.endswith("/**") else entry
    assert not any(character in stem for character in "*?[!"), (
        f"the ignore entry {entry!r} is not a plain path or a `dir/**` "
        "subtree -- this reader refuses to evaluate a pattern shape it "
        "was not written for rather than answer plausibly and wrongly"
    )
    return stem


def _overlaps(one: str, other: str) -> bool:
    """Whether two repository subtrees can hold a file in common. A plain
    file path is simply a subtree of one member, which makes this one
    rule rather than four."""
    return one == other or one.startswith(f"{other}/") or other.startswith(f"{one}/")


def test_the_overlap_rule_reproduces_the_distinction_it_exists_to_draw() -> None:
    """Positive control. The whole of this filter's correctness sits on one
    distinction: `docs/reference` and `docs/handbook/governance/board-rules.md`
    do *not* overlap even though both live under `docs/`, while `config`
    and `declarations/integrations.yml` do. A rule that could not draw that
    line would either pass on a broken list or fail on the correct one."""
    assert not _overlaps("docs/reference", "docs/handbook/governance/board-rules.md")
    assert not _overlaps("site", "site-map.md")
    assert _overlaps("declarations", "declarations/integrations.yml")
    assert _overlaps("instance/data/events", "instance/data")
    assert _overlaps("cspell.json", "cspell.json")


def _git_ls_files(subtree: str) -> list[str]:
    """What this repository tracks under `subtree`.

    A runner checks out the repository and sees exactly this; a working
    tree can hold anything beside it. `paths-ignore:` is evaluated
    against pushed changes, so tracked is the reading that matches what
    the filter is for.
    """
    # Fixed argv, shell=False; `subtree` comes out of deploy.yml.
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files", "--", subtree],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return listed.stdout.split()


@pytest.mark.parametrize("entry", _deploy_paths_ignore())
def test_no_path_the_deploy_ignores_can_reach_the_deployed_bundle(entry: str) -> None:
    """The ignore list, pinned as the relationship rather than
    as the list.

    Each entry of `paths-ignore:` asserts something about this
    repository: that nothing under it is an input to the bundle
    `deploy.yml` publishes. Should that stop being true -- an app source
    importing from `config/`, a copy script reading `site/`, a `tools/`
    command the workflow runs opening a file under either -- the workflow
    silently stops firing for changes to that path, and a stale site is
    published with nothing red anywhere. That is the D-25 failure
    `paths-ignore:` was chosen to avoid, arriving through the list's
    contents rather than through its direction, which is exactly why the
    direction alone does not cover it.
    """
    ignored = _ignored_subtree(entry)
    reachable = sorted(path for path in _bundle_inputs() if _overlaps(ignored, path))
    assert not reachable, (
        f"deploy.yml ignores {entry!r}, but the deploy build reads "
        f"{reachable} -- a commit touching that path would now publish "
        "nothing, and no run would go red to say so. Either the input is "
        "wrong and should leave the build, or this entry is wrong and "
        "must leave the ignore list (D-25)"
    )


@pytest.mark.parametrize("entry", _deploy_paths_ignore())
def test_every_ignored_path_still_names_something_in_this_repository(
    entry: str,
) -> None:
    """The cheap half of the reverse direction.

    An entry that names nothing is not dangerous -- `paths-ignore:` fails
    safe, and a filter matching no file merely runs the workflow -- but
    it is invisible: a typo, or a directory that has since been renamed,
    leaves a line that reads like a decision and enforces nothing.

    **Against what git tracks, not against a working tree**, and that is
    a correction made after finding the old reading was wrong. It said
    "including an untracked working directory, which git does not track
    but which is present in a working tree" -- true on the machine it was
    written on and false in every fresh checkout, including the runner
    that decides whether a pull request merges.

    An entry naming nothing tracked is therefore reported as what it is:
    a line that filters nothing on the only machine whose filtering
    matters. It used to be excused when the whole subtree was missing,
    for the sake of one entry naming a directory a derived repository
    would not carry; that entry is gone, every remaining one names a
    subtree the product itself owns, and an exemption no case reaches is
    an exemption that only hides the next dead line.
    """
    ignored = _ignored_subtree(entry)
    tracked = _git_ls_files(ignored)
    assert tracked, (
        f"deploy.yml ignores {entry!r}, which matches nothing this "
        "repository tracks -- the line reads as a decision and filters "
        "nothing on a runner, which only ever sees tracked files"
    )
    assert any(
        _git_ls_files(_ignored_subtree(other)) for other in _deploy_paths_ignore()
    ), "no entry of paths-ignore names anything tracked -- this proves nothing"


# ------------------------------------------------------------------ #
# Nothing outside the default branch runs.
#
# The queue of public submissions lives somewhere in this
# repository: the signup relay writes each encrypted submission down, and
# one drain later handles the lot in a single run instead of one run per
# person who fills in a form. The whole saving rests on a single fact --
# a push to a branch other than the default one starts no workflow at
# all -- and that fact is true today by accumulation, not by contract.
# Thirteen workflows declare `push:`; all thirteen carry
# `branches: [main]` because thirteen separate decisions happened to go
# that way.
#
# The trap is worth stating in full, because it is the opposite of the
# usual one. The relay pushes with its own token, not with a job's
# `GITHUB_TOKEN`, so GitHub's recursion guard -- which is what normally
# stops a workflow's own commit from starting another workflow -- does
# not apply to anything the relay writes. A queue on the default branch
# would start `deploy`, `register` and `validate-data` on every single
# submission: four billed runs per registrant where there is one today,
# the exact inverse of the phase's purpose. A queue anywhere else is
# free only for as long as this invariant holds, and the invariant is
# one absent-minded `push:` away from being gone with nothing red
# anywhere (D-25).
#
# The narrower sweep above does not hold it. It visits workflows
# declaring both `push:` and `pull_request:` -- five of the thirteen --
# because the property it was written for is about running the same
# checks twice on one commit. The eight that declare `push:` alone,
# `deploy.yml` and `derive-decision-register.yml` among them, escape it entirely.
#
# Two properties are held below, because a branch write reaches a
# workflow by two different routes and only one of them is a `push:`
# filter.
# ------------------------------------------------------------------ #


def _workflows_triggered_by_a_push() -> list[Path]:
    """Every workflow declaring `push:`, whatever else it declares --
    derived from each file's own trigger block, never a list of names.
    That is the point of the derivation rather than a stylistic
    preference: a workflow written next month has to be covered without
    anyone
    remembering it exists, and a list of names is precisely the thing
    that would not cover it."""
    return [
        workflow
        for workflow in _workflow_files()
        if "push"
        in workflow_event_names(safe_load(workflow.read_text(encoding="utf-8")) or {})
    ]


def test_the_push_sweep_reaches_the_workflows_the_double_run_sweep_cannot() -> None:
    """Non-vacuity, in the form that also pins the gap this sweep exists
    to close.

    A parametrisation that silently found nothing would report green
    forever, so the count is guarded like every other sweep here. But the
    sharper statement is the containment: this sweep must be a strict
    superset of the narrower one, and `derive-decision-register.yml` -- `push:` with no
    `pull_request:` beside it -- must be in the difference. The day both
    sweeps agree, either the repository changed shape or this one has
    quietly narrowed to the older property.
    """
    found = {workflow.name for workflow in _workflows_triggered_by_a_push()}
    also_reviewed = {
        workflow.name
        for workflow in _workflows_triggered_by_both_push_and_pull_request()
    }
    assert len(found) >= 13, (
        f"only {sorted(found)} were detected as declaring `push:` -- "
        "thirteen did when this was written, so either they really are "
        "gone or the sweep has stopped seeing them"
    )
    assert also_reviewed < found, (
        f"the push sweep ({sorted(found)}) no longer strictly contains "
        f"the double-run sweep ({sorted(also_reviewed)}) -- this sweep "
        "exists because the older one visits only workflows declaring "
        "`pull_request:` too, and it is now no wider than the thing it "
        "was written to widen"
    )
    assert "derive-decision-register.yml" in found - also_reviewed, (
        f"derive-decision-register.yml is no longer among the `push:`-only workflows "
        f"({sorted(found - also_reviewed)}) -- it is the plainest example "
        "of the eight the narrower sweep cannot see, and if it has "
        "stopped being one, check that this sweep still sees the others"
    )


@pytest.mark.parametrize(
    "workflow",
    _workflows_triggered_by_a_push(),
    ids=lambda p: p.name,
)
def test_no_push_trigger_starts_outside_the_default_branch(workflow: Path) -> None:
    """The invariant the queue is built on, stated over the whole
    directory.

    Note that it is a statement about the set of branches, not about one
    sample branch. Asking `_push_trigger_fires_on(push, "feature-x")` --
    which is what the narrower property does, correctly, for its own purpose
    -- would pass on `branches: [main, submissions]` while the queue
    branch it names started a run on every submission. So what is
    asserted is that the trigger reaches no branch beyond the default
    one, and `_push_trigger_branches` refuses every filter shape it
    cannot answer that about rather than guessing.
    """
    triggers = workflow_triggers(safe_load(workflow.read_text(encoding="utf-8")))
    fires_on = _push_trigger_branches(triggers["push"])
    reach = (
        "every branch there is"
        if fires_on is None
        else f"{sorted(fires_on - {DEFAULT_BRANCH})} besides {DEFAULT_BRANCH!r}"
    )
    assert fires_on is not None and fires_on <= {DEFAULT_BRANCH}, (
        f"{workflow.name}'s `push:` trigger starts on {reach}, and this "
        f"repository holds that a push to a branch other than "
        f"{DEFAULT_BRANCH!r} starts no workflow at all. That is not "
        "tidiness. The signup relay writes public submissions into this "
        "repository with its own token, not with a job's `GITHUB_TOKEN`, "
        "so GitHub's recursion guard does not apply to what it pushes: "
        "every trigger a queue write can reach bills one run per member "
        "of the public who fills in a form, which is the thing the queue "
        "exists to stop. Add `branches: [main]` to this trigger; if this "
        "workflow genuinely has to run elsewhere, then it is the queue "
        "that has to move first, and that is a decision, not a fix"
    )


# ------------------------------------------------------------------ #
# The second route, and the reason the branch filters above are not the
# whole invariant.
#
# `create:` fires when a branch or a tag is created, and it takes no
# filter of any kind -- no `branches:`, nothing. `delete:` is the same on
# the way out. A single workflow declaring either would start on the day
# the relay first creates the queue branch, and no amount of care with
# `push: branches:` would say a word about it. Neither event is declared
# here today, which is exactly why this is worth pinning now rather than
# after someone adds one.
#
# Held as an allowlist rather than as a blocklist of those two. A
# blocklist answers "is this one of the two events I know about", which
# is green by default for every event GitHub adds after today; an
# allowlist answers "has anyone worked out whether a branch write starts
# this", which is red by default and asks the question of the person who
# is actually adding the trigger.
# ------------------------------------------------------------------ #

#: Events that a write to a branch other than the default one cannot
#: start, with the reason each is on the list -- because a name alone
#: would be an assertion nobody could check.
#:
#: * `workflow_dispatch` and `repository_dispatch` are deliberate calls,
#:   by a person or by an external system holding a token scoped for it.
#:   Neither is a consequence of a commit arriving, and the relay's token
#:   carries `Contents: read & write` and nothing else, so it cannot make
#:   either call however much it writes.
#: * `schedule` runs from the default branch only, on its own clock.
#: * `workflow_run` fires when a named workflow completes, so it is inert
#:   here by transitivity: no run of the named workflow, no run of this
#:   one. It is on the list because of the property above, not beside it
#:   -- if a push trigger ever escaped the default branch, this would
#:   escape with it.
#: * `pull_request` fires on pull-request activity, and a push to a
#:   branch is such activity only when an open pull request has that
#:   branch as its head. That is repository state, not file content: no
#:   test here can see it, and no test here goes near the network to look.
#:   It is an operational precondition on wherever the queue ends up
#:   living -- no pull request is ever opened from the queue branch --
#:   and it is written down here rather than left implied.
_EVENTS_NO_BRANCH_WRITE_CAN_START: Final = frozenset(
    {
        "workflow_dispatch",
        "repository_dispatch",
        "schedule",
        "workflow_run",
        "pull_request",
    }
)


def test_the_event_classification_still_refuses_the_two_events_it_exists_for() -> None:
    """Positive control on the allowlist itself.

    `create:` and `delete:` are the whole reason this classification is
    here: they fire on a branch being created or removed and accept no
    filter at all, so the queue branch appearing would start them. An
    allowlist that had quietly grown either name would pass the sweep
    below on the exact workflow that breaks the invariant.

    The second half is the non-vacuity half: the six events this
    repository declares today must all be classified, or the sweep below
    is asserting something about an empty set.
    """
    assert not {"create", "delete"} & _EVENTS_NO_BRANCH_WRITE_CAN_START, (
        "`create` or `delete` has been classified as an event a branch "
        "write cannot start -- both fire on a branch being created or "
        "deleted, and neither accepts a branch filter, so a workflow "
        "declaring one runs the moment the queue branch appears"
    )
    declared: set[str] = set()
    for workflow in _workflow_files():
        declared |= workflow_event_names(
            safe_load(workflow.read_text(encoding="utf-8")) or {}
        )
    assert declared >= {
        "push",
        "pull_request",
        "schedule",
        "repository_dispatch",
        "workflow_dispatch",
        "workflow_run",
    }, (
        f"this repository declares {sorted(declared)} -- six events were "
        "declared when this was written, and a sweep that has stopped "
        "seeing some of them classifies less than it appears to"
    )


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_every_event_a_workflow_declares_has_been_weighed_against_the_queue(
    workflow: Path,
) -> None:
    """Every event declared anywhere in the directory is either `push:`
    -- whose branch filter the sweep above reads -- or one somebody has
    worked out a branch write cannot start.

    This fails on an event nobody has classified yet, and that is the
    intended behaviour rather than an inconvenience: the person adding
    the trigger is the one holding the answer, and a suite that shrugged
    at an unknown event would go on reporting that the queue is
    unreachable while having no idea whether it still is.
    """
    events = workflow_event_names(safe_load(workflow.read_text(encoding="utf-8")) or {})
    unclassified = sorted(events - _EVENTS_NO_BRANCH_WRITE_CAN_START - {"push"})
    assert not unclassified, (
        f"{workflow.name} declares {unclassified}, which nothing here has "
        "weighed against the queue's invariant: a push to a branch other "
        f"than {DEFAULT_BRANCH!r} starts no workflow at all, which is "
        "what makes it free to queue public submissions on a branch "
        "instead of billing a run per submission. Work out whether a "
        "write to a branch that is not the default one can start this "
        "event. If it cannot, add it to "
        "`_EVENTS_NO_BRANCH_WRITE_CAN_START` with the reason. If it can "
        "-- `create:` and `delete:` do, and take no filter to stop them "
        "-- then this trigger and the queue cannot both stay where they "
        "are"
    )


def test_the_branch_reader_reports_which_branches_a_push_trigger_reaches() -> None:
    """Reader control, on probes rather than on the real files.

    The narrower control asks the yes/no question; this one asks the set
    question, and the third case is what separates them. A trigger
    listing the default branch and another one fires on a branch that is
    not the default while `_push_trigger_fires_on(push, "feature-x")`
    still answers `False`, so a set this reader could not report would
    leave the property above unable to see its own failure mode.
    """
    assert _push_trigger_branches(None) is None
    assert _push_trigger_branches({"paths": ["instance/data/**.yml"]}) is None
    assert _push_trigger_branches({"branches": [DEFAULT_BRANCH]}) == frozenset(
        {DEFAULT_BRANCH}
    )
    assert _push_trigger_branches(
        {"branches": [DEFAULT_BRANCH, "submissions"], "paths": ["queue/**"]}
    ) == frozenset({DEFAULT_BRANCH, "submissions"})


@pytest.mark.parametrize(
    ("push", "refusal"),
    [
        ({"branches-ignore": ["gh-pages"]}, "branches-ignore"),
        ({"branches": ["main", "release/*"]}, "glob pattern"),
        ({"tags": ["v*"]}, "by tag"),
        ({"branches": ["main"], "tags-ignore": ["v*"]}, "by tag"),
        ({"branches": []}, "non-empty list"),
        (["main"], "not a mapping"),
    ],
    ids=[
        "branches-ignore",
        "glob",
        "tags-only",
        "tags-ignore",
        "empty-list",
        "not-a-mapping",
    ],
)
def test_the_branch_reader_refuses_the_filter_shapes_it_cannot_evaluate(
    push: Any, refusal: str
) -> None:
    """The refusals are load-bearing, so they are controlled like the
    answers.

    A reader that answered plausibly here would be worse than no reader
    at all: `branches-ignore:` and a glob would be read against the wrong
    syntax, and a tag-only filter would be read as reaching no branch --
    the permissive answer, on the one shape this was never written for.
    Each must raise, and the message must say which shape it declined.
    """
    with pytest.raises(AssertionError, match=refusal):
        _push_trigger_branches(push)


# ------------------------------------------------------------------ #
# One Node version, written once, and it clears what the toolchain
# declares.
#
# Seven workflows installed Node 20, four installed 22, and `quality.yml`
# installed both -- a split nothing here could see, because every one of
# those pins was correct on its own. Node 20 left maintenance in April
# 2026, so the larger half of this pipeline ran on a runtime that receives
# no security fix, while the packages it installs had already moved past
# it: `wrangler` 4 declares `engines.node: >=22.0.0` and the three relays
# deploy through it; `puppeteer-core` 25 declares `>=22.12.0` and `site/`
# installs it for its own accessibility and performance checks. Both were
# being installed on 20.
#
# The agreement that ended that split was a property of sixteen matching
# literals in eleven files, held by a sweep that read them and compared
# them to each other. It is now a property of one file: `.nvmrc` at the
# repository root, which every `actions/setup-node` step reaches through
# `node-version-file:` and every `package.json` states a floor against in
# `engines.node`. That is the shape this repository already gives the
# directory map, the charter tokens, the motif and the two renderings of
# the standing-up sequence -- the value is written once and everything
# that needs it reads it -- and a version somebody has to retype in
# sixteen places is the defect that shape exists to remove.
#
# Three properties, deliberately separate:
#
#   1. every Node installation reads that one file and names no version
#      of its own, swept over the directory rather than over a list of
#      file names, so a workflow added later is held the same way without
#      being added anywhere;
#   2. every npm tree declares its floor as the same major, so `npm
#      install` in a duplicate's own checkout refuses a runtime this
#      pipeline would never have run on;
#   3. what all of them agree on clears the floor the lock files
#      themselves declare -- without it, the first two are satisfied just
#      as well by the whole repository drifting back onto an unsupported
#      runtime together.
# ------------------------------------------------------------------ #

#: How `actions/setup-node` is named in a `uses:` line. What follows the
#: `@` is a full commit SHA, pinned by the sweep near the top of this
#: module, so the prefix is what identifies the action here.
_SETUP_NODE: Final = "actions/setup-node@"

#: The one file the version is written in, root-relative and spelled
#: exactly as a `node-version-file:` has to name it.
NODE_VERSION_FILE: Final = ".nvmrc"


def _setup_node_steps(workflow: Path) -> list[tuple[str, str, str | None, str | None]]:
    """`(job id, step name, node-version-file, node-version)` for every
    `actions/setup-node` step in `workflow`.

    Both keys are carried back, and both are `None` for a step naming
    neither, which is not the same thing as a step this reader missed:
    such a step takes whatever the runner image happens to ship, which is
    the drift this section exists to refuse, so it is a finding rather
    than a dropped row. A step with no `name:` is reported by its `id:`,
    and one with neither by its position, because the message has to name
    something a reader can find in the file.
    """
    loaded = safe_load(workflow.read_text(encoding="utf-8"))
    jobs = loaded.get("jobs") if isinstance(loaded, dict) else None
    found: list[tuple[str, str, str | None, str | None]] = []
    if not isinstance(jobs, dict):
        return found
    for job_id, job in jobs.items():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list):
            continue
        for position, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if not (isinstance(uses, str) and uses.startswith(_SETUP_NODE)):
                continue
            given = step.get("with")
            options = given if isinstance(given, dict) else {}
            named = step.get("name") or step.get("id") or f"step {position}"
            read = options.get("node-version-file")
            version = options.get("node-version")
            found.append(
                (
                    str(job_id),
                    str(named),
                    None if read is None else str(read),
                    None if version is None else str(version),
                )
            )
    return found


def _node_installations() -> list[tuple[str, str, str, str | None, str | None]]:
    """Every Node installation this repository performs in CI, as
    `(workflow, job, step, node-version-file, node-version)`."""
    return [
        (workflow.name, job, step, read, version)
        for workflow in _workflow_files()
        for job, step, read, version in _setup_node_steps(workflow)
    ]


def _node_version() -> str:
    """What `.nvmrc` says, which is what every reference to it resolves
    to."""
    declared = (ROOT / NODE_VERSION_FILE).read_text(encoding="utf-8").strip()
    assert declared, f"{NODE_VERSION_FILE} is empty, so it names no runtime"
    return declared


def test_the_setup_node_reader_finds_the_installations_this_repository_has() -> None:
    """Reader control before the three properties that rest on it: a
    reader matching nothing would make all of them pass by finding no
    disagreement and no shortfall, which is the one way a sweep fails
    silently."""
    found = _node_installations()
    assert found, (
        f"no step in any workflow uses {_SETUP_NODE} -- the reader itself is "
        "wrong, and every check below would pass over an empty sweep"
    )
    assert len({workflow for workflow, *_ in found}) > 1, (
        "every Node installation found sits in one workflow, which has not "
        "been true here since the relays grew workflows of their own"
    )


def test_every_workflow_reads_the_node_version_from_the_one_file() -> None:
    """No workflow states a Node version; every one of them reads
    `.nvmrc`.

    Nothing here names 24. The version is not this test's to state --
    changing it is an edit to one file and to nothing else, and this is
    what makes that true: a step that spelled the version out would go on
    installing the old one after that edit, silently and correctly by its
    own lights, which is how seven workflows came to be a major version
    behind four others.
    """
    found = _node_installations()
    assert found, "the reader found no Node installation at all"
    assert (ROOT / NODE_VERSION_FILE).is_file(), (
        f"{NODE_VERSION_FILE} does not exist, so every `node-version-file:` "
        "in these workflows points at nothing"
    )
    stated = [
        f"{workflow}::{job}/{step} states node-version: {version!r}"
        for workflow, job, step, _, version in found
        if version is not None
    ]
    assert stated == [], (
        "a Node version is written into a workflow rather than read from "
        f"{NODE_VERSION_FILE}: " + "; ".join(stated)
    )
    elsewhere = [
        f"{workflow}::{job}/{step} reads {read!r}"
        for workflow, job, step, read, _ in found
        if read != NODE_VERSION_FILE
    ]
    assert elsewhere == [], (
        f"a Node installation that does not read {NODE_VERSION_FILE}: "
        + "; ".join(elsewhere)
    )


#: The first integer in a version expression -- the major of the lowest
#: release that expression admits, for every shape `engines.node` takes in
#: these lock files (`>=22.12.0`, `^20.19.0`, `>= 0.8`, `20`, `6.*`,
#: `>=v12.22.7`).
_FIRST_MAJOR_RE: Final = re.compile(r"(\d+)")


def _branch_floor_major(branch: str) -> int | None:
    """The lowest Node major one branch of an `engines.node` range admits,
    or `None` for a branch naming no version at all (`*`)."""
    match = _FIRST_MAJOR_RE.search(branch)
    return int(match.group(1)) if match else None


def _range_floor_major(spec: str) -> int | None:
    """The lowest Node major a whole `engines.node` range admits.

    `||` separates alternatives, so a range's own floor is the *lowest* of
    its branches, never the highest: `^20.19.0 || >=22.12.0` is satisfied
    by 20.19, so it requires nothing of 22. Only a range with no
    alternative -- `>=22.12.0` -- states a floor the toolchain cannot get
    under, and those are the ones the check below rests on.

    A floor, and not a full range check. It cannot see that
    `^20.19.0 || ^22.13.0 || >=24` excludes 23 outright, so a repository
    that moved to 23 would pass here and fail on the runner. What it does
    catch is the drift this section exists for -- staying on a runtime the
    packages have left -- and it catches it in majors, which is the unit
    `.nvmrc` is written in.

    `test_node_floor.py` reads the rest of that grammar. It holds the
    finer question inside the one line `.nvmrc` names: whether a
    `package.json` admits a version of that line its own lock file
    refuses, which is what `>=24` did against `jsdom`'s 24.15.0 until a
    maintainer's machine happened to be old enough to be told.
    """
    floors = [
        floor
        for branch in spec.split("||")
        if (floor := _branch_floor_major(branch)) is not None
    ]
    return min(floors) if floors else None


def test_the_engines_reader_takes_the_lowest_branch_of_an_alternative() -> None:
    """Reader control. Taking the highest branch instead would read
    `^20.19.0 || >=22.12.0` -- the commonest shape in these lock files, and
    the one Vite and Vitest both use -- as demanding 22, and the check
    below would then be quoting a floor no package actually sets."""
    assert _range_floor_major(">=22.12.0") == 22
    assert _range_floor_major("^20.19.0 || >=22.12.0") == 20
    assert _range_floor_major("^20.19.0 || ^22.13.0 || >=24") == 20
    assert _range_floor_major(">=20.19.0 <22.0.0 || >=22.12.0") == 20
    assert _range_floor_major(">=v12.22.7") == 12
    assert _range_floor_major("*") is None


#: What the runner these workflows declare actually is. A lock file entry
#: gated to another platform (`@img/sharp-win32-ia32`, `os: [win32]`,
#: `cpu: [ia32]`) is never installed there, so its own `engines.node` says
#: nothing about what CI needs -- and left in, a Windows-only package
#: could raise this floor against a runtime it will never run on.
_RUNNER_OS: Final = "linux"
_RUNNER_CPU: Final = "x64"


def _installed_on_the_runner(entry: Mapping[str, Any]) -> bool:
    for key, runner in (("os", _RUNNER_OS), ("cpu", _RUNNER_CPU)):
        declared = entry.get(key)
        if isinstance(declared, list) and runner not in declared:
            return False
    return True


def _declared_node_floor() -> tuple[int, list[str]]:
    """The highest Node major this repository's npm trees require between
    them, and every package that requires it.

    Read from the committed lock files, which are what `npm ci` installs
    from -- never from `node_modules`, which a laptop may not have and a
    fresh clone certainly does not.
    """
    floor = 0
    requiring: list[str] = []
    lockfiles = _git_ls_files("*package-lock.json")
    assert lockfiles, "this repository tracks no package-lock.json at all"
    for relative in lockfiles:
        lock = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        packages = lock.get("packages")
        for name, entry in (packages or {}).items():
            if not isinstance(entry, dict) or not _installed_on_the_runner(entry):
                continue
            spec = (entry.get("engines") or {}).get("node")
            if not isinstance(spec, str):
                continue
            major = _range_floor_major(spec)
            if major is None or major < floor:
                continue
            where = f"{relative} {name or '(the tree itself)'} ({spec})"
            if major > floor:
                floor, requiring = major, [where]
            else:
                requiring.append(where)
    return floor, requiring


def test_every_npm_tree_declares_the_floor_the_one_file_names() -> None:
    """`engines.node` in every tracked `package.json`, against `.nvmrc`.

    The workflows read that file, so continuous integration cannot drift
    on its own; nothing made a duplicate's laptop read it too.
    `engines.node` is what `npm install` itself enforces, and it is a
    literal -- npm reads no `.nvmrc` -- so it is the one restatement of
    the version that has to exist, and this is the control that makes it
    follow. A duplicate that raises `.nvmrc` and stops there is told which
    trees did not move.
    """
    declared = _node_version()
    wanted = _branch_floor_major(declared)
    assert wanted is not None, (
        f"{NODE_VERSION_FILE} says {declared!r}, which names no major at all"
    )
    manifests = _git_ls_files("*package.json")
    assert manifests, "this repository tracks no package.json at all"
    problems: list[str] = []
    for relative in manifests:
        manifest = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        engines = manifest.get("engines")
        spec = engines.get("node") if isinstance(engines, dict) else None
        if not isinstance(spec, str):
            problems.append(f"{relative} declares no engines.node")
            continue
        floor = _range_floor_major(spec)
        if floor != wanted:
            problems.append(f"{relative} declares {spec!r}, a floor of {floor}")
    assert problems == [], (
        f"{NODE_VERSION_FILE} names Node {declared}, and these trees do not: "
        + "; ".join(problems)
    )


def test_the_installed_node_version_clears_what_the_lock_files_declare() -> None:
    """The half the two sweeps above cannot state.

    Every workflow agreeing on Node 20 satisfies them perfectly while
    `wrangler` and `puppeteer-core` both declare they need 22 -- which is
    the state this repository was actually in. The floor comes out of the
    lock files `npm ci` installs from, so a dependency bump that raises it
    fails here rather than on a runner.
    """
    declared = _node_version()
    installed = _branch_floor_major(declared)
    assert installed is not None, (
        f"{NODE_VERSION_FILE} says {declared!r}, which names no version at "
        "all, so no floor can be checked against it"
    )
    floor, requiring = _declared_node_floor()
    assert installed >= floor, (
        f"{NODE_VERSION_FILE} names Node {declared}, below the {floor} this "
        f"repository's own lock files require: {'; '.join(sorted(requiring))}"
    )


# ------------------------------------------------------------------ #
# The security scanner kept beside ruff, and its three halves.
#
# Ruff's `S` rules are a port of bandit, so `bandit` looks like a tool
# this project could drop and a step `quality.yml` could stop paying for.
# It was measured instead of assumed, and kept: `tools/pyproject.toml`'s
# own `[tool.ruff.lint]` comment carries the comparison finding by
# finding. What that comment cannot do is stop the three halves of the
# decision from being removed one at a time -- a dependency nothing runs,
# a step whose tool is not installed, or eighteen `# nosec` comments no
# tool reads any more, each of which is silent on its own.
# ------------------------------------------------------------------ #

#: The scanner itself, as `pyproject.toml` names it, as `quality.yml`
#: invokes it, and as the suppression syntax below belongs to.
_SECURITY_SCANNER: Final = "bandit"

#: Bandit's own suppression comment. Ruff does not read it -- it reads a
#: `noqa` directive instead -- so every one of these is text nothing
#: checks at all the moment this scanner stops running.
_SUPPRESSION: Final = "# nosec"


def _dev_dependencies() -> list[str]:
    """`tools/pyproject.toml`'s dev group, as declared."""
    settings = tomllib.loads(
        (ROOT / "tools" / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = settings["dependency-groups"]["dev"]
    assert isinstance(declared, list) and declared, (
        "tools/pyproject.toml declares no dev dependency group at all"
    )
    return [str(entry) for entry in declared]


def _modules_carrying_a_suppression() -> list[str]:
    """Every module under `convener_ops` that silences a finding.

    `rglob`, because the package is seven sub-packages and nothing at its
    root: a flat walk reads none of the modules that carry a suppression,
    and the check below passes on an empty list.
    `quality.yml` points bandit at the package with `-r`, so the sweep
    that holds the step has to be as deep as the step itself.
    """
    package = ROOT / "tools" / "convener_ops"
    return sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if _SUPPRESSION in path.read_text(encoding="utf-8")
    )


def test_the_security_scanner_is_declared_run_and_reads_its_own_suppressions() -> None:
    """One decision, three files, and none of them enough on its own.

    The dependency without the step is a tool nobody runs. The step
    without the dependency is a red job. And either without the
    suppressions is the reverse: `# nosec` is bandit's syntax, so the
    eighteen of them in `convener_ops` are the part that would quietly
    become decoration -- ruff reads a `noqa` directive instead, and would
    go on reporting
    nothing about lines that are annotated for a tool that no longer runs.

    This does not re-argue the comparison; `tools/pyproject.toml` holds
    that. It refuses the half-removal the comparison cannot see.
    """
    declared = [
        entry for entry in _dev_dependencies() if entry.startswith(_SECURITY_SCANNER)
    ]
    assert declared, (
        f"tools/pyproject.toml no longer declares {_SECURITY_SCANNER} -- if it "
        "was swapped for ruff's own `S` rules, that comparison is in that "
        "file's own [tool.ruff.lint] comment and says why it is not a swap"
    )
    run_by = [
        f"{job}/{step}"
        for job, step, script in _all_run_scripts(ROOT / QUALITY_WORKFLOW)
        if f"{_SECURITY_SCANNER} " in script
    ]
    assert run_by, (
        f"quality.yml runs no {_SECURITY_SCANNER} step, while "
        f"tools/pyproject.toml still installs it: {', '.join(declared)}"
    )
    suppressing = _modules_carrying_a_suppression()
    assert suppressing, (
        f"no module under convener_ops carries a {_SUPPRESSION!r} any more, "
        f"so {_SECURITY_SCANNER} is being installed and run over a package "
        "with nothing left to say about it -- which is the point at which "
        "the comparison in tools/pyproject.toml is worth running again"
    )
    assert any("/" in name for name in suppressing), (
        f"every module found carrying a {_SUPPRESSION!r} sits at the root of "
        f"convener_ops ({suppressing}) -- the walk stopped at the package's "
        "own directory, and whatever the sub-packages silence is unread"
    )
