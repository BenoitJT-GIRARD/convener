# example-showcase

Public showcase of The Example Collective Monthly Reading Group — and nothing else.

**This repository holds no source.** Everything under it is generated and pushed by
the private `example-cockpit` repository's CI (D-15: private source, public artefact):

- The site itself (`index.html`, `style.css`, `fonts/`, `.nojekyll`) is built from
  `site/` there and pushed by `.github/workflows/publish-vitrine.yml`.
- `app/` is the organiser cockpit application, built from `app/` there and pushed
  by `.github/workflows/deploy.yml`.

Do not edit anything here by hand — it is overwritten on the next push from either
workflow. To change the showcase, edit the templates under `example-cockpit`'s own
`site/` and push to its `main`.

## Deployment

GitHub Pages, "branch `main`, folder root" — already active, and already exactly
what these two workflows' pushes serve. No `gh-pages` branch, no Pages Actions.
