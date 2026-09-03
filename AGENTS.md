# For an agent

This repository is duplicated and run by volunteers, and some of that work is
done with an agent. Everything an agent needs is already written for a person.
This page holds no procedure of its own; it says where each one lives, so that
every agent reaches the same page by the same route, whatever its tooling
discovers on its own. Nothing here is in a vendor's directory; a second
vendor gets another line on this page, never a second copy of a procedure.

`CLAUDE.md`, beside this file, is the one exception to that and it is a
bridge rather than a rendering: it holds a pointer back here and no
procedure. It exists because it was measured rather than assumed — a fresh
Claude Code session in this repository, asked with no tools what declares the
standing-up sequence, answers only when `CLAUDE.md` is present; it does not
read this file on its own. Codex reads this one directly. Both end on the
same page, and neither has a copy of it.

## Standing an instance up

`declarations/standing-up.yml`, beside the other two declarations this
product owns, declares the sequence that turns no repositories and no
accounts into a running instance: every step in order, with the actor who
carries it out, what proves it is done, and what an instance loses by
skipping it. Nothing restates that file. Two renderings are
generated from it and refused by continuous integration if they drift:

- `docs/operating/standing-up.md` — the guide a person follows with a web
  browser and a text editor, and no agent at all. It is the product, not a
  fallback, and nothing may make it slower or less complete.
- `docs/operating/standing-up-for-an-agent.md` — the same sequence as a
  procedure for an agent: which steps to carry out, which to hand over word
  for word, how to prove each one, and what may never be printed. It is
  written for any agent rather than for one, and nothing will offer it to
  you, so read it directly.

## Working on the product itself

`README.md` has the day-to-day commands, `docs/engineering/architecture.md` has the gate
each directory is held to, and `CONTRIBUTING.md` says what a contribution
certifies and how a commit is signed off.

`docs/engineering/content-rules.md` is the rule those three answer to: one notion,
one home. A passage that has to appear in two places is included from the
first rather than copied into the second, and a test refuses the copy. That is
the rule most worth knowing before writing anything here, because it is the
one an agent breaks most easily: the obliging thing to do with a fact that is
needed twice is to write it twice.
