/**
 * Global data derived from `events.json` for the archive pages (task 8):
 *
 * - `archive.past` -- delivered/archived editions, each augmented with the
 *   four-digit `year` its `date` falls in (`events.json`'s own dates are
 *   always `YYYY-MM-DD`, the same shape `public_data.py` and every
 *   fixture in this repository already use), in the order `events.json`
 *   already carries them.
 * - `archive.years` -- the distinct years at least one past edition falls
 *   in, newest first, each paired with how many editions that year holds.
 *   `archives-year.njk` walks this as its own pagination data to generate
 *   one `/archives/<year>/` page per year; `archives.njk` and
 *   `archives-filter.njk` read it to build the filter bar every archive
 *   page shares.
 *
 * Kept as one small, pure computation here rather than repeated with a
 * string-slice in every template that needs a year out of a date --
 * Eleventy's template language has no built-in for it, and a template is
 * the wrong place to invent one.
 */
const events = require('./events.json');

function past() {
  return events
    .filter(e => e.status === 'delivered' || e.status === 'archived')
    .map(e => ({ ...e, year: String(e.date).slice(0, 4) }));
}

function years(pastEvents) {
  const counts = new Map();
  for (const e of pastEvents) {
    counts.set(e.year, (counts.get(e.year) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([year, count]) => ({ year, count }))
    .sort((a, b) => b.year.localeCompare(a.year));
}

module.exports = () => {
  const pastEvents = past();
  return { past: pastEvents, years: years(pastEvents) };
};
