"""Pins `.github/workflows/quality.yml`'s own `site` lane
and `site/scripts/check-performance-budget.mjs` against the properties a
green run does not, by itself, prove. A budget verified automatically only
means something if the check that enforces it can actually turn red.

Three things a passing job could still be wrong about, each with its own
test below (the identical three-part shape
`tests/repository/test_a11y_workflow.py`'s own module docstring names for the
accessibility checker):

* it could be weighing a stale, partial, or empty build rather than the
  real one -- checked by pinning the page-count guard, the same defence
  `check-a11y.mjs` already uses;
* it could be silently under-counting a page's real weight by resolving a
  resource reference against the wrong address, or not noticing one that
  is missing this project's own published prefix (D-26);
* it could be a budget nobody could ever breach -- D-25's "a control that
  cannot fail loudly is not a control" -- proved by hand once and pinned
  structurally by the tests below, so a
  future edit cannot quietly turn the ceiling into a floor high enough to
  never matter.

Read as text and asserted against with `in`/regex checks, the same idiom
`test_a11y_workflow.py` and `test_workflows.py` already use for every
workflow file and JavaScript checker in this project -- never parsed and
executed, which here would also mean a real `npm ci` and a real build,
exactly the network access and runtime this suite must not take on.
Running the checker for real -- against the actual built `site/_site` and
`app/dist` -- is `site/scripts/check-performance-budget.mjs`'s own job,
exercised by hand, not by this module.
"""

from __future__ import annotations

from convener_ops.declaration.paths import repo_root

_ROOT = repo_root()
_WORKFLOW = (_ROOT / ".github" / "workflows" / "quality.yml").read_text(
    encoding="utf-8"
)
_CHECKER = (_ROOT / "site" / "scripts" / "check-performance-budget.mjs").read_text(
    encoding="utf-8"
)
_PACKAGE_JSON = (_ROOT / "site" / "package.json").read_text(encoding="utf-8")

# quality.yml carries several jobs, and one of them
# carries several lanes: what were the `typescript`, `site` and
# `spelling` jobs are three lanes of one `web` job (eight billed jobs
# grouped into four, no check dropped -- see quality.yml's own header).
# Every assertion below that reads "the site lane" means exactly this
# slice -- the same isolation `test_register.py`'s own `python_job`
# already uses for a different job in this identical file, and for the
# identical reason (a workflow-wide `in` check could match a different
# surface entirely; `--omit=dev` now lives one lane above this one).
#
# The lane opens at its own `Install site` step -- the step whose `id:`
# every check in the lane guards on in the workflow itself -- and ends
# where the spelling lane begins. `Build app` sits inside it on purpose:
# the performance budget weighs `app/`'s real island bundles, so the
# build that produces them belongs to the lane that reads them, while
# the `npm ci` that used to accompany it is now the `web` job's single
# app install, one lane above.
_WEB_JOB = _WORKFLOW.split("\n  web:\n", 1)[1].split("\n  relays:\n", 1)[0]
_SITE_LANE = _WEB_JOB.split("- name: Install site\n", 1)[1].split(
    "- name: Spell check", 1
)[0]


def test_the_site_lane_is_isolated_correctly() -> None:
    """A probe on the slicing above itself: if either marker ever moves
    (a job or a step renamed, a lane reordered, a new lane inserted
    between the site one and the spelling one), every other test in this
    module would silently start reading the wrong slice rather than
    failing here with a clear reason."""
    assert "working-directory: site" in _SITE_LANE
    assert "npm run build" in _SITE_LANE


def test_the_checker_reads_the_path_prefix_from_its_one_source() -> None:
    """D-26: never a second, hand-typed prefix that could drift from
    `instance/config.json` -- the identical property
    `test_a11y_workflow.py::test_the_checker_reads_the_path_prefix_from_
    its_one_source` already pins for the accessibility checker.
    """
    assert "from './published.cjs'" in _CHECKER, (
        "check-performance-budget.mjs no longer reads the published address "
        "through site/scripts/published.cjs -- it must derive the served "
        "prefix from instance/config.json, never restate it"
    )
    assert "publishedAddress().pathPrefix" in _CHECKER


def test_the_checker_discovers_pages_by_walking_the_build_not_a_fixed_list() -> None:
    """The same defence `test_a11y_workflow.py`'s own analogous test
    names: a recursive directory walk over the real build, never a
    hand-typed array of routes a future page could fall outside of."""
    assert "async function discoverHtmlPages" in _CHECKER
    assert "readdir" in _CHECKER


def test_the_checker_computes_its_expected_page_count_from_the_fixture() -> None:
    """The page count this checker demands a match against is derived
    from `events.json` at run time, not a bare `14` that would silently
    stop matching reality the day a sixth event or a third archive year
    is added -- and the mismatch must actually stop the run (D-25), not
    merely log it."""
    assert "function expectedPageCount(events)" in _CHECKER
    assert "htmlFiles.length !== expected" in _CHECKER
    body = _CHECKER.split("if (htmlFiles.length !== expected)")[1].split("}", 1)[0]
    assert "throw new Error" in body


def test_the_checker_classifies_a_page_by_what_it_actually_references() -> None:
    """A page's class (static or island) is read from whether its own
    rendered HTML loads a script under `app/islands/` -- never a
    hardcoded page name (`mrg-05`, `/verify/`) that would silently stop
    matching reality the day a different edition starts accepting
    registrations, or a third island is added."""
    assert "/app/islands/" in _CHECKER
    assert "'mrg-05'" not in _CHECKER
    assert '"mrg-05"' not in _CHECKER


def test_the_checker_measures_gzip_transfer_weight_not_raw_disk_weight() -> None:
    """GitHub Pages serves gzip on every compressible response -- a raw
    byte count would be wrong in the direction that flatters this check.
    Both a page's own HTML and every
    resource it references are passed through `gzipSize` before being
    added to its total; only the font payload (already woff2-compressed,
    see the module comment) is compared in raw bytes."""
    assert "function gzipSize(buffer)" in _CHECKER
    assert "zlib.gzipSync" in _CHECKER
    total_line = [
        line
        for line in _CHECKER.splitlines()
        if line.strip().startswith("const totalGzip")
    ]
    assert total_line, "no totalGzip computation found"
    assert "gzipSize(htmlBuffer)" in total_line[0]


def test_the_checker_refuses_a_resource_reference_missing_the_path_prefix() -> None:
    """D-26, applied to this checker's own resolution step: a same-origin
    resource reference that does not carry the configured prefix is
    exactly the class of defect D-26 exists to catch, and would also make
    this budget silently under-count the page it belongs to -- so this
    must throw, never skip the reference."""
    assert "function resolveLocalHref" in _CHECKER
    body = _CHECKER.split("function resolveLocalHref")[1].split("\n}\n", 1)[0]
    assert "throw new Error" in body
    assert "startsWith(prefix)" in body


def test_a_page_over_its_budget_fails_the_run() -> None:
    """D-25: the per-page budget comparison must actually be able to fail
    the job, not merely be printed. `failed` is set from `withinBudget`
    and the run's own exit code is driven by it -- proved by hand once
    (lowering each threshold below a real measurement and watching the
    run exit 1 with the right page named), and this pins the wiring so a
    future
    edit cannot quietly remove the ability to fail while leaving the
    printed numbers looking the same."""
    assert "if (!withinBudget) failed = true;" in _CHECKER
    assert "if (failed) {" in _CHECKER
    exit_block = _CHECKER.split("if (failed) {", 1)[1].split("}", 1)[0]
    assert "process.exitCode = 1" in exit_block


def test_the_font_payload_is_measured_separately_from_the_page_budgets() -> None:
    """D-17: the self-hosted fonts must never be folded into a per-page
    number that could later read, to whoever next sees this job red, as
    "drop the fonts". This asserts the font check is its own comparison
    against its own constant, can independently fail the run, and that
    its own failure message names D-17 and points at what actually
    changed rather than at self-hosting itself."""
    assert "FONT_PAYLOAD_BUDGET_RAW_BYTES" in _CHECKER
    assert "fontBytes <= FONT_PAYLOAD_BUDGET_RAW_BYTES" in _CHECKER
    # A fixed-size window after the marker, not a brace-balanced split:
    # the block's own template literal (`${fontLine}`) contains a `}` of
    # its own that closes the interpolation, not the surrounding `if`, so
    # splitting on the first `}` cuts this slice short before the text it
    # is meant to check.
    font_failure = _CHECKER.split("if (!fontWithinBudget) {", 1)[1][:300]
    assert "failed = true;" in font_failure
    assert "D-17" in font_failure
    assert "do not remove it" in font_failure


def test_the_two_page_budgets_are_measured_independently_of_each_other() -> None:
    """A static page and an island page are different problems -- this
    asserts the two budgets are in fact two
    distinct constants, an island page's budget is the larger of the two
    (it carries a real bundle a static page does not), and neither
    constant is zero, which would make that budget impossible to pass
    rather than impossible to fail (the opposite defect, and just as
    much a "control that proves nothing")."""
    assert "const STATIC_PAGE_BUDGET_GZIP_BYTES = 40 * 1024;" in _CHECKER
    assert "const ISLAND_PAGE_BUDGET_GZIP_BYTES = 110 * 1024;" in _CHECKER


def test_the_workflow_builds_both_the_site_and_the_app() -> None:
    """The island budget needs the app's own built islands
    (`app/dist/islands/signup/signup.js`, `.../verify/verify.js`) -- a
    lane that only ever built `site/` could never weigh either page
    carrying one, and `--app-dir` would have nothing real to point at.

    This lane's job was merged with the one that installs
    `app/`; the install moved, the build did not, and this assertion is
    what would fail if a future tidy-up moved the build out of the lane
    that reads its output."""
    for working_directory in ("site", "app"):
        marker = f"working-directory: {working_directory}"
        assert marker in _SITE_LANE, (
            f"the site lane never runs a step in {working_directory}/"
        )


def test_the_workflow_runs_the_budget_check_against_the_apps_real_build() -> None:
    """The check must run `npm run check:budget` and must point it at the
    app's own build output -- omitting `--app-dir` would make the script
    itself refuse to run (see `parseArgs`'s own required-argument check),
    but a hand-typed path drifting from where the "Build app" step above
    actually writes would silently point this check at nothing."""
    assert "npm run check:budget" in _SITE_LANE
    assert "--app-dir ../app/dist" in _SITE_LANE


def test_the_workflow_lints_the_new_checker_script() -> None:
    """A script this project ships in `site/scripts/` must be linted like
    `check-a11y.mjs` already is -- an unlisted file is invisible to the
    one lint command this job runs, `npx --yes eslint@9 ...`, no matter
    how strict `site/eslint.config.js`'s own rules are."""
    assert "check-performance-budget.mjs" in _SITE_LANE
    lint_line = [line for line in _SITE_LANE.splitlines() if "eslint@9" in line]
    assert lint_line, "no eslint invocation found in the site lane"
    assert "check-performance-budget.mjs" in lint_line[0]
    assert "check-a11y.mjs" in lint_line[0]


def test_the_workflow_audits_site_dependencies() -> None:
    """The quality chain holds Python to `pip-audit` (this same
    workflow's `python` job); `site/`'s own dependencies went unaudited
    until this step existed. `npm audit` with no flags added -- never
    `--omit=dev`, which would exempt every dependency this package
    declares (all of them are `devDependencies`: Eleventy, axe-core,
    puppeteer-core, all build-time tooling) and make the step pass
    vacuously regardless of what it found (D-25)."""
    assert "npm audit" in _SITE_LANE
    assert "--omit=dev" not in _SITE_LANE


def test_the_generator_version_is_pinned_exactly() -> None:
    """The generator's version is aligned: the
    declared Eleventy dependency must equal the version actually
    resolved, never a caret range that could silently install a
    different major version on a fresh lock regeneration -- which is
    exactly how the site's own dependency tree was found carrying known
    high-severity vulnerabilities in Eleventy 2's transitive dependencies
    (`markdown-it`/`linkify-it`) with no version bump ever surfacing as a
    diff to review."""
    assert '"@11ty/eleventy": "3.1.6"' in _PACKAGE_JSON, (
        "site/package.json's @11ty/eleventy dependency is no longer an exact "
        "pin at 3.1.6 -- a caret or tilde range here can float across a "
        "major version silently on the next `npm install`"
    )


def test_the_checker_is_zero_cost_no_new_runtime_dependency() -> None:
    """This checker must add no dependency of its own: `zlib` is a Node
    built-in, and every other import is one already used elsewhere in
    this project's own scripts (`node:fs/promises`, `node:path`, ...).
    `site/package.json`'s `devDependencies` must gain nothing beyond what
    the accessibility checker already declared."""
    assert "import zlib from 'node:zlib';" in _CHECKER
    for forbidden in (
        "require(",
        "node-fetch",
        "axios",
        "http.request",
        "https.request",
    ):
        assert forbidden not in _CHECKER
