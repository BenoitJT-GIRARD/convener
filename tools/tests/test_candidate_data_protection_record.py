"""`docs/governance/candidate-data-protection.md`, against the schema it
describes.

A security review found that `docs/governance/traitement-donnees.md`
described `instance/data/speakers.yml` in one sentence -- "speakers' own names and
institutional email addresses" -- and pointed at
`docs/governance/selection-criteria.md` for the rest, which is the Board's
editorial judgement and never described a data-handling process at all. This
page is the fix: an honest account of what the file holds, established
against the schema rather than against what would be convenient to claim.

The finding was that a hand-written sentence and the schema had already
drifted apart once. Pinning today's field list against today's schema would
only prove they agree *today* -- exactly the gap that let the drift happen
the first time -- so this module binds the page's own field list to
`app/src/state/candidate-data.ts::PERSONAL_DATA_FIELDS` through
`tools/tests/fixtures/governance-cases.json`, the same fixture
`app/tests/personal-data-fields.test.ts` reads on the TypeScript side. A
field the model gains later and nobody classifies fails there, in the
language the model lives in, before this page can go on describing a file
that has moved on without it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from convener_ops.declaration.paths import repo_root

ROOT = repo_root()
PAGE = ROOT / "docs" / "governance" / "candidate-data-protection.md"
OLD_PAGE = ROOT / "docs" / "governance" / "traitement-donnees.md"

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "governance-cases.json").read_text(
        encoding="utf-8"
    )
)
PERSONAL_DATA_FIELDS = frozenset(CASES["speaker_personal_data_fields"]["personal"])

#: A bullet naming one or more fields, of the exact shape this page writes
#: them: backtick-quoted names, comma-separated, before the em dash that
#: opens the description. Restricted to the lead-in before the first " -- "
#: (an em dash) on the line, deliberately: several bullets go on to mention
#: a *code path* in backticks too (`PUBLISHABLE_ALWAYS`,
#: `app/src/state/diversity.ts`), inside the description rather than the
#: list of names, and a token pattern that did not stop at the em dash would
#: mistake one of those for a fifteenth field.
_BULLET_FIELD = re.compile(r"`(\w+)`")


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _what_we_hold_fields(text: str) -> set[str]:
    start = text.index("## What we hold")
    end = text.index("\n## ", start + 1)
    section = text[start:end]
    fields: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("- `"):
            continue
        lead_in = line.split(" — ", 1)[0]
        fields.update(_BULLET_FIELD.findall(lead_in))
    return fields


def test_the_record_exists() -> None:
    assert PAGE.is_file(), f"{PAGE.as_posix()} is missing"


def test_the_record_names_every_personal_data_field_the_schema_has() -> None:
    """The mechanism this module exists for. See the module docstring."""
    described = _what_we_hold_fields(_page())
    missing = PERSONAL_DATA_FIELDS - described
    extra = described - PERSONAL_DATA_FIELDS
    assert not missing, (
        f"{PAGE.as_posix()} no longer describes {sorted(missing)}, which "
        "app/src/state/candidate-data.ts::PERSONAL_DATA_FIELDS still "
        "classifies as personal data the schema holds."
    )
    assert not extra, (
        f"{PAGE.as_posix()} describes {sorted(extra)} as personal data, but "
        "candidate-data.ts::PERSONAL_DATA_FIELDS no longer does -- the page "
        "and the classification have drifted apart."
    )


def test_the_extraction_finds_something_when_there_is_something_to_find() -> None:
    """An empty match would make the test above pass for the wrong reason."""
    assert _what_we_hold_fields(_page()) == PERSONAL_DATA_FIELDS
    assert len(PERSONAL_DATA_FIELDS) > 0


def test_the_record_does_not_promise_a_retention_window_it_does_not_have() -> None:
    """The finding this page fixes included 'no retention and no erasure
    path'. A future edit that quietly added a retention promise here without
    the code to back it would be the same overclaim `test_processing_record.py`
    already guards against on the sibling page, made here instead."""
    text = _page().lower()
    assert "kept indefinitely" in text
    assert "no erasure path" in text


def test_the_old_record_points_at_this_one_instead_of_selection_criteria() -> None:
    """The broken pointer half of the fix: the participant-pipeline record
    used to credit `selection-criteria.md` with a process it never
    described. It must now point at this page instead."""
    old_text = OLD_PAGE.read_text(encoding="utf-8")
    assert "(candidate-data-protection.md)" in old_text
    assert "speakers' own names and institutional email addresses" not in old_text
