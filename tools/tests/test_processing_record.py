"""The processing record spec §4 asks for
(`docs/governance/traitement-donnees.md`), against the code it describes.

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

from convener_ops.confirmation import CONTACT_EMAIL
from convener_ops.eventkeys import RETENTION_DAYS
from convener_ops.paths import repo_root

ROOT = repo_root()
PAGE = ROOT / "docs" / "governance" / "traitement-donnees.md"

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
    text = _page()
    match = _CONTACT.search(text)
    assert match is not None, (
        f"{PAGE.as_posix()} no longer states a contact address in the form "
        "this test reads; it can drift from confirmation.CONTACT_EMAIL "
        "again without this failing."
    )
    assert match.group(1) == CONTACT_EMAIL


def test_the_record_names_every_field_spec_4_asks_for() -> None:
    """S:4's own words: "données, finalité, base légale, destinataires,
    durée, mesures" -- a one-page record with a heading missing one of the
    six is not what §4 asks for, even if every sentence under the headings
    it does have is accurate. Matched as a whole line, not a substring --
    "## Measures" is also a substring of "## Measures Renamed", which this
    test must not silently accept as still having a "Measures" heading."""
    headings = {line.strip() for line in _page().splitlines() if line.startswith("## ")}
    for heading in (
        "## What we hold",
        "## Purpose",
        "## Legal basis",
        "## Recipients",
        "## Duration",
        "## Measures",
    ):
        assert heading in headings, f"{PAGE.as_posix()} is missing {heading!r}"


def test_the_record_does_not_overclaim_the_fingerprints_irreversibility() -> None:
    """Round-tripped once already (certificate.py's own module docstring,
    'the fingerprint is reversible, given the salt'): a claim that the
    fingerprint is 'never reversible in practice', unqualified, is exactly
    the overclaim that module was corrected away from. This page must not
    reintroduce it."""
    text = _page()
    assert "never reversible" not in text.lower()
