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

**The tags are in this repository and not in the product's.**
`convener-derive` clones with `--no-tags` and rewrites every commit it
carries over, so a tag made here names a commit the public repository does
not hold.
[`docs/operating/publishing-the-product.md`](docs/operating/publishing-the-product.md)
is where the product's own tag is made, on the derived history, by the
person publishing it.

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
  project's can run, so the team a review request goes to is typed rather
  than derived. A duplicate writes its own organisation's team into it
  before its first pull request.
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

## 2.0.0 — 2026-09-04

**The Board's own rule for seating a member changed, and the shape of a
nomination record changed with it.** A nomination now carries on a majority
of the eligible board inside its window: silence refuses it, an objection
still defers the candidate to the annual meeting, and every nomination
record now carries the members who have said yes. That is what makes this a
major release, and it is the first item below, because the file it changes
is yours.

Everything else here a merge takes on its own. The numbered governance rules
were renumbered so the sequence follows the order the handbook states them
in, and the Board's rules page now carries a generated index naming every
one and the page that states it — a number quoted in a Board's own minutes
before this release may name a different rule after it. The workspace's
pipeline was rebuilt around one order, *what a status knows · what it asks
somebody to do · what it records*, with each status's dates and closing
control inside it rather than in a column beside it; a scheduled talk, a
delivered recording nobody may publish and a wrapped-up edition each gained
the way out of their status they had been missing. The standing-up
declaration moved in beside the other two, and every command the guides tell
somebody to type now runs on the shell a Windows machine opens by default.
The worked example is drawn in the product's own charter, holds a record at
every status, and dates them against the week they are read in. And the
product publishes a working demonstration of itself, built from that example
by a workflow every duplicate inherits and none has to run.

### Before you merge this

**`instance/data/` — every nomination needs one new key.** Each entry under
`nominations:` in your `instance/data/config.yml` now carries `supports:`, a
list of `{member, date}`: the board members who have said yes, and the day
each of them said it. The cockpit refuses to load a file without it and
names the entry it stopped at. A file whose `nominations:` is empty needs
nothing at all. For a nomination still open, list the member who put the
candidate forward against the day the window opened, and anybody who has
agreed since; for one already decided, the same list, and the outcome
already on it stays what it says. The count that seats somebody is of
distinct members inside the window, so a support dated after the window
closed stays on the record and out of the count.

**`instance/config.json` and `instance/data/` — the design a duplicate
inherited changes.** Upstream stopped shipping a palette of its own and
names one instead, so the merge deletes `instance/data/brand.json` and adds
`"charter": "convener"` to your `instance/config.json`. A duplicate that
never touched either is drawn in the product's navy and coral afterwards
rather than in the green and ochre it inherited, on every published page. A
duplicate that wrote its own palette keeps the file — a merge raises a
deletion against a file you have edited rather than taking it — and then
has to delete the `charter` line, because naming a charter and writing one
is the one combination the build refuses, and it refuses at the build
rather than at the merge. Either way the answer is one line: keep `charter`
and be drawn in a design upstream maintains, or delete it and keep your
own.

**`instance/actions-budget.yml` — nothing to change, and one more job to
count.** The demonstration workflow arrives with this release and runs on a
merge and on a weekly schedule of its own. It reads nothing of your instance
and publishes nothing until a repository variable is set that no duplicate
has set, so what it costs you is its own build minutes against the allowance
this file measures you against. If you would rather it did not run at all,
GitHub disables a workflow from the Actions tab, which leaves the file where
the next merge expects to find it.

**Nothing else.** No other path in the two lists above was reached: your
records, your keys, the published projection of them and the two relays'
configuration are as 1.0.0 left them, and the register rewrites itself on
your own next push.

## 1.0.0 — 2026-09-02

The first published state. What is in it is the whole product as this
repository has it: the cockpit and the public showcase, the three edge
workers, the operational tooling every workflow runs, the standing-up
sequence a person walks with a browser and a text editor, and the
derivation that produces the public repository this page is read in.
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
