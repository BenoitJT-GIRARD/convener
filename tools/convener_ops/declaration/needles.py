"""Every writable form of what one instance declares about itself.

This began as `tools/tests/instance_identity.py`, for one reader:
the sweep that builds a second instance and refuses anything of the first
in what it produced. It has a second now, `derivation_guard.py`,
which asks the same question of every blob of every ref before a public
push -- and a second reader is exactly when a thing has to move out of
`tests/` rather than be copied into the package. The test helper still
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


def needles(root: Path) -> dict[str, str]:
    """Every writable form of what one instance declares about itself.

    Derived, never typed: the address and the identity from
    `instance/config.json` through the reader that owns them, the palette
    from the charter in force through `brand.source`. A needle nobody can
    derive is a needle that goes stale the day the declaration moves.

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
    address = published.load(root)
    identity = published.load_identity(root)
    editions = published.load_edition_prefix(root)
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
    for name, value in brand.colours(brand.load(root)).items():
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

    Colour needles are the one family whose *case* is a rendering choice
    rather than a value: `#FECAC1` in the charter, `#fecac1` in the
    stylesheet generated from it. The two are the same leak and a
    case-sensitive search sees only one of them, so anything sweeping raw
    text asks for both forms through here rather than lower-casing the
    haystack -- which would also fold a declared abbreviation into its
    lower-case spelling and make a short needle fire on prose.

    A build sweep does not need this: it compares a *built* artefact with
    the values that built it, and both sides went through the same
    renderer. A history sweep does, because it reads whatever anybody
    ever typed.
    """
    if needle.startswith("#") and needle[1:].isalnum():
        return (needle.lower(), needle.upper())
    return (needle,)
