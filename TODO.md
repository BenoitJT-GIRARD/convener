# What's left to do

A short list so nothing gets forgotten. Tick items as they are done.

## Put it all online — one-off, technical (for Anonymous)

### `workshop-series` (this private repo) — handbook + data + team app

- [ ] Create an **empty private repository** named `workshop-series` in the The Example Collective GitHub organisation.
- [ ] Push this folder to it: `git remote add origin <url>` then `git push -u origin main`.
- [ ] Enable **GitHub for Nonprofits** (free) to allow Pages on private repos.
- [ ] In *Settings → Pages*, set source to branch `gh-pages` (will be created by the first deploy Action). The handbook lands at `/` and the team app at `/team-app/` (one page inside the handbook site, deployed by the same unified workflow).
- [ ] Check that `repo_url` in `mkdocs.yml` matches the real organisation address.
- [ ] Create the **`editorial-board` team** in the org and add the founding Board members. The `CODEOWNERS` file references it.
- [ ] Set **branch protection** on `main`: require PR + 1 review for all paths **except** `data/**`. This activates the Board's auto-review on handbook changes; the team app commits to `data/` directly.
- [ ] Set the repo variables `ARCHITECT_USERNAME` (your GitHub login) and `APP_URL` (e.g. `https://example-instance.github.io/workshop-series/team-app/`) so the gate-issue Action assigns reviewers and links into the app.

### `example-showcase` — the public vitrine (separate repo)

- [ ] Create an **empty public repository** named `example-showcase` in the The Example Collective org.
- [ ] From `C:\Users\Ben\Desktop\TEC_Workshop_Series\example-showcase\`: `git remote add origin <url>` then `git push -u origin main`. The Action will build it and publish to GitHub Pages.
- [ ] Back in the **private** repo, create a PAT (or deploy key) with write access to `example-showcase`, and set it as the secret `VITRINE_DEPLOY_TOKEN` in *Settings → Secrets and variables → Actions*. The `publish-vitrine` Action uses it to push the filtered public data.

### Tally form (public proposal form)

- [ ] Create a Tally account in the org name.
- [ ] Build a form **"Propose a speaker"** with fields: Name · Email · Institution · Topic · Preliminary title · Short abstract · Country · How you propose (self / a colleague) · Conflicts of interest.
- [ ] Configure a webhook: type `repository_dispatch` to `https://api.github.com/repos/example-instance/workshop-series/dispatches`, event type `proposal-submitted`. The payload must be the form fields.
- [ ] If using HMAC signature: pick a strong secret and set it as `TALLY_WEBHOOK_SECRET` in the repo secrets. (Optional — the script skips signature check when unset.)
- [ ] Copy the public form URL and put it in `example-showcase/src/_data/site.json` (`applyForm`), then commit + push.

## Team app — first sign-in

Each Editorial Board member and Event Host who needs to use the team app:

- [ ] Make sure you have a free GitHub account, added to the `workshop-series` repo with at least read access (write for editors).
- [ ] On <https://github.com/settings/personal-access-tokens/new>, generate a **fine-grained personal access token**: resource owner `The Example Collective`, repository access only `workshop-series`, permissions *Contents: read & write* and *Issues: read & write*.
- [ ] Open the team app, paste the token, sign in.

---

*Once these steps are done, this file can be trimmed.*
