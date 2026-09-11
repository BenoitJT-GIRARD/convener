# Changelog

Every published state of this product, newest first, with what an operator
running a duplicate does about each one.

A duplicate is how this product is installed and a merge is how it is
updated ([`declarations/boundary.yml`](declarations/boundary.yml)). Three
things follow, and this page is all three: a name for the upstream state a
duplicate is on, a reading of what a merge would bring before it is pulled,
and a warning when a change has reached a file the boundary hands to that
operator rather than to upstream. The last of the three is the section every
entry below carries.

## What a version names

An upstream state, and nothing about support.
[`SECURITY.md`](SECURITY.md) is where that question is answered, and the
answer is unchanged: the default branch, with no backport and no patched
release behind it, because a fix reaches every instance through the merge
each of them already does.

The interface the numbers are about is the merge:

- **Major** — a release a duplicate cannot take by merging alone. A path it
  owns changes shape, a value it typed by hand moves, or a repository
  setting has to be changed before the merge is safe.
- **Minor** — new behaviour, and a merge is the whole of what it takes.
- **Patch** — a fix, and a merge is the whole of what it takes.

[`tools/pyproject.toml`](tools/pyproject.toml) holds the number itself, in
one place. The newest entry below has to name that same value:
`tools/scripts/generate_changelog.py --check` fails a page where the two
disagree, so a release that bumps one and forgets the other never lands.

## What a duplicate owns

<!-- BEGIN GENERATED PATHS A DUPLICATE OWNS -- tools/scripts/generate_changelog.py -->
*The lists below are generated from* `declarations/boundary.yml` *and from this
repository's own index: the paths a merge can arrive at that are not
upstream's to change. Do not edit this block — run*
`uv run python scripts/generate_changelog.py`
*from* `tools/` *and commit what it writes.*

**Yours, by the declaration.** Upstream ships each of these filled in for
the instance that happens to run this repository, and never edits one
afterwards. A release that changes the *shape* of one names it below.

- `docs/handbook/governance/register.md` — rewritten in full by your own
  next push.
- `instance/actions-budget.yml`
- `instance/config.json`
- `instance/data/`
- `instance/keys/`
- `instance/public-data/`
- `instance/queue-drain.yml`
- `instance/registration-lanes.yml`

**The product's, with one value of yours typed into it.** Upstream
maintains these; your copy differs from upstream's by the value you
entered, so a release that changes one arrives at that edit.

- `.github/CODEOWNERS` — read by GitHub verbatim, before any code of this
  project's can run, so the owner a review request goes to is typed rather
  than read from the declaration. It arrives naming a single account, which
  a duplicate replaces with its own organisation's team before its first
  pull request.
- `services/form-relay/wrangler.toml` — the identifier of the storage
  namespace the proposal relay binds to, which does not exist until
  `wrangler kv namespace create` has printed it and so cannot be shipped
  filled in.
- `services/signup-relay/wrangler.toml` — the same one value, for the relay
  a registration and a survey response pass through.

**Inside those directories and not yours.** Upstream owns and maintains
each of these, so a release that changes one needs nothing from you:

- `instance/data/schema.md`
- `instance/keys/events/README.md`
- `instance/keys/signing/README.md`
- `instance/public-data/README.md`
<!-- END GENERATED PATHS A DUPLICATE OWNS -- edit tools/scripts/generate_changelog.py, not this block -->

## How an entry is written

The decision records under
[`docs/engineering/decisions/`](docs/engineering/decisions/index.md) are the
*why* of every structural choice, and
[`docs/handbook/governance/register.md`](docs/handbook/governance/register.md)
is the generated history of the votes. An entry here repeats neither. What
it carries is what a release does to somebody else's repository:

- a short passage saying what changed, in the terms an operator reads
  rather than in the terms the diff does;
- a `### Before you merge this` section, in **every** entry, naming each
  path from the two lists above that the release touched and what the
  operator does about it. An entry whose answer is that there is nothing to
  do says that in as many words: an operator has no way to tell a silence
  from an omission.

`tools/scripts/generate_changelog.py --check` holds three of those: that
every entry carries the section, that no entry names a path under it which
the declaration says is upstream's, and that the versions descend without
repeating.

## 1.0.0 — 2026-09-02

The first published state. What is in it is the whole product as this
repository has it: the cockpit and the public showcase, the three edge
workers, the operational tooling every workflow runs, the standing-up
sequence a person walks with a browser and a text editor.
[`README.md`](README.md) says what the product does and
[`docs/engineering/architecture.md`](docs/engineering/architecture.md) how
it is built.

**1.0.0 rather than a 0.x**, and the reason is the interface the number is
about. A 0.x says that anything may move under a duplicate without notice.
What a duplicate actually merges against here is the boundary — which paths
it owns, which values it types by hand — and that is declared in one file,
enforced on every run, and the thing this product has been run on for two
years. A 0.x would have promised less than the repository already refuses
to break.

### Before you merge this

Nothing, and there is no earlier release for it to be about. A duplicate
made at 1.0.0 starts here.
