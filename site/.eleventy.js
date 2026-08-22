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

// Fix round 1: the series' one standing start time, Europe/Paris *local*
// -- what a recurring seminar series means by "the seminar starts at
// 12:30" is 12:30 in Paris, not a fixed UTC offset that happens to be
// right for half the year. `data/speakers.yml` carries a `time` field
// per record, and `public_data.py::PUBLISHABLE_ALWAYS` classifies it as
// publishable -- but `PUBLIC_FIELD_SOURCES`, the mapping that actually
// decides what a built row carries, has no entry pointing any column at
// it, so `time` never reaches `events-public.json` (confirmed by
// regenerating that file from the real `data/speakers.yml` and
// inspecting the output, not merely by reading the two files side by
// side) and so never reaches this project's own `events.json` either.
// With nothing to read per edition, this stays one constant rather than
// a per-edition value with a fallback the other side can never populate
// -- "do not build a path to data that cannot arrive", a rule this
// project has already paid for five times. The day `time` is wired
// through `PUBLIC_FIELD_SOURCES`, this is the one constant to replace
// with `event.time || STANDING_START_LOCAL`, in `parisStandingStart`
// below.
const STANDING_START_LOCAL = '12:30';

// Fix round 1: Europe/Paris's own UTC offset and abbreviation for the
// *edition's own date*, at the standing local time above -- +01:00/CET
// from late October to late March, +02:00/CEST the rest of the year.
// This used to be a hand-typed `+01:00`/`CET` regardless of season,
// silently wrong by one hour for any edition in daylight-saving time --
// three of this project's own five fixture editions -- in both the
// machine-readable JSON-LD `startDate` and the feed's `pubDate`, and
// mislabelled on the page's own visible text besides: a calendar import
// or a search engine reading `+01:00` in June books the wrong hour, and
// nobody reading the page's own text can tell it is wrong.
//
// Derived from `Intl`, built into Node -- no dependency, no network --
// rather than a hand-rolled DST calendar, the same instrument
// `app/src/state/derived.ts::parisWallTimeToEpoch` already uses for this
// project's identical zone (duplicated rather than imported: a
// `.eleventy.js` cannot import from `app/`'s own build, and D-14 already
// settles that a fixture binds two independent implementations across a
// language boundary rather than moving the decision to one side -- there
// is nothing to bind here, since neither side reads the other's answer,
// but the technique is the same one already vetted on the Python/
// JavaScript boundary elsewhere in this file).
//
// Probed at midday UTC on the edition's own date, not at the standing
// local time itself (computing that would need the offset already known
// to convert it to UTC first): Europe/Paris's DST transitions always
// happen in the small hours (01:00 UTC), well before midday on the
// transition day itself, so a midday-UTC probe always resolves the
// offset actually in effect at 12:30 Paris local time on that same
// calendar date -- transition days included.
function parisStandingStart(isoDate) {
  const probe = new Date(`${isoDate}T12:00:00Z`);
  // `timeZoneName: 'shortOffset'` is stable across locales ('GMT+1',
  // 'GMT+2'); the CET/CEST *abbreviation* is not -- `en-US`'s own ICU
  // data renders it as this same 'GMT+1'/'GMT+2' string, not the letters,
  // while `en-GB`'s does (confirmed by probing both locally). Rather than
  // pin this project's output to whichever one locale's data happens to
  // spell it out, the offset is the only thing asked of `Intl` here.
  const offsetPart = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/Paris',
    timeZoneName: 'shortOffset',
  })
    .formatToParts(probe)
    .find((part) => part.type === 'timeZoneName').value; // 'GMT+1' or 'GMT+2'
  const match = /^GMT([+-])(\d{1,2})$/.exec(offsetPart);
  if (!match) {
    throw new Error(`unexpected Europe/Paris UTC offset from Intl: ${offsetPart}`);
  }
  const [, sign, hours] = match;
  const offset = `${sign}${hours.padStart(2, '0')}:00`;
  // Europe/Paris observes exactly two offsets, and this project has only
  // ever named them CET and CEST (never "GMT+1"): naming the offset this
  // zone is already in is a fixed convention, not a second DST calendar
  // to keep in step with the one `Intl` resolved above.
  const abbreviation = offset === '+02:00' ? 'CEST' : 'CET';
  return {
    startDate: `${isoDate}T${STANDING_START_LOCAL}:00${offset}`,
    label: `${STANDING_START_LOCAL} ${abbreviation}`,
  };
}

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

  // `event.date | parisStandingStart` for both the JSON-LD `startDate`
  // (event.njk) and the visible "12:30 CET"/"12:30 CEST" label
  // (event.njk, index.njk) -- one Paris-DST computation feeding every
  // place this project states the edition's start time, so they cannot
  // state three different answers about the same date. See
  // `parisStandingStart`'s own comment above for the derivation and for
  // why `time` (the field that would otherwise let a per-edition value
  // override the standing 12:30) does not reach this data yet.
  cfg.addFilter('parisStandingStart', parisStandingStart);

  // A feed item needs a machine-readable publication timestamp (RSS 2.0's
  // `pubDate`, RFC-822/1123) -- built from the *edition's own* `date`, never
  // from `new Date()` read with no argument at build time, which would make
  // every rebuild churn the feed for a reason that has nothing to do with
  // its actual content (the same failure `parisToday()`/`paris_today`
  // exists to rule out on the Python side of this project). `isoDate` is
  // always `YYYY-MM-DD` (`events.json`'s own shape); `parisStandingStart`
  // above resolves the real Europe/Paris offset for that date rather than
  // a fixed `+01:00` -- see its own comment for why that fix matters here.
  cfg.addFilter('rfc822', function (isoDate) {
    return new Date(parisStandingStart(isoDate).startDate).toUTCString();
  });

  return {
    dir: { input: 'src', output: '_site' },
    templateFormats: ['njk', 'md'],
    htmlTemplateEngine: 'njk',
    pathPrefix: PATH_PREFIX,
  };
};
