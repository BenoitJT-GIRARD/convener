#!/bin/sh
# Every gate `.github/workflows/quality.yml` runs, one target each, and
# `all` for the lot in the order that workflow runs them.
#
#     sh gates.sh            # every gate
#     sh gates.sh types      # just mypy
#
# Dispatch and nothing else. Each line below is the command
# `docs/operating/publishing-the-product.md` already told a reader to type,
# from the directory it already told them to type it in, so a gate that
# passes here passes there and the two cannot drift into different checks.
# The installs are not here: they are three commands run once per tree
# (`npm ci` in `app/` and `site/`, `uv sync --all-extras` in `tools/`),
# ordered for a reason that page states, and a runner that hid them behind
# a target would invite running the gates before them.
#
# `--frozen` on every `uv run`: an unfrozen one rewrites `tools/uv.lock`,
# which is a change to the environment made by the act of checking it.
#
# The claim, and what holds it
# ----------------------------
# The first line above used to read "every gate this repository is held
# to". It was false, and had been for a long time: eight targets stood
# against twenty-eight of `quality.yml`'s own checks, so the six
# generators' `--check`, the decision register, the commit-message check,
# the security scan, the dependency audits of all seven trees, both
# lint runs outside `tools/`, the application's own types, the
# performance budget and the relays' lint were all things a maintainer
# believed `sh gates.sh` had run. A gate you think you ran and did not is
# worse than one you know is missing.
#
# The claim is now bounded to one workflow and `tools/tests/repository/test_gates.py`
# holds it: it reads every named step out of `quality.yml`, reads the
# table below, and fails when either one carries a step the other does
# not. Adding a step there without a line here is a red suite, and so is
# a target here that no longer runs anything.
#
# What `quality.yml` runs, and the target that runs it
# ----------------------------------------------------
# One line per named step, in the workflow's own order. `Install ...` is
# not in the table for the reason the header gives; every other step is,
# and `none` is a statement rather than an omission.
#
#   Lint -> lint
#   Format check -> lint
#   Types -> types
#   Security patterns -> security
#   Dependency audit -> audit
#   Tests -> tests
#   Integration status -> integrations
#   Commit messages -> commits
#   Decision register -> generated
#   Schema appendix -> generated
#   Standing-up guide -> generated
#   Standing-up run sheet -> generated
#   Brand tokens and templates -> generated
#   Chrome motif -> generated
#   Directory map -> generated
#   Rule index -> generated
#   Changelog -> generated
#   Dependency audit (production) -> audit
#   Dependency audit (development tooling, informational) -> none
#   Lint app -> app
#   Types app -> app
#   Tests and coverage app -> app
#   Lint site -> site
#   Dependency audit site -> audit
#   Build -> site
#   Build app -> app
#   Performance budget -> budget
#   Spell check (en-GB) -> spelling
#   Dependency audit auth-proxy -> audit
#   Lint auth-proxy -> relays
#   Test auth-proxy -> relays
#   Dependency audit form-relay -> audit
#   Lint form-relay -> relays
#   Test form-relay -> relays
#   Dependency audit signup-relay -> audit
#   Lint signup-relay -> relays
#   Test signup-relay -> relays
#   Validate workflows against GitHub's schema -> workflows
#
# The one `none`, and why. `Dependency audit (development tooling,
# informational)` carries `continue-on-error: true` -- that step reports
# the findings in `app/`'s own `devDependencies` and cannot fail the job,
# deliberately, for the reason written beside it in `quality.yml`. A
# target here would fail a run that continuous integration passes, which
# is the opposite of mirroring it. The findings it prints are the ones
# `audit`'s own `npm audit --omit=dev` leaves out by design.
#
# Two places where the same check is not the same command
# -------------------------------------------------------
# `audit` runs the dependency audits of all seven trees together, at the
# position `quality.yml` runs the first of them, rather than four
# fragments scattered through the order. That is the one departure from
# "the order that workflow runs them", and it is deliberate: an audit
# reads an advisory database rather than this repository, so the seven
# belong to each other and not to the lanes they sit in --
# `.github/dependabot.yml`'s own header already treats them as one family.
#
# `workflows` passes `-shellcheck= -pyflakes=`, and `quality.yml` runs a
# bare `./actionlint`. A GitHub runner has both of those on its `PATH` and
# `actionlint` uses them when it finds them; a maintainer's machine
# usually has neither, and an `actionlint` that silently checked less
# would be worse than one that says which two checks it is not making.
# So this is the one gate that is deliberately weaker here than there.
#
# Every Python tool is run as a module of the environment's own
# interpreter (`python -m mypy`), never through the launcher `uv` puts in
# `tools/.venv/`. Two reasons, and neither is this machine's:
# `publishing-the-product.md` already warns that a console-script launcher
# embeds an absolute interpreter path, so a copied environment goes on
# checking the tree it came from; and a launcher is an executable, which
# an application-control policy can refuse -- one does, on the
# maintainer's own machine, for `mypy` and `pytest` (`os error 4551`),
# which is how long this runner had two targets that could not run at all.
# This project's own `convener-*` commands have no module form and stay as
# they are.
#
# What is not here at all
# -----------------------
# Four checks of this repository run in workflows of their own, and none
# of them is a target here: `check-a11y` (`a11y.yml`), `render-and-compare`
# (`visuals.yml`), `check-templates` (`templates.yml`) and `check-posters`
# (`visuals-production.yml`). Each needs a browser binary and a pinned
# rendering environment -- `CHROME_PATH`, and a real `npm run build` of
# `app/` beneath it -- so a target for one would fail on a machine that
# never set those, for a reason that is not a defect in anything. That is
# exactly the failure this file exists to stop being possible: a gate
# whose red says nothing. They are run through the pages that already
# describe them, and the table above says nothing about them because this
# runner's claim is `quality.yml` and no more.
set -e
cd "$(dirname "$0")"
case "${1:-all}" in
  lint)      cd tools && uv run --frozen python -m ruff check . && uv run --frozen python -m ruff format --check . ;;
  types)     cd tools && uv run --frozen python -m mypy ;;
  security)  cd tools && uv run --frozen python -m bandit -q -r convener_ops ;;
  audit)     (cd tools && uv run --frozen python -m pip_audit)
             (cd app && npm audit --omit=dev)
             (cd site && npm audit)
             for r in auth-proxy form-relay signup-relay; do (cd "services/$r" && npm audit); done ;;
  tests)     cd tools && uv run --frozen python -m pytest --cov=convener_ops --cov-report=term-missing ;;
  integrations) cd tools && uv run --frozen convener-check-config ;;
  commits)   range="$(cd tools && uv run --frozen convener-commit-range)"
             # Unquoted on purpose, the way `quality.yml` spells it: the
             # range is either one token (`start..head`) or two
             # (`-1 head`), and quoting would hand `git log` one bad
             # revision instead of two arguments. See `commit_format`.
             # shellcheck disable=SC2086
             git log --format=%B%x00 $range | (cd tools && uv run --frozen convener-check-commits) ;;
  generated) cd tools && uv run --frozen convener-register --check \
               && uv run --frozen python scripts/generate_schema_doc.py --check \
               && uv run --frozen python scripts/generate_standing_up_doc.py --check \
               && uv run --frozen python scripts/generate_standing_up_run_sheet.py --check \
               && uv run --frozen python scripts/generate_brand_css.py --check \
               && uv run --frozen python scripts/generate_motif.py --check \
               && uv run --frozen python scripts/generate_directory_map.py --check \
               && uv run --frozen python scripts/generate_rule_index.py --check \
               && uv run --frozen python scripts/generate_changelog.py --check ;;
  app)       cd app && npm run lint && npm run typecheck && npm run test:cov && npm run build ;;
  site)      cd site && npx --yes eslint@9 .eleventy.js scripts/check-a11y.mjs scripts/check-performance-budget.mjs scripts/check-paris-standing-start.cjs scripts/published.cjs scripts/print-published.cjs && npm run build ;;
  budget)    cd site && npm run check:budget -- --app-dir ../app/dist ;;
  spelling)  npx --yes cspell@8 lint --no-progress ;;
  relays)    for r in auth-proxy form-relay signup-relay; do (cd "services/$r" && npx --yes eslint@9 src test && npm test); done ;;
  workflows) actionlint -shellcheck= -pyflakes= .github/workflows/*.yml ;;
  all)       for gate in lint types security audit tests integrations commits generated app site budget spelling relays workflows; do sh "$0" "$gate"; done ;;
  *) echo "usage: sh $0 [lint|types|security|audit|tests|integrations|commits|generated|app|site|budget|spelling|relays|workflows|all]" >&2; exit 2 ;;
esac
