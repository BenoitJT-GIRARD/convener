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
`uv run --frozen python scripts/generate_changelog.py`
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
- a `- **A session did not survive a reload, and D-03 did not say so.** In an
  operator’s own words, standing an instance up: refreshing the page, leaving it
  or going back signed them out and made them do the GitHub code again. The
  access token lived in React state and nowhere else, so every one of those
  was a full device flow. D-03 argues for that flow on friction — on a
  non-technical population, onboarding friction is what determines whether the
  tool gets used at all — and its Cost section recorded only how long the
  token lasts, which is a different question from what a session survives.

  It is held in `sessionStorage` now: a reload, a back navigation and an
  ordinary tab restore cost nothing; closing the tab still ends it, and a
  second tab signs in on its own. `localStorage` is what it is deliberately
  not — that would outlive the tab, the day and the person at the machine, on
  an application whose repository holds participants’ personal data. It is no
  defence against a script running on this origin, which reads a state
  variable as easily as a storage key; what it changes is how long the token
  outlives the page. D-03’s Cost section now says all of that.

  One thing came out of it that was not in the report. The startup check
  treated a token GitHub refused and a GitHub it could not reach as the same
  outcome, so an outage signed everybody out. `checkToken` separates the
  three now, and only a refusal discards the session — measured against a 502,
  on a day GitHub was returning 5xx from its authorization endpoints.
- a `- **The settings screen was the one write surface that never asked the
  role.** Every other one asks it, and this is the screen that settles how the
  instance runs: the Actions allowance and the alarm before it is exhausted,
  the routing every registration passes through, the submission-queue alarm.
  Measured on a live instance, two of the five repository admins are exactly
  the organizer the product models, and could change all three from that
  screen. The fields are read-only for anyone but the Board now, and the
  control is refused rather than merely hidden.

  Read-only rather than disabled, because seeing what the instance is set to
  is the part an organizer keeps, and a disabled input is skipped by keyboard
  navigation and reads as broken rather than as somebody else’s to change.

  The sentence that appears says it is a division of responsibility and not a
  lock, which is the honest limit: an organizer holds write access and can
  edit those three files on GitHub whichever way this screen renders. It is
  stated here because there is nowhere else to state it — GitHub refuses
  branch protection and rulesets on a private repository on the free plan,
  the shape D-15 asks a cockpit to have, so the CODEOWNERS file the
  standing-up sequence writes is advisory on every instance shaped the way
  the sequence shapes it. That step now says so, and says why to set it
  anyway.
- a `- **The cockpit wrote a new speaker with its id last of thirty-five keys.**
  Every other writer puts `id` first, `data/validate.ts` included, which is
  the model's own order. The screen built the record by spreading the form
  fields and appending the id afterwards, and `data/yaml.ts` dumps with
  `sortKeys: false` — deliberately, because that is what keeps the bytes
  matching PyYAML — so construction order was file order. Nothing to a
  parser; the cost is a diff. The next Python-side rewrite of such a record
  re-emits it in canonical order and moves the whole thirty-five-line block
  for a change that touched one field, on a file whose review is part of the
  governance.

  The agreement between the two writers was pinned one step downstream of
  where it broke: the boundary fixture holds the two sides' YAML output together
  and never sees the record this screen constructs. It is read from the bytes
  the screen actually sends now, against the same record after
  `data/validate.ts` has rebuilt it — neither side writes the order down, so
  a field added to the model and forgotten here lands red on its own.
- a `- **One transient failure and the volunteer became the retry loop.** The
  cockpit's single write path replayed a conflict and nothing else, so a 500,
  502 or 503 was final on the first click: an operator creating a lead on a
  live instance was told *"GitHub is not responding"* and got through by
  pressing the button at intervals until it worked. Twenty-two modules reach
  that path — creating a lead, moving a status, recording a ballot, setting
  consent, saving settings — and each was one attempt per click.

  Transient failures are replayed now, **but only once it is known what they
  did**, which is the part that is not simply "retry a 5xx". A gateway can
  answer 502 after the commit already exists, and no caller's transform is
  idempotent against its own result — creating a lead appends a record and
  derives its id from what it reads — so a blind replay is how one speaker
  becomes two. The next read settles it first: the file holds the bytes that
  attempt wrote (it landed, and the answer was lost on the way back), or its
  sha has not moved (it did not land, replay is safe), or neither, and then
  the failure that actually happened is reported rather than guessed at. A
  refusal — 409, 422 — still replays immediately, because somebody else
  writing is exactly when reading again should not wait.

- **A duplicate merging an update could lose its own records, silently.**
  The boundary gives an instance `instance/data/`, `instance/keys/` and
  `instance/public-data/`, and [taking an update](docs/operating/taking-an-update.md)
  said upstream does not write those paths. That was true while nothing
  upstream had run. It stopped being true the day it did: upstream is itself a
  running instance, and its own scheduled jobs commit into all three — the
  sweep writes the speakers and the queue, retention writes the destruction
  ledger and the event keys, the deploy writes all three projections, the
  certificate workflows write more.

  **And the bad outcome was not a conflict.** Measured on a duplicate one
  release behind: upstream’s own edits went into the duplicate’s
  `instance/data/speakers.yml` with no conflict at all, because the header
  and the records occupy different regions of the file and git applied
  upstream’s hunks in silence. A conflict would have been the good outcome —
  loud, and a person gets to decide.

  The three directories carry `merge=ours` now, which is the resolution the
  decision register already had for the same reason. A file upstream *adds*
  still arrives, because the driver is consulted only when both sides changed
  the same path — measured on the same merge, which created
  `instance/data/queue-watch.yml` normally. The four files upstream maintains
  inside those directories are excepted by name. The reading is taken through
  `git check-attr` rather than by reading the file, because a pattern that
  matches nothing reads exactly like one that works.

- **The merge rules above govern a second merge, and there they destroy
  rather than protect.** Git cannot tell one remote from another:
  `merge=ours` means *this working tree wins*, in every merge the clone
  performs — including `git merge origin/main`, which is what an operator
  reaches for after a refused push. In that merge the clone is the **stale**
  side, because the cockpit writes to `origin` from volunteers’ browsers all
  day. Measured on real commits: a clone two leads behind, one local edit to
  the same file, `git merge origin/main` — both leads discarded, git
  reporting success, nothing in its output naming the file.

  The procedure now opens with `git pull --ff-only origin main`, which
  consults no merge rule at all and makes yours mean the live instance rather
  than a clone that has been sitting. A refused push sends you back to that
  line rather than to `git pull`. Both the page and `.gitattributes` name
  the second merge now; before this, every word written about these rules was
  about upstream.

- **A confirmation said the room link was not set, on the line above the room
  link.** Composed with a live instance’s real records: *The room link for this
  event has not been set yet — we will send it as soon as it is, to this same
  address.* and then, immediately under it, the join URL and the access code.

  The configuration that produced it is the documented one. D-06 is that the
  meeting account **is** a single permanent room; the provider returns no
  per-event link, and `convener-check-config` tells the operator to put the
  joining instructions in `instance/data/config.yml`, one value for the whole
  series. So `zoom_link` is empty by design and the sentence fired on the
  strength of half the test.

  What it cost is not the awkwardness. *We will send it as soon as it is* is a
  commitment made in writing, on behalf of a volunteer team, to every
  registrant — and nothing tracks it: no queue of editions with a pending
  link, no job that notices, no reminder. It misleads the careful reader
  first. Someone who read past the first sentence joined anyway; someone who
  trusted it waited for an e-mail nobody was going to send.

  The claim is made only when both sources are empty now, which is the one
  state in which it is true.

- **Nothing raised the edition counter, so the first edition an instance
  scheduled turned `sh gates.sh` red.** `next_edition_number` appeared in
  five places across both languages and every one of them **read** it. So an
  operator locked their first edition in through the cockpit, the screen
  reported success, and a gate then failed naming a key they had never heard
  of and cannot reach from any screen — with a message that said the instance
  had assigned no edition at all, which was the opposite of what had just
  happened.

  Nothing was broken by the stale value: `nextEditionCode` walks past
  whatever codes are taken, so no duplicate code was ever possible. The guard
  is still right to fail. The counter is a high-water mark rather than a count
  of rows — it is the one thing left in the repository that a renumbering
  would have to go through, and the reason it exists is that rows can be
  cleared while editions stay on posters and in sent mail.

  The cockpit raises it now, in the same act that assigns the code, and it
  raises it as a **maximum** so a replay against fresher data can never lower
  it. The record is written first and the counter second: a counter raised
  first on a record that then failed would burn an edition number nothing
  used, which shows up on a poster and cannot be taken back, while a counter
  that lags is exactly the state this fixes — visible, loud, and repaired by
  the next lock-in. The assertion now says what actually happened, and where
  to look.

- **The e-mail stopped denying the room link; the runbook step went on doing
  it.** `artefacts.ts::room` asked the per-event `zoom_link` alone, which on a
  permanent-room account is empty by design — so at the very step where a
  volunteer prepares the seminar the screen read *No room link is on this
  record yet*, while the confirmation e-mail for the same edition carried the
  link. Before the e-mail was fixed the two were wrong together, which is why
  neither was noticed; afterwards they disagreed, and the surface a person
  checks before the event was the wrong one. It reads both sources now, like
  the e-mail. And when the per-event field is only a second spelling of the
  series one, both surfaces print it once instead of twice.

- **Two runbook steps ticked a fact they never captured.** *Meeting link in
  hand* and *Forum announcement seeded* were checkboxes. A volunteer ticked
  that the link was in hand and the record still had no link; the step below
  then reported it missing, and the confirmation e-mail sent nothing. The
  same for the thread, which the speaker reminder interpolates three days
  before the talk. Both are fields now, the shape the `approved` phase
  already uses for the two host names — which also means a host who is an
  organizer can record them: the only place either could be typed was the
  Admin override panel, and that opens for the Board alone.

- **The speaker was sent the wrong hour, and a promise nothing keeps.** The
  reminder hard-typed *12:30 CET* and *12:20* while `speaker.time` sat on the
  record, so any series running at another hour sent its speaker the wrong
  time in the message whose whole job is to get them into the room — silently
  wrong, which a blank would not have been. `toolkit/index.md` already states
  the rule it broke: read `{{ speaker.when }}`, which computes the real Paris
  offset for that day, and never write `{{ speaker.time }}` beside a hand-typed
  zone. Two templates did. Both read `when` now.

  The same reminder asked the speaker to join a room it did not name; it now
  points at the joining details they already hold, from registering for their
  own talk at T-14. And the T-21 message promised *we will send you the links
  as they go out* — a commitment in writing that no step of the runbook ever
  came back to. It promises what actually happens instead.

### Before you merge this` section, in **every** entry, naming each
  path from the two lists above that the release touched and what the
  operator does about it. An entry whose answer is that there is nothing to
  do says that in as many words: an operator has no way to tell a silence
  from an omission.

`tools/scripts/generate_changelog.py --check` holds three of those: that
every entry carries the section, that no entry names a path under it which
the declaration says is upstream's, and that the versions descend without
repeating.

## 1.1.0 — 2026-09-12

The first release after 1.0.0, and almost all of it comes from one thing:
somebody stood an instance up by following
[`docs/operating/standing-up.md`](docs/operating/standing-up.md) end to end,
as an operator with no knowledge of how any of this was built. Twenty-one
defects came out of that walk. Nineteen are fixed here.

**Two of them would have broken a seminar**, and neither was visible to any
test, because both were about what a third-party service actually does
rather than what this repository believes about it.

- **Taking the register worked nowhere.** The meeting provider's calls
  endpoint moved to a `{calls: [...]}` envelope and this code accepted only
  a bare array. That path runs once an event exists, so the first time any
  duplicate exercised it would have been the day of its first seminar, with
  a room open. The error now also names the keys that did arrive — the old
  one described the failure without describing the response, which is why
  it went unnoticed.
- **Every published proposal form was missing `phd`.** Tally enforces an
  undocumented length limit on a dropdown option's `placeholder` and drops
  the whole option carrying one that is too long — silently, with the API
  returning success. A PhD student had no way to say so. The gloss rides in
  a block of its own now.

**Nothing this software calls could reach it.** `urllib` sends
`Python-urllib/3.x` when nothing else is set, and Cloudflare refuses that
string with a 403 the origin never sees, so the failure reads as an
authentication problem it is not. The header is stated once and a sweep
refuses a call site that does not send it. The relays had carried one from
the day they were written; the lesson had never crossed into Python.

### New

- **An event key is minted by a machine now, not typed by a person.** It was
  the last per-event manual step on the whole journey: for every edition that
  takes registrations, somebody opened a Python shell, called
  `eventkeys.generate()`, pasted the private half into a repository secret
  through a browser, committed the public half, and waited for the showcase to
  republish. Twelve times a year on a monthly series.

  With a mandatory order and an unrecoverable failure if it is broken.
  Publish the public half before the private secret exists and every
  registration accepted in that window is told sent, genuinely encrypted, and
  can never be read again — the job that would read it fails closed for ever,
  and nobody finds out until the certificates fail weeks later. A procedure
  with those properties should not depend on somebody getting two browser tabs
  in the right sequence.

  `.github/workflows/mint-event-keys.yml` runs every morning and mints for
  any edition that has reached `scheduled` with no public half published. It
  adds no party that did not hold these keys already — every decrypt already
  runs in a runner with `CONVENER_EVENT_KEY_<ID>` in its environment, and
  `retention.yml` already deletes these same secrets under the same token,
  whose Secrets permission is read *and* write. It removes four surfaces the
  manual route touched: a terminal, a clipboard, a browser form and a shell
  history.

  The order is structural rather than documented: the private half is piped
  straight into `gh secret set` and reaches no file and no log, the secret is
  confirmed by re-listing rather than by an exit code, and the public half is
  copied into place only after that. It never mints twice for one edition,
  because a published public half means a live key and a second pair would
  leave the first edition’s registrations unreadable.

  The signing key stays the deliberate opposite, and `operations.md` says why
  in both places now.

- **A notice before a credential expires.** Four watchdogs already watched
  things that *stop*; none watched a thing that *expires*, and an expiry
  gives no signal until it is too late. The meeting token is the worst of
  them — it falls back to the manual adapter and says nothing at all. Dates
  are declared in `instance/data/credential-renewals.yml` and the daily
  sweep posts to the board thread a fortnight ahead. See *Before you merge
  this*.
- **A thank-you page on the proposal form**, emitted by the builder rather
  than added in Tally's editor — where the next run of the form command
  would have erased it, along with anything else a volunteer added there.
- **The proposal form is drawn in your charter.** It was the one surface
  carrying this project's identity that nothing generated and nothing
  checked — the first thing a stranger proposing a talk sees, wearing
  Tally's factory palette beside a showcase in your own colours, unless
  somebody remembered to dress it by hand. The five colours Tally offers now
  come from `instance/data/brand.json` and are re-asserted on every run of
  the form command. Measured against the live service: the published page
  served none of the charter's colours before and serves the dominant most
  of all after, with no re-publish.
- **[Taking an update](docs/operating/taking-an-update.md)**, which is the
  command this product is built around and had never written down.

### Fixed

- **The Actions budget alarm measured nothing.** It read the minutes GitHub
  *charges*, which inside an included allowance are zero — so it reported
  all was well, from a real number, and could not fire before the allowance
  was spent. It reads each job's own elapsed time now.
- **CodeQL turned every duplicate's security workflow red** from its first
  commit, burying the gitleaks job beside it. It now runs where it can run
  and stops where it cannot.
- **The Board was a team created in an optional step**, while two mandatory
  things read its handle. It is made with the organisation now, and given
  Write on the cockpit at the step where the cockpit exists.
- **The salt behind every matching code licensed any generator**, on the one
  value the sequence forbids rotating. Three exact commands now, Python
  first, and `Get-Random` named as the trap it is.
- **Every documented command rewrote `tools/uv.lock` as you typed it.**
  `gates.sh`'s header states the rule — an unfrozen `uv run` rewrites the
  lockfile, which is a change to the environment made by the act of checking
  it — and `gates.sh` was the only thing that followed it. 133 invocations
  across 46 files now carry `--frozen`, and a reading in
  `test_typed_commands.py` refuses the next one that does not. The lockfile
  also names the version `pyproject.toml` names, which it had stopped doing. And
  because `--frozen` prevents a rewrite without detecting a stale lockfile,
  the signal that freezing removed is a reading of its own: the lockfile is
  held against `pyproject.toml`'s version, which is the one field that can
  drift in silence.
- **A step asked for a control that does not exist.** `dependency_updates`
  sent an operator to a Settings toggle for Dependabot version updates, and
  GitHub replaces that toggle with a *Configure* button whenever
  `.github/dependabot.yml` is present — which a duplicate inherits two steps
  earlier. No endpoint exposes it either, so the step could never have been
  walked to its end on a real duplicate. It is a file edit now:
  `open-pull-requests-limit: 0` on each entry, measured on two repositories
  differing only by those lines.
- **The only monthly step had no written procedure.** The provider hides its
  OAuth flow in prose inside an OpenAPI description; it is in
  [`operations.md`](docs/operating/operations.md) now, measured.
- Four readings only the example instance could satisfy, a stale assertion
  no duplicate could pass, and two configuration headers that contradicted
  the values a duplicate had just written under them.
- **A reading measure had been put on things nobody reads.** The showcase's
  colophon, the demonstration banner and the unconfigured banner were capped
  at a character count, which froze them: measured at six viewport widths,
  none moved a pixel between 820px and 1920px while the page around them
  grew by 1 100px. The cockpit's own footer had it right all along and this
  repository carried a comment arguing for the difference. A plate takes the
  width; a text somebody reads keeps a measure. The cockpit's explanatory
  paragraphs now move too, between 521px and 658px instead of standing at
  521px everywhere.
- **`sh gates.sh` needed six trees installed and named three.** Its header
  listed `app/`, `site/` and `tools/`, and said they were ordered for a
  reason a page states — no page states one, and the trees are independent.
  The three relays were the ones it left out, so `relays` and `audit` both
  died on `'vitest' is not recognised`, a message naming neither the missing
  install nor the tree it was missing from, for anyone who followed [taking
  an update](docs/operating/taking-an-update.md) straight to the runner
  after a merge. That page carries the list now as well, and both are held
  against `.github/workflows/quality.yml`'s own `Install …` steps — the one
  place that cannot go stale, because a workflow cannot check a tree it has
  not installed. The commands run from the repository root and chain nothing,
  because Windows PowerShell 5.1 refuses the operator that would.

- **A high-severity alert that read as a false positive and was not
  entirely one.** CodeQL reported the credential watchdog logging a secret
  in clear text. It reads the *name* of a field, and that field held a
  credential's name — `CONVENER_MEETING_API_TOKEN` — never its value;
  naming the credential about to expire is the whole point of the watchdog.
  So far, a false positive.

  What nobody had checked is that the field would go on holding a name.
  Nothing structural stopped a credential being pasted under `secret:` in
  `instance/data/credential-renewals.yml` — the only defence was a sentence
  in that file's own header, and a convention nobody can check is a
  convention that drifts. Here it drifts into a credential committed to a
  repository whose duplicates are public by design, and then read aloud by
  the watchdog into a run log. The loader now refuses anything not shaped
  like a repository secret's name, and that one refusal deliberately says
  nothing about what it read: if what was written there is the credential,
  this message is bound for the same log. Every other message in the module
  may name the secret, because by the line that raises them it is a name.

  The field is `secret_name` now — what it always held, and the word the
  code already used one line below it. The declaration's key stays `secret`:
  it reads correctly in YAML and renaming it would break a file every
  duplicate has written. Renaming did not silence the alert, and that was
  measured rather than assumed — CodeQL re-analysed and reported the same
  line, because the heuristic reads the word and an accurate name keeps it.
  What changed is the thing the alert was pointing at without being able to
  see it. The alert itself is dismissed on that record. A suppression
  marker was tried first and is not worth trying again: code scanning
  ignored it and the alert simply moved down the file with the line,
  closing at the old position and opening at the new one — which reads
  like a fix and is not one. No duplicate ever sees any of this:
  `security.yml` runs CodeQL only where the repository is not private,
  and a cockpit is private by design.

### Before you merge this

- **Take this release's merge rules before you merge this release.** Git
  reads `.gitattributes` from your working tree, so the merge that *brings*
  `merge=ours` is judged by the file it is about to replace — and that one
  does not have it. Measured: the plain descent, with the driver configured,
  still took upstream's edits into the duplicate's own
  `instance/data/speakers.yml` in silence; taking the file first left the blob
  identical. Once, for this release only:

  ```sh
  git config merge.ours.driver true
  git fetch upstream
  git checkout upstream/main -- .gitattributes
  git commit -m "repo: take the merge rules before merging"
  git merge upstream/main
  ```

  After this release the rules are already in your tree and an ordinary
  `git merge upstream/main` is enough. If you have already merged without
  doing this, check `git diff` on `instance/data/` and `instance/public-data/`
  in that merge: anything upstream changed there is upstream's example
  instance, and yours is the version to keep.

- `instance/data/credential-renewals.yml` — **new, and it arrives empty.**
  Nothing about the merge needs doing first and nothing breaks if you leave
  it: an instance that declares no date is an ordinary state, said out loud
  in every run's log rather than passed over. But it is empty because
  upstream cannot know your dates, and it is the file that turns "somebody
  has to notice" into the thing that notices. Write one line per credential
  that expires, at the next renewal of each.

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
