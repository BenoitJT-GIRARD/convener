# Taking an update

Your instance is a **duplicate**, not a fork. It has upstream's code and none
of GitHub's fork machinery, which is what lets it be private and hold your
participants' records. The price is that nothing updates it for you: an
update is a merge, and you perform it.

This page is the command. [`CHANGELOG.md`](../../CHANGELOG.md) is the other
half — it says what each release brings and which of your own paths it
reaches, so you can read what a merge will do before you do it.

## Once, when you stand the instance up

```sh
git remote add upstream https://github.com/BenoitJT-GIRARD/convener.git
```

Nothing about your own `origin` changes. `upstream` is read-only in
practice: you fetch from it and you never push to it.

## Every time

```sh
git fetch upstream
git merge upstream/main
```

**Fetch immediately before you merge**, not once at the start of a session.
Somebody else writes to upstream while you work, and a stale `upstream/main`
does not fail loudly — it produces a conflict that is not really there, which
you then resolve by hand, in a decision that looks reasonable and is wrong.
That is the failure mode to watch for: not a merge that breaks, a merge that
succeeds against yesterday's facts.

## "refusing to merge unrelated histories"

Then this repository was created from an extracted archive rather than from a
clone, so it shares no commit with the product and there is no common base to
merge against. `private_cockpit` allows both routes and its check cannot tell
them apart.

You fix it once:

```sh
git merge --allow-unrelated-histories upstream/main
```

Expect a large number of conflicts **that one time**. They are not the
boundary failing; they are git being asked to reconcile two histories that
have never met, so every file either side has touched since the archive was
taken comes up — including files you have never opened. Resolve by the rule
below, and afterwards a common base exists:

```sh
git merge-base HEAD upstream/main     # prints a commit, silently, when it worked
```

Every merge after that is an ordinary one.

## The conflicts to expect, and what each one is

`declarations/boundary.yml` hands a set of paths to the instance, and a merge
never fights over those: upstream does not write them. What is left are
product files that nonetheless carry a value of yours. There are two kinds
and they are resolved differently.

### Seven files generated from your charter

```
app/src/design/motif.ts          site/src/style.css
app/src/design/tokens.css        docs/handbook/assets/announcement-template.svg
site/src/_data/motif.json        docs/handbook/assets/flyer-template.svg
                                 docs/handbook/assets/video-call-background.svg
```

These are written by a command, from `instance/data/brand.json`. They are
also the conflicts most likely to be unreadable, because a change to either
generator rewrites the whole file on both sides at once.

**Do not resolve them by hand.** Take either side — it does not matter which —
and re-run the generators:

```sh
cd tools
uv run --frozen python scripts/generate_brand_css.py
uv run --frozen python scripts/generate_motif.py
```

Then let the checks prove it, which is the point of resolving this way rather
than by reading:

```sh
uv run --frozen python scripts/generate_brand_css.py --check
uv run --frozen python scripts/generate_motif.py --check
```

Both run in `gates.sh` and in continuous integration, so a file left
half-merged fails before it reaches anybody.

### A handful of lines only you can hold

| file | the line |
|---|---|
| `.github/CODEOWNERS` | the catch-all rule, naming your Board's team |
| `services/form-relay/wrangler.toml` | the KV namespace id |
| `services/signup-relay/wrangler.toml` | the KV namespace id |
| `.github/dependabot.yml` | whatever you did to stop version updates |

**Keep yours.** Each is one line in a file upstream otherwise maintains, so
take upstream's version of everything else in the file and put your line
back. Git conflicts per region rather than per file, so upstream can rewrite
the rest of any of these freely without ever touching your line — and most
releases will not bring a conflict here at all.

## After a merge

Install first, once per tree and in any order, every one of them from the
repository root. An update can bring a tree that was not there when you last
did this, and a gate that runs in a tree with no dependencies installed fails
on a missing tool rather than on anything your merge did.

```sh
npm ci --prefix app
npm ci --prefix site
npm ci --prefix services/auth-proxy
npm ci --prefix services/form-relay
npm ci --prefix services/signup-relay
uv sync --all-extras --project tools
```

Then, from the repository root:

```sh
sh gates.sh
```

That is every check continuous integration runs, and none of them needs an
account or a secret.

Then push. A push runs every workflow this repository has, which on a private
repository is billed against your organisation's Actions allowance — so batch
several upstream releases into one merge rather than taking each as it lands,
if you are watching that budget.

## What never conflicts

Everything the boundary declares: `instance/data/`, `instance/keys/`,
`instance/public-data/`, `instance/config.json`, the four configuration files
beside it, and `docs/handbook/governance/register.md`. Upstream does not
write those paths, so nothing arrives to disagree with what you put there.
[What a duplicate edits](what-a-duplicate-edits.md) is the list, and
`declarations/boundary.yml` is where it is declared and argued.
