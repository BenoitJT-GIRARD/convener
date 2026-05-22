# What's left to do

A short list so nothing gets forgotten. Tick items as they are done.

## Put the handbook online — one-off, technical (for Anonymous)

- [ ] Create an **empty private repository** named `workshop-series` in the The Example Collective GitHub organisation.
- [ ] Push this folder to it: `git remote add origin <url>` then `git push -u origin main`.
- [ ] Turn on the website: enable **GitHub for Nonprofits** (free), then *Settings → Pages → source `gh-pages`*.
- [ ] Check that `repo_url` in `mkdocs.yml` matches the real organisation address.
- [ ] Create the **`editorial-board` team** in the The Example Collective org and add the Board members. The `CODEOWNERS` file references it.
- [ ] Set **branch protection** on `main`: require PR + 1 review for all paths **except** `data/**`. This activates the Board's auto-review on handbook changes, while letting the team app push to `data/` directly.

## Later — the team app + public vitrine

- [ ] Build the **team app** (private, GitHub-login) and the **public vitrine** following the design spec. Separate project; see `app/README.md`.

---
*Once the GitHub steps above are done, this file can be trimmed.*
