---
name: standing-up
description: Carry out STANDING-UP.yml, the declared sequence that turns no repositories and no accounts into a running instance of this product: run the steps it marks for an agent, hand the browser-only steps to the person word for word, and prove each one with its own declared check. Use when standing an instance up, resuming a half-standing one, or working out which steps are still outstanding.
---

# Carrying out the standing-up sequence

This page is generated from `STANDING-UP.yml`, the one declaration of this
sequence. Do not edit it: run `uv run python
scripts/generate_standing_up_skill.py` from `tools/` and commit what it
writes, and continuous integration refuses a page the declaration does not
derive. `docs/reference/standing-up.md` is the same declaration rendered for a
person, and `AGENTS.md` points here for an agent that does not find this file
on its own. The prose below lives in
`tools/scripts/generate_standing_up_skill.py`; the run sheet at the end comes
from the declaration.

## What this page is, and what it is not

`STANDING-UP.yml` declares what somebody with no repositories and no accounts
does, in order, to have a running instance. It is a declaration rather than a
page because more than one thing reads it, and this is one of them.

**No step's content is repeated here, deliberately.** What a step does, what
proves it is done, what an instance loses by skipping it, and the lines a
person is handed word for word are all fields of that file, read out of it
when the step comes up. The run sheet at the end of this page carries the
order, the identifier and who acts — nothing else. A skill that restated the
steps would be a second copy of one procedure, and the copy is the one that
goes stale.

**The guide is the product; this page is an accelerator.** One person with a
web browser and a text editor finishes the whole sequence without an agent,
and that is the path the product is designed around: nothing it does may
depend on a tool somebody has to pay for. So nothing here makes that path
slower or less complete, and no step below is reachable only through an agent.
15 of the 28 steps are a person's whatever else is available — a flow that
exists only in a browser, or a value that must never leave the hands of
whoever minted it.

## Before the first step

1. Read `STANDING-UP.yml` from its first line to its last, header included.
   The header states what each field means, why a step belongs to a person or
   to an agent, and the five places where the order carries weight.
2. Run `cd tools && uv run convener-check-config` and show the person what it
   prints. Each row reported absent is a step below that has not happened yet,
   and that row's `meanwhile:` line is what its absence costs today.
3. Work out where the sequence has already got to from the checks, never from
   what anybody remembers doing. Resuming a half-standing instance is the
   ordinary case, not the exception.
4. Say which steps you will carry out and which you will hand over, before
   starting either.

## The loop

For each step in the declared order, one step at a time:

1. Read that step's own entry in the declaration: `does`, `check`, `command`
   where it has one, `sets`, `walkthrough`, and either `degraded` or
   `integrations`.
2. Where the run sheet says **carry out**, do it — with `gh`, `wrangler`,
   `tools/scripts/create_tally_form.py`, a file edit, or one of this
   repository's own commands.
3. Where it says **hand over**, stop, give the person the step, and wait for
   them.
4. Prove it with that step's own `check`.
5. Only then move to the next one.

Never run two steps together, and never take one early. The declaration's own
note above `steps:` names the five places where the order is load-bearing and
what each one costs to get wrong.

## Handing a step over

A step belongs to a person for one of two reasons, both operational rather
than a preference about who ought to do the work. Either the flow exists only
in a browser and has no interface anything could call — GitHub mints no
fine-grained personal access token through an API, and an App is registered on
a form from start to finish — or the value the step produces must never exist
anywhere but in the hands of whoever minted it. Neither is worked around.

Hand one over like this:

- Name the step and read out its `does`.
- Read out every line of its `walkthrough`, in order and unaltered. Those
  lines are written to be complete on their own; summarising one drops the
  sentence that stops somebody choosing the wrong option on a form with twenty
  fields.
- Read out its `check`, so the person knows what they are aiming at.
- Add nothing. A screen described from memory rather than from the declaration
  is worse than no description, because it is specific and wrong.

Then wait. Do not offer to do the person's half, and never ask for a value so
that you can set it on their behalf.

## Proving a step

The check belongs to the step, not to you. Satisfy the one the declaration
gives, as it is written.

- Where it names a command, run the command and read what it prints.
- Where it names the configuration report, run `cd tools && uv run
  convener-check-config` and find the row the check names by its own label.
- Where it can only be read in a browser, ask the person what the page shows
  and take their answer. Asking is the check working; inferring is the check
  skipped.

**A step that looks done is not done.** Several of the failures this sequence
exists to surface are green runs: a publishing workflow that logs one line and
exits cleanly because no token is set, a deploy that skips itself while a
placeholder identifier stands, a Pages source answering 200 with a
repository's README over a site that does not exist. An exit code of zero is
not a check, and neither is your own reading of what probably happened.

## When a check fails

Stop. Report which step, quote its `check`, and say what happened instead. Do
not attempt the next step, do not reach the same effect by another route, and
do not guess at a value.

A half-configured instance that reports success is worse than one that stops.
This product's own rule is that an absent integration stays visible, and an
instance believed to be finished is one nobody looks at again.

Stopping on purpose is a different thing, and it is a normal end. The last
stage is a menu rather than a queue. Where somebody decides to stop there, say
what each remaining step costs — from that step's own `degraded`, or, for a
step that names integration rows, from the report's `meanwhile:` line for
those rows. Do not write that sentence yourself.

## Secrets

None of these is a preference, and none has an exception that is not written
here.

- **Never read, print, echo, log or write a secret value.** Not into a
  transcript, not into a file, not into a command line, not into an example
  that looks real. If a value reaches you anyway, say so and ask for it to be
  replaced rather than carrying on with it.
- **A repository secret is set by the person, under their own credentials.**
  `gh secret set <NAME>` reads the value from its own prompt under that
  person's `gh auth`; run it only with somebody at the keyboard, and never
  with `--body`, which puts the value in a command line and in a shell
  history. That prompt is a gate rather than an obstacle. Where a browser is
  easier, the declaration's `secrets:` table carries the menu path for every
  credential it names, and the browser is a complete route.
- **A worker secret has the same shape.** `npx wrangler secret put <NAME>`
  prompts too, and the declaration carries that command beside the dashboard
  path for each one.
- **Where a walkthrough says a value must never be written to a file, that is
  the whole rule.** Do not offer to generate it, do not offer a shell to
  generate it in, and do not read the terminal it is generated in.
  `docs/reference/operations.md` states the same refusal for the certificate
  signing key, which is the one credential in this product that nothing
  automated is allowed near.
- **A local `.env` is allowed exactly once, and is deleted.** One credential
  in this sequence is spent from a shell rather than set on a repository or a
  worker: the key that builds the public proposal form. The person writes it
  into `.env` at the repository root — never you — and `git check-ignore .env`
  confirms the file is ignored before it is created. Delete it as soon as the
  form exists, whether or not the run succeeded, and say that you have.

## The sequence, in order

28 steps in 8 stages. 15 are handed over; the rest an agent carries out. Read
each step's own entry in `STANDING-UP.yml` before carrying it out or handing
it over.

### Stage 1 — Nothing exists yet

| # | Step | Action | Title |
|---|---|---|---|
| 1 | `mail_account` | hand over | An address the organisation owns |
| 2 | `credential_store` | hand over | A store two people can open |
| 3 | `github_owner` | hand over | The GitHub account or organisation the repositories sit under |

### Stage 2 — The two repositories

| # | Step | Action | Title |
|---|---|---|---|
| 4 | `private_cockpit` | carry out | The private repository, duplicated and never forked |
| 5 | `public_showcase` | carry out | The public repository the site is published into |
| 6 | `pages_source` | carry out | Pages, on the public repository only |

### Stage 3 — The three files a duplicate edits

| # | Step | Action | Title |
|---|---|---|---|
| 7 | `instance_declaration` | carry out | Who is publishing, and where |
| 8 | `board_and_thresholds` | carry out | The Board, the season and the bar a vote is measured against |
| 9 | `own_records` | carry out | Your own records, starting empty |

### Stage 4 — Getting a public site

| # | Step | Action | Title |
|---|---|---|---|
| 10 | `vitrine_deploy_token` | hand over | The token that lets the cockpit push into the showcase |
| 11 | `first_publish` | carry out | The first publish, and reading it in a browser |

### Stage 5 — The three workers

| # | Step | Action | Title |
|---|---|---|---|
| 12 | `github_app` | hand over | The GitHub App that signs volunteers in |
| 13 | `cloudflare_account` | hand over | The Cloudflare account, and the token CI deploys with |
| 14 | `relay_bindings` | carry out | The one value in the workers a duplicate has to fill in |
| 15 | `relay_tokens` | hand over | The two dispatch tokens the relays hold |
| 16 | `auth_relay` | carry out | The sign-in relay, deployed and pointed at |
| 17 | `signup_relay` | carry out | The relay a registration passes through |

### Stage 6 — The public proposal form

| # | Step | Action | Title |
|---|---|---|---|
| 18 | `tally_account` | hand over | The form account, and the key that builds from code |
| 19 | `form_relay` | carry out | The relay between the public form and the repository |
| 20 | `tally_form` | carry out | The form, built from this repository rather than clicked together |
| 21 | `proposal_form_live` | hand over | Publishing the form, pointing its webhook, and naming it |

### Stage 7 — What protects a participant's record

| # | Step | Action | Title |
|---|---|---|---|
| 22 | `retention_token` | hand over | The credential that destroys a key on its deadline |
| 23 | `signing_key` | hand over | The key that signs a certificate, minted by a person and only once |
| 24 | `matching_salt` | hand over | The salt behind a matching code and a register's fingerprint |

### Stage 8 — What is left, and what each costs to skip

| # | Step | Action | Title |
|---|---|---|---|
| 25 | `board_notifications` | carry out | Where the Board is told what happened |
| 26 | `outbound_email` | hand over | Sending a confirmation, a certificate and a survey invitation |
| 27 | `video_channel` | hand over | Where a recording is published |
| 28 | `meeting_platform` | hand over | The room the webinar happens in |

## When the sequence ends

- Run `cd tools && uv run convener-check-config` once more and show the person
  every row and its state.
- Confirm no `.env` is left anywhere in the working tree.
- Confirm the working tree holds nothing else you did not mean to leave in it.
- List the steps that were not done and what each costs, from the declaration.
- Say that every credential minted along the way belongs in the store two
  people can open. A value held only in one person's browser is what the first
  stage exists to prevent, and it is the one failure in this sequence that
  cannot be corrected later.

`docs/reference/operations.md` is what an instance runs on afterwards. This
page hands over to it and does not repeat it.
