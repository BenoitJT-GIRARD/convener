# What this instance publishes about itself

Everything this instance publishes about itself, derived from
`instance/data/` by the product's own commands and committed by
`.github/workflows/deploy.yml`. Nothing here is authored: each file is a
projection of the records next door, filtered to what may leave a private
repository, and rewritten in full on every run.

**This directory is empty in a fresh clone, and a fresh duplicate stays in
that state until its first `deploy.yml` run.** `.gitignore` excludes
`instance/public-data/*` and names its exceptions one at a time, so a
projection reaches this directory because somebody decided it should. This
file is one of those exceptions, for the reason
`instance/keys/signing/README.md` is one: a directory that documents its
own contract has to survive holding nothing.

## What lands here

| File | Written by | Read by |
|---|---|---|
| `events-public.json` | `convener-public-data` | the showcase's build, copied to `site/src/_data/events.json` |
| `survey-status.json` | `convener-survey-status-public-data` | `services/signup-relay`, over the GitHub Contents API |
| `registration-routing.json` | `convener-registration-routing-public-data` | `services/signup-relay`, over the same API call shape |
| `certificates-public.json` | `convener-certificates-public-data` | the cockpit's certificate verification page |
| `agenda-internal.ics` | `convener-agenda-internal` | an internal subscriber's calendar client, from this repository |

Each command is one function in `tools/convener_ops/cli.py`, and the module
it calls into states which fields it drops. `docs/operating/operations.md`
is the operator's procedure for all five.

## What never lands here

A participant's name, address or affiliation, and any room link.
`tools/convener_ops/publication/public_data.py` classifies every field of
every record, `NEVER_PUBLISHED` among the classifications, and
`tools/tests/publication/test_public_data.py` refuses a projection that
carries one. The encrypted records themselves stay under
`instance/data/events/<event id>/`, and no command here reads them.
