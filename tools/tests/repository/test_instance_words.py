"""No path the product ships is named after the instance that runs it.

**The gap this closes, and why nothing already held it.** Every sweep in
this repository that looks for one instance's identity in another's
output compares *declared values*: `needles` derives them from
`instance/config.json` and the charter in force, and
`test_second_instance.py` looks for them in a build. Every one of them
reads **content**. A file *name* is nobody's declared value, so they are
all blind to it, and the identity walked out in one:

    .github/workflows/publish-vitrine.yml
    site/publish/gitignore-for-vitrine

`vitrine` is the French for showcase and it is the second half of
`example-showcase`, the repository this instance publishes its showcase into.
The product's own prose says *showcase* everywhere; those two paths said
this instance's word, in an English tree, in files every duplicate
receives, and the derivation could not rewrite them -- it rewrites what a
file says, not what a file is called.

**How a word is decided to be the instance's, without anybody typing a
list.** Two declarations are read, not one: this instance's, and the
example instance's (`examples/the-example-collective/instance/config.json`), which the
product ships filled in and `test_second_instance.py` already builds this
whole repository as. A word both declarations contribute is the
*product's* -- it is a word this project uses about itself, which is why
it survives being written out twice for two different instances. A word
only this instance's declaration contributes is this instance's.

That subtraction is the whole argument, and it is what makes `cockpit`
pass without an exemption: this instance's `identity.repository` is
`.../example-cockpit` and the example's is `.../example-cockpit`, so
`cockpit` cancels, and `tools/convener_ops/publication/cockpit.py` is a
product module named in the product's own word. `series`, `github` and
`https` cancel the same way. `vitrine` does not: the example's counterpart
is `example-showcase`.

**Matched as whole path tokens, never as substrings.** A path is split on
everything that is not a letter or a digit, so `publish-vitrine.yml`
offers `publish`, `vitrine`, `yml`. Substring matching would fire
`com` on every `components/` and `org` on every `organisation`, and a
sweep that fires on a coincidence is a sweep somebody widens an exemption
for until it means nothing -- the same reasoning `needles._WORD_BOUNDED`
already gives for the one needle short enough to be matched loosely.
Tokens shorter than three characters are dropped for the same reason: the
edition prefix reaches an artefact as `MRG-` and `mrg-`, which a path
segment cannot be told apart from an abbreviation.

**Product-owned paths only.** `declarations/boundary.yml` says which paths are
the instance's, and a path the instance owns is *supposed* to be able to
carry the instance's name -- `instance/keys/events/mrg-05.pub` is that
file's whole point. The question here is only ever about what upstream
ships.

**What this cannot see**, stated rather than left to be found: the
*contents* of a file (that is `needles`' half, and it is the larger one),
a word neither declaration spells out (an organisation that runs its own
words together is `repository.SERIES_RESIDUE`'s problem, not this one),
and a name that is this instance's for a reason nothing declares -- a
volunteer's initials, a room number, a supplier. The subtraction can only
know what one declaration says and another does not.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Final

import pytest
from helpers import instance_identity

from convener_ops.declaration import boundary, published
from convener_ops.declaration.paths import repo_root

ROOT: Final = repo_root()

#: The example instance's own declaration, at the path
#: `declarations/boundary.yml`'s own header describes: one file for each path
#: an instance owns, at the same relative path under `examples/the-example-collective/`.
EXAMPLE: Final = Path("examples/the-example-collective/instance/config.json")

#: A token this short is not a name in a path, it is an extension or an
#: abbreviation, and both declarations are full of them (`io`, `so`, `vw`,
#: `www` is three and stays). Below this length a match is a coincidence
#: far more often than a leak.
MINIMUM_TOKEN: Final = 3

#: Words this instance's declaration contributes that are nonetheless not
#: this instance's, each with the argument for it. The shape is
#: `boundary.yml`'s `kept:`: an
#: exemption states its reason beside itself, and
#: `test_no_exemption_survives_the_word_it_was_written_for` below refuses
#: one that no longer excuses anything -- an exemption nobody needs is a
#: line that only hides the next one.
#:
#: Both come from the two declared values that are not *names*. Everything
#: else under `identity` names this instance; these two do not, and a
#: subtraction against another instance's declaration cannot tell the
#: difference on its own.
NOT_A_NAME_OF_THIS_INSTANCE: Final = {
    "online": (
        "from `identity.tagline`, which is a sentence of ordinary English "
        "describing what the series is rather than a name -- 'a community "
        "series of online behavioural-science webinars'. "
        "`docs/handbook/toolkit/emails/video-online.md` is the product's "
        "own template for a call that happens online, and it is named "
        "after the call, not after this series"
    ),
    "tally": (
        "from `identity.proposal_form`, whose address is a third party's. "
        "Tally is the form service `declarations/integrations.yml` declares this "
        "product integrates with, so the word belongs to the vendor and "
        "reaches the declaration only because this instance's form happens "
        "to be hosted there. `tools/scripts/create_tally_form.py` creates a "
        "form on that service for any instance at all"
    ),
}

pytestmark = pytest.mark.skipif(
    instance_identity.ships_the_example_as_its_instance(ROOT),
    reason=instance_identity.ONE_INSTANCE,
)


def _tokens(text: str) -> set[str]:
    """The words of one string, lower-cased, with everything that is not a
    letter or a digit treated as a separator.

    The same reader for a declared value and for a path, deliberately: the
    comparison below is only meaningful if both sides were cut the same
    way, and two readers would eventually be cut differently.
    """
    return {
        token.lower()
        for token in re.split(r"[^A-Za-z0-9]+", text)
        if len(token) >= MINIMUM_TOKEN
    }


def _declared_tokens(declaration: Path) -> set[str]:
    """Every word one declaration's own values are made of.

    `published.declared_values` is asked for the values rather than the
    file being read key by key here: it already answers "every value this
    declaration carries about *who* is publishing", it is the reader
    `unconfigured` uses to decide whether a duplicate has made the
    declaration its own, and a second enumeration here would be a second
    thing to remember to extend.
    """
    data = json.loads((ROOT / declaration).read_text(encoding="utf-8"))
    words: set[str] = set()
    for value in published.declared_values(data).values():
        words |= _tokens(value)
    return words


def instance_words() -> set[str]:
    """The words that name this instance and not the product.

    This declaration's words, less the example declaration's, less the two
    exemptions above. Derived on every call rather than cached: it is
    cheap, and a module-level constant would be a copy of a declaration,
    which is the thing this whole tree exists to stop making.
    """
    return (
        _declared_tokens(Path("instance/config.json"))
        - _declared_tokens(EXAMPLE)
        - set(NOT_A_NAME_OF_THIS_INSTANCE)
    )


def _product_paths() -> list[str]:
    """Every path this repository tracks that `declarations/boundary.yml` leaves
    to the product.

    `git ls-files`, never a walk: a walk sees `node_modules/`,
    `site/_site/` and whatever else a working tree happens to hold, and
    the question here is about what upstream ships.
    """
    # Fixed argv, shell=False.
    listed = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    declaration = boundary.load(ROOT)
    return [
        path
        for path in listed.stdout.split()
        if declaration.owner_of(path) == boundary.PRODUCT
    ]


def test_no_product_path_is_named_after_this_instance() -> None:
    """The property, over every tracked path at once rather than one test
    per path: a failure has to be able to print the whole list, because
    the fix for one of these is nearly always the fix for all of them.
    """
    words = instance_words()
    found = {
        path: sorted(_tokens(path) & words)
        for path in _product_paths()
        if _tokens(path) & words
    }
    assert not found, (
        "these paths belong to the product -- upstream ships them and "
        "every duplicate receives them -- and they are named after the "
        f"instance that happens to run this repository: {found}. A "
        "declared value in a file's *contents* is rewritten when another "
        "instance takes this repository over, and swept for afterwards; a "
        "file's *name* is neither, so this is the only place it can be "
        "refused. Rename the path after what the file does, in the "
        "product's own words"
    )


def test_the_sweep_reproduces_the_defect_it_exists_for() -> None:
    """Positive control, in the exact shape the repository carried.

    Two paths, one word, and the word had to survive the subtraction
    against the example's declaration to be found at all -- so this pins
    both halves at once: `vitrine` is refused, and `showcase`, the word
    the example's own address is built from, is not.
    """
    words = instance_words()
    assert _tokens(".github/workflows/publish-vitrine.yml") & words == {"vitrine"}
    assert not _tokens(".github/workflows/publish-showcase.yml") & words
    assert not _tokens("site/publish/gitignore-for-showcase") & words


def test_the_product_s_own_words_survive_the_subtraction() -> None:
    """The other half of the same control, and the reason the example
    declaration is read at all.

    `cockpit` is this product's word for the application it ships, used
    throughout its prose and in three tracked paths. It is also the second
    half of this instance's own `identity.repository`, so a sweep built on
    one declaration would have refused
    `tools/convener_ops/publication/cockpit.py` and forced an exemption
    that says nothing. Both declarations spell it, so it cancels, and no
    exemption is needed for it or for the three below.
    """
    words = instance_words()
    for shared in ("cockpit", "series", "github", "https"):
        assert shared not in words, (
            f"{shared!r} is spelt in both declarations, so it is a word "
            "this product uses about itself rather than a word that names "
            "one instance -- the subtraction was supposed to cancel it"
        )


def test_the_subtraction_still_leaves_something_to_look_for() -> None:
    """Non-vacuity. A declaration whose every value the example also
    carried -- or a reader that stopped finding values -- would leave the
    sweep above passing over an empty needle set for ever, which is the
    one failure a green result cannot distinguish from success.

    Not asserted in a repository whose declaration *is* the example's:
    the module abstains there in full, for the reason
    `instance_identity.ONE_INSTANCE` gives.
    """
    assert instance_words(), (
        "no word separates this instance's declaration from the example's, "
        "so the sweep above has nothing to look for and cannot fail"
    )


def test_no_exemption_survives_the_word_it_was_written_for() -> None:
    """An exemption that excuses nothing is a line that reads as a
    judgement and makes none -- the same defect `.github/CODEOWNERS`
    carried and `test_codeowners.py` refuses, one file along.

    Each entry has to still be a word this declaration contributes and the
    example's does not; the day the tagline is reworded or the proposal
    form moves, the entry that mentioned it fails here rather than sitting
    on quietly, widening the hole for the next word that lands in it.
    """
    live = _declared_tokens(Path("instance/config.json")) - _declared_tokens(EXAMPLE)
    for word, reason in NOT_A_NAME_OF_THIS_INSTANCE.items():
        assert word in live, (
            f"{word!r} is exempt here because {reason}, but this "
            "instance's declaration no longer contributes it -- the "
            "exemption is dead and belongs deleted, not kept in case it "
            "comes back"
        )
