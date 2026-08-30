# Standing up an instance

*This page is generated from* `STANDING-UP.yml` — *the one
declaration of this sequence, which the agent that carries it out reads too.
Do not edit it: run* `uv run python scripts/generate_standing_up_doc.py` *from* `tools/` *and commit what it writes,
and continuous integration refuses a page the declaration does not derive.
Every step, actor, check, command and degradation below comes from that file;
what an absent integration costs comes from*
`config/integrations.yml`*, which* `convener-check-config` *already
prints. The prose between the steps lives in*
`tools/scripts/generate_standing_up_doc.py`*.*

Everything else written here is written for an instance that already exists.
This page is the other half: what somebody with no repositories and no
accounts does, in order, to have a seminar series running at the end of it.

**It costs nothing, and it needs nothing installed.** Every step below can be
carried out with a web browser and a text editor. Where a command is faster it
is given, and the browser equivalent is given beside it — an operator who
cannot install a command-line tool, or will not, is not a second-class reader
of this page. Every account it asks for has a free tier that this project fits
inside; none of them asks for a card.

**Nothing here depends on anybody's goodwill.** Each account belongs to the
organisation rather than to a person, each credential is written into a store
two people can open, and the whole of it can be handed to a successor by
transferring two repositories. That is not a nicety — it is the constraint
the rest of the design follows from.

Read it once before starting. The order matters in five places, each of them
noted where it arises, and reordering those is the difference between a
working instance and one that has published something it cannot take back.

## The two repositories, and why they are two

| Repository | Visibility | What it is |
|---|---|---|
| `cockpit` | private | The instance itself: the code, the workflows, the participant records, and every secret. Private because `instance/data/speakers.yml` and the per-event registration files hold personal data, and a repository holding those cannot be public. Created as a new repository of your own, never as a fork — repositories in one fork network share an object store, so a commit pushed to a private-looking fork stays reachable from the public parent for ever, and no setting inside the fork closes that route. |
| `showcase` | public | The publication target, and nothing else. GitHub Pages will not serve a private repository without a paid plan, which the no-cost constraint rules out, so continuous integration in the cockpit builds `site/` and `app/` and pushes the result into this repository's root. Nobody edits anything here. Every byte is reproducible from the cockpit, so losing it costs a rebuild. |

The split is forced, not preferred, and
`docs/decisions/d-15-publication-topology.md` is the argument in full. Both
exist before anything else works.

## How to read a step

Each step says who has to carry it out, what it does, what proves it is done,
and what an instance loses by skipping it.

**Who.** A step marked *a person* has no other option: either the flow exists
only in a browser and has no interface anything could call (creating a
mailbox, registering a GitHub App, minting a personal access token), or the
value it produces must never exist anywhere but in the hands of whoever minted
it. A step marked *an agent, or a person* is a file edit, a command or an API
call, and it makes no difference which of you does it.

**Proves it is done.** Stated so that a browser is enough to read it. A step
with a command carries it underneath; the command is faster, never required.

**Without it.** What the instance loses. For most of these the answer is a
feature that degrades visibly and nothing else — an absent integration is a
normal state in this project, not an error, and an instance that stops
halfway down this page is a working instance. The steps where that is *not*
true say so in those words.

**Run the report.** `cd tools && uv run convener-check-config` prints every
integration this product declares, what each one is waiting on, and what
happens meanwhile. It is the same source the *Without it* paragraphs below
quote, so it is worth running before the first step and after each of the
later ones.

## Stage 1 — Nothing exists yet

Three things that have to be somebody's before anything can be created under
them, and one rule that governs all three: no account this instance depends on
is ever created with a personal address.

### 1. An address the organisation owns

**Who:** a person.

Create an email address that belongs to the series rather than to a person,
and use it for every account this sequence creates. Any provider with a free
tier will do; nothing here depends on which one.

**Proves it is done.** Sign in to it from a private browser window using only
what is written in the shared store below, and have a second Board member do
the same. An address only one person can reach has not been created yet,
whatever it says on the mailbox.

**Without it.** Every account below ends up tied to one person's own mailbox,
and the series continues only for as long as that person stays reachable and
willing. This is the mechanism behind D-11, and it is the one step in this
sequence that cannot be corrected later without recreating everything
downstream of it: password resets go to the mailbox, so whoever holds the
mailbox holds the instance.

**In a browser, in full:**

1. Choose a provider with a free tier. Nothing in this project reads the
   mailbox; it receives password resets and it is what other accounts are
   created under.
2. Create the address under the series' own name, not a person's — the form
   organisers would put on a poster.
3. Set recovery to something the organisation controls too. A recovery address
   belonging to one volunteer reintroduces exactly the dependency this step
   removes.
4. Write the address and its password into the shared store, in the next step,
   before creating anything else with it.

### 2. A store two people can open

**Who:** a person.

Create the shared password store that every credential below is written into —
a file in the organisation's existing shared drive, or a password manager the
Board already uses. Never in this repository, and never in one person's
browser.

**Proves it is done.** A second Board member opens it, unaided, and finds the
mailbox credentials from the step above already in it.

**Without it.** Credentials survive only in the browser profile of whoever
created them. A handover then loses the workers, the public form and the
mailbox at once, and none of the three can be recovered from this repository,
because nothing about them is in it. D-11 rejects storing them here even in
the private repository, and that ruling is what leaves this step with no
alternative.

**In a browser, in full:**

1. Decide where it lives — the organisation's shared drive, or a password
   manager the Board already pays nothing for. Do not open a new subscription;
   there is nothing here a plain encrypted file cannot do.
2. Create it, and set a master password that is not any individual's own.
3. Share that master password out of band with two or three Board members, not
   one, and not over the mailbox the store protects.
4. Never commit it. It is not in `.gitignore` because it is never in this
   directory tree at all.

### 3. The GitHub account or organisation the repositories sit under

**Who:** a person.

Create the GitHub account, or the organisation, that will own both
repositories, using the address from the first step. The free tier is the tier
this project is designed for; nothing below needs a paid plan.

**Proves it is done.** Signed in as that account, the *New repository* button
offers it as an owner. If a team of people will run the series, an
organisation is what makes that possible without sharing one login.

**Without it.** There is nothing to create the two repositories under, so the
sequence stops here. An organisation rather than a personal account also
decides whether the Board can ever be a team rather than a list of names: the
board-notification step below needs an organisation team, and a personal
account has none.

**In a browser, in full:**

1. Sign up at github.com with the address from the first step, or sign in if
   it already has an account.
2. If more than one person will ever run this series, create an organisation
   as well — Settings → Organizations → New organisation, and choose the free
   plan.
3. Store both logins and their recovery codes in the shared store.
4. Turn on two-factor authentication. GitHub requires it, and the recovery
   codes belong in the store beside the password.

## Stage 2 — The two repositories

Both, in this order, with the visibility each one needs from its first commit.
A repository created public and made private afterwards has already published
whatever it held.

### 4. The private repository, duplicated and never forked

**Who:** an agent, or a person.

Create a new private repository of your own and put this repository's contents
in it, with no fork relationship to the product. GitHub offers *Fork* as the
obvious action and it is the wrong one here: a fork of a public repository
cannot be made private, and repositories in one fork network share an object
store, so a commit pushed to a fork stays reachable from the public parent
permanently and after the fork is deleted.

**Proves it is done.** The repository's own page shows *Private* and carries
no *forked from* line under its name. Both have to be true; either one alone
is not the thing being checked.

```bash
gh repo create <owner>/<name> --private --source=. --remote=origin --push
```

**Without it.** Nothing else in this sequence has anywhere to live. Done as a
fork instead, or created public and made private afterwards, it publishes
participants' names and addresses by a route nobody would think to check — and
no setting inside the repository closes that route once it is open. D-15 has
the reasoning in full.

### 5. The public repository the site is published into

**Who:** an agent, or a person.

Create a second repository, public and empty. Nothing is authored in it ever:
two workflows in the private repository push into its root, each touching a
subtree the other never reads. Do not initialise it with a README — Pages will
serve that README rather than the site until the first real publish lands,
which is a failure that returns 200.

**Proves it is done.** The repository exists, is public, and its file list is
empty.

```bash
gh repo create <owner>/<name> --public
```

**Without it.** Both publishing workflows have nowhere to push, so there is no
public site: no registration page, no certificate verification page, and no
cockpit for anyone to sign in to. The deploy token in the publishing stage
below also has nothing to be scoped to.

### 6. Pages, on the public repository only

**Who:** an agent, or a person.

Turn GitHub Pages on for the public repository, serving from a branch rather
than from an action: Settings → Pages → Source = *Deploy from a branch*,
branch `main`, folder `/ (root)`. Pages stays off on the private repository,
and there is nothing to enable there.

**Proves it is done.** Settings → Pages names `main` and `/ (root)`, and shows
the address the site will be served at. That address, with its trailing slash,
is what the next stage writes into `instance/config.json`.

**Without it.** Nothing is served, or — worse, and this is the failure this
project has already met once — the wrong thing is served with no sign of it. A
push that reaches a branch Pages is not configured to serve leaves Pages
rendering the repository's own README instead, and a bare request answers 200
over a site that does not exist. Read the served page's source, not its status
code.

## Stage 3 — The three files a duplicate edits

What makes the instance yours rather than the worked example's. Until these
are done the showcase prints a band above its masthead and the cockpit prints
one above its sign-in screen, naming the keys still to fill in.

### 7. Who is publishing, and where

**Who:** an agent, or a person.

Edit `instance/config.json`: the published address and its trailing slash, the
edition prefix your talks are numbered under, and the nine identity values a
stranger reads — the organisation and its short form, the series, its
strapline and its tagline, the forum, the contact address, the proposal form,
and the cockpit's own repository. Leave `proposal_form` as it is for now; the
intake stage writes it once the form exists. Then correct the one product file
carrying a value derived from this one that nothing can derive for it:
`.github/CODEOWNERS` names the team every review request goes to as
`@<organisation>/editorial-board`, and `<organisation>` is the owner half of
the repository just declared. GitHub parses that file itself, before any code
of this project's can run, which is why it holds a literal at all.

**Proves it is done.** After the first publish, open any page of the showcase
and the cockpit's sign-in screen: the band naming unfilled keys is gone from
both. The band compares each value against the worked example's own
declaration, value by value, so a half-filled file still shows it and names
exactly which keys are left. `.github/CODEOWNERS` has a check of its own, and
it answers long before the first publish: the command below refuses any
organisation but the declared one.

```bash
cd tools && uv run pytest tests/declaration/test_published.py -k literals
```

**Without it.** The showcase and the cockpit both announce that they are not
configured, on every page, which is correct and is the point. Worse than the
band is what the band exists to prevent: the published address is what every
other address in this project is derived from, so a duplicate that renames the
organisation and leaves that address alone publishes under somebody else's
prefix while every page reads as its own. An uncorrected `.github/CODEOWNERS`
degrades the other way, quietly: every review request goes to a team in an
organisation this repository does not own, GitHub resolves it to nobody, and
the pull request waits for a review that cannot arrive.

### 8. The Board, the season and the bar a vote is measured against

**Who:** an agent, or a person.

Edit `instance/data/config.yml`: the Editorial Board's GitHub logins, the
season, and the thresholds a vote is counted against. Logins, not names — the
cockpit asks GitHub who is signed in, and a first name is not an answer to
that question.

**Proves it is done.** `convener-validate` exits 0, and the *Validate data*
workflow is green on the commit that changed the file.

```bash
cd tools && uv run convener-validate
```

**Without it.** The Board screen has nobody on it, no ballot can reach a
threshold, and both gates — approving a speaker, publishing a recording — are
unpassable, so the pipeline stops at its first decision. An identifier that is
not a GitHub login is the specific half-done state this repository has met
before: the file is valid, the person exists, and the cockpit still does not
recognise them when they sign in.

### 9. Your own records, starting empty

**Who:** an agent, or a person.

Empty `instance/data/speakers.yml`. A duplicate starts with no speakers and no
events; the file that ships holds the worked example's invented reading group,
which exists to prove the product can be built as somebody else and for
nothing else.

**Proves it is done.** `convener-validate` exits 0 on the emptied file, and
the showcase's archive page lists nothing.

```bash
cd tools && uv run convener-validate
```

**Without it.** Your showcase publishes an invented series' sessions as though
they were yours: three events with dates, an archive page, and a feed
announcing them. Nothing warns about it, because a file full of well-formed
records is exactly what this file is supposed to hold.

## Stage 4 — Getting a public site

The first real deployment, and the first honest answer to whether any of the
stage above is right. Nothing until now has been verified against anything a
visitor can open.

### 10. The token that lets the cockpit push into the showcase

**Who:** a person.

Mint a fine-grained personal access token scoped to the public repository
alone, with *Contents: read and write* and nothing else, and set it as a
repository secret on the private repository. GitHub offers no API that mints
one, which is why this is a person's step.

**Proves it is done.** The secret is listed under the private repository's
Actions secrets. Its value cannot be read back — GitHub shows only that it is
set, and that is the check.

**Without it.** Neither publishing workflow fails. Each logs a line and exits
cleanly at its own first push step, so the Actions tab shows green runs while
nothing is pushed anywhere and there is no public site at all. There is no
fallback publishing route, and nothing about the green run says so.

**Credentials.** `VITRINE_DEPLOY_TOKEN`

**In a browser, in full:**

1. Signed in as the account that owns both repositories, open Settings →
   Developer settings → Personal access tokens → Fine-grained tokens →
   Generate new token.
2. Name it for what it does, so the next person can tell what breaks if they
   revoke it.
3. Under *Repository access*, choose *Only select repositories* and pick the
   public one. Not the private one — this token pushes the built site outward,
   and giving it the repository holding the records would hand a write
   credential to the data.
4. Under *Repository permissions*, set *Contents* to *Read and write*. Leave
   every other permission alone.
5. Set an expiry you will actually notice, and put the renewal date in the
   shared store beside the token.
6. Generate it, copy it once, and paste it into the private repository's
   Settings → Secrets and variables → Actions → Secrets → New repository
   secret, named `VITRINE_DEPLOY_TOKEN`. Then paste it into the shared store.
   GitHub will not show it again.

### 11. The first publish, and reading it in a browser

**Who:** an agent, or a person.

Run *Publish vitrine* and *Deploy app* from the private repository's Actions
tab, and then open what they produced. This is the first moment anything in
this sequence has been checked against a deployment rather than against a
local run.

**Proves it is done.** All four addresses answer, and the showcase's page
source carries no Jekyll generator tag. A build served from a bare local root
is not a preview of this — the path prefix is baked in at build time, so a
page that resolves locally and 404s once published is the defect D-26 exists
to catch, and only the deployed page can catch it.

**Without it.** Every later step in this sequence is verified against a site
nobody has opened. The two failures this stage is here to surface — a Pages
source pointing at a branch nothing pushes to, and an address written into
`instance/config.json` that does not match the one Pages serves — both look
like success from inside the repository, and both are obvious from one browser
tab.

## Stage 5 — The three workers

Sign-in, registration intake and proposal intake each need an edge worker, and
all three deploy to one free Cloudflare account. Two of them also need a
storage namespace, which does not exist until it is created and cannot be
shipped filled in.

### 12. The GitHub App that signs volunteers in

**Who:** a person.

Register a GitHub App under the account or organisation from the first stage,
with device flow enabled and *Contents: read and write* on the private
repository and nothing else. There is no API for registering an App: it is a
browser form, start to finish, which is why this step is written out in full.

**Proves it is done.** The App's own settings page shows *Enable Device Flow*
ticked, one repository permission, and a client id beginning `Iv`. The client
id is not a secret — it ships inside the browser bundle by construction — and
it is what the next steps set as a repository variable.

**Without it.** Half of the sign-in relay is missing, so the relay row stays
absent whatever else is deployed, and every volunteer signs in with a personal
access token they have to mint themselves. Nothing is broken; onboarding is
simply slower, and each volunteer ends up holding a credential the
organisation did not issue and cannot revoke centrally.

**Credentials.** `VITE_GITHUB_APP_CLIENT_ID`

**In a browser, in full:**

1. Open Settings → Developer settings → GitHub Apps → New GitHub App. Use the
   organisation's settings if the repositories are owned by an organisation,
   so the App belongs to the organisation and not to you.
2. Give it a name — it appears on the sign-in screen — and set the homepage
   URL to the published address from the publishing stage. This is a setting
   no test and no workflow will ever notice drifting, so it is worth getting
   right now.
3. Leave the callback URL empty and tick *Enable Device Flow*. The device flow
   is what lets a static page sign somebody in without a server; it is D-03's
   whole subject.
4. Untick *Webhook → Active*. This App receives nothing.
5. Under *Repository permissions*, set *Contents* to *Read and write*. Set
   nothing else, and in particular not *Issues*. The board notifications are
   posted by the workflow's own token, so *Issues* here would be a permission
   nobody uses on a repository holding personal data.
6. Under *Where can this GitHub App be installed*, choose *Only on this
   account*.
7. Create it, then use *Install App* to install it on the private repository
   alone.
8. Copy the client id from the App's settings page into the shared store.
   Generate no client secret. The device flow does not need one, and the relay
   is deliberately secret-free.

### 13. The Cloudflare account, and the token CI deploys with

**Who:** a person.

Create a free Cloudflare account with the organisation address, and mint an
API token that can edit Workers. All three workers deploy to this one account.
Creating the account and minting the token are both browser flows.

**Proves it is done.** The token is listed on Cloudflare's API Tokens page as
active, and it is set as a repository secret on the private repository.

**Without it.** None of the three workers can be deployed by continuous
integration, and each *Deploy* workflow reports that it is skipping rather
than failing — a normal state until the account exists, and indistinguishable
from a quiet day unless you read the job log. Deploying by hand instead needs
Node and a browser login on the machine doing it, which is exactly the
dependency the rest of this project avoids.

**Credentials.** `CLOUDFLARE_API_TOKEN`

**In a browser, in full:**

1. Sign up at cloudflare.com with the address from the first stage. The
   Workers free plan is what this project is sized for; add no domain and no
   paid plan.
2. Open My Profile → API Tokens → Create Token.
3. Use the *Edit Cloudflare Workers* template. It grants exactly what
   `wrangler deploy` needs and nothing that touches DNS.
4. Under *Account Resources*, restrict it to this one account.
5. Create the token, copy it once, and paste it into the private repository's
   Settings → Secrets and variables → Actions → Secrets → New repository
   secret, named `CLOUDFLARE_API_TOKEN`. Then paste it into the shared store;
   Cloudflare will not show it again either.

### 14. The one value in the workers a duplicate has to fill in

**Who:** an agent, or a person.

Two of the three workers keep a counter in a KV namespace, and a namespace
does not exist until somebody creates it: Cloudflare allocates the id, per
account, so it cannot be shipped filled in. Create the two namespaces the form
relay and the signup relay bind to, pasting each printed id over the
placeholder in that worker's own `wrangler.toml`. Nothing else in those
workers is yours to correct. Two values were, and neither is written down
anywhere but `instance/config.json` now: the origin each relay answers
cross-origin requests for, and the repository the form relay and the signup
relay dispatch into. Each deploy workflow derives what its worker needs and
hands it to `wrangler deploy`.

**Proves it is done.** No `wrangler.toml` still holds a placeholder id, and no
worker names either value — an origin written back into a configuration or a
repository written back into a worker's source is refused by
`tools/tests/declaration/test_published.py`, on the Python suite, with no
worker's suite run. Both greps below are anchored on what an assignment looks
like rather than on the name: every one of these files explains in a comment
why the value is not there, so a search for the bare word matches the
explanation and can never come back empty.

```bash
grep -RE "REPLACE_WITH_|^ALLOWED_ORIGIN" services/*/wrangler.toml ; grep -RE "github.com/repos/[A-Za-z0-9]" services/*/src/index.js
```

**Without it.** A failure that is not loud. A KV id left at its placeholder
makes *Deploy form relay* and *Deploy signup relay* skip the deploy and end
green, so nothing is deployed and the Actions tab says everything is fine.

### 15. The two dispatch tokens the relays hold

**Who:** a person.

Mint two separate fine-grained personal access tokens, both scoped to the
private repository with *Contents: read and write*, one for the form relay and
one for the signup relay. Two, not one reused: each worker spends GitHub API
calls against the same hourly budget, and a shared token couples the two
workers' quotas so that a flood of registrations silences the proposal form.

**Proves it is done.** Two tokens are listed on the fine-grained tokens page,
each naming the private repository and no other, and both are in the shared
store. They are set on the workers themselves in the two steps below, not
here.

**Without it.** Neither the registration path nor the proposal path can reach
the repository. A worker without its token cannot turn a submission into
anything, so a participant's registration is accepted by the browser,
encrypted, and then goes nowhere.

**In a browser, in full:**

1. Open Settings → Developer settings → Personal access tokens → Fine-grained
   tokens → Generate new token.
2. Name the first one for the form relay. Under *Repository access* choose
   *Only select repositories* and pick the private repository.
3. Under *Repository permissions*, set *Contents* to *Read and write*. Nothing
   else. The relay sends a repository dispatch and reads one published key
   file; neither needs more.
4. Generate it, copy it once, and paste it into the shared store.
5. Repeat the whole form for the second token, named for the signup relay. Do
   not reuse the first — the reason is a quota, not a permission, so nothing
   will ever warn you that you have.
6. Set an expiry you will notice, and record both renewal dates beside the
   tokens.

### 16. The sign-in relay, deployed and pointed at

**Who:** an agent, or a person.

Deploy the worker in `services/auth-proxy/` — run *Deploy auth relay* from the
Actions tab now that the Cloudflare token is set — and then set two repository
variables on the private repository: the deployed worker's URL, and the client
id of the App from two steps above. Both are variables rather than secrets,
and that is not an oversight: a relay URL and an OAuth client id ship inside
the browser bundle, so a secret would be a secret in name only.

**Proves it is done.** Run the configuration report and read the
*Authentication relay* row: it moves from `absent` to `production`. In a
browser, sign out of the cockpit and reload — the screen offers a short code
rather than a field asking for a token.

```bash
cd tools && uv run convener-check-config
```

**Without it.** *The* **Authentication relay** *row of*
`config/integrations.yml`*, which* `convener-check-config` *prints as this
row's* `meanwhile:` *line. It is maintained there, and quoted here.*

> Sign-in falls back to a personal access token. The team app stays fully
> usable; onboarding is simply slower.

**Credentials.** `VITE_AUTH_PROXY_URL`, `VITE_GITHUB_APP_CLIENT_ID`

### 17. The relay a registration passes through

**Who:** an agent, or a person.

Deploy the worker in `services/signup-relay/` and set its dispatch token as a
Wrangler secret, then set the deployed URL as a repository variable on the
private repository. This worker cannot read what it forwards: the body is
ciphertext the participant's own browser produced under the event's public
key, and the worker holds no private half. Its second route carries the
post-event survey, on the same deployment, with no second variable and no
second secret.

**Proves it is done.** Run the configuration report and read the *Registration
relay* row: it moves from `absent` to `production`. Then the browser check,
which is the one that exercises the worker itself: with the variable set and
the application rebuilt, submit the registration form for an event that has a
published key, and the worker answers 204. Seeing no workflow run at all can
be correct: a registration further from its event than the queue threshold is
written to a queue branch and confirmed on the next daily drain.

```bash
cd tools && uv run convener-check-config
```

**Without it.** *The* **Registration relay** *row of*
`config/integrations.yml`*, which* `convener-check-config` *prints as this
row's* `meanwhile:` *line. It is maintained there, and quoted here.*

> One variable with two consumers in app/src, and one row rather than two
> because -- unlike CONVENER_MATCHING_SALT below -- both consumers have the
> same shape of absence. app/src/islands/signup/SignupForm.tsx reads it for a
> registration and app/src/islands/survey/SurveyForm.tsx for a post-event
> response, the second posting to the same worker's own /survey route instead
> of a second deployment, so there is no second variable to declare. Neither
> island degrades before a participant meets it: the event page still fetches
> that event's published public key, still renders real fields, and the
> browser still encrypts what was typed under that key. The absence is met at
> submit -- after the encryption, before any request -- so the form reports
> "Registration is not open for this event yet" (the survey: "Submitting
> answers is not available yet"), the typed fields are left exactly as typed
> for a later attempt, and nothing at all leaves the browser. It never falls
> back to sending anything in the clear, and there is nothing queued behind
> it: a registration attempted while this is unset is a registration that was
> never made, and the participant is told so rather than left to assume
> otherwise. Ordinary D-13 in shape, and the widest of these rows in reach --
> every registration this project takes passes through this one address. The
> worker's own dispatch credential (CONVENER_DISPATCH_TOKEN) is deliberately
> not a second secret here: it is a Wrangler secret held by the deployed
> worker, never a name any code in this repository reads, and declaring it
> would report it permanently absent everywhere, which is the noise the three
> CI-only secrets are excluded for above. site/src/_data/csp.js reads this
> same variable at build time to admit the relay's origin into the showcase's
> connect-src and omits it when unset, so the policy and the islands agree by
> construction rather than by a second decision.

**Credentials.** `VITE_SIGNUP_RELAY_URL`, `CONVENER_DISPATCH_TOKEN`

## Stage 6 — The public proposal form

The one surface a stranger reaches without being invited. It is built from
code rather than clicked together, so that it can be rebuilt if the account is
ever lost.

### 18. The form account, and the key that builds from code

**Who:** a person.

Create a free Tally account with the organisation address and copy its API
key. The key is used once, from a shell, to build the public proposal form; it
is never a repository secret and never reaches CI.

**Proves it is done.** The key is in the shared store, and Tally's dashboard
shows no form yet.

**Without it.** The proposal form has to be clicked together by hand instead,
which works and cannot be recovered: a form built in the editor cannot be
recreated if the account is lost, and its field labels are matched against
this project's own reader by text, so a label reworded in the editor silently
stops resolving. Building it from code is D-03's argument applied to something
other than code.

**Credentials.** `TALLY_API_KEY`

**In a browser, in full:**

1. Sign up at tally.so with the address from the first stage. The free plan is
   what this project uses.
2. Open the workspace settings and find the API key section.
3. Generate a key and paste it into the shared store. It is a credential like
   any other; it simply never leaves an operator's own machine.

### 19. The relay between the public form and the repository

**Who:** an agent, or a person.

Deploy the worker in `services/form-relay/` and set its dispatch token as a
Wrangler secret. It is a second worker rather than a route on the first
because turning a form submission into a repository dispatch needs a GitHub
token, and the sign-in relay's whole claim is that it holds none. Its shared
signing secret is set in the step below, once the form exists to produce one.

**Proves it is done.** *Deploy form relay* ends green with a *Deploy* step
that actually ran — not the skip message, which is what it prints while a
placeholder id stands — and the worker answers on its own root path.

**Without it.** The public form has nowhere to send a submission. No proposal
becomes a lead, and *Handle proposal* is never triggered, so the intake a
visitor can see is the one part of this project that fails silently on the
visitor's side and leaves nothing on yours.

**Credentials.** `CONVENER_DISPATCH_TOKEN`

### 20. The form, built from this repository rather than clicked together

**Who:** an agent, or a person.

Run the one-shot script that builds the public proposal form on Tally, with
the API key in the environment. It removes the whole of the manual path: every
question, its label, whether it is required, and the closed vocabularies
behind *Gender* and *Career stage* are read from this project's own reader
rather than retyped, so a label renamed on one side breaks a test rather than
breaking the live form. Re-running it finds the form by its title and updates
it in place. The key reaches the command through a `.env` file at the
repository root rather than through the command line, which a shell keeps in
its history and every terminal recording keeps for ever; `.gitignore` already
refuses that file, and the command below deletes it whether the run succeeded
or not, so it exists for one command and no longer. It is the only credential
in this sequence ever put in a file on the machine running these commands:
every other one is typed into a browser or into a prompt that reads it without
showing it.

**Proves it is done.** Tally's dashboard shows one form, in `DRAFT`, whose
questions match the reader's own field list. The script creates it as a draft
deliberately — publishing is the next step, and it is a person's. `.env` is
gone afterwards, whichever way the run ended.

```bash
cd tools && set -a && . ../.env && set +a && uv run python scripts/create_tally_form.py; rm -f ../.env
```

**Without it.** The form is built by hand, which is slower and, more to the
point, unverifiable: the two dropdown questions deliver a closed vocabulary
the reader compares literally, and a respondent whose answer does not match
one of those tokens is recorded as undisclosed, silently, with no log line and
at a steady rate rather than as an edge case.

### 21. Publishing the form, pointing its webhook, and naming it

**Who:** a person.

Open the draft in Tally, confirm the hint text renders under the two
dropdowns, publish it, point its webhook at the deployed form relay, set the
signing secret Tally shows in the two places that verify it, and write the
published form's address into `instance/config.json`.

**Proves it is done.** Submit the form yourself. A new lead appears in
`instance/data/speakers.yml` shortly afterwards, committed by *Handle
proposal*, and the showcase's propose page links the form instead of saying it
is not open yet.

**Without it.** A form that exists and reaches nobody. A webhook pointed at
any path but the worker's root answers 404 and the submission is lost with no
error anyone sees, and a signing secret set on one side only makes the worker
refuse every request outright. Left unpublished, the showcase's propose page
offers the contact address instead, which is a working fallback and not a
failure.

**Credentials.** `TALLY_WEBHOOK_SECRET`

**In a browser, in full:**

1. Open the draft form in Tally's dashboard and read the two dropdown
   questions. Their hint text is placed on each dropdown's first option, a
   location inferred from Tally's own schema rather than confirmed against a
   worked example — if it does not render as a hint, the answers still resolve
   correctly, but a respondent sees a bare token with no explanation. Reword
   the question itself if so.
2. Publish the form. A later run of the build script never touches its
   published state, so this is a one-time check.
3. Do not rename the form in Tally's editor. The script finds it again by its
   title, so a rename makes the next run create a second form beside the first
   rather than update it.
4. Open the form's Integrations → Webhooks and add a webhook pointing at the
   form relay's URL with no path after it. The worker's only route is its
   root; anything else answers 404 and the submission is silently lost.
5. Copy the signing secret Tally shows for that webhook. Set it as a Wrangler
   secret named `TALLY_WEBHOOK_SECRET` on the form relay, and as a repository
   secret of the same name on the private repository. The worker verifies it
   before forwarding anything, and the workflow verifies it again on arrival.
6. Copy the published form's address into `instance/config.json` as
   `identity.proposal_form`, and commit. Until that value is a real address,
   the showcase's propose page reads as not yet open.

## Stage 7 — What protects a participant's record

Three credentials that are not features. Two are minted once and never
rotated; the third is what makes this project's central promise — a key
destroyed on a deadline — happen without anybody remembering to do it.

### 22. The credential that destroys a key on its deadline

**Who:** a person.

Mint a fine-grained personal access token scoped to the private repository
with *Secrets: read and write* and nothing else, and set it as a repository
secret. Destroying an event's key means deleting a repository secret, and the
token a workflow is issued by default cannot delete one whatever permissions
that workflow grants itself.

**Proves it is done.** Run the configuration report: *Retention sweep
credential* moves from `absent` to `production`. Until it does, the scheduled
retention job is red every single day.

```bash
cd tools && uv run convener-check-config
```

**Without it.** *The* **Retention sweep credential** *row of*
`config/integrations.yml`*, which* `convener-check-config` *prints as this
row's* `meanwhile:` *line. It is maintained there, and quoted here.*

> The third exception to D-13, and the strongest one in this project.
> Destroying an event's key means deleting a repository secret, which the
> default GITHUB_TOKEN cannot do no matter what permissions: a workflow grants
> it -- this needs a fine-grained personal access token, scoped to this
> repository, with the Secrets permission set to read and write and nothing
> else. Unlike every other row here, and unlike CONVENER_EVENT_KEY_<ID> above,
> this absence is loud on every single scheduled run, whether or not any event
> is actually due for destruction that day: a retention job that exits 0
> having destroyed nothing must never look, from the Actions tab, identical to
> one that genuinely had nothing to do -- a promise with legal weight deserves
> a red job every day until the credential is set, not a quiet skip. See
> tools/convener_ops/cli.py::retention_sweep and docs/reference/operations.md,
> 'Retention and early erasure'.

This is one of the rows whose absence is not an ordinary state. The report
marks it so, on the row and again in its closing line.

**Credentials.** `CONVENER_RETENTION_TOKEN`

**In a browser, in full:**

1. Open Settings → Developer settings → Personal access tokens → Fine-grained
   tokens → Generate new token.
2. Under *Repository access*, choose *Only select repositories* and pick the
   private repository.
3. Under *Repository permissions*, set *Secrets* to *Read and write*. Set
   nothing else at all — this is the one credential in this project that can
   delete a secret, and every other permission on it is unnecessary reach.
4. Generate it, copy it once, and paste it into the private repository's
   Settings → Secrets and variables → Actions → Secrets → New repository
   secret, named `CONVENER_RETENTION_TOKEN`. Then paste it into the shared
   store.
5. Put its expiry date in the calendar. This token expiring turns the
   retention job red every day until it is replaced, which is the right way
   round, but somebody has to be the one to notice.

### 23. The key that signs a certificate, minted by a person and only once

**Who:** a person.

Generate the certificate signing key pair yourself, interactively, commit its
public half, and paste its private half straight into the repository's
secrets. This is not an automated step and not one to delegate: it mints the
one key every certificate this series ever issues depends on, and it is minted
exactly once by somebody who then holds the only copy of its private half
until it is pasted in and never printed again.

**Proves it is done.** Run the configuration report: *Certificate signing key*
moves from `absent` to `production`, and `instance/keys/signing/` holds one
public half named for the day it was generated.

```bash
cd tools && uv run convener-check-config
```

**Without it.** *The* **Certificate signing key** *row of*
`config/integrations.yml`*, which* `convener-check-config` *prints as this
row's* `meanwhile:` *line. It is maintained there, and quoted here.*

> No certificate is issued in this run. The job that would sign one
> (tools/convener_ops/certificate.py) cannot, and does not fall back to
> anything -- there is no partially-written document, and nothing sensitive is
> exposed by the absence, because signing attests rather than conceals: unlike
> CONVENER_EVENT_KEY_<ID> above, there is no confidentiality risk this row
> exists to prevent. This is an ordinary D-13 absence, the same shape as
> video_publishing's "entered by hand" or board_notifications' "printed
> instead of sent" -- a feature that degrades, not a failure this repository
> fails closed over. Unlike CONVENER_EVENT_KEY_<ID>, there is exactly one of
> these at a time (not one per event), and it is never destroyed: see
> tools/convener_ops/signing.py for why a certificate signing key's lifecycle
> runs opposite to an event key's.

**Credentials.** `CONVENER_SIGNING_KEY`

**In a browser, in full:**

1. Open a Python shell inside `tools/` with `uv run python`, and generate the
   pair with `from convener_ops.signing import generate; private_pem,
   public_pem = generate()`.
2. Commit the public half first, as `instance/keys/signing/` plus the day it
   was generated and a `.pub` suffix. The order is load-bearing, because a
   private secret set before its public half is published lets a job sign a
   certificate nothing can yet verify.
3. Paste the private half directly from that terminal into the private
   repository's Settings → Secrets and variables → Actions → Secrets → New
   repository secret, named `CONVENER_SIGNING_KEY`. Never write it to a file,
   not a temporary one and not an ignored one.
4. Confirm the paste, then close the terminal that generated it. Nothing else
   should retain a copy, including the shared store — the public half is what
   a stranger verifies against, and the private half exists to be usable by
   one workflow and nobody else.
5. Never remove a published public half later. Verification is handed every
   one of them and tries each in turn, so deleting one is what would make an
   already-issued certificate stop verifying.

### 24. The salt behind a matching code and a register's fingerprint

**Who:** a person.

Generate one long random value and set it as a repository secret. One secret,
two unrelated derivations: the code a participant types into the meeting
room's display name, and the certificate register's own salted trace of an
address. It is never per-event, and it must never be rotated once
registrations exist under it.

**Proves it is done.** Run the configuration report: *Registration matching
salt* and *Certificate register fingerprint* both move from `absent` to
`production`. Two rows, one secret — they are separate rows because their
absences mean different things, not because there are two values.

```bash
cd tools && uv run convener-check-config
```

**Without it.** *The* **Registration matching salt** *row of*
`config/integrations.yml`*, which* `convener-check-config` *prints as this
row's* `meanwhile:` *line. It is maintained there, and quoted here.*

> tools/convener_ops/registration.py::matching_code returns nothing: no
> matching code is derived, printed, or put in the confirmation email.
> Attendance falls back to its own cascade -- exact address, then normalised
> name -- instead of the typed code. convener-match- attendance's own
> unmatched-attendance.md degrades the same way: with no salt, no salted
> record identifier can be computed for an unmatched connection or a tied
> candidate either, so the host's list falls back to naming each entry by its
> own position in the run instead. An ordinary D-13 absence: the salt exists
> so the code and the report cannot be forged, guessed or reversed by anyone
> who knows an address, not so a job can refuse to run without it, and every
> fallback it degrades to is documented and working, never personal data
> landing somewhere it should not. The same secret has a second, unrelated
> consumer with a different, non-ordinary shape of absence -- see the
> certificate_fingerprint row below, which declares that difference
> structurally rather than in this row's own prose.
**Without it.** *The* **Certificate register fingerprint** *row of*
`config/integrations.yml`*, which* `convener-check-config` *prints as this
row's* `meanwhile:` *line. It is maintained there, and quoted here.*

> tools/convener_ops/certificate.py::fingerprint reads the same
> CONVENER_MATCHING_SALT as the matching_salt row above, for a second,
> domain-separated purpose: the certificate register's own salted trace of an
> address. Here the absence is *not* ordinary: a fingerprint that cannot be
> salted cannot be written to a register that must never carry an address in
> the clear, so convener-issue-certificates and convener-reissue-certificate
> issue nothing this run rather than write one unsafely. Outwardly this still
> degrades the same way as an ordinary absence (a printed line, a clean exit,
> nothing partially written) -- only the reason differs, named in each job's
> own message. This is one of this project's rare exceptions to D-13's "an
> absent integration is a normal state": an absent secret here forbids
> writing, it does not license writing insecurely.

This is one of the rows whose absence is not an ordinary state. The report
marks it so, on the row and again in its closing line.

**Credentials.** `CONVENER_MATCHING_SALT`

**In a browser, in full:**

1. Generate a long random value on your own machine. `openssl rand -base64 32`
   is enough; so is anything that produces thirty-odd bytes nobody could
   guess.
2. Paste it into the private repository's Settings → Secrets and variables →
   Actions → Secrets → New repository secret, named `CONVENER_MATCHING_SALT`,
   and into the shared store.
3. Do not rotate it afterwards. Rotating changes every matching code already
   given to a participant, so a resent confirmation no longer matches what
   they were told — and it changes every past attendee's fingerprint too, so
   certificate issuance stops recognising them and mints each a second
   certificate on its next run.

## Stage 8 — What is left, and what each costs to skip

Every remaining integration degrades visibly and none of them breaks anything.
An instance that stops here is a working instance, and this stage is a menu
rather than a queue.

### 25. Where the Board is told what happened

**Who:** an agent, or a person.

Open a standing issue in the private repository to serve as the notification
thread, create an organisation team named `editorial-board` and put the Board
in it, and set the issue's number and the team's handle as repository secrets.
No external service and no account: GitHub itself is the delivery mechanism.

**Proves it is done.** Run the configuration report: *Board notifications*
moves from `absent` to `production`. Reading the day's message without sending
it is a command of its own.

```bash
cd tools && uv run convener-notify-digest --dry-run
```

**Without it.** *The* **Board notifications** *row of*
`config/integrations.yml`*, which* `convener-check-config` *prints as this
row's* `meanwhile:` *line. It is maintained there, and quoted here.*

> Nothing is sent. The digest and the immediate events are still composed and
> printed to the job log, where any volunteer can read them, but they are
> addressed to nobody: a message needs both a thread to be posted on and a
> team to mention, and without them no postable message is constructed at all.
> Both are needed because a thread with no mention posts into a page nobody is
> watching, and a mention with no thread has nowhere to be written.

**Credentials.** `CONVENER_NOTIFY_THREAD`, `CONVENER_NOTIFY_MENTION`

### 26. Sending a confirmation, a certificate and a survey invitation

**Who:** a person.

Give the workflows a way to send mail as the organisation's own address over
ordinary SMTP — five values, on whatever mailbox the first stage created. No
transactional-email service and no subscription: D-07 arbitrated that, and the
mailbox already exists.

**Proves it is done.** Run the configuration report: *Outbound email* moves
from `absent` to `production`.

```bash
cd tools && uv run convener-check-config
```

**Without it.** *The* **Outbound email** *row of* `config/integrations.yml`*,
which* `convener-check-config` *prints as this row's* `meanwhile:` *line. It
is maintained there, and quoted here.*

> Three consumers, all reported rather than retained -- none ever prints a
> composed message, sent or not, and none writes one to a file or a build
> artefact either. tools/convener_ops/confirmation.py: the registration
> confirmation, carrying a participant's address and matching code, used to be
> written to a local, .gitignore'd file and uploaded as a short-retention
> build artefact instead of being sent -- removed once
> docs/governance/traitement-donnees.md's own Recipients section turned out to
> call that artefact a documented exception, when with this row absent (this
> project's default state) it was the path every registration took, not an
> exception. Every attempt is folded into a bare sent/not-sent count instead,
> and convener-resend-confirmation reproduces the identical message from the
> stored registration and the same deterministic matching code, so nothing is
> ever the only copy of anything. tools/convener_ops/delivery.py: the
> certificate document this row would carry is never written anywhere at all,
> not even to a private artefact, from the day this module was written -- see
> that module's own docstring for why a signed, nominative document must never
> land in any Actions surface, a stricter constraint than the registration
> confirmation was held to at first. tools/convener_ops/survey_invite.py: the
> post-event survey invitation, reusing confirmation.py's own transport rather
> than a third copy of it, degrades the same bare-count way delivery.py does
> -- and for a related but distinct reason: a survey invitation carries no
> identifier at all to keep an unsent copy filed against, unlike a
> certificate, which at least has a public one.

**Credentials.** `CONVENER_SMTP_HOST`, `CONVENER_SMTP_PORT`,
`CONVENER_SMTP_USER`, `CONVENER_SMTP_PASSWORD`, `CONVENER_SMTP_FROM`

**In a browser, in full:**

1. Find the provider's SMTP settings for the mailbox from the first stage.
   Most want port 587 with STARTTLS; some want 465 with implicit TLS. Either
   works — the port itself is what decides which is used, so there is no code
   change to make.
2. If the provider offers application-specific passwords, mint one for this
   and not the mailbox's own password. That is a browser flow with no API,
   which is why this step is a person's.
3. Set all five as repository secrets on the private repository, under
   Settings → Secrets and variables → Actions → Secrets. Four of them are not
   secret in any real sense; they are set alongside the password because a
   partially-set transport is worse than an unset one.
4. Put the application password in the shared store.

### 27. Where a recording is published

**Who:** a person.

Create the video channel with the organisation's address and record its
identifier as a repository secret. The channel belongs to the organisation and
not to a volunteer, which is also what makes the Board's publication gate mean
anything.

**Proves it is done.** Run the configuration report: *Video channel* moves
from `absent` to `production`.

```bash
cd tools && uv run convener-check-config
```

**Without it.** *The* **Video channel** *row of* `config/integrations.yml`*,
which* `convener-check-config` *prints as this row's* `meanwhile:` *line. It
is maintained there, and quoted here.*

> Recording URLs are entered by hand after publishing. No upload is attempted.

**Credentials.** `CONVENER_VIDEO_CHANNEL_ID`

**In a browser, in full:**

1. Create the channel with the address from the first stage, on whichever
   platform the series will publish to.
2. Copy its channel identifier from the channel's own settings.
3. Set it as a repository secret named `CONVENER_VIDEO_CHANNEL_ID` on the
   private repository, and put the channel's credentials in the shared store.

### 28. The room the webinar happens in

**Who:** a person.

Create the meeting account with the organisation's address and set its current
access token as a repository secret. This one is not a one-time value: the
token expires and is renewed roughly monthly, which makes it a step of the
event journey rather than a step of standing up.

**Proves it is done.** Run the configuration report: *Meeting platform* moves
from `absent` to `production`.

```bash
cd tools && uv run convener-check-config
```

**Without it.** *The* **Meeting platform** *row of*
`config/integrations.yml`*, which* `convener-check-config` *prints as this
row's* `meanwhile:` *line. It is maintained there, and quoted here.*

> The manual adapter (tools/convener_ops/platform.py::ManualPlatform) is used.
> The room and recording links are typed by hand into
> instance/data/speakers.yml's existing zoom_link and youtube_url, join
> instructions into instance/data/config.yml's instructions (one value for the
> whole series -- the account is the permanent room), and attendance is
> imported from instance/data/events/<id>/attendance-import.csv, a file that
> is never committed. No room link is published automatically, and no
> recording storage is managed on our side. Once set,
> tools/convener_ops/platform_fcc.py::PlatformFCC is used instead (selected by
> platform_fcc.py::platform_from_env, D-13): real per-person attendance is
> read from the provider's own calls endpoint -- undocumented by the vendor,
> but verified empirically -- and the recording is reported and deleted
> through its own API instead of being tracked by hand. The value is the
> current access token itself, not a client id and secret; it expires and must
> be renewed roughly monthly, a step of the event journey rather than a
> one-time secret -- see docs/reference/operations.md's "Meeting platform"
> section.

**Credentials.** `CONVENER_MEETING_API_TOKEN`

**In a browser, in full:**

1. Create the account with the address from the first stage. A permanent room
   on one account is what the manual path already assumes, so this step is
   worth doing even if the token never is.
2. Find the current access token in the provider's own developer area and copy
   it. It is the token itself that is set here, not a client id and secret.
3. Set it as a repository secret named `CONVENER_MEETING_API_TOKEN` on the
   private repository.
4. Put the renewal in the calendar. An expired token falls back to the manual
   path, which is a working state, so nothing will interrupt to tell you it
   has lapsed.

## Every credential, in one table

No value is written down here or anywhere else in this repository. What
follows is which credential exists, which repository or worker it belongs to,
and the menu path a person reaches it by. Every repository credential is set
on the private repository: the public one holds none, because nothing runs in
it.

| Credential | Kind | Where | Set through |
|---|---|---|---|
| `VITRINE_DEPLOY_TOKEN` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CLOUDFLARE_API_TOKEN` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `VITE_AUTH_PROXY_URL` | repository-variable | `cockpit` | Settings → Secrets and variables → Actions → Variables → New repository variable |
| `VITE_GITHUB_APP_CLIENT_ID` | repository-variable | `cockpit` | Settings → Secrets and variables → Actions → Variables → New repository variable |
| `VITE_SIGNUP_RELAY_URL` | repository-variable | `cockpit` | Settings → Secrets and variables → Actions → Variables → New repository variable |
| `CONVENER_DISPATCH_TOKEN` | worker-secret | services/form-relay | Cloudflare dashboard → Workers & Pages → the form relay → Settings → Variables and Secrets → Add, or `cd services/form-relay && npx wrangler secret put CONVENER_DISPATCH_TOKEN` |
| `TALLY_WEBHOOK_SECRET` | worker-secret | services/form-relay | Cloudflare dashboard → Workers & Pages → the form relay → Settings → Variables and Secrets → Add, or `cd services/form-relay && npx wrangler secret put TALLY_WEBHOOK_SECRET` |
| `TALLY_WEBHOOK_SECRET` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_DISPATCH_TOKEN` | worker-secret | services/signup-relay | Cloudflare dashboard → Workers & Pages → the signup relay → Settings → Variables and Secrets → Add, or `cd services/signup-relay && npx wrangler secret put CONVENER_DISPATCH_TOKEN` |
| `CONVENER_RETENTION_TOKEN` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_SIGNING_KEY` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_MATCHING_SALT` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_NOTIFY_THREAD` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_NOTIFY_MENTION` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_SMTP_HOST` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_SMTP_PORT` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_SMTP_USER` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_SMTP_PASSWORD` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_SMTP_FROM` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_VIDEO_CHANNEL_ID` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `CONVENER_MEETING_API_TOKEN` | repository-secret | `cockpit` | Settings → Secrets and variables → Actions → Secrets → New repository secret |
| `TALLY_API_KEY` | operator-shell | the operator's own machine | Not set anywhere at all — passed in the environment of the one command that builds the public form, and never committed, never a repository secret and never read by continuous integration. |

## What is deliberately not on this page

**`CONVENER_EVENT_KEY_<ID>`.** One per event, not one per instance. The pair
is generated when an event opens for registration, its public half is
committed first so that the registration page can encrypt, and the private
half is deleted at the end of that event's retention window — which is the
destruction this whole project is built around. Setting one at standing-up
time would mean naming an event that does not exist yet.

## After this page

`docs/reference/operations.md` is the page to read next, and the one to keep
open afterwards: it covers everything an instance does *after* it is standing
— handling a registration, matching attendance, issuing and revoking a
certificate, draining the queue, the retention sweep and the early-erasure
path. This page hands over to it and does not repeat it.
