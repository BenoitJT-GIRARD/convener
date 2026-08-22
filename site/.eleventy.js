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

// Phase 5, task 10: structured event data, share metadata, the sitemap and
// the feed all need this project's real, *absolute* published address --
// a root-relative link, even one already carrying PATH_PREFIX, is nonsense
// outside a browser that already has this page open: a search engine's
// crawler, a link-preview bot and an RSS reader all resolve a URL against a
// document of their own, not this one. `SITE_ORIGIN` is the one place this
// project's public host is written down on the JavaScript side -- the same
// D-14 discipline PATH_PREFIX above already follows, and for the identical
// reason (a JavaScript config cannot import a Python constant) -- bound to
// `registration.SIGNUP_BASE` and `certificate.VERIFICATION_BASE`, which
// already carry this exact host, by `tools/tests/test_site.py::
// test_absolute_urls_share_the_one_origin_this_project_already_pins`.
// Change all three together.
const SITE_ORIGIN = 'https://example-instance.github.io';

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

  // `path` is root-relative and unprefixed -- exactly `| url`'s own input
  // contract (every existing `| url` call site in this project's templates).
  // This filter does that identical prefixing plus SITE_ORIGIN, in one step,
  // for the handful of places a URL leaves this document for a context with
  // no address of its own to resolve a relative link against: canonical
  // links, Open Graph/Twitter Card metadata, JSON-LD, the sitemap and the
  // feed. Never chain the two (`x | url | absoluteUrl` doubles the prefix) --
  // a page uses one or the other, never both.
  cfg.addFilter('absoluteUrl', function (path) {
    return `${SITE_ORIGIN}${PATH_PREFIX.slice(0, -1)}${path}`;
  });

  // JSON-LD objects built in event.njk carry `null` for a field that does
  // not apply to this edition's state -- no `potentialAction` on a past
  // edition (it is not still accepting registrations), no `subjectOf`
  // without a published recording, no `performer.affiliation` without one
  // on the speaker record -- rather than a separate, fully-`{% if %}`-guarded
  // object literal per state. This replacer drops any key whose value is
  // `null`, at every nesting depth, so the emitted JSON-LD never carries an
  // explicit `null` a search engine would have to make sense of.
  cfg.addFilter('jsonLd', function (value) {
    return JSON.stringify(value, function (key, val) {
      return val === null ? undefined : val;
    });
  });

  // A feed item needs a machine-readable publication timestamp (RSS 2.0's
  // `pubDate`, RFC-822/1123) -- built from the *edition's own* `date`, never
  // from `new Date()` read with no argument at build time, which would make
  // every rebuild churn the feed for a reason that has nothing to do with
  // its actual content (the same failure `parisToday()`/`paris_today`
  // exists to rule out on the Python side of this project). `isoDate` is
  // always `YYYY-MM-DD` (`events.json`'s own shape); the fixed 12:30 CET is
  // the same advertised start time `event.njk`'s own rail already prints
  // as plain text, kept here rather than a second, disagreeing assumption.
  cfg.addFilter('rfc822', function (isoDate) {
    return new Date(`${isoDate}T12:30:00+01:00`).toUTCString();
  });

  return {
    dir: { input: 'src', output: '_site' },
    templateFormats: ['njk', 'md'],
    htmlTemplateEngine: 'njk',
    pathPrefix: PATH_PREFIX,
  };
};
