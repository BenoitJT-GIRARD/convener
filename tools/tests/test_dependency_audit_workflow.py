"""A dependency audit was first wired into
`.github/workflows/quality.yml`'s `site/` steps only. `site/` was the surface
that happened to pass -- `app/`'s own tree was never audited at all, and
it is the larger one: `react-router`/`react-router-dom` and `js-yaml` are
`app/package.json` `dependencies`, not `devDependencies`, so they ship in
the built application bundle the operators' cockpit serves at
its own published base behind its login screen, and the three relay services
under `services/` had never been audited either. "The audit runs in one
place" is exactly the shape D-25 names: a control positioned so it could
not fail on the surface that mattered.

This module pins two things a green run of the *expanded* chain would not,
by itself, prove:

* every surface with a lockfile (`app/`, and the three `services/*`
  relays, alongside `site/`, already covered) now has its own audit step
  -- not just the one that happened to be zero already;
* the policy chosen for each is the one its own dependency shape
  justifies, not a threshold that happens to pass today. `app/` has a real
  `dependencies` tree that ships to a real (if gated) surface, so its
  blocking gate is `npm audit --omit=dev` -- production only -- with a
  second, `continue-on-error` step surfacing (never blocking on) the
  purely tooling-side findings. The three relays and `site/` declare no
  `dependencies` at all -- every package they carry is a
  `devDependency` by npm's own label, but for them that label names their
  *entire* dependency tree, not a carved-out subset that never ships --
  so `--omit=dev` there would exempt everything and pass regardless of
  what it found, the identical reasoning
  `test_performance_workflow.py::test_the_workflow_audits_site_dependencies`
  already pins for `site/`'s own step.

Read as text and asserted against with `in` checks, the same idiom every
other workflow-pinning module in this suite already uses -- never parsed
and executed, which here would mean a real `npm ci` against the live
registry, exactly the network access this suite must not take on.
Running the real audits for real -- against the real installed trees, on
both the current state and (reverted afterwards) the state before this
fix -- is a hand-run job, not this module's. Each command below was run
for real once, and what it printed was read.
"""

from __future__ import annotations

from convener_ops.paths import repo_root

_ROOT = repo_root()
_WORKFLOW = (_ROOT / ".github" / "workflows" / "quality.yml").read_text(
    encoding="utf-8"
)
_APP_PACKAGE_JSON = (_ROOT / "app" / "package.json").read_text(encoding="utf-8")


def _job(name: str, next_job: str | None) -> str:
    """Slices one job's own text out of `quality.yml`, the same isolation
    `test_performance_workflow.py::_SITE_LANE` and
    `test_a11y_workflow.py` already use -- a workflow-wide `in` check
    could match a different surface entirely, including the one this
    module exists to tell apart from the one it replaced (`app/` carries
    two audit steps now; a check that did not isolate its surface could
    silently pass by matching the *other* one)."""
    start = _WORKFLOW.split(f"\n  {name}:\n", 1)[1]
    if next_job is None:
        return start
    return start.split(f"\n  {next_job}:\n", 1)[0]


def _lane(job: str, first_step: str, next_step: str | None) -> str:
    """Slices one *lane* out of a merged job's own text.

    `quality.yml`'s eight jobs were grouped into four: what
    were the `typescript`, `site` and `spelling` jobs are now three lanes
    of one `web` job, and the three relays are three lanes of one
    `relays` job -- eight billed jobs became four with no check dropped.
    The isolation this module has always needed did not change with them:
    `--omit=dev` still belongs to exactly one surface, and a check that
    read the whole merged job would pass by matching a neighbouring lane.
    So the boundary moved from the job to the lane, and nothing else did.

    Each lane is marked by the `Install ...` step it opens with -- the
    same step whose `id:` that lane's own checks guard on in the workflow
    (`if: always() && steps.install-app.outcome == 'success'`, and its
    siblings), so the marker read here and the structure the workflow
    actually runs cannot drift apart without one of the isolation probes
    below saying so."""
    start = job.split(f"- name: {first_step}\n", 1)[1]
    if next_step is None:
        return start
    return start.split(f"- name: {next_step}\n", 1)[0]


_WEB_JOB = _job("web", "relays")
_RELAYS_JOB = _job("relays", "workflow-schema")

_APP_LANE = _lane(_WEB_JOB, "Install app", "Install site")
_AUTH_PROXY_LANE = _lane(_RELAYS_JOB, "Install auth-proxy", "Install form-relay")
_FORM_RELAY_LANE = _lane(_RELAYS_JOB, "Install form-relay", "Install signup-relay")
_SIGNUP_RELAY_LANE = _lane(_RELAYS_JOB, "Install signup-relay", None)


def test_the_app_lane_is_isolated_correctly() -> None:
    """A probe on the slicing above itself, the same self-check
    `test_performance_workflow.py::test_the_site_lane_is_isolated_correctly`
    already runs for its own slice: if either marker moves -- a step
    renamed, a lane reordered -- every other test in this module would
    silently start reading the wrong slice rather than failing here with
    a clear reason."""
    assert "working-directory: app" in _APP_LANE
    assert "npm run typecheck" in _APP_LANE


def test_the_app_lane_audits_production_dependencies() -> None:
    """The blocking gate: `react-router`/`react-router-dom` and `js-yaml`
    are real `dependencies` (`app/package.json`), shipped in the built
    application bundle -- `--omit=dev` is what makes this step fail on
    exactly that shipped surface, the one that went unaudited
    longest."""
    assert "npm audit --omit=dev" in _APP_LANE


def test_the_app_lane_surfaces_development_findings_without_blocking() -> None:
    """The 19 findings that are `devDependencies`-only (eslint,
    typescript-eslint, `@babel/core`, the autoprefixer/postcss/tailwindcss
    chain) never reach any built output, but a finding
    nothing ever surfaces is just as much the D-25 shape as a check that
    cannot fail: this step is not the gate, but it must exist, run the
    *full* audit (no `--omit=dev`, or it would just repeat the production
    step above and never show a dev-only finding at all), and be marked
    `continue-on-error` so it cannot itself fail the job."""
    lines = _APP_LANE.splitlines()
    audit_lines = [i for i, line in enumerate(lines) if "run: npm audit" in line]
    assert len(audit_lines) == 2, (
        "expected exactly two `npm audit` invocations in the app lane "
        "-- one production gate, one informational full audit"
    )
    full_audit_line = [i for i in audit_lines if lines[i].strip() == "run: npm audit"]
    assert full_audit_line, (
        "no bare `npm audit` (full, no --omit) step found in the "
        "app lane -- the informational step must run the full "
        "audit, not repeat the production-only one"
    )
    # The step's own preceding lines (name: / continue-on-error: /
    # working-directory:) must carry the informational marker -- a step
    # that runs the full audit but is not marked `continue-on-error`
    # would silently become a second blocking gate on findings this
    # policy deliberately does not block on.
    preceding = "\n".join(lines[max(0, full_audit_line[0] - 4) : full_audit_line[0]])
    assert "continue-on-error: true" in preceding


def test_the_app_lanes_two_audit_steps_are_not_the_same_step() -> None:
    """The production gate must not itself be marked `continue-on-error`
    -- that would silently turn the one check that has to block
    into another step nothing can fail."""
    omit_dev_index = _APP_LANE.index("npm audit --omit=dev")
    preceding = _APP_LANE[max(0, omit_dev_index - 200) : omit_dev_index]
    assert "continue-on-error" not in preceding


def test_relay_jobs_have_no_production_dependencies_to_omit() -> None:
    """The premise behind choosing a full, unqualified `npm audit` for
    every relay lane below rather than the `app/`-style split: none of
    these three services declares a `dependencies` key at all (each
    `package.json` carries only `devDependencies` -- `vitest` and
    `wrangler`), so `--omit=dev` would exempt their entire tree and pass
    vacuously. If a relay ever gains a real runtime dependency, this
    assertion is the thing that must fail first, forcing a real decision
    about that service's own gate rather than a silent one."""
    for service in ("auth-proxy", "form-relay", "signup-relay"):
        package_json = (_ROOT / "services" / service / "package.json").read_text(
            encoding="utf-8"
        )
        assert '"dependencies"' not in package_json, (
            f"services/{service}/package.json now declares a "
            "`dependencies` key -- the reasoning for auditing this "
            "service with a bare `npm audit` (D-25, no --omit=dev) "
            "assumed there was nothing to omit; revisit that job's "
            "own audit step now that this is no longer true"
        )


def test_the_relay_lanes_audit_their_whole_dependency_tree() -> None:
    """Each relay lane runs the same full audit `site/`'s own step already
    does, and never `--omit=dev` -- the identical reasoning
    `test_performance_workflow.py::test_the_workflow_audits_site_dependencies`
    pins for `site/` applies here for the same cause (see
    `test_relay_jobs_have_no_production_dependencies_to_omit` above)."""
    for name, lane in (
        ("auth-proxy", _AUTH_PROXY_LANE),
        ("form-relay", _FORM_RELAY_LANE),
        ("signup-relay", _SIGNUP_RELAY_LANE),
    ):
        audit_run_lines = [
            line for line in lane.splitlines() if line.strip() == "run: npm audit"
        ]
        assert audit_run_lines, f"{name} lane has no bare `npm audit` step"
        assert len(audit_run_lines) == 1, (
            f"{name} lane has more than one bare `npm audit` step"
        )


def test_the_relay_audit_step_runs_before_the_test_step() -> None:
    """A dependency audit that ran after the tests would still leave a
    broken build merged if the audit step were ever accidentally ordered
    last and someone stopped reading past the first failure -- ordered
    the same way `site/`'s own lane already runs its audit before its
    build, this keeps the cheapest, most actionable check first."""
    for name, lane in (
        ("auth-proxy", _AUTH_PROXY_LANE),
        ("form-relay", _FORM_RELAY_LANE),
        ("signup-relay", _SIGNUP_RELAY_LANE),
    ):
        audit_pos = lane.index("run: npm audit")
        test_pos = lane.index("run: npm test")
        assert audit_pos < test_pos, f"{name} lane audits after it tests"


def test_app_production_dependencies_that_were_the_finding_are_still_declared() -> None:
    """`react-router-dom` and `js-yaml` must stay real `dependencies` --
    the fact that made the finding real (they ship in the
    built cockpit bundle) rather than academic. This does not pin a
    version (the fix was a lockfile-only bump within the existing caret
    ranges, not a package.json edit); a floating range
    drifting back to a vulnerable version is exactly what the CI audit
    step above exists to catch on every push, not something a static
    text match on a version string could ever guarantee."""
    assert '"react-router-dom"' in _APP_PACKAGE_JSON
    assert '"js-yaml"' in _APP_PACKAGE_JSON
