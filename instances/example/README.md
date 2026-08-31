# The example instance

A second instance, invented, whose files sit here so that this repository
can be built as somebody other than the series that happens to run it
today.

`config/boundary.yml` names the paths an instance owns. This directory
holds one file for each of them, at the same relative path — so
`instances/example/instance/config.json` is what
`instance/config.json` would be, and `instances/example/instance/data/brand.json`
is what `instance/data/brand.json` would be. Nothing here is read at run time by
anything: a build that uses these files is a build in which they have
been copied into the places the boundary names.

**It belongs to the product, not to an instance.** Upstream ships it,
upstream maintains it, and a duplicate that edits it is editing an example
rather than its own configuration. That is why it is not in
`config/boundary.yml`'s list: the default there is the product, and this
directory takes the default.

## What it is for

**Proving the separation.** Instance from code is not a claim
anybody can read their way to. `tools/tests/test_second_instance.py`
copies this repository into a scratch tree, deletes every file the
boundary hands to the instance, lays these files into the holes, runs the
whole build — the four bundles, the showcase, the handbook copy, the
generated templates, the published feeds, the posters — and sweeps the
result for every written form of the *first* instance's name, addresses,
series and charter. If any survives, the build fails and names the file.

**Being the product's first consumer.** This is the
example instance a visitor can click through and the fixture `convener`'s
own test suite runs against. It is not a test double written for a
demonstration; it is what a duplicate looks like on the day it is made.

**Being what "not configured" is measured against.** The declaration here
is the thing every instance's own declaration is compared
with, value by value: while any of the eleven values in
`instance/config.json` is still one of these, the showcase prints a band
above its masthead on every page and the cockpit prints one above its
sign-in screen, naming the keys still to fill in
(`tools/convener_ops/declaration/published.py::unconfigured`, and one reader per language
beside it). That is why every value here has to stay invented and reserved
rather than merely plausible: a value somebody could genuinely declare
would make the warning fire on an instance that had been configured, and a
warning that shows when it should not is deleted within a week.

## Everything here is invented, and it can be checked

No real person, no real organisation, no real institution, no real
address. Three habits keep that true rather than merely intended:

- every address is under `.test`, which RFC 2606 reserves and no registry
  will ever delegate;
- every affiliation names an institution that does not exist, and every
  board login is prefixed `example-`;
- the combination is what makes a record unmistakably synthetic even if an
  invented name happens to be somebody's somewhere.

The one address that cannot follow the first habit is `published_url`.
`published.Published.publish_repository` derives the repository a built
site is pushed into, and derives it only from a GitHub Pages project
address; an `example.test` address there would make this instance refuse a
derivation the real one performs, leaving the most load-bearing half of
the declaration untested by the very build that exists to test it. So it
is `example-instance.github.io`, a name nobody is asked to register and
that nothing here resolves.

## What it deliberately does not hold

Three of the paths the boundary hands to an instance have no counterpart
here, and each absence is a decision recorded in
`test_second_instance.py::DELIBERATELY_ABSENT`, which fails if one of them
ever gains a counterpart or if a new instance path gains neither one nor a
reason:

- **`instance/keys/`** — a fresh duplicate holds no cryptographic material at all.
  Generating an event key or a signing key is an operator's act.
- **`instance/public-data/`** — empty in a fresh clone by construction: everything
  in it is derived from `instance/data/` by the product's own commands, and the
  second-instance build runs them.
- **`docs/handbook/governance/register.md`** — declared `regenerated: true`, which
  means a scheduled job rewrites it in full on both sides of any merge. A
  duplicate inherits upstream's copy and its own next push replaces it, so
  an authored one here would be an authored copy of a generated file.

## What it numbers its own editions

`instance/config.json` declares `edition_prefix: MRG`, and
`instance/data/speakers.yml` numbers the reading group's sessions `MRG-1`, `MRG-2`,
`MRG-3`. The prefix is the instance's, not the product's: nothing in
`tools/convener_ops/` or `app/src/` fixes one, and `validate_speakers` builds
its pattern from whatever the declaration holds.

It is also deliberately not `identity.short_name`, which is `TEC` here.
The two have no reason to move together — a series can want one form in
an e-mail subject and another in an identifier — and `short_name` is
prose, which gets reworded. An edition code cannot be: it is in a
published address (`/events/mrg-1/`), on every certificate issued for that
event and in `instance/keys/events/mrg-1.pub`, so it is declared once and then
frozen. Changing it after an edition has been assigned makes every code
already written fail validation, by name and with the reason.
