/**
 * Which event ids currently have a share banner ready to
 * publish -- `event.njk`'s own `eleventyComputed.pageImage` reads this list
 * (via `.eleventy.js::eventBannerUrl`) to decide whether an edition gets an
 * `og:image`/`twitter:image` tag at all, rather than always emitting one
 * that might not resolve. The tag was left out entirely at first
 * for exactly that reason -- see `layout.njk`'s own comment on the block
 * this feeds.
 *
 * Read from disk, from a sibling `banners/` directory, not from
 * `events.json`: nothing in the public data says whether a banner exists,
 * only whether an edition is `scheduled`, and those are not the same
 * question -- a scheduled edition still needs one *rendered* run before a
 * file exists for it. `path.join(__dirname, '..', 'banners')` resolves
 * relative to *this file's own location on disk*, which is inside
 * whichever copy of `src/` Eleventy is actually reading data from: unlike
 * `.eleventy.js`'s own passthrough copies (anchored to this project's
 * root, confirmed empirically -- see that file's own comment on
 * `addPassthroughCopy('src/banners')`), a `require`d `_data/*.js` file
 * runs from wherever it was loaded, the same reason `archive.js` above can
 * read a scratch copy's own `events.json` rather than the real
 * repository's. `tools/tests/test_site.py`'s own comment on its
 * `built_site_with_share_banner` fixture explains why that split matters
 * for testing this feature end to end.
 *
 * `visuals-production.yml` is the one writer of the real `src/banners/`:
 * it renders every currently *scheduled* real edition's own banner and
 * commits exactly that set, regenerating the directory whole on every run
 * -- an edition no longer scheduled loses its file the same run, so this
 * list, and therefore every `og:image` this build can ever emit, only
 * ever names a real, still-current announcement.
 */
const fs = require('fs');
const path = require('path');

module.exports = () => {
  const dir = path.join(__dirname, '..', 'banners');
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((name) => name.toLowerCase().endsWith('.png'))
    .map((name) => name.slice(0, -'.png'.length).toLowerCase())
    .sort();
};
