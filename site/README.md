# site

Source of the public showcase. Which series, under whose name, is in
`instance/config.json` and nowhere else. Built with
[Eleventy](https://www.11ty.dev/) and pushed, built, to the public `example-showcase`
repository's root by `.github/workflows/publish-showcase.yml` — see
`docs/engineering/decisions/d-15-publication-topology.md`. `example-showcase` itself
holds no source: every byte there is reproducible from this directory.

`src/_data/events.json` is committed here as a build fixture only. In CI it is
overwritten from `instance/public-data/events-public.json`
(`uv run convener-public-data`, `tools/`) before every build; a local edit is not preserved.

`site.*` is derived, not written down here: `.eleventy.js` composes it --
title, tagline, the forum, the proposal form, the organisation's own name
-- from `instance/config.json`, the one file that says whose series this
is. It replaced a hand-typed `src/_data/site.json`, for
the reasons that file's own successor comment gives.

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
`instance/config.json` declares. The dev server honours the
same path prefix the published site is served under, so a bare root only
redirects there.
