// Fix round 4 (the path-prefix defect): GitHub Pages serves this project's
// build output at <https://example-instance.github.io/example-showcase/>, not at
// a bare domain root -- there is no CNAME and no custom domain
// (`publish-vitrine.yml`'s own "already-active GitHub Pages setting" is
// "branch main, folder root" on the *example-showcase* repository, so the
// address is this repository's own name). Every template used to write its
// internal links as a bare `/foo`, which resolves to the *domain* root, one
// path segment short of where the site actually lives -- invisible on a
// developer's own `localhost` build, total once published.
//
// `pathPrefix` is Eleventy's own mechanism for exactly this: every call to
// the built-in `url` filter (`{{ '/foo' | url }}`) resolves against it, so
// this is the one place that address is written down for every template in
// this project -- see each `.njk` file's own `| url` filter calls, and
// `style.css`'s `@font-face` block, which needs no prefix at all because a
// relative `url('fonts/...')` inside a stylesheet already resolves against
// the stylesheet's own address, at any prefix.
//
// A hand-typed literal, the same D-14 discipline `tools/convener_ops/
// registration.py::SIGNUP_BASE` and `tools/convener_ops/certificate.py::
// VERIFICATION_BASE` already use for this identical address, rather than an
// import across the Python/JavaScript boundary this project does not build
// tooling to cross -- bound to those two constants, and to
// `app/vite.config.ts`'s own published `base`, by
// `tools/tests/test_site.py::
// test_the_path_prefix_agrees_with_the_addresses_python_already_pins`, so
// the four cannot silently drift apart. Change all four together.
const PATH_PREFIX = '/example-showcase/';

module.exports = function (cfg) {
  cfg.addPassthroughCopy('src/style.css');
  // Self-hosted fonts and their licences. Copied rather than pulled from a CDN
  // at runtime: the phase 5 specification forbids any third-party dependency,
  // and a webfont request is one — it discloses every visitor's address.
  //
  // Fix round 1 (task 3): the files themselves moved from `src/fonts/` to
  // `../fonts/` -- one repository root shared with `app/`'s own copy step
  // (`app/scripts/copy-fonts.mjs`), rather than each side keeping its own
  // committed set that could drift apart the way the colour tokens already
  // had. The object form maps that parent directory back onto the same
  // `/fonts/` output path this build always served, so nothing downstream
  // (style.css's relative `url('fonts/...')`, layout.njk's `| url`-filtered
  // preload) had to change.
  cfg.addPassthroughCopy({ '../fonts': 'fonts' });
  // Phase 5, task 2: the public showcase repository now receives this
  // project's own build output at its root, alongside `app/`, which is
  // exactly what its already-active GitHub Pages setting ("branch main,
  // folder root") serves. Without this file, GitHub's default Jekyll
  // processing swallows that output and serves the README instead. Sourced
  // here rather than `touch`-ed by the publish workflow so that the built
  // site is reproducible from this repository alone.
  cfg.addPassthroughCopy('src/.nojekyll');
  return {
    dir: { input: 'src', output: '_site' },
    templateFormats: ['njk', 'md'],
    htmlTemplateEngine: 'njk',
    pathPrefix: PATH_PREFIX,
  };
};
