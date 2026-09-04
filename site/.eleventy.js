// The path-prefix defect: GitHub Pages serves this project's
// build output one path segment below a bare domain root -- there is no
// CNAME and no custom domain (`publish-showcase.yml`'s own "already-active
// GitHub Pages setting" is "branch main, folder root" on the published
// repository, so the address is that repository's own name). Every
// template used to write its internal links as a bare `/foo`, which
// resolves to the *domain* root, one path segment short of where the site
// actually lives -- invisible on a developer's own `localhost` build,
// total once published.
//
// `pathPrefix` is Eleventy's own mechanism for exactly this: every call to
// the built-in `url` filter (`{{ '/foo' | url }}`) resolves against it, so
// this is where that address reaches every template in this project -- see
// each `.njk` file's own `| url` filter calls, and `style.css`'s
// `@font-face` block, which needs no prefix at all because a relative
// `url('fonts/...')` inside a stylesheet already resolves against the
// stylesheet's own address, at any prefix.
//
// Both constants below used to be hand-typed literals,
// bound to `tools/convener_ops/journey/registration.py::SIGNUP_BASE`, to
// `certificate.py::VERIFICATION_BASE` and to `app/vite.config.ts`'s own
// `base` by tests that could say the copies still agreed but never that
// there was one. They are now read from `instance/config.json`, the
// instance's own declaration, through `scripts/published.cjs` -- the
// showcase's side of a boundary Python and the application build read
// from their own (D-14). The names stay: everything below this line uses
// them exactly as before.
const {
  publishedAddress,
  identity,
  isPlaceholder,
  unconfigured,
} = require('./scripts/published.cjs');
const { notice } = require('./scripts/notice.cjs');
const { isDemonstration, cockpitQuery } = require('./scripts/demonstration.cjs');

const PUBLISHED = publishedAddress();

const PATH_PREFIX = PUBLISHED.pathPrefix;

// Who runs this series, read from `instance/config.json` through the same
// `scripts/published.cjs` this file already reads the published address
// from.
//
// This was `src/_data/site.json` once: four hand-typed
// keys -- the series' title, its tagline, its forum, its proposal form --
// declared an instance path by `declarations/boundary.yml`. Clean as far as it
// went, and still a second home for the same notion, with the
// organisation's name written out a hundred and fifty other times across
// this repository's shipped prose, and nothing holding the two together.
// There is one declaration now.
//
// Composed here rather than in a `src/_data/site.js` for a reason a first
// attempt found the hard way: several suites copy `src/` to a scratch
// directory and build it with `--input=<tmp>/src`, at which point a data
// file's own relative `require('../../scripts/published.cjs')` resolves
// against the copy and there is nothing there. This file is loaded from
// `site/` whatever `--input` says, so this is the one place the
// derivation can live and still be the same derivation in every build.
// Three of these values never pass through a template at all -- the
// sentence every event page's meta description ends on, and the two
// calendar headers below -- so they would have needed reading here in any
// case.
const IDENTITY = identity();

/** Everything a template reads as `site.*`. `title` is composed, not
 *  declared. Every instance that declared one wrote exactly its own
 *  `short_name` and `series` with a space between them, so declaring it
 *  as well would have been a third way to spell one fact. */
const SITE = {
  title: `${IDENTITY.short_name} ${IDENTITY.series}`,
  tagline: IDENTITY.tagline,
  // The display line `src/index.njk` sets the home page's own headline
  // in, and the same key `tools/convener_ops/publication/visual.py` sets
  // the poster's hero band from. Two or three words in heavy capitals,
  // which is why the declaration carries it beside `tagline` rather than
  // instead of it -- `instance/config.json`'s own `_identity_comment`
  // states the typographic difference between the two.
  strapline: IDENTITY.strapline,
  // The forum: the whole address where a link is wanted, the bare host
  // where a sentence names it.
  forum: IDENTITY.forum,
  forumHost: IDENTITY.forum_host,
  // The proposal form `src/propose.njk` sends people to -- the same form
  // `tools/convener_ops/journey/proposal.py`'s webhook receives from.
  //
  // Empty while the declaration still carries a placeholder instead of an
  // address, and `propose.njk` renders the page's other half when it is:
  // a duplicate has not built its form before its first publish, and this
  // instance had not built one at all -- `identity.proposal_form` was
  // `https://forms.example.test/propose`, published as that page's one call to
  // action. Mirrors
  // `published.py::Identity.proposal_form_url`, and
  // `test_published.py::test_the_showcase_feeds_its_templates_the_declared_
  // identity` compares this value against that one.
  applyForm: isPlaceholder(IDENTITY.proposal_form) ? '' : IDENTITY.proposal_form,
  // The organisation itself: the masthead, the footer's "run by
  // volunteers from", every event page's `Organization` structured data,
  // and the address a participant writes to about their own data.
  organisation: IDENTITY.organisation,
  shortName: IDENTITY.short_name,
  series: IDENTITY.series,
  contact: IDENTITY.contact,
  // The two repositories `src/publish-readme.njk` names on the published
  // site's own landing page: the one this build is pushed into (derived
  // from the address it is served at) and the one it is built from.
  publishRepository: PUBLISHED.publishRepository,
  publishRepositoryName: PUBLISHED.publishRepository.split('/')[1],
  repository: IDENTITY.repository,
  // Which declared values this instance has not made
  // its own yet -- empty for an instance that has been configured, and
  // the names of the offending keys for one that has not. `_includes/
  // layout.njk` prints a banner across every page while it is not empty.
  //
  // The first thing anybody does with a template is deploy it before
  // configuring it, and until this the result was a public showcase
  // announcing the example collective's name, address and contact
  // address as though they were the duplicate's own -- silently, with
  // every check green, because a declaration that is somebody else's is
  // still a perfectly valid declaration. `scripts/published.cjs::
  // unconfigured` is the showcase's reader of that; `tools/convener_ops/
  // published.py::unconfigured` states the whole rule and why the
  // `REPLACE` marker is deliberately not part of it.
  unconfigured: unconfigured(),
  // Whether this build is the product's own demonstration rather than a
  // series somebody runs -- `scripts/demonstration.cjs`, from one
  // environment variable the demonstration's own build sets and nothing
  // else ever does.
  //
  // It changes exactly two things and neither of them is the shape of a
  // page: a band above the masthead saying whose records these are, and
  // the flag on the two links into the cockpit, so that following one
  // lands on the demonstration rather than on a sign-in screen. The
  // structure and the navigation are the deployed instance's, because
  // they are the same templates --
  // `tools/tests/repository/test_navigation.py` builds the showcase both
  // ways and refuses a page or a link that exists in one and not the
  // other.
  demo: isDemonstration(),
  // `?demo=1`, or nothing at all. Appended in the template rather than
  // composed here, because the prefix comes off Eleventy's own `url`
  // filter and a whole href built here would have to restate it.
  cockpitQuery: cockpitQuery(),
};

// Structured event data, share metadata, the sitemap and
// the feed all need this project's real, *absolute* published address --
// a root-relative link, even one already carrying PATH_PREFIX, is nonsense
// outside a browser that already has this page open: a search engine's
// crawler, a link-preview bot and an RSS reader all resolve a URL against a
// document of their own, not this one. The origin and the prefix come out
// of the one declaration together, which is why they cannot disagree about
// which deployment they describe.
// What this *product* says about itself, read from `NOTICE.json` at the
// repository root: whose work the software is, that a licensee may convey it
// and under what, that there is no warranty, and where to read the licence.
//
// Beside `SITE` above rather than inside it, and the separation is the whole
// point. Every value in `SITE` answers "who runs this series" and a duplicate
// changes all of them before its first build. Nothing here changes in any
// duplicate: it is the product's own Appropriate Legal Notice, in the sense
// section 0 of the licence gives that phrase, and section 5 is what obliges a
// modified version's own pages to keep displaying one. Folding it into
// `site.*` would file it among the values an instance is invited to edit.
const NOTICE = notice();

const SITE_ORIGIN = PUBLISHED.origin;

// The series' one standing start time, Europe/Paris *local*
// -- what a recurring seminar series means by "the seminar starts at
// 12:30" is 12:30 in Paris, not a fixed UTC offset that happens to be
// right for half the year. `instance/data/speakers.yml` carries a `time` field
// per record, and `public_data.py::PUBLISHABLE_ALWAYS` classifies it as
// publishable -- but `PUBLIC_FIELD_SOURCES`, the mapping that actually
// decides what a built row carries, has no entry pointing any column at
// it, so `time` never reaches `events-public.json` (confirmed by
// regenerating that file from the real `instance/data/speakers.yml` and
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

// Europe/Paris's own UTC offset and abbreviation for the
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

// The fallback description for an
// edition that carries no `abstract` yet -- the speaker's name, optionally
// `, affiliation`, then " — a <organisation> virtual seminar." -- has to
// read the same way in three places about the same edition: event.njk's
// own `<meta name="description">`/Open Graph/Twitter Card metadata
// (`eleventyComputed.pageDescription`), its JSON-LD `description`, and
// feed.njk's `<description>`. Those three used to be three separately
// hand-typed copies; feed.njk's own comment claimed they "never state the
// description of the same edition two different ways" while actually
// missing the closing sentence -- the exact drift `parisStandingStart`
// above already exists to rule out for the start time, one call site short
// of applying here too. One function, called from all three places, so
// there is exactly one rule to get right rather than three that happen to
// agree today.
function eventDescriptionFallback(event) {
  if (event.abstract) return event.abstract;
  let description = event.speaker_name;
  if (event.speaker_affiliation) {
    description = `${description}, ${event.speaker_affiliation}`;
  }
  return `${description} — a ${IDENTITY.organisation} virtual seminar.`;
}

// `path` is root-relative and unprefixed -- exactly `| url`'s own input
// contract (every existing `| url` call site in this project's templates).
// This does that identical prefixing plus SITE_ORIGIN, in one step, for the
// handful of places a URL leaves this document for a context with no address
// of its own to resolve a relative link against: canonical links, Open
// Graph/Twitter Card metadata, JSON-LD, the sitemap, the syndication feed and
// the agenda feed below. A plain function, not only a filter (like
// `parisStandingStart` and `eventDescriptionFallback` above), so this file's
// own agenda-calendar code can call it directly with no Nunjucks pipeline of
// its own -- see `eventPageUrl` below. Never chain the two (`x | url |
// absoluteUrl` doubles the prefix) -- a page uses one or the other, never
// both.
function absoluteUrl(path) {
  return `${SITE_ORIGIN}${PATH_PREFIX.slice(0, -1)}${path}`;
}

// ------------------------------------------------------------------ //
// The share image reaches the showcase.
//
// `og:image`/`twitter:image` were left out of layout.njk
// entirely at first rather than point either at a file that did not exist
// yet (see that file's own comment, still there, on the block this feeds).
// The banner (`tools/convener_ops/publication/formats.py::BANNER`) existed before anything
// carried it to a stable public address -- `.github/workflows/
// visuals-production.yml` renders every currently *scheduled* real
// edition's own banner on its one pinned-browser job (that cost is
// paid there, never here) and commits exactly that set under
// `src/banners/<event id>.png`, regenerated whole on every run so an
// edition that is no longer scheduled loses its file the same run --
// never a stale image sitting at a live public address once the seminar it
// pictures is no longer upcoming.
//
// `eventBannerUrl` is the read side of that write: given an event and the
// list of ids that currently have a file (`src/_data/banners.js`, below),
// it returns this edition's real, published address, or `''` when none
// exists -- `event.njk`'s own `eleventyComputed.pageImage` calls this, and
// `layout.njk`'s `{% if pageImage %}` treats the empty string exactly like
// "unset", so a page with no banner ready emits no `og:image`/
// `twitter:image` tag at all, the identical "a correct absence, not a
// broken pointer" choice the metadata block already made.
// ------------------------------------------------------------------ //

function eventBannerUrl(event, banners) {
  const id = String(event.id).toLowerCase();
  if (!banners.includes(id)) return '';
  return absoluteUrl(`/banners/${id}.png`);
}

// `tools/convener_ops/publication/formats.py::BANNER`'s own pixel size, copied here by hand
// -- the identical D-14 cross-language split `SEMINAR_DURATION_MINUTES`
// above already accepts for the same reason (this file cannot import a
// Python constant). Exposed as the global data `shareImageWidth`/
// `shareImageHeight` (below, `addGlobalData`) for `layout.njk`'s own
// `og:image:width`/`og:image:height`, rather than hand-typed a second time
// in that template -- one number to change if `BANNER`'s own dimensions
// ever do. Change both together.
const SHARE_IMAGE_WIDTH = 1200;
const SHARE_IMAGE_HEIGHT = 630;

// ------------------------------------------------------------------ //
// The public agenda feed -- iCalendar (RFC 5545), a
// second and unrelated feed format from the syndication one above
// (`feed.njk`): a calendar client subscribes to this one, an RSS reader
// to that one. Every function below builds towards `agendaCalendar`, the
// one filter `src/agenda.njk` calls; see that file's own comment for why
// line-ending purity (CRLF, RFC 5545's own requirement) is enforced by a
// build-wide transform rather than trusted to this function's own return
// value.
// ------------------------------------------------------------------ //

// The seminar's own fixed length, `instance/data/config.yml::
// seminar_duration_minutes` (also read, with the same 90-minute default,
// by `tools/convener_ops/maintenance/sweep.py::sweep` and now by this feed's own Python
// twin, `tools/convener_ops/publication/agenda.py::build_internal_calendar`) -- a plain
// site-wide constant, on the same footing `STANDING_START_LOCAL` above
// already stands on, not a computed rule the D-14 fixture would need to
// bind across languages. This build has no path to `instance/data/config.yml`
// itself: that file also carries board membership and other internal
// governance fields no public build may see (the same reason `time`
// never reaches this data either -- see `STANDING_START_LOCAL`'s own
// comment). So the one number a calendar entry needs beside its start
// time is copied here by hand, the same way the standing start time
// already is. Change both together if either changes.
const SEMINAR_DURATION_MINUTES = 90;

// RFC 5545 §3.3.11 TEXT escaping: a backslash, then a semicolon, then a
// comma, then a literal line break -- in that order, so escaping a later
// character never re-escapes a backslash this function just inserted for
// an earlier one. Applied to every free-text property value this feed
// writes (SUMMARY, DESCRIPTION, LOCATION): `eventDescriptionFallback`'s
// own fallback text already contains a comma ("<speaker>, <affiliation>
// — a <organisation> virtual seminar."), which an unescaped ICS file
// would misparse as the start of a second property.
//
// Mechanical and RFC-mandated, unlike `parisStandingStart`: there is no
// project decision here that the two languages could disagree about, so
// this is not bound to a shared fixture the way that function is --
// each side (this one, and `tools/convener_ops/publication/agenda.py::_escape_text`) is
// instead checked independently against the RFC itself, by a test that
// parses the rendered file back rather than re-running this same code.
function icsEscapeText(value) {
  return String(value)
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n');
}

// Fold one already-escaped "NAME:value" content line at 75 octets (RFC
// 5545 §3.1): a continuation line is a CRLF followed by a single leading
// space, repeated until the whole line is written -- so a continuation
// line's own budget is 74 octets, the 75th being that mandatory leading
// space. Every split lands on a UTF-8 character boundary, never inside a
// multi-byte sequence's own continuation bytes (`10xxxxxx`, the top two
// bits `10`): a title in this series can run past a hundred characters
// and carry an accented or non-Latin character, and a fold mid-byte
// would corrupt the file from that point on, not just misplace one line
// break.
function icsFoldLine(line) {
  const bytes = Buffer.from(line, 'utf8');
  if (bytes.length <= 75) return line;
  const parts = [];
  let start = 0;
  let budget = 75;
  while (start < bytes.length) {
    let end = Math.min(start + budget, bytes.length);
    while (end < bytes.length && (bytes[end] & 0xc0) === 0x80) end -= 1;
    parts.push(bytes.slice(start, end).toString('utf8'));
    start = end;
    budget = 74;
  }
  return parts.join('\r\n ');
}

// `SIGNUP_BASE` plus the edition's own lower-cased id (D-19) -- the event
// page's own address, exactly as `feed.njk`'s own `itemUrl` and
// `event.njk`'s own registration link already build it, factored out here
// so this file's agenda calendar can build the identical address with no
// Nunjucks `| sort` pipeline of its own. Never the meeting room:
// `events.json` carries no column that could resolve to one --
// `PUBLIC_FIELD_SOURCES` in `tools/convener_ops/publication/public_data.py` maps
// `zoom_link` to nothing published at all.
function eventPageUrl(event) {
  return absoluteUrl(`/events/${String(event.id).toLowerCase()}/`);
}

// A Europe/Paris local instant (`parisStandingStart`'s own `startDate`,
// e.g. `2026-09-10T12:30:00+02:00`) as an RFC 5545 UTC DATE-TIME
// (`20260910T103000Z`): iCalendar's basic format strips every separator
// `Date#toISOString` still carries, and drops the milliseconds `Date`
// always writes even for a whole second. `minutes` shifts the instant
// before formatting, for `DTEND`.
function icsUtcStamp(isoWithOffset, minutes) {
  const shifted = new Date(new Date(isoWithOffset).getTime() + (minutes || 0) * 60000);
  return shifted.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
}

// One VEVENT block for a scheduled edition: title, start, end, timezone
// and the event page's address -- the whole of what a subscriber needs.
//
// UTC (`Z`), not a `VTIMEZONE` component: a `VTIMEZONE` would carry its
// own copy of Europe/Paris's DST transition rule, which is exactly the
// rule `parisStandingStart` above already resolves once, from `Intl`,
// per edition -- a second, static encoding of "when Paris changes clocks"
// sitting inside every generated file is one more copy for that rule to
// drift from, the identical failure D-14 already binds three
// implementations against. Resolving the real offset once and writing an
// absolute UTC instant carries no DST rule of its own to go stale, ever.
//
// `UID` is the event page's own address, not a manufactured `id@domain`:
// the same identity `feed.njk`'s own `<guid isPermaLink="true">` already
// uses for this exact edition, so the two feeds name the same thing the
// same way. Stable across rebuilds (an edition's id does not change once
// assigned) and globally unique by construction, being a URL.
//
// `DTSTAMP` is the same instant as `DTSTART`, not `new Date()` read at
// build time: a calendar feed rebuilt on every push must not change
// merely because it was rebuilt (the exact discipline `parisToday()` /
// `paris_today` already enforce project-wide). RFC 5545 only asks that
// `DTSTAMP` be *a* valid UTC instant, not that it record when this
// particular file happened to be generated, so reusing `DTSTART`'s own
// value is a legitimate, and the only deterministic, choice available.
//
// `LOCATION` and `URL` both carry the event page's address, never the
// meeting room: "an event's location or URL is the event page, never the
// room" (D-19) -- a calendar entry is forwarded and re-synced far more
// casually than a web page, so a room link reaching a `LOCATION` field
// would end up on devices this project never intended it to.
function agendaVevent(event) {
  const { startDate } = parisStandingStart(event.date);
  const dtstart = icsUtcStamp(startDate);
  const dtend = icsUtcStamp(startDate, SEMINAR_DURATION_MINUTES);
  const url = eventPageUrl(event);
  const lines = [
    'BEGIN:VEVENT',
    `UID:${url}`,
    `DTSTAMP:${dtstart}`,
    `DTSTART:${dtstart}`,
    `DTEND:${dtend}`,
    `SUMMARY:${icsEscapeText(event.title)}`,
    `DESCRIPTION:${icsEscapeText(eventDescriptionFallback(event))}`,
    `LOCATION:${icsEscapeText(url)}`,
    `URL:${url}`,
    'END:VEVENT',
  ];
  return lines.map(icsFoldLine).join('\r\n');
}

// The public agenda feed in full: every `scheduled` edition (never a
// `delivered` or `archived` one -- a calendar is for what has not
// happened yet), soonest first, wrapped in the one VCALENDAR every
// consumer expects. `events` is `events.json`'s own array, unfiltered and
// unsorted -- the same input `feed.njk` receives -- so this is the only
// place that does either for this feed.
//
// Each element of the array joined below is either one short, fixed
// ASCII header/footer line (never long enough to need folding) or one
// already-folded, already-CRLF-joined `agendaVevent` block: `.join`
// inserts its separator only *between* array elements, never inside one,
// so folding a VEVENT block a second time here would wrongly treat its
// own internal CRLFs as ordinary content bytes -- deliberately not done.
function agendaCalendar(events) {
  const scheduled = events
    .filter((event) => event.status === 'scheduled')
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    `PRODID:-//${IDENTITY.organisation}//${IDENTITY.series}//EN`,
    'CALSCALE:GREGORIAN',
    `X-WR-CALNAME:${IDENTITY.organisation} ${IDENTITY.series}`,
    ...scheduled.map(agendaVevent),
    'END:VCALENDAR',
  ];
  return `${lines.join('\r\n')}\r\n`;
}

module.exports = function (cfg) {
  // `site.*`, for every template. Config global data rather than a
  // `src/_data/` file -- see `SITE`'s own comment above for why that is
  // not a matter of taste here.
  cfg.addGlobalData('site', () => SITE);
  // `notice.*`, for `_includes/layout.njk`'s colophon -- its own namespace,
  // never a key of `site`, for the reason `NOTICE` above gives.
  cfg.addGlobalData('notice', () => NOTICE);

  cfg.addPassthroughCopy('src/style.css');
  // Self-hosted fonts and their licences. Copied rather than pulled from a CDN
  // at runtime: this showcase admits no third-party dependency,
  // and a webfont request is one — it discloses every visitor's address.
  //
  // The files themselves moved from `src/fonts/` to
  // `../fonts/` -- one repository root shared with `app/`'s own copy step
  // (`app/scripts/copy-fonts.mjs`), rather than each side keeping its own
  // committed set that could drift apart the way the colour tokens already
  // had. The object form maps that parent directory back onto the same
  // `/fonts/` output path this build always served, so nothing downstream
  // (style.css's relative `url('fonts/...')`, layout.njk's `| url`-filtered
  // preload) had to change.
  cfg.addPassthroughCopy({ '../assets/fonts': 'fonts' });
  // The tab icon, copied from the one place the mark is drawn rather than
  // committed a second time here — the arrangement `app/scripts/copy-mark.mjs`
  // already makes for the cockpit, and that script's own comment carries the
  // reasoning in full: a charter declares a palette and a motif family and
  // never a logotype, so an instance naming `ribbon` has no mark of its own
  // for this to follow, and what a tab shows before a page is read is the
  // product a visitor is looking at.
  //
  // Declared rather than left to the browser's own guess. Without a
  // `<link rel="icon">` a browser asks the domain root for `/favicon.ico`,
  // which no build here writes, so every page of the showcase and of the
  // cockpit beneath it was served with a 404 behind the tab.
  cfg.addPassthroughCopy({ '../assets/brand/convener/convener-mark.svg': 'favicon.svg' });
  // The public showcase repository receives this
  // project's own build output at its root, alongside `app/`, which is
  // exactly what its already-active GitHub Pages setting ("branch main,
  // folder root") serves. Without this file, GitHub's default Jekyll
  // processing swallows that output and serves the README instead. Sourced
  // here rather than `touch`-ed by the publish workflow so that the built
  // site is reproducible from this repository alone.
  cfg.addPassthroughCopy('src/.nojekyll');
  // The published repository's own front page and its ignore file. They must
  // be *emitted by this build*, not merely committed once to the showcase:
  // `publish-showcase.yml::refresh_published_site` wipes everything at that
  // root except `.git` and `app/` before copying this output in, so anything
  // that lives only there is destroyed by the first publish. A public
  // repository whose landing page is a bare file listing explains nothing.
  //
  // The ignore file is stored under a neutral name because a real
  // `.gitignore` here would apply to this build's own directory.
  //
  // The front page itself is no longer a passthrough copy: it is
  // `src/publish-readme.njk`, a template with `permalink:
  // "/README.md"`, because it names the organisation and both repositories
  // and those are the instance's, declared once in `instance/config.json`.
  // A passthrough copy renders nothing, so a `{{ }}` in it would have been
  // published verbatim -- the exact failure `docs/handbook/toolkit/index.md` warns
  // about. A `.njk` under `src/` is fine where a `.md` was not: only `md`
  // is in `templateFormats` as a page-producing extension whose permalink
  // would have landed at `/README/`.
  cfg.addPassthroughCopy({ 'publish/gitignore-for-showcase': '.gitignore' });
  // The share banner(s) `visuals-production.yml` commits
  // under `src/banners/`. A plain string, anchored to this project's own
  // root exactly like the three passthrough copies above -- confirmed
  // empirically, not assumed, that Eleventy neither errors
  // nor writes anything when the source directory does not exist yet,
  // which is the ordinary state whenever no real edition is currently
  // scheduled (D-13): zero editions is zero banners, not a build failure.
  cfg.addPassthroughCopy('src/banners');

  // See `absoluteUrl`'s own comment above for what this does and why.
  cfg.addFilter('absoluteUrl', absoluteUrl);
  // `event | eventBannerUrl(banners)` for event.njk's own `pageImage` --
  // see `eventBannerUrl`'s own comment above for the argument in full.
  cfg.addFilter('eventBannerUrl', eventBannerUrl);
  // `shareImageWidth`/`shareImageHeight` -- see their own comment above.
  cfg.addGlobalData('shareImageWidth', SHARE_IMAGE_WIDTH);
  cfg.addGlobalData('shareImageHeight', SHARE_IMAGE_HEIGHT);

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

  // `event | eventDescription` for event.njk's `pageDescription` (its
  // <meta>/Open Graph/Twitter Card tags) and its own JSON-LD
  // `description`, and for feed.njk's per-item `<description>` -- see
  // `eventDescriptionFallback`'s own comment above for why this must be
  // one computation, not three hand-typed copies.
  cfg.addFilter('eventDescription', eventDescriptionFallback);

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

  // `events | agendaCalendar` for `src/agenda.njk` -- see
  // `agendaCalendar`'s own comment above for the feed in full.
  cfg.addFilter('agendaCalendar', agendaCalendar);

  // RFC 5545 requires CRLF line endings throughout, unlike every other
  // format this build writes (HTML, `style.css`, `feed.njk`'s own XML,
  // all plain `\n`). Neither the template source file nor Nunjucks
  // itself is CRLF-aware -- `agenda.njk`'s own trailing newline, and any
  // future edit to it, writes whatever line ending that source file
  // happens to end on, and this repository's own `.gitattributes`
  // normalises checked-in text to `eol=lf` besides (the reverse of the
  // CRLF-on-write trap `tools/convener_ops`'s own YAML writers guard against
  // with `newline=""`). Rather than trust every layer between
  // `agendaCalendar`'s own return value and the file GitHub Pages
  // serves to preserve the CRLFs it already wrote correctly, this
  // transform normalises the *rendered bytes* of every `.ics` output to
  // CRLF, once, as the last thing that touches them before Eleventy
  // writes the file.
  cfg.addTransform('crlfForCalendarFeeds', function (content, outputPath) {
    if (typeof outputPath === 'string' && outputPath.endsWith('.ics')) {
      return content.replace(/\r\n|\r|\n/g, '\r\n');
    }
    return content;
  });

  return {
    dir: { input: 'src', output: '_site' },
    templateFormats: ['njk', 'md'],
    htmlTemplateEngine: 'njk',
    pathPrefix: PATH_PREFIX,
  };
};

// D-14: `parisStandingStart` above is one of three independent
// implementations of the identical Europe/Paris seasonal-offset rule --
// `tools/convener_ops/publication/visual.py::paris_standing_start` and `app/src/state/
// derived.ts::parisStandingStart` are the other two -- and nothing bound
// the three together until now: each side's own test suite pinned its own
// hand-typed list of dates, and two of those lists had already drifted.
// `tools/tests/fixtures/paris-standing-start.json` is the one list every
// side now reads. Eleventy itself only ever calls `require('./.eleventy.js')`
// as a factory function (see `module.exports = function (cfg) {...}`
// above) and never looks at its own properties, so attaching this named
// export is inert to the real build -- it exists only for `site/scripts/
// check-paris-standing-start.cjs`, run from `tools/tests/
// test_paris_standing_start_fixture.py::test_eleventy_js_matches_the_
// shared_fixture` (`site/` carries no JS test runner of its own -- no new
// dependency -- so that Python suite is this function's only test).
module.exports.parisStandingStart = parisStandingStart;
