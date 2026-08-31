# For an agent

This repository is duplicated and run by volunteers, and some of that work is
done with an agent. Everything an agent needs is already written for a person.
This page holds no procedure of its own; it says where each one lives, so that
an agent whose tooling does not discover `.claude/skills/` still reads the
same page as one that does.

## Standing an instance up

`STANDING-UP.yml`, at the root of this repository, declares the sequence that
turns no repositories and no accounts into a running instance: every step in
order, with the actor who carries it out, what proves it is done, and what an
instance loses by skipping it. Nothing restates that file. Two renderings are
generated from it and refused by continuous integration if they drift:

- `docs/operating/standing-up.md` — the guide a person follows with a web
  browser and a text editor, and no agent at all. It is the product, not a
  fallback, and nothing may make it slower or less complete.
- `.claude/skills/standing-up/SKILL.md` — the same sequence as a procedure for
  an agent: which steps to carry out, which to hand over word for word, how to
  prove each one, and what may never be printed. It is written for any agent
  rather than for one, so read it directly if it is not offered to you.

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
