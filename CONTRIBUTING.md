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

**Every commit carries one `Signed-off-by` line. There is no form to sign
and no copyright to assign.** One right is asked beyond the certificate, and
the paragraph headed *One thing is asked beyond the certificate* below is
where it is asked -- not in a document, and not in passing.

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
project. It is a statement about *your* right to contribute the code, and
it transfers nothing: you keep the copyright in what you wrote, and may do
anything you like with it elsewhere.

The alternative was a contributor licence agreement. It was rejected for
what it would cost the people this product is for: a CLA is a document an
academic has to route past an institution's legal office before they can
fix a typo. This project does ask for one right the licence does not need
granted -- the next paragraph says which, and why -- but it asks in a
paragraph rather than in a document, and nothing here has to be signed.

**One thing is asked beyond the certificate.** By submitting a contribution
you also grant the copyright holder a perpetual, irrevocable, **non-exclusive**
right to license your contribution under terms other than this project's
licence. Non-exclusive is the operative word: the copyright stays yours, and
this takes nothing away from what you may do with your own work.

The reason is in `README.md` under *Licence*. The holder can offer a separate
licence to somebody the AGPL does not suit, and that stays possible only while
no part of the software sits outside this right -- a licence nobody can grant
over somebody else's copyright is not a licence. Without this paragraph the
option would close on the first merge, with nobody having decided anything.

**For a substantial contribution, expect to be asked to say so in the pull
request itself**, in one line and in your own words. A paragraph in a file
somebody may not have read is weaker evidence than a sentence written by the
person who wrote the code.

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
them needs an account or a secret. `docs/engineering/architecture.md` has the
per-directory commands; `README.md` has the day-to-day ones, and the
optional pre-commit hook that runs the formatting, linting, secret and
British-English spelling checks before each commit.

Two conventions that are not obvious from the diff:

- **Handbook content under `docs/` is the source of truth for what the
  application displays**, so a wording fix there is an ordinary pull
  request and needs no development environment at all — every page carries
  an edit link.
- **One notion, one home.** `docs/engineering/content-rules.md` is the contract,
  and a passage that has to appear on two pages is included from the first
  rather than copied into the second. A copy is refused by a test, not by
  a reviewer's memory.

## If you are forking rather than contributing

Rename it. `TRADEMARK.md` says what a fork renames, what it must keep, and
how little an unregistered mark is actually worth — it asks rather than
threatens, and it is short.
