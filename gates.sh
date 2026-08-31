#!/bin/sh
# Every gate this repository is held to, one target each, and `all` for the
# lot in the order `.github/workflows/quality.yml` runs them.
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
set -e
cd "$(dirname "$0")"
case "${1:-all}" in
  lint)      cd tools && uv run --frozen ruff check . && uv run --frozen ruff format --check . ;;
  types)     cd tools && uv run --frozen mypy ;;
  tests)     cd tools && uv run --frozen pytest ;;
  app)       cd app && npx vitest run ;;
  site)      cd site && npm run build ;;
  relays)    for r in auth-proxy form-relay signup-relay; do (cd "services/$r" && npm test); done ;;
  spelling)  npx --yes cspell@8 lint --no-progress ;;
  workflows) actionlint -shellcheck= -pyflakes= .github/workflows/*.yml ;;
  all)       for gate in lint types tests app site relays spelling workflows; do sh "$0" "$gate"; done ;;
  *) echo "usage: sh $0 [lint|types|tests|app|site|relays|spelling|workflows|all]" >&2; exit 2 ;;
esac
