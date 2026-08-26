# Contributing

## What you can expect back

**This software is provided as is. Issues are read. No response is
guaranteed, and none is promised anywhere on this repository.**

That is worth saying out loud rather than leaving to be discovered. An
unanswered issue makes a project look abandoned, and the reader who opens
one has no way to tell "nobody is maintaining this" from "one unpaid
person is maintaining this and has a day job". Saying which it is costs a
paragraph and saves everybody the guess. A pull request that leaves the
gates green is far more likely to be merged than an issue is to be
answered, because merging is a smaller act than deciding.

Security reports are the one thing that does not belong in an issue at
all: `SECURITY.md` has the private channel and says what to expect from it.

## Signing off a commit

**Every commit carries one `Signed-off-by` line. There is no contributor
licence agreement, no form to sign and no copyright to assign.**

```bash
git commit -s
```

`-s` appends the line for you, using your configured name and email:

```text
Signed-off-by: Jane Developer <jane@example.test>
```

By adding it you certify the **Developer Certificate of Origin 1.1**
(<https://developercertificate.org>): that you wrote the contribution or
otherwise have the right to submit it under this project's licence, and
that you understand it will be kept indefinitely and redistributed with the
project. It is a statement about *your* right to contribute the code. It
transfers nothing, and it asks for no rights over your work beyond the
licence the whole repository is already under.

The alternative was a contributor licence agreement. It was rejected for
what it would cost the people this product is for: a CLA is a document an
academic has to route past an institution's legal office before they can
fix a typo, and it asks them to grant rights the AGPL does not need granted.
The certificate asks for a line in a commit message instead.

**One consequence of that, written here rather than discovered later.** The
sign-off leaves every contributor holding their own copyright, licensed to
this project under the AGPL and nothing else. While the whole repository is
one person's work, that person can also grant a different licence to somebody
whose use the AGPL does not fit, which is what `README.md` offers under
*Licence*. The first substantive contribution of code ends that, because a
licence nobody can grant over somebody else's copyright is not a licence.

That is not a reason to refuse a contribution. It is a reason to know, on the
day one arrives, that merging it is a decision with two sides: take it as it
stands and the separate-licence route closes, or ask that contributor for the
right to relicense their part and keep it open. Either is defensible.
Finding out afterwards is not.

**Nothing automated enforces it, and that is a decision rather than an
omission.** `convener-check-commits` was the obvious place to put it, and
it is the wrong one twice over. It reads every commit in the range on every
push, and most commits here are not written by a person at all: the cockpit
records a board vote through the GitHub API, a scheduled job rewrites the
decision register, another commits the published projection of the data. A
certificate of origin signed by a job is a false certificate, not a
formality. And every instance duplicating this repository inherits that
check, so a rule about who may contribute code upstream would stand between
a volunteer and recording a vote in their own series.

So the sign-off is checked where it can actually be judged: by the person
merging the pull request, on the commits the pull request brings. What is
automated is the other half — `tools/tests/test_public_repository.py`
refuses a commit-message check that starts rejecting a contributor's
sign-off as an attribution trailer, which is the way this could quietly
stop working.

## Before you open a pull request

Every gate continuous integration runs is runnable locally, and none of
them needs an account or a secret. `docs/architecture.md` has the
per-directory commands; `README.md` has the day-to-day ones, and the
optional pre-commit hook that runs the formatting, linting, secret and
British-English spelling checks before each commit.

Two conventions that are not obvious from the diff:

- **Handbook content under `docs/` is the source of truth for what the
  application displays**, so a wording fix there is an ordinary pull
  request and needs no development environment at all — every page carries
  an edit link.
- **One notion, one home.** `INFORMATION-ARCHITECTURE.md` is the contract,
  and a passage that has to appear on two pages is included from the first
  rather than copied into the second. A copy is refused by a test, not by
  a reviewer's memory.

## If you are forking rather than contributing

Rename it. `TRADEMARK.md` says what a fork renames, what it must keep, and
how little an unregistered mark is actually worth — it asks rather than
threatens, and it is short.
