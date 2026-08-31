"""The data-protection processing record
(`docs/handbook/governance/traitement-donnees.md`), against the code it describes.

A page that states a number or an address the code also holds is a copy --
this project has paid for that drift before (`test_handbook_claims.py`'s own
module docstring records the view-counting window doing exactly this,
underneath a sentence claiming it could not). The two facts this page states
that carry legal weight -- the retention window, and the address a
participant is told to write to -- are pinned here against the constant and
the module the rest of the codebase already reads them from, the same D-14
discipline `test_confirmation.py` already applies to `SignupForm.tsx` and
the documentation copy of the matching-code instruction.
"""

from __future__ import annotations

import re

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.published import load_identity
from convener_ops.journey.confirmation import CONTACT_EMAIL
from convener_ops.journey.eventkeys import RETENTION_DAYS

ROOT = repo_root()
PAGE = ROOT / "docs" / "handbook" / "governance" / "traitement-donnees.md"

#: Written as a pattern, not a loose `"90" in text` check -- a page free to
#: mention "90" anywhere (a percentage, a different count) would still pass
#: that, and this test exists so it cannot.
_RETENTION = re.compile(r"destroyed \*\*(\d+) days\*\* after the event")

#: Same reasoning, for the address: the exact sentence a participant reads
#: under "Rights", not any address-shaped substring on the page.
_CONTACT = re.compile(r"Write to `([^`]+)` for any of the above")


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_the_record_exists() -> None:
    assert PAGE.is_file(), f"{PAGE.as_posix()} is missing"


def test_the_retention_window_matches_the_constant_the_code_uses() -> None:
    text = _page()
    match = _RETENTION.search(text)
    assert match is not None, (
        f"{PAGE.as_posix()} no longer states the retention window in the "
        "form this test reads; it can drift from eventkeys.RETENTION_DAYS "
        "again without this failing."
    )
    assert int(match.group(1)) == RETENTION_DAYS


def test_the_contact_address_matches_confirmation_pys_own_constant() -> None:
    """One address, and this page reaches it the way every other page the
    cockpit renders does.

    The literal here became `{{ instance.contact }}`,
    resolved by `render.ts::substituteWithoutSpeaker` when the cockpit
    renders this record -- the surface a Board member actually reads it
    on. So the assertion is that the token is what the page carries, and
    that it resolves to the address `confirmation.py` sends from.
    """
    text = _page()
    match = _CONTACT.search(text)
    assert match is not None, (
        f"{PAGE.as_posix()} no longer states a contact address in the form "
        "this test reads; it can drift from confirmation.CONTACT_EMAIL "
        "again without this failing."
    )
    assert match.group(1) == "{{ instance.contact }}", (
        f"{PAGE.as_posix()} writes the contact address out rather than "
        "naming it -- a duplicate would send its own participants here"
    )
    assert load_identity().namespace["contact"] == CONTACT_EMAIL


def test_the_record_names_every_one_of_the_seven_required_fields() -> None:
    """The seven a processing record has to name: the controller, what is
    held, the purpose, the legal basis, the recipients, the duration and
    the measures. A one-page record with a heading missing one of the seven
    is not a processing record, even if every
    sentence under the headings it does have is accurate. Matched as a
    whole line, not a substring --
    "## Measures" is also a substring of "## Measures Renamed", which this
    test must not silently accept as still having a "Measures" heading.

    `## Controller` was the one this page did not have, and its absence was
    not cosmetic: this page ships with the product, so a duplicate inherits
    it, and a record naming no controller is a record every reader is free
    to assume names the software's author. It answers for whoever runs the
    instance, which is why the heading below names the instance's own
    declaration rather than a person -- see
    `test_the_controller_is_the_instance_and_not_the_author`.
    """
    headings = {line.strip() for line in _page().splitlines() if line.startswith("## ")}
    for heading in (
        "## Controller",
        "## What we hold",
        "## Purpose",
        "## Legal basis",
        "## Recipients",
        "## Duration",
        "## Measures",
    ):
        assert heading in headings, f"{PAGE.as_posix()} is missing {heading!r}"


def test_the_controller_is_the_instance_and_not_the_author() -> None:
    """The controller has to be named the way every other identity on this
    page is named -- by the instance's own declaration, resolved when the
    cockpit renders the page -- and not written out.

    A literal organisation name here would be the whole defect this section
    exists to prevent, arriving from the other direction: a duplicate would
    publish somebody else's organisation as the controller of its own
    participants' data, on a page that reads as authoritative because every
    other claim on it is true.
    """
    controller = _page().split("## Controller", 1)[1].split("\n## ", 1)[0]
    assert "{{ instance.organisation }}" in controller, (
        f"{PAGE.as_posix()}'s Controller section no longer names the "
        "instance's own declared organisation; a duplicate inheriting this "
        "page would name whoever wrote the section instead"
    )
    assert "{{ instance.contact }}" in controller, (
        f"{PAGE.as_posix()}'s Controller section gives no contact address "
        "for the controller, which is half of what naming one is for"
    )


def test_the_record_does_not_overclaim_the_fingerprints_irreversibility() -> None:
    """Round-tripped once already (certificate.py's own module docstring,
    'the fingerprint is reversible, given the salt'): a claim that the
    fingerprint is 'never reversible in practice', unqualified, is exactly
    the overclaim that module was corrected away from. This page must not
    reintroduce it."""
    text = _page()
    assert "never reversible" not in text.lower()
