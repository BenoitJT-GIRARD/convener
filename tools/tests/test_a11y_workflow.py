"""Pins `.github/workflows/a11y.yml` and
`site/scripts/check-a11y.mjs` against the properties a green run does not,
by itself, prove. A green accessibility job proves nothing on its own;
these are the checks that make it mean something.

Three things a passing job could still be wrong about, each with its own
test below:

* it could be pointed at the wrong address -- checked at a bare
  `localhost` root rather than the path prefix GitHub Pages actually
  serves this project under (D-26);
* it could be looking at a handful of pages rather than everything the
  site generates -- a hand-typed URL list would pass forever even after a
  page nobody added to it stopped being checked;
* it could report the two islands (the registration form, the
  certificate-verification panel) as empty and pass for the wrong reason
  -- exactly the "control that cannot fail loudly" D-25 names.

Read as text and asserted against with `in`/regex checks, the same idiom
`test_workflows.py` and `test_registration_workflow.py` already use for
every other workflow file in this project -- never parsed and executed,
which would mean a real GitHub Actions runner and a real browser, exactly
the network access this suite must not take on. Running the checker for
real -- building `site/` and `app/`, launching Chrome, rendering every
page -- is `site/scripts/check-a11y.mjs`'s own job, exercised by hand,
not by this module.
"""

from __future__ import annotations

import re

from convener_ops.paths import repo_root

_ROOT = repo_root()
_WORKFLOW = (_ROOT / ".github" / "workflows" / "a11y.yml").read_text(encoding="utf-8")
_CHECKER = (_ROOT / "site" / "scripts" / "check-a11y.mjs").read_text(encoding="utf-8")
_PACKAGE_JSON = (_ROOT / "site" / "package.json").read_text(encoding="utf-8")


def test_the_checker_reads_the_path_prefix_from_its_one_source() -> None:
    """D-26: "on vérifie à la forme déployée, jamais à une forme locale
    commode." `config/instance.json` is the one place this project's
    published address is written down -- a second, hand-typed prefix here
    could drift from it exactly the way the site's own templates once
    could. This checker's own regular expression
    over `.eleventy.js` gave way to the same reader the build itself uses, so
    what is asserted here is that the checker asks the declaration rather
    than any intermediary. That the value actually agrees is
    `test_published.py`'s own job, from a real run of both.
    """
    assert "from './published.cjs'" in _CHECKER, (
        "check-a11y.mjs no longer reads the published address through "
        "site/scripts/published.cjs -- it must derive the served prefix from "
        "config/instance.json, never restate it"
    )
    assert "publishedAddress().pathPrefix" in _CHECKER


def test_the_checker_discovers_pages_by_walking_the_build_not_a_fixed_list() -> None:
    """ "A checker pointed at a stale directory, an empty build, or one
    page out of fourteen will pass forever" -- the defence against that
    is a recursive directory walk over the real build output, never a
    hand-typed array of routes that a fifteenth page could silently fall
    outside of.
    """
    assert "async function discoverHtmlPages" in _CHECKER
    assert "readdir" in _CHECKER
    # A hand-typed route list would look like an array of string literals
    # passed straight to page.goto -- there is exactly one array literal
    # of viewport objects in this file (desktop/mobile), and it is not a
    # page list.
    assert re.search(r"\[\s*'/events/", _CHECKER) is None
    assert re.search(r"\[\s*'/'", _CHECKER) is None


def test_the_checker_computes_its_expected_page_count_from_the_fixture() -> None:
    """The page count this checker demands a match against is derived
    from `events.json` at run time (`expectedPageCount`), not a bare `14`
    that would silently stop matching reality the day a sixth event or a
    third archive year is added -- proven, not merely argued for.
    """
    assert "function expectedPageCount(events)" in _CHECKER
    assert "htmlFiles.length !== expected" in _CHECKER
    # The guard must actually stop the run, not just log a mismatch --
    # D-25's "a control that cannot fail loudly is not a control".
    body = _CHECKER.split("if (htmlFiles.length !== expected)")[1].split("}", 1)[0]
    assert "throw new Error" in body


def test_the_checker_refuses_an_empty_island_mount_point() -> None:
    """D-25, applied to the one failure mode a static-HTML sweep cannot
    even see: a checker that never executes the islands' own JavaScript
    would find `#registration-form` and `#verify-app` empty and call that
    a pass. This asserts the emptiness check exists and that it can
    actually fail the run, not merely warn.
    """
    assert "registration-form" in _CHECKER
    assert "verify-app" in _CHECKER
    assert "emptyIslands.length > 0" in _CHECKER
    # The final exit-code decision must name emptyIslands, not only
    # violations -- an empty island with zero axe violations (nothing to
    # find any rule against) must still fail the build.
    exit_decision = _CHECKER.split("process.exitCode = 1")[0][-400:]
    assert "emptyIslands.length > 0" in exit_decision


def test_incomplete_results_are_reviewed_by_name_never_suppressed_wholesale() -> None:
    """ "If a tool reports something you judge to be a false positive, say
    so with the measurement, and suppress it named and justified, never
    wholesale." This checker keeps a named allow-list of specific,
    reviewed axe nodes (`REVIEWED_INCOMPLETE_NODES`) rather than treating
    every `incomplete` result as a mere warning -- an unfamiliar
    incomplete result must still fail the build.
    """
    assert "REVIEWED_INCOMPLETE_NODES" in _CHECKER
    assert "unreviewedIncompleteByPage.length > 0" in _CHECKER
    exit_decision = _CHECKER.split("process.exitCode = 1")[0][-400:]
    assert "unreviewedIncompleteByPage.length > 0" in exit_decision


def test_the_reviewed_allow_list_is_scoped_by_element_not_only_by_message_key() -> None:
    """A review found that `REVIEWED_INCOMPLETE_NODES`'s predecessor
    (`REVIEWED_INCOMPLETE_MESSAGE_KEYS`) matched on axe's `messageKey`
    alone -- the generic *reason* color-contrast gave up on a node, never
    the node itself. Reproduced by hand: a deliberately broken,
    never-measured `::before`-painted pairing (~1.07:1) reports the
    identical `messageKey` (`pseudoContent`) as the three legitimately
    reviewed pairings, and the old allow-list waved it through, silently,
    forever. This pins the fix -- matching must require the CSS selector
    axe resolved the node to as well, so a new element sharing only the
    *shape* of a reviewed one still fails until a human measures it.
    """
    assert "REVIEWED_INCOMPLETE_MESSAGE_KEYS" not in _CHECKER, (
        "the selector-blind allow-list must not come back under its old name"
    )
    assert "function isReviewedIncomplete(" in _CHECKER
    body = _CHECKER.split("function isReviewedIncomplete(", 1)[1].split(
        "\nfunction ", 1
    )[0]
    # The match must read the node's own selector, not just its
    # messageKey: a messageKey alone would wave through a different node.
    assert "node.target" in body
    assert "entry.selector" in body
    assert "entry.messageKey" in body


def test_heading_order_is_opted_in_by_rule_not_by_the_whole_best_practice_tag() -> None:
    """axe-core classifies `heading-order` as `best-practice`, never a
    `wcag2a`/`wcag2aa`/`wcag21aa` rule (confirmed against the installed
    axe-core package, not assumed) -- a plain tag-based `runOnly` would
    silently never run it. This project opts that one rule in by name
    rather than pulling in the rest of `best-practice`, which would blur
    "not AA" with "a maintainer's taste".
    """
    assert "'heading-order'" in _CHECKER
    assert "type: 'rule'" in _CHECKER
    # The whole best-practice category must never be pulled in wholesale --
    # as a quoted tag value, not merely absent from prose (this file's own
    # module comment explains the exclusion using the same word).
    assert "'best-practice'" not in _CHECKER


def test_puppeteer_core_not_the_full_package_that_bundles_a_chromium_download() -> None:
    """Zero cost, by construction: `puppeteer-core` is a thin remote-control
    client with no bundled browser of its own, unlike `puppeteer`, whose
    install step downloads a full Chromium build from a third party. This
    project never needs that download -- `.github/workflows/a11y.yml`
    locates an already-installed browser instead (see the next test).
    """
    assert '"puppeteer-core"' in _PACKAGE_JSON
    assert '"puppeteer"' not in _PACKAGE_JSON.replace('"puppeteer-core"', "")


def test_the_workflow_locates_an_installed_browser_rather_than_downloading_one() -> (
    None
):
    """`ubuntu-latest` ships Google Chrome preinstalled -- this job must
    only ever locate it (`command -v`), never invoke a browser-download
    action or set an environment variable that would let `puppeteer-core`
    fetch one of its own. A missing browser must fail the step loudly
    (D-25), not fall back silently.
    """
    assert "command -v google-chrome" in _WORKFLOW
    assert "CHROME_PATH" in _WORKFLOW
    for forbidden in ("browser-actions/setup-chrome", "PUPPETEER_"):
        assert forbidden not in _WORKFLOW, (
            f"{forbidden!r} found in a11y.yml -- this job must locate an "
            "already-installed browser, never download one"
        )


def test_the_workflow_builds_both_the_site_and_the_app() -> None:
    """D-26's own consequence here: the two islands live in the
    app's build, not the site's, so a checker that only ever built
    `site/` could never reach `ready` state for the registration form or
    render the verify island's real markup at all -- both would be
    checked as permanently empty, exactly the "cannot fail loudly"
    shape D-25 refuses.
    """
    for working_directory in ("site", "app"):
        marker = f"working-directory: {working_directory}"
        assert marker in _WORKFLOW, (
            f"a11y.yml never runs a step in {working_directory}/"
        )
        section = _WORKFLOW.split(marker, 1)[1][:200]
        assert "npm run build" in section or "npm ci" in section


def test_the_workflow_generates_event_keys_before_building_the_app() -> None:
    """Without a usable event key, `SignupForm.tsx` never reaches its
    `ready` state, so its real `<input>`/`<label>` markup -- the one
    thing a label regression could break -- would never be rendered for
    axe to see at all. This asserts the workflow generates one (never a
    committed key: `eventkeys.py`'s own module docstring is explicit that
    a private half must never touch disk outside a CI job either) *before*
    the app is built, not after.
    """
    assert "eventkeys.generate()" in _WORKFLOW
    key_step = _WORKFLOW.index("Generate throw-away event keys")
    app_build_step = _WORKFLOW.index("Build app")
    assert key_step < app_build_step


def test_the_workflow_never_pushes_or_writes_repository_state() -> None:
    """This job only ever reads: `permissions: contents: read`, and no
    step commits or pushes anything -- the throw-away event keys it
    generates must never reach a commit, since a *real* one is exactly
    the secret `eventkeys.py`'s own module docstring says must never
    touch disk outside a job that holds the matching private half under
    a repository secret, which this job never does.
    """
    assert "contents: read" in _WORKFLOW
    for forbidden in (
        "git push",
        "git commit",
        "actions-bot",
        "secrets.VITRINE_DEPLOY_TOKEN",
    ):
        assert forbidden not in _WORKFLOW
