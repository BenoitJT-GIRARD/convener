# site

Source of the public showcase (The Example Collective Monthly Reading Group). Built with
[Eleventy](https://www.11ty.dev/) and pushed, built, to the public `example-showcase`
repository's root by `.github/workflows/publish-vitrine.yml` — see D-15 in
`docs/superpowers/specs/2026-08-18-convener-cadrage-decisions.md`. `example-showcase` itself
holds no source: every byte there is reproducible from this directory.

`src/_data/events.json` is committed here as a build fixture only. In CI it is
overwritten from `public-data/events-public.json` (`uv run convener-public-data`,
`tools/`) before every build; a local edit is not preserved.

`src/_data/site.json` is genuine source: the showcase's own static configuration
(title, tagline, external links).

Fonts are self-hosted, from `../fonts/` at the repository root -- shared with
`app/`'s own copy step (`app/scripts/copy-fonts.mjs`) rather than a second,
separately committed set that could drift apart from it. No third-party
request is made from a published page — D-17.

## Local preview

```
cd site
npm install
npm start
```

Then open `http://localhost:8080` plus the path prefix
`config/instance.json` declares. The dev server honours the
same path prefix the published site is served under, so a bare root only
redirects there.
