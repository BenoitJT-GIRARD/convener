"""Fix round 1 (task 12 follow-up): task 12 wired a dependency audit into
`.github/workflows/quality.yml`'s `site` job only. `site/` was the surface
that happened to pass -- `app/`'s own tree was never audited at all, and
it is the larger one: `react-router`/`react-router-dom` and `js-yaml` are
`app/package.json` `dependencies`, not `devDependencies`, so they ship in
the built application bundle the operators' cockpit serves at
`/example-showcase/app/` behind its login screen, and the three relay services
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
fix -- is this task's own report, not this module: see
`.superpowers/sdd/2026-08-22-phase-5-vitrine-publique/task-12-report.md`,
"Fix round 1", for the exact commands and the exact findings each printed.
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
    `test_performance_workflow.py::_SITE_JOB` and
    `test_a11y_workflow.py` already use -- a workflow-wide `in` check
    could match a different job entirely, including the one this module
    exists to tell apart from the one it replaced (`typescript` carries
    two audit steps now; a check that did not isolate the job could
    silently pass by matching the *other* one)."""
    start = _WORKFLOW.split(f"\n  {name}:\n", 1)[1]
    if next_job is None:
        return start
    return start.split(f"\n  {next_job}:\n", 1)[0]


_TYPESCRIPT_JOB = _job("typescript", "site")
_AUTH_PROXY_JOB = _job("auth-proxy", "form-relay")
_FORM_RELAY_JOB = _job("form-relay", "signup-relay")
_SIGNUP_RELAY_JOB = _job("signup-relay", None)


def test_the_typescript_job_is_isolated_correctly() -> None:
    """A probe on the slicing above itself, the same self-check
    `test_performance_workflow.py::test_the_site_job_is_isolated_correctly`
    already runs for its own slice: if either marker moves, every other
    test in this module would silently start reading the wrong slice
    rather than failing here with a clear reason."""
    assert "working-directory: app" in _TYPESCRIPT_JOB
    assert "npm run typecheck" in _TYPESCRIPT_JOB


def test_the_typescript_job_audits_production_dependencies() -> None:
    """The blocking gate: `react-router`/`react-router-dom` and `js-yaml`
    are real `dependencies` (`app/package.json`), shipped in the built
    application bundle -- `--omit=dev` is what makes this step fail on
    exactly that shipped surface, the one this fix round found unaudited
    and fixed (see the report)."""
    assert "npm audit --omit=dev" in _TYPESCRIPT_JOB


def test_the_typescript_job_surfaces_development_findings_without_blocking() -> None:
    """The 19 findings that are `devDependencies`-only (eslint,
    typescript-eslint, `@babel/core`, the autoprefixer/postcss/tailwindcss
    chain -- see the report) never reach any built output, but a finding
    nothing ever surfaces is just as much the D-25 shape as a check that
    cannot fail: this step is not the gate, but it must exist, run the
    *full* audit (no `--omit=dev`, or it would just repeat the production
    step above and never show a dev-only finding at all), and be marked
    `continue-on-error` so it cannot itself fail the job."""
    lines = _TYPESCRIPT_JOB.splitlines()
    audit_lines = [i for i, line in enumerate(lines) if "run: npm audit" in line]
    assert len(audit_lines) == 2, (
        "expected exactly two `npm audit` invocations in the typescript "
        "job -- one production gate, one informational full audit"
    )
    full_audit_line = [i for i in audit_lines if lines[i].strip() == "run: npm audit"]
    assert full_audit_line, (
        "no bare `npm audit` (full, no --omit) step found in the "
        "typescript job -- the informational step must run the full "
        "audit, not repeat the production-only one"
    )
    # The step's own preceding lines (name: / continue-on-error: /
    # working-directory:) must carry the informational marker -- a step
    # that runs the full audit but is not marked `continue-on-error`
    # would silently become a second blocking gate on findings this
    # policy deliberately does not block on.
    preceding = "\n".join(lines[max(0, full_audit_line[0] - 4) : full_audit_line[0]])
    assert "continue-on-error: true" in preceding


def test_the_typescript_jobs_two_audit_steps_are_not_the_same_step() -> None:
    """The production gate must not itself be marked `continue-on-error`
    -- that would silently turn the one check this fix round exists to
    make block into another step nothing can fail."""
    omit_dev_index = _TYPESCRIPT_JOB.index("npm audit --omit=dev")
    preceding = _TYPESCRIPT_JOB[max(0, omit_dev_index - 200) : omit_dev_index]
    assert "continue-on-error" not in preceding


def test_relay_jobs_have_no_production_dependencies_to_omit() -> None:
    """The premise behind choosing a full, unqualified `npm audit` for
    every relay job below rather than the `app/`-style split: none of
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


def test_the_relay_jobs_audit_their_whole_dependency_tree() -> None:
    """Each relay job runs the same full audit `site/`'s own step already
    does, and never `--omit=dev` -- the identical reasoning
    `test_performance_workflow.py::test_the_workflow_audits_site_dependencies`
    pins for `site/` applies here for the same cause (see
    `test_relay_jobs_have_no_production_dependencies_to_omit` above)."""
    for name, job in (
        ("auth-proxy", _AUTH_PROXY_JOB),
        ("form-relay", _FORM_RELAY_JOB),
        ("signup-relay", _SIGNUP_RELAY_JOB),
    ):
        audit_run_lines = [
            line for line in job.splitlines() if line.strip() == "run: npm audit"
        ]
        assert audit_run_lines, f"{name} job has no bare `npm audit` step"
        assert len(audit_run_lines) == 1, (
            f"{name} job has more than one bare `npm audit` step"
        )


def test_the_relay_audit_step_runs_before_the_test_step() -> None:
    """A dependency audit that ran after the tests would still leave a
    broken build merged if the audit step were ever accidentally ordered
    last and someone stopped reading past the first failure -- ordered
    the same way `site/`'s own job already runs its audit before its
    build, this keeps the cheapest, most actionable check first."""
    for name, job in (
        ("auth-proxy", _AUTH_PROXY_JOB),
        ("form-relay", _FORM_RELAY_JOB),
        ("signup-relay", _SIGNUP_RELAY_JOB),
    ):
        audit_pos = job.index("run: npm audit")
        test_pos = job.index("run: npm test")
        assert audit_pos < test_pos, f"{name} job audits after it tests"


def test_app_production_dependencies_that_were_the_finding_are_still_declared() -> None:
    """`react-router-dom` and `js-yaml` must stay real `dependencies` --
    the fact that made this fix round's finding real (they ship in the
    built cockpit bundle) rather than academic. This does not pin a
    version (the fix was a lockfile-only bump within the existing caret
    ranges, not a package.json edit -- see the report); a floating range
    drifting back to a vulnerable version is exactly what the CI audit
    step above exists to catch on every push, not something a static
    text match on a version string could ever guarantee."""
    assert '"react-router-dom"' in _APP_PACKAGE_JSON
    assert '"js-yaml"' in _APP_PACKAGE_JSON
