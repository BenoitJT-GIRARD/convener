"""Every writable form of what one instance declares about itself.

This began as `tools/tests/helpers/instance_identity.py`, for one reader:
the sweep that builds a second instance and refuses anything of the first
in what it produced. It moved here the day a second reader appeared --
one asking the same question of every blob of every ref rather than of
one build -- and a second reader is exactly when a thing has to move out
of `tests/` rather than be copied into the package. The test helper still
exists and still owns the *deferred register*; it imports what is here
rather than restating it, so there is one derivation and not two.

**Derived, never typed.** The address and the identity come from
`instance/config.json` through the reader that owns them, the palette from
the charter in force through `brand.source`. A needle nobody can derive is
a needle that goes stale the day the declaration moves, and this project
has already been caught by exactly that (see `needles`' own docstring).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..publication import brand
from . import published

#: A needle short enough that an accidental run of the same letters inside
#: minified output is plausible is matched on word boundaries instead of
#: as a bare substring. Only `identity.short_name` qualifies today, and
#: the alternative -- dropping it from the sweep -- would drop the one
#: form of an instance's name that its own templates use most.
_WORD_BOUNDED = re.compile(r"^[A-Za-z0-9]{1,5}$")


def needles(root: Path, instance: Path | None = None) -> dict[str, str]:
    """Every writable form of what one instance declares about itself.

    Derived, never typed: the address and the identity from
    `instance/config.json` through the reader that owns them, the palette
    from the charter in force through `brand.source`. A needle nobody can
    derive is a needle that goes stale the day the declaration moves.

    `instance` is `brand.under`: the directory this instance's own files
    sit in, `None` for the one whose files sit at `root` itself. Both
    readers below take it, and they take it for different halves of the
    same question -- the declaration is always a file of the instance's,
    and the charter is one only while the instance writes its own. The
    product's worked example names one instead, and the file that names
    is under the instance while the file it names is under the product.

    Both derived forms of a declared value are here as well as the value
    itself, because a copy does not have to be a copy of the whole thing
    to be one: a page can write the origin without the path, a poster can
    write the forum's registrable domain without the `www.`, and an
    architecture note can write the repository's name without its owner.

    Every field of the identity is here by enumeration, not by hand, and
    the reason is below in the code. Nothing about the *address* half is
    enumerable the same way -- `Published` derives four different shapes
    from one string -- so those four stay written out, and so are the two
    the edition prefix reaches an artefact as.

    **Nothing written out here can go missing all the same.**
    `test_second_instance.py::test_every_value_the_declaration_holds_is_
    swept` reads the declaration itself and fails on any value no needle
    covers, which is what turns the hand-written half of this dictionary
    from a list somebody has to remember to extend into one the suite
    extends for them.

    Deliberately absent, so that every needle below can be *proved* to
    match something in a real build rather than passing green by matching
    nothing (`test_second_instance.py`):

    - **`published.Published.publish_repository`.** It is where a build is
      pushed, read by two workflows and by nothing that renders. Its two
      halves are already needles (`host`, `path_prefix`).
    - **`published.CHARTER_KEY`.** The name of one of the product's own
      charters, and the one declared value that is the product's rather
      than the instance's -- `assets/brand/` is where the file it names is
      maintained. What reaches a page is that file's colours, and every
      one of them is a needle below, read through this key:
      `brand.load` asks `brand.source`, and `brand.source` reads it. So
      the key is swept by what it selects, which
      `test_second_instance.py::test_the_charter_key_is_swept_through_the_
      palette_it_names` measures rather than assumes. Sweeping for the
      name itself would fire on the product's own directory in every
      duplicate.
    - **`motif.width_ratio`.** The templates multiply it by a
      dimension and write the product, so the ratio itself never reaches
      an artefact.
    - **`typography`.** Both the product's default charter and this
      instance's name the two faces the product ships and serves from its
      own origin (D-17). A face is not an identity here; naming one that
      is not shipped would build a page that silently falls back.
    - **`black` and `white`.** Two colours in the charter's own palette
      that are nobody's identity, and that appear in every stylesheet ever
      written.
    """
    here = root / brand.under(instance)
    address = published.load(here)
    identity = published.load_identity(here)
    editions = published.load_edition_prefix(here)
    found = {
        "published_url": address.url,
        "origin": address.origin,
        "host": address.host,
        "path_prefix": address.path_prefix,
        # The edition prefix, as the two forms that actually reach an
        # artefact: `MRG-` in a code the showcase prints and the poster
        # sets, `mrg-` in the event page's own address, in
        # `instance/keys/events/<id>.pub` and in a certificate's verification
        # link (D-19). The declared value alone -- two letters, no
        # separator -- is *not* a needle, and that is a decision rather
        # than an omission: `contains` would match it on word boundaries,
        # and a two-letter run bounded by punctuation is exactly what a
        # minifier emits for an identifier. A needle that can fire on a
        # coincidence is a needle somebody eventually widens an exemption
        # for. Both forms below carry the separator the product itself
        # adds, so neither can be an accident.
        "edition_code_prefix": editions.code_prefix,
        "event_id_prefix": editions.event_prefix,
    }
    # Every declared identity field, enumerated from the declaration's own
    # list rather than written out again here. A near miss is why:
    # `strapline`, the poster's own hero line, joined the eight fields
    # below were a hand-typed dict -- so the new one was not a needle, and
    # the sweep of a second instance's build passed green over a poster
    # hard-typing this instance's motto. Found by breaking it on purpose
    # and watching nothing fail. A field that a duplicate declares is a
    # field a duplicate's artefacts print; there is no such thing as one
    # this sweep should not look for.
    found.update({name: getattr(identity, name) for name in published.IDENTITY_FIELDS})
    found.update(
        {
            "forum_host": identity.forum_host,
            "forum_domain": identity.forum_host.removeprefix("www."),
            "repository_name": identity.repository.partition("/")[2],
        }
    )
    for name, value in brand.colours(brand.load(root, instance)).items():
        if value in ("#ffffff", "#000000"):
            continue
        found[f"colour.{name}"] = value
    return found


def contains(text: str, needle: str) -> bool:
    """Whether `text` writes `needle`, on word boundaries when the needle
    is short enough for a coincidence to be plausible."""
    if _WORD_BOUNDED.match(needle):
        return re.search(rf"\b{re.escape(needle)}\b", text) is not None
    return needle in text


def forms(needle: str) -> tuple[str, ...]:
    """The spellings one needle actually reaches raw text as.

    Two of them, always, and both because *case* is a rendering choice
    this product's own generators make rather than a value anybody
    declared.

    - A colour is `#FECAC1` in the charter and `#fecac1` in the
      stylesheet generated from it.
    - A name is set in capitals wherever a composition sets it in
      capitals. `brand_templates` writes `organisation_caps`,
      `strapline_caps`, `address_caps` and `series_caps` -- and its own
      comment beside them calls that "a display treatment and not a
      re-spelling", which is exactly why it is invisible to a
      case-sensitive search: the declared value is the same value, spelt
      in a case nobody wrote down.

    The second was measured rather than supposed, and the values are
    deliberately not quoted here -- naming them is the defect. A
    repository built as another instance, which every check then in force
    had passed, still carried five of them in capitals: the organisation,
    its forum, its published host, the series' name and its strapline, in
    the two downloadable templates, in the video-call background, in an
    edge worker's test and in a typeface fixture, at the tip and
    throughout its history. Neither the rewrite nor the search that
    follows it saw one: both looked for the declared spelling only, and
    both built that spelling from this function.

    Returning the upper-case spelling here closes both at once, because
    both read this function: a rewrite converts what it now knows to look
    for, and a search refuses whatever the rewrite missed. It is not case
    *folding*, which this deliberately still does not do -- lower-casing
    the haystack would fold a declared abbreviation into its lower-case
    spelling and make a short needle fire on prose. It is one more
    spelling, named because a generator in this repository produces it.

    What this still does not reach is a value a composition *re-spells*
    rather than re-cases: an organisation that runs its own words
    together is set with those words separated, and that string is not
    this one upper-cased. `repository.SERIES_RESIDUE` is where a spelling
    nothing derives is written down, and it carries that one.

    Always a pair, even where the two halves are identical -- a needle
    already in capitals: `repository.identity_rules` pairs a value's
    forms with its replacement's positionally, and a tuple whose length
    depended on the value would pair the wrong two.

    A build sweep does not need any of this: it compares a *built*
    artefact with the values that built it, and both sides went through
    the same renderer. A history sweep does, because it reads whatever
    anybody ever typed.
    """
    if needle.startswith("#") and needle[1:].isalnum():
        return (needle.lower(), needle.upper())
    return (needle, needle.upper())
