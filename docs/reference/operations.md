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
  proposal is empty — by design, not by accident.
- name a member who declared an absence covering today, or one carrying a
  nomination the Board has not settled. Either of those is a live question
  already.
- take the Board below three members able to vote (decision G-03). Members
  it holds back for that reason still appear in the output, so the meeting
  reads the same list either way. The floor is three, never `board_min`,
  which is knowingly wrong until the September merge above.

## After the September collaborators' meeting

Two changes to the governance data are deliberately deferred until the
collaborators' meeting in September. They are a deferred configuration in
the sense of decision D-13 — the state below is normal and expected, not a
defect to be rediscovered and not something to fix piecemeal beforehand.
Both changes touch `data/config.yml` and `data/speakers.yml`, and they are
easiest done together, in one commit, with `cd tools && uv run convener-validate`
run before it is pushed.

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

`board_min` is `5` in `data/config.yml` and must become `3` in the same
change, or validation fails with `board has 4 members, outside
board_min..board_max`. Three is the floor set by decision G-03: a vote is
suspended rather than decided below three eligible members, so the Board
must never be declared smaller than that.

Rewrite the ballots of whichever identifier disappears to the surviving
one. If any lead ends up with two ballots from the merged person, keep one:
one person casts one voice, and a repeated voter is a validation error.
No lead carries ballots from both identifiers at the time of writing —
`Anonymous` has never voted — but confirm it rather than assume it.
