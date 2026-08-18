# Operations

Everything the *application code* needs from the outside world. Each
integration is optional: without it the feature degrades visibly and
nothing breaks.

Run `cd tools && uv run convener-check-config` at any time to see what is
configured and what is still waiting. That declaration
(`config/integrations.yml`) covers only what `tools/convener_ops` and `app/src`
themselves read at runtime — three further secrets exist to gate CI
workflow behaviour and are documented in their own section below instead,
since `convener-check-config` running on a laptop would otherwise report them
as permanently missing.

## Before anything else

1. Create an email address owned by the organisation — never a personal one.
2. Create the shared password vault (`secrets.kdbx`) in the organisation's
   existing shared Drive, or in a password manager the Board already uses —
   never committed to this repository — and share the master password out
   of band with two or three Board members.
3. Create every account below with that address, and store its credentials
   in the vault.

A service account tied to one person's mailbox defeats the whole point:
anyone with organisation access must be able to pick this up. Do the vault
first.

This repository must stay private: `data/speakers.yml` holds personal data
(names and institutional email addresses of external academics).

## Authentication relay

**Without it:** sign-in falls back to a personal access token. The app stays
fully usable; onboarding is simply slower.

**To create:**
1. Register a GitHub App in the organisation. Permissions: *Contents: read &
   write*, *Issues: read & write*, on `workshop-series` only. Enable device
   flow.
2. Create a Cloudflare account with the organisation address; deploy the
   worker from `services/auth-proxy/` (`npx wrangler deploy` from that
   folder — see its README).

**Secrets to set:**
- Repository secret `CLOUDFLARE_API_TOKEN` (used by *Deploy auth relay* to
  deploy the worker).
- Repository **variables** `VITE_AUTH_PROXY_URL` and
  `VITE_GITHUB_APP_CLIENT_ID` (Settings → Secrets and variables → Actions →
  Variables). Both are public by construction — a relay URL and an OAuth
  client id ship inside the bundle — so they belong in Variables, not
  Secrets.

The worker needs no client secret. Its device-flow login does not require
one, and the app does not attempt to refresh access tokens — refreshing
would require a client secret, and putting one into a relay we deliberately
built stateless and secret-free is a worse trade than re-running the
30-second device flow each session. Users re-authenticate once per session
instead.

These variables are read only at build time (Vite requires the `VITE_`
prefix to expose a variable to the browser bundle at all). Setting or
changing them has no effect until the application is rebuilt — push to
`main` or run the *Deploy app* workflow manually.

**To verify:** sign out, reload; the screen should offer a short code rather
than a token field.

## GitHub Pages

**Without it:** nothing else is affected here — this is how the app itself
is published, not an optional integration.

**To create:** Settings → Pages → Source = *GitHub Actions*.

If the repository is private and the current GitHub plan does not offer
private Pages, fall back to another static host (for example Netlify or
Cloudflare Pages) pointed at the `app/dist` build output.

**To verify:** push to `main`; the *Deploy app* workflow ends green and the
site answers.

## Meeting platform

**Without it:** the manual adapter is used — links are typed by hand and
attendance is imported from a file. No room link is published
automatically.

**To create:** requires production API credentials from the meeting
provider, granted after a manual request (see phase 4).

**Secret to set:** `CONVENER_MEETING_API_TOKEN`.

**To verify:** run `cd tools && uv run convener-check-config`; *Meeting platform*
moves from `absent` to `production`.

## Outbound email

**Without it:** messages are written to an inspectable log instead of being
sent, and the interface says so. Nothing is silently dropped.

**To create:** see phase 4.

**Secrets to set:** `CONVENER_SMTP_HOST`, `CONVENER_SMTP_USER`, `CONVENER_SMTP_PASSWORD`,
`CONVENER_SMTP_FROM`.

**To verify:** run `cd tools && uv run convener-check-config`; *Outbound email*
moves from `absent` to `production`.

## Video channel

**Without it:** recording URLs are entered by hand after publishing. No
upload is attempted.

**To create:** create the video channel (for example a YouTube channel)
with the organisation address, and record its id.

**Secret to set:** `CONVENER_VIDEO_CHANNEL_ID`.

**To verify:** run `cd tools && uv run convener-check-config`; *Video channel*
moves from `absent` to `production`.

## Board notifications

**Without it:** nothing is sent. The digest and the immediate events are
still composed and printed to the *Notify the board* job log, where any
volunteer can read exactly what would have gone out, but they are addressed
to nobody and no comment is posted.

This is structural rather than a setting. A message needs both a thread to
be posted on and a team to mention; without both, no addressed message is
built at all, so the workflow's posting step finds nothing to post. There is
no notifications on/off switch anywhere in the chain, and a quiet day and an
unconfigured repository behave identically.

**To create:** no external service and no account — GitHub itself is the
delivery mechanism.

1. Open an issue in this repository to serve as the standing notification
   thread (for example *Board notifications*), and note its number.
2. Create an organisation team for the editorial board (for example
   `@example-instance/editorial`) and add the Board members to it. A team,
   never a person: the channel must keep working when any one volunteer
   stops reading.
3. Ask each member to watch the thread, so GitHub emails them its comments.

**Secrets to set:** `CONVENER_NOTIFY_THREAD` (the issue number) and
`CONVENER_NOTIFY_MENTION` (the team handle, `@org/team`).

**What travels:** record identifiers (`spk-014`), stored calendar days,
`nomination N` labels and the four fixed step names. No speaker name, email
address, affiliation, country, talk title or board login is ever included —
`tools/convener_ops/notify.py` reads none of those fields.

**To verify:** run `cd tools && uv run convener-check-config`; *Board
notifications* moves from `absent` to `production`. Run
`uv run convener-notify-digest --dry-run` to read the day's message without
sending anything.

## CI-only secrets

These gate GitHub Actions workflow behaviour rather than anything the
application itself reads, so they never appear in `convener-check-config` (see
the note at the top of this document) — but a successor inheriting this
repository still needs to know they exist and where they live.

- **`TALLY_WEBHOOK_SECRET`** — verifies that a `proposal-submitted`
  `repository_dispatch` reaching *Handle proposal*
  (`.github/workflows/candidate-form.yml`) really came from the public
  Tally form and not a forged request. Set as a repository secret; its
  value is the signing secret Tally shows when the webhook is configured.
- **`VITRINE_DEPLOY_TOKEN`** — a fine-grained personal access token,
  scoped to the separate `example-instance/example-showcase` repository
  (contents: read & write only), that *Publish vitrine data*
  (`.github/workflows/publish-vitrine.yml`) uses to push the public events
  feed there. Without it the workflow logs a message and exits cleanly —
  no vitrine publish happens, nothing else breaks. Set as a repository
  secret on `workshop-series`.
- **`CLOUDFLARE_API_TOKEN`** — already introduced above under
  *Authentication relay*: used by *Deploy auth relay* to deploy the
  worker in `services/auth-proxy/`. Listed again here because it is the
  same kind of CI-only, cross-account credential as the other two.

## Inactivity (G-09)

A Board member who has cast no ballot for `inactivity_months` stops counting
toward the vote threshold. Nothing about this happens on its own.

The window is **twelve months** (decision G-09), set in `data/config.yml`.
The series runs roughly monthly, so six months of silence is an ordinary
heavy year, a sabbatical or a period of leave; twelve is long enough that a
proposal cannot be triggered by accident, which matters because every line
the rule prints names a real volunteer.

`tools/convener_ops/sweep.py::sweep_inactive_members` computes the proposal — the
config as it would read, and one line per member naming the date of their
last ballot — and **no command applies it**.

Detection is the half the scheduled task operates. Every `convener-sweep` run ends
by printing whatever the rule has to propose, after the `scheduled →
delivered` and vote-window lines and whether or not those changed anything
(each proposal is one line; it is wrapped here to fit the page):

```
Board inactivity (G-09) - proposed, not applied; a human decides:
  - <login>: no ballot since <date>; proposed inactive so the threshold stops
    counting the seat - the seat is kept, the annual meeting decides, and one
    word in config.yml undoes it
```

Nothing is printed when the rule has nothing to propose, which is the live
case today (see the first of the three points below). The proposed config the
rule returns is discarded on the spot: `convener-sweep` writes `data/speakers.yml`
and never `data/config.yml`, and what it writes is byte-for-byte the same
whether or not there were proposals to print. A scheduled job with nobody's
name on it must not be able to change a volunteer's standing overnight — the
same reason a vote window that runs out parks a lead rather than declining it.
Applying the proposal is a human act on the Board screen, or a hand edit to
`data/config.yml`, and the annual meeting is what settles the question.

`inactive` is not a departure and not a judgement. The entry stays in the
file with its `login` and `joined_on` intact; the seat is kept; the only
effect is that the member leaves the denominator `N`, so a Board that has
really been four for a year stops needing four voices to agree. Coming back
is the same one word changed back to `active`, and a member re-seated
through a nomination is reactivated in place rather than added twice.

Three things the rule will not do:

- name anyone whose record cannot say when the silence began. Every
  `joined_on` in `data/config.yml` is empty today, so on the live data the
  proposal is empty — by design, not by accident. Step 3 of the September
  list below is what ends that, and until it is done this rule cannot say
  anything at all.
- name a member who declared an absence covering today, or one carrying a
  nomination the Board has not settled. Either of those is a live question
  already.
- take the Board below three members able to vote (decision G-03). Members
  it holds back for that reason still appear in the output, so the meeting
  reads the same list either way. The floor is three, never `board_min`: a
  rule that removes members must not be free to take the Board past the
  point where it can decide anything, including the decision to let those
  members go, and `board_min` is a target rather than a rule (see
  *The Board's target size* below).

## The Board's target size

`board_min` is a **target**, not a rule. No code refuses anything because the
Board is short of it: a nomination may be opened
(`app/src/state/board.ts::nominationBlocker`), a candidate may be seated
(`resolveNominations`), a vote may be decided, and the inactivity rule uses
its own floor of three. The reason is that every act a Board below its target
could be refused is an act that would bring it back up — refusing them would
lock the shortfall in.

`board_max` is the opposite: it is enforced at the moment of seating, a
candidate who does not fit becomes `waiting`, and a file above the ceiling is
one the app could not have written, so `convener-validate` rejects it.

A target nobody states is a decoration, so it is reported in two places, and
in both directions rather than only on bad news:

- the Board screen, under the composition table — *4 active members, below
  the board's target of 5* — or *5 active members. The board aims for 5 and
  seats at most 9.*
- `convener-validate`, as a `Note:` line printed alongside its verdict. It does
  not add to the errors and does not change the exit code; a target that
  could fail a run would be a rule wearing a softer word.

## The one-shot scripts

`scripts/migrate_v3.py` and `scripts/open_vote_window.py` have both already
run, and their effects are committed. They are kept, separately, and neither
is deleted nor merged into the other.

Kept, because each is the record of what was done to the data on a day
nobody will remember. Both are pure functions with a `main()` that reads,
transforms and writes, both are idempotent, and each has a test file that
pins, field by field, what it touched and — more usefully — what it left
alone: `tools/tests/test_migrate_v3.py` and
`tools/tests/test_open_vote_window.py`. Deleting the scripts would leave the
two commits that changed every record in `data/speakers.yml` with no
statement of what they changed.

Separate, because they are two decisions taken for two reasons. The
migration moved every record to schema v3; the backfill stamped
`selection.opened_on` on the leads so the board had a window to vote in.
Merging them would fuse two acts into one file, and with them the two
"nothing else was touched" proofs, which are per-act or they prove nothing.
It would also make re-running the migration re-apply a backfill that was
never part of it. This repository's argument throughout is that the history
is the record; merging two executed records is rewriting one of them.

Neither should be run again. If a third one-shot is ever needed, it is a
third script with a third test, not an edit to either of these.

## Reading the register (decision commits)

There is no database. The commit history is where a decision's author and
date survive, so the app writes a fixed line for every act the Board takes:

```
data: <act> <record> by <login>
data: <act> <record> by <login> (<qualifier>)
```

for example `data: record a ballot on spk-007 by ada (recused)`,
`data: reopen the vote on spk-012 by grace`, or
`data: settle the nomination of erin by ada`. The acts are a closed
list (`tools/convener_ops/commit_format.py`, mirrored in
`app/src/state/decisions.ts`), each naming a record rather than a person,
and the qualifier is closed per act. So the register can be read back with
`git log --format=%s -- data/` and filtered on one act, and no line in it
can say anything about a volunteer beyond which record they touched.

Ordinary commits -- code, docs, the nightly sweep, the public form -- are
not decisions and follow no such shape. The `Commit messages` step of the
`python` CI job checks only the commits under review, and only those that
open with one of the acts above; it also refuses an attribution trailer in
any message.

## After the September collaborators' meeting

Three changes to the governance data are deliberately deferred until the
collaborators' meeting in September. They are a deferred configuration in
the sense of decision D-13 — the state below is normal and expected, not a
defect to be rediscovered and not something to fix piecemeal beforehand.
All three touch `data/config.yml`, the first two `data/speakers.yml` as
well, and they are easiest done together, in one commit, with
`cd tools && uv run convener-validate` run before it is pushed.

**What this costs until then:** the Board is declared as five members while
only four people sit on it (see step 2), so the threshold — two thirds of
the eligible board, rounded up — is four, and only four people ever vote.
A lead therefore needs every available voice to be approved: effective
unanimity. This is a known, accepted, temporary state.

### 1. Replace the Board identifiers with real GitHub logins

`data/config.yml` currently lists the Board as `Anonymous`, `Anonymous`,
`Anonymous`, `Anonymous` and `Anonymous`. Only `Anonymous` is a GitHub login; the
other four are first names. Role detection matches the signed-in GitHub
account against these values, so today it recognises nobody but that one
account — every other member is treated as a visitor.

Collect each member's GitHub login at the meeting, then rewrite both files
in step:

1. `data/config.yml` — every `board[].login`.
2. `data/speakers.yml` — every `selection.ballots[].voter`, using exactly
   the same mapping. The ballots carry the same first-name identifiers, and
   a vote is tallied only from ballots whose voter is on the Board
   (`tools/convener_ops/governance.py`), so a Board renamed on its own would
   silently discard every vote cast so far.

Nothing else in `data/speakers.yml` holds a Board identifier today:
`assigned_to` and `publication.approved_by` are empty everywhere, and
`host_1` and `host_2` hold people's display names, which are not logins and
must not be rewritten. Check that this is still true before starting.

`convener-validate` reports any voter you miss as `ballot from a non-member`.

### 2. Merge the duplicate member and lower `board_min`

`Anonymous` and `Anonymous` are the same person, recorded twice. Delete one of
the two entries, keeping that person's real GitHub login. The Board then
goes from five members to four, and the threshold from four to three.

`board_min` is `5` in `data/config.yml` and should become `3` in the same
change — not because anything breaks otherwise, but because it is the
Board's stated target and the Board is choosing a new one. Nothing fails if
you forget: `convener-validate` prints `board has 4 active members, below its
target of 5 (board_min)` and still exits `0`. The count is of *active*
members: an entry marked `inactive` stays in the file, keeps its `login` and
`joined_on`, and does not occupy a seat. Three is also the floor set by
decision G-03 — a vote is suspended rather than decided below three eligible
members — so a target below three would be a target the Board could meet
and still not be able to decide anything.

Rewrite the ballots of whichever identifier disappears to the surviving
one. If any lead ends up with two ballots from the merged person, keep one:
one person casts one voice, and a repeated voter is a validation error.
No lead carries ballots from both identifiers at the time of writing —
`Anonymous` has never voted — but confirm it rather than assume it.

### 3. Fill in `joined_on` for every Board member

Every `board[].joined_on` in `data/config.yml` is the empty string. The
field is what the inactivity rule measures silence from: with no start
date there is no window to count, so the rule proposes nobody and will go
on proposing nobody for as long as the field stays empty. It is not a rule
that has been switched off — it runs nightly, reads every member, and
declines to name anyone, which reads exactly like a Board where everybody
has voted recently.

Ask each member at the meeting when they joined and record it as
`YYYY-MM-DD`. An approximate month is better than an empty field, because
the window the rule counts is twelve months long and a proposal is only
ever a prompt for the annual meeting to consider — nothing is applied
automatically. Do not fill these in from guesswork beforehand: a date
nobody confirmed would start a silence the member never had.

Once the dates are in, run `cd tools && uv run convener-sweep` and read what it
prints under `Board inactivity (G-09)`. Nothing there is applied; it is the
list the meeting discusses.
