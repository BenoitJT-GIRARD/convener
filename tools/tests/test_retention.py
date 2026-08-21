"""Task 15: retention, early erasure, and provable key destruction.

The brief's own words are the standard this module is held to: "a
retention announced and never carried out is worse than no retention -- it
makes people believe in a protection that does not exist." Acceptance
criterion 6 asks for the destruction to be *verified by a test*, not
merely implemented; this module is that verification, plus the two
companion guarantees phase 4 spec S4 names in the same breath: an early
erasure that touches only the entry it names (R-31), and a destruction
that leaves the certificate register untouched (R-29, ruling 2 in
`tools/convener_ops/certificate.py`'s own module docstring).

Three layers, in three sections below:

* `eventkeys.py`'s own pure functions -- the boundary date rule and the
  registry file format -- plus the one test that justifies the whole
  scheme: encrypt, destroy the key, try to read, and fail.
* `registration.py`'s `erase` and `find_by_matching_code` -- the early
  erasure procedure, tested the same way task 6 tested `upsert`: assert
  `==` on the neighbours, not merely "the file still decrypts" (R-31).
* `cli.py`'s `retention_sweep`, `record_destructions` and
  `erase_registration` -- the commands `.github/workflows/retention.yml`
  and `erase-registration.yml` actually run, including the credential
  that must fail the job loud rather than let it exit green having
  destroyed nothing (R-28).
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import speaker

from convener_ops import certificate, eventkeys
from convener_ops.certificate import CertificateEntry, register_from_data, register_to_data
from convener_ops.cli import erase_registration, record_destructions, retention_sweep
from convener_ops.eventkeys import DecryptionError, decrypt, encrypt, generate
from convener_ops.paths import repo_root
from convener_ops.registration import (
    AmbiguousMatchingCodeError,
    Registration,
    RegistrationFile,
    dump_registration_file,
    erase,
    find_by_matching_code,
    load_registration_file,
    matching_code,
    to_registration,
    upsert,
)

# ==================================================================== #
# eventkeys.py: is_due_for_destruction, the registry file format, and
# the test that justifies the whole scheme.
# ==================================================================== #


def test_is_due_for_destruction_is_false_the_day_before_the_boundary() -> None:
    """Day 89: still inside the retention window. Catches a mutant that
    shifts the deadline to `event_date + 89` -- that mutant would already
    say `True` here, one day early."""
    event_date = date(2026, 1, 1)
    assert (
        eventkeys.is_due_for_destruction(event_date, date(2026, 3, 31)) is False
    )  # 2026-01-01 + 89 days = 2026-03-31


def test_is_due_for_destruction_is_true_on_the_boundary_day() -> None:
    """Day 90 itself: the spec's own deadline ("date de l'evenement + 90
    jours"), inclusive. Catches a mutant that shifts the deadline to
    `event_date + 91` -- that mutant would still say `False` here."""
    event_date = date(2026, 1, 1)
    assert (
        eventkeys.is_due_for_destruction(event_date, date(2026, 4, 1)) is True
    )  # 2026-01-01 + 90 days = 2026-04-01


def test_is_due_for_destruction_stays_true_well_past_the_boundary() -> None:
    event_date = date(2026, 1, 1)
    assert eventkeys.is_due_for_destruction(event_date, date(2026, 9, 1)) is True


def test_after_the_key_is_destroyed_the_ciphertext_is_unreadable_forever() -> None:
    """Le test qui justifie tout le schema : on chiffre, on detruit, on
    essaie de relire, et l'echec est le resultat attendu. Sans lui, "les
    donnees deviennent definitivement illisibles" est une phrase et non
    une garantie.

    There is no separate cryptographic "destroy" call to invoke: R-30
    (`eventkeys.py`'s own module docstring) is that the private key IS the
    only thing that ever made a registration's ciphertext readable, so
    losing it -- `CONVENER_EVENT_KEY_<ID>` removed from the repository's
    secrets, `retention.yml`'s own `gh secret delete` step -- is
    destruction, in full. `del private_pem` below makes that literal: this
    test never holds the real key again after this line, exactly as a
    retention job never does once the secret is gone.

    **What this does not cover (Minor 5).** This proves the *scheme*
    cryptographically: destroying a key makes its ciphertext unreadable,
    full stop. It never calls `retention_sweep`, `record_destructions` or
    anything else in `cli.py`, and `del private_pem` is a no-op on a local
    Python name -- it would stay exactly this green even if a future
    change to production code quietly kept a second copy of the key
    somewhere the retention sweep does not know to destroy. There is no
    way to assert "the GitHub secret is actually gone" offline; the
    nearest available check is
    `test_no_write_call_in_convener_ops_ever_writes_a_private_key`, below,
    which is the reason such a second copy is implausible rather than
    merely untested.
    """
    private_pem, public_pem = generate()
    plaintext = b'{"first_name": "Ada", "surname": "Lovelace"}'
    ciphertext = encrypt(public_pem, plaintext)

    # Before destruction: readable, exactly as a job holding the secret
    # would read it inside the retention window.
    assert decrypt(private_pem, ciphertext) == plaintext

    # Destruction: the private key is gone. R-30 -- the ciphertext itself
    # is untouched; `ciphertext` above is the identical string, still
    # sitting right here, committed and unreadable, never deleted.
    del private_pem

    # The proof: nobody -- not even a fresh, entirely unrelated key pair
    # generated specifically to try -- can read this ciphertext any more.
    another_private_pem, _ = generate()
    with pytest.raises(DecryptionError):
        decrypt(another_private_pem, ciphertext)


def test_no_write_call_in_convener_ops_ever_writes_a_private_key() -> None:
    """Minor 5's own strengthening: the assertion that *is* available
    offline, since "the GitHub secret is gone" is not. Walks every `.py`
    file's AST under `tools/convener_ops` and refuses any `.write_text(...)`,
    `.write(...)` or `.write_bytes(...)` call whose argument is built from
    a name that looks like a private key, or a string literal carrying the
    PEM marker itself -- which would catch a second, forgotten copy on
    disk the moment someone wrote it, rather than trusting nobody ever
    will. `write_bytes` has no caller in this module today (round 2
    trivia); it is here so that stays true rather than merely assumed."""
    suspect_fragments = ("private_pem", "private_key")
    convener_ops_dir = repo_root() / "tools" / "convener_ops"
    checked = 0
    for path in sorted(convener_ops_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"write_text", "write", "write_bytes"}
            ):
                continue
            checked += 1
            for arg in (*node.args, *(kw.value for kw in node.keywords)):
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        assert "PRIVATE KEY" not in sub.value.upper(), (
                            f"{path.name}:{node.lineno} writes a string "
                            "literal carrying the PEM private key marker"
                        )
                    if isinstance(sub, ast.Name) and any(
                        fragment in sub.id.lower() for fragment in suspect_fragments
                    ):
                        raise AssertionError(
                            f"{path.name}:{node.lineno} calls "
                            f"{node.func.attr}(...) with {sub.id!r}, which "
                            "looks like a private key -- see this test's "
                            "own docstring (Minor 5)"
                        )
    assert checked > 0, "no write_text/write call found -- the walk itself is broken"


# -------------------------------------------------------------------- #
# The destruction registry: data/event-key-destructions.yml
# -------------------------------------------------------------------- #


def test_destructions_path_is_under_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (
        eventkeys.destructions_path(tmp_path)
        == tmp_path / "data" / "event-key-destructions.yml"
    )


def test_registry_from_data_is_empty_when_the_file_is_missing() -> None:
    assert eventkeys.registry_from_data(None) == {}


def test_registry_round_trips_through_to_data_and_back() -> None:
    registry = {"mrg-042": date(2026, 4, 1), "mrg-043": date(2026, 5, 1)}
    data = eventkeys.registry_to_data(registry)
    assert eventkeys.registry_from_data(data) == registry


def test_registry_to_data_sorts_by_event_id_for_a_stable_diff() -> None:
    registry = {"mrg-999": date(2026, 4, 1), "mrg-001": date(2026, 4, 1)}
    data = eventkeys.registry_to_data(registry)
    assert [entry["event_id"] for entry in data["destructions"]] == [
        "mrg-001",
        "mrg-999",
    ]


def test_registry_from_data_rejects_the_wrong_version() -> None:
    with pytest.raises(ValueError, match="format version"):
        eventkeys.registry_from_data({"v": 2, "destructions": []})


def test_registry_from_data_rejects_an_entry_with_an_extra_field() -> None:
    data = {
        "v": 1,
        "destructions": [
            {"event_id": "mrg-042", "destroyed_on": "2026-04-01", "by": "someone"}
        ],
    }
    with pytest.raises(ValueError, match="exactly an event id and a destruction date"):
        eventkeys.registry_from_data(data)


def test_registry_from_data_rejects_a_duplicate_event_id() -> None:
    data = {
        "v": 1,
        "destructions": [
            {"event_id": "mrg-042", "destroyed_on": "2026-04-01"},
            {"event_id": "mrg-042", "destroyed_on": "2026-05-01"},
        ],
    }
    with pytest.raises(ValueError, match="more than once"):
        eventkeys.registry_from_data(data)


def test_registry_from_data_rejects_an_invalid_date() -> None:
    data = {
        "v": 1,
        "destructions": [{"event_id": "mrg-042", "destroyed_on": "not-a-date"}],
    }
    with pytest.raises(ValueError, match="invalid"):
        eventkeys.registry_from_data(data)


def test_registry_from_data_rejects_a_non_list_destructions_value() -> None:
    with pytest.raises(ValueError, match="malformed"):
        eventkeys.registry_from_data({"v": 1, "destructions": "not-a-list"})


def test_registry_from_data_rejects_a_field_of_the_wrong_type() -> None:
    data = {"v": 1, "destructions": [{"event_id": "mrg-042", "destroyed_on": 20260401}]}
    with pytest.raises(ValueError, match="wrong type"):
        eventkeys.registry_from_data(data)


# ==================================================================== #
# registration.py: erase() and find_by_matching_code() -- the early
# erasure procedure, spec S4's "effacement avant echeance".
# ==================================================================== #


def test_erase_removes_the_named_entry() -> None:
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    updated, removed = erase(file, "ada@example.org", private_pem)

    assert removed is True
    assert updated.entries == ()


def test_erase_returns_false_when_nothing_matches() -> None:
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    updated, removed = erase(file, "grace@example.org", private_pem)

    assert removed is False
    assert len(updated.entries) == 1


def test_erase_on_an_empty_file_returns_false() -> None:
    private_pem, _ = generate()
    updated, removed = erase(RegistrationFile(), "ada@example.org", private_pem)
    assert removed is False
    assert updated.entries == ()


def test_erase_matches_regardless_of_case_or_whitespace() -> None:
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    _, removed = erase(file, " Ada@Example.ORG ", private_pem)

    assert removed is True


def test_erase_skips_an_entry_it_cannot_decrypt() -> None:
    """The `erase` twin of `upsert`'s and `find_by_email`'s own handling: a
    stray entry from another event's key must never read as a match, and
    must never be dropped by mistake."""
    private_pem, _ = generate()
    stray_entry = {
        "v": 1,
        "encrypted_key": "AA==",
        "iv": "AAAAAAAAAAAAAAAA",
        "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
    }
    file = RegistrationFile(entries=(stray_entry,))

    updated, removed = erase(file, "ada@example.org", private_pem)

    assert removed is False
    assert updated.entries == (stray_entry,)


def test_erase_leaves_every_other_entrys_ciphertext_byte_for_byte_unchanged() -> None:
    """R-31, and the test the task 15 brief names by its own reasoning:
    "reecriture du fichier chiffre sans l'enregistrement concerne, et rien
    d'autre ne bouge." Not "the file still decrypts" -- a rewrite that
    re-encrypted every survivor under fresh AES keys would still pass that
    weaker check. Ada's and Marie's entries must be the identical `dict`,
    key for key and byte for byte, both before and after Grace's is
    erased -- the same `==` idiom task 6's own
    `test_upsert_leaves_every_other_entrys_ciphertext_byte_for_byte_unchanged`
    already uses for an update, now applied to a removal."""
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    marie = Registration("Marie", "Curie", "marie@example.org", "", True)
    file = RegistrationFile()
    for registration in (ada, grace, marie):
        file, _replaced = upsert(file, registration, private_pem=private_pem)
    ada_entry, grace_entry, marie_entry = file.entries

    updated, removed = erase(file, "grace@example.org", private_pem)

    assert removed is True
    assert len(updated.entries) == 2
    assert ada_entry in updated.entries
    assert marie_entry in updated.entries
    assert grace_entry not in updated.entries
    # Every survivor is still independently decryptable -- an erasure that
    # broke the file for everyone else is not an erasure (task 15 brief,
    # step 3).
    assert to_registration(json.dumps(ada_entry), private_pem) == ada
    assert to_registration(json.dumps(marie_entry), private_pem) == marie


def test_find_by_matching_code_finds_the_matching_entry() -> None:
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)
    code = matching_code("mrg-042", "ada@example.org", "s3cr3t-salt")

    found = find_by_matching_code(
        file, "mrg-042", code or "", "s3cr3t-salt", private_pem
    )

    assert found == ada


def test_find_by_matching_code_is_case_insensitive_and_trims_whitespace() -> None:
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)
    code = matching_code("mrg-042", "ada@example.org", "s3cr3t-salt") or ""

    found = find_by_matching_code(
        file, "mrg-042", f"  {code.lower()}  ", "s3cr3t-salt", private_pem
    )

    assert found == ada


def test_find_by_matching_code_is_none_when_no_entry_matches() -> None:
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    assert (
        find_by_matching_code(file, "mrg-042", "ZZZZ-9999", "s3cr3t-salt", private_pem)
        is None
    )


def test_find_by_matching_code_is_none_without_a_salt() -> None:
    """An ordinary D-13 absence -- see `matching_code`'s own docstring:
    with no salt, no code was ever derivable for anyone, so nothing here
    could match by construction."""
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)

    assert find_by_matching_code(file, "mrg-042", "ABCD-2345", None, private_pem) is None


def test_find_by_matching_code_skips_an_entry_it_cannot_decrypt() -> None:
    private_pem, _ = generate()
    stray_entry = {
        "v": 1,
        "encrypted_key": "AA==",
        "iv": "AAAAAAAAAAAAAAAA",
        "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAA=",
    }
    file = RegistrationFile(entries=(stray_entry,))

    assert (
        find_by_matching_code(file, "mrg-042", "ABCD-2345", "s3cr3t-salt", private_pem)
        is None
    )


def test_find_by_matching_code_refuses_a_collision_instead_of_returning_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minor 8, against the reviewer's own recommendation: the probability
    of two registrations sharing a matching code is negligible
    (`matching_code`'s own docstring: ~1.9e-7 at the relay's 500-per-event
    ceiling), but the consequence -- erasing the wrong person's data
    irreversibly, with no signal -- is not something this codebase accepts
    elsewhere (`attendance._settle` refuses the identical situation by
    tying rather than guessing). A real collision is not reproducible
    without astronomical luck, so `matching_code` itself is monkeypatched
    to force one, the same technique the review used.

    Also asserts `tied` carries both colliding entries: `cli.py::erase_
    registration` reads this to attempt resolving the tie from a second
    field the requester actually supplied (a coordinator ruling after the
    review), so the exception must carry enough for that -- see
    `test_erase_registration_resolves_an_ambiguous_matching_code_using_
    the_address`."""
    private_pem, _ = generate()
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    file, _replaced = upsert(RegistrationFile(), ada, private_pem=private_pem)
    file, _replaced = upsert(file, grace, private_pem=private_pem)
    monkeypatch.setattr(
        "convener_ops.registration.matching_code",
        lambda event_id, email, salt: "ABCD-2345",
    )

    with pytest.raises(AmbiguousMatchingCodeError) as excinfo:
        find_by_matching_code(file, "mrg-042", "ABCD-2345", "s3cr3t-salt", private_pem)
    assert set(excinfo.value.tied) == {ada, grace}


# ==================================================================== #
# cli.py: retention_sweep(), record_destructions(), erase_registration()
# ==================================================================== #


def _publish_event_key(tmp_path: Path, event_id: str = "mrg-042") -> tuple[str, str]:
    private_pem, public_pem = generate()
    keys_dir = tmp_path / "keys" / "events"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{event_id}.pub").write_text(public_pem, encoding="ascii")
    return private_pem, public_pem


def _write_speaker(
    tmp_path: Path, event_id: str = "mrg-042", event_date: str = ""
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "speakers.yml").write_text(
        yaml.safe_dump([speaker(edition_code=event_id.upper(), date=event_date)]),
        encoding="utf-8",
    )


def _write_registrations(
    tmp_path: Path, event_id: str, private_pem: str, *registrations: Registration
) -> None:
    file = load_registration_file(None)
    for registration in registrations:
        file, _replaced = upsert(file, registration, private_pem=private_pem)
    path = tmp_path / "data" / "events" / event_id / "registrations.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_registration_file(file), encoding="utf-8")


def _write_certificate_register(
    tmp_path: Path, event_id: str = "mrg-042"
) -> tuple[Path, str]:
    """A minimal, valid `certificates.yml` for `event_id` -- R-29's own
    fixture: the register this task's destruction must leave untouched."""
    entry = CertificateEntry(
        identifier="a" * 32,
        event_id=event_id,
        issued_on=date(2026, 1, 5),
        fingerprint="f" * 64,
        state=certificate.STATE_ISSUED,
    )
    path = certificate.certificates_path(tmp_path, event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(register_to_data((entry,)))
    path.write_text(text, encoding="utf-8")
    return path, text


def _write_destruction_registry(tmp_path: Path, registry: dict[str, date]) -> None:
    path = eventkeys.destructions_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(eventkeys.registry_to_data(registry)), encoding="utf-8"
    )


def _github_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    output_file = tmp_path / "gh_output"
    output_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    return output_file


def _outputs(output_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output_file.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


# -------------------------------------------------------------------- #
# retention_sweep(): mutation 5 -- the credential must fail the job loud,
# not skip it.
# -------------------------------------------------------------------- #


def test_retention_sweep_fails_without_the_retention_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R-28's own test: a retention job that exits 0 having destroyed
    nothing must never look the same, from the Actions tab, as a run that
    genuinely had nothing to do. This must fail even though there is
    nothing on disk for it to find due -- the credential's absence alone
    is the failure, checked before anything else."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CONVENER_RETENTION_TOKEN", raising=False)

    assert retention_sweep() == 1
    assert "CONVENER_RETENTION_TOKEN" in capsys.readouterr().err


def test_retention_sweep_reports_nothing_due_on_an_ordinary_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    _write_speaker(tmp_path, "mrg-042", event_date="2026-08-01")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")

    # 2026-08-20 is day 19 of the retention window -- nowhere near due.
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 8, 20, 12, 0, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    assert "nothing due" in capsys.readouterr().out


class _FixedDatetime:
    """A stand-in for the `datetime` class `cli.py` imports, whose `now()`
    always returns the same instant -- the idiom this suite needs to pin
    "today" for a boundary test without waiting for the calendar.

    `combine` is the real `datetime.combine`, not a fixed stand-in: a test
    that patches `convener_ops.cli.datetime` to pin `retention_sweep`'s clock
    and then, in the same test, also calls `record_destructions` (which
    needs `datetime.combine` to turn `DESTROYED_ON` into a `now` for
    `eventkeys.destroy`) would otherwise see an `AttributeError` on a
    class this fixture never meant to touch."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self, tz: Any = None) -> datetime:
        return self._fixed

    combine = staticmethod(datetime.combine)


def test_retention_sweep_finds_an_event_past_its_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    _write_speaker(tmp_path, "mrg-042", event_date="2026-01-01")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    output_file = _github_output(tmp_path, monkeypatch)

    # 2026-04-01 is exactly day 90 -- due.
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 4, 1, 3, 0, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    out = capsys.readouterr().out
    assert "mrg-042" in out
    outputs = _outputs(output_file)
    assert outputs["destroyed_ids"] == "mrg-042"
    assert outputs["destroyed_secrets"] == "CONVENER_EVENT_KEY_MRG_042"
    assert outputs["destroyed_on"] == "2026-04-01"


def test_retention_sweep_uses_the_paris_day_not_the_utc_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Important 4: `today = paris_today(datetime.now(UTC))` at
    `cli.py:899` -- pinned at the one kind of instant where the mutant
    `datetime.now(UTC).date()` and the real implementation disagree.
    Every other delivered clock in this suite is fixed at 03:00 or 12:00
    UTC, where the Paris day and the UTC day happen to agree, which is
    exactly why that mutant survived the whole suite at 100% branch
    coverage (the review's own finding). An event held 2026-01-01, swept
    at 2026-03-31 22:30Z: still day 89 in UTC (not due), already day 90 in
    Paris, which is 2026-04-01 00:30 CEST after the spring change -- so
    the correct implementation reports it due, and the mutant does not.
    """
    _publish_event_key(tmp_path, "mrg-042")
    _write_speaker(tmp_path, "mrg-042", event_date="2026-01-01")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    output_file = _github_output(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 3, 31, 22, 30, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    outputs = _outputs(output_file)
    assert outputs["destroyed_ids"] == "mrg-042"
    assert outputs["destroyed_on"] == "2026-04-01"


def test_retention_sweep_uses_the_paris_day_not_a_fixed_cest_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Important 4, second half: the probe above pins one direction only
    -- it is fixed in summer, so a mutant that hardcodes CEST
    (`datetime.now(UTC) + timedelta(hours=2)`, always two hours ahead)
    agrees with the real implementation there and survives. Paris has two
    offsets, not one, and this project runs on Paris time year round.

    An event held 2025-10-04, swept at 2026-01-01 22:30Z: the real Paris
    offset in January is CET, one hour, not two. 22:30 UTC + 1 hour is
    23:30, still 2026-01-01 -- day 89, not due. A permanent-CEST mutant
    adds two hours instead, landing on 2026-01-02 -- day 90, wrongly due
    a day early. The two disagree only in this direction; the sibling
    test above disagrees only in the other (a permanent-CET mutant
    survives it, since CEST is the correct summer answer there) -- both
    are needed, and this one is not redundant with it.
    """
    _publish_event_key(tmp_path, "mrg-042")
    _write_speaker(tmp_path, "mrg-042", event_date="2025-10-04")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    output_file = _github_output(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 1, 1, 22, 30, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    outputs = _outputs(output_file)
    assert outputs["destroyed_ids"] == ""
    assert outputs["destroyed_on"] == "2026-01-01"


def test_retention_sweep_skips_an_event_already_in_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    _write_speaker(tmp_path, "mrg-042", event_date="2026-01-01")
    _write_destruction_registry(tmp_path, {"mrg-042": date(2026, 4, 1)})
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    _github_output(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 9, 1, 3, 0, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    assert "nothing due" in capsys.readouterr().out


def test_retention_sweep_skips_an_event_with_no_speaker_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "speakers.yml").write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    _github_output(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 9, 1, 3, 0, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    err = capsys.readouterr().err
    assert "mrg-042" in err
    assert "cannot be determined" in err
    # Important 1: the exit code and the message alone are not enough --
    # both held on the delivered code even though the message landed on
    # stderr, where nobody looks at a green job. `::warning::` is the
    # annotation this diff already uses twice elsewhere and is what
    # actually surfaces in the Actions run summary.
    assert "::warning::" in err


def test_retention_sweep_skips_an_event_with_no_usable_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    _write_speaker(tmp_path, "mrg-042", event_date="")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    _github_output(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 9, 1, 3, 0, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    err = capsys.readouterr().err
    assert "cannot be determined" in err
    assert "::warning::" in err


def test_retention_sweep_fails_on_a_malformed_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_path = eventkeys.destructions_path(tmp_path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("v: 2\ndestructions: []\n", encoding="utf-8")
    (tmp_path / "data" / "speakers.yml").write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")

    assert retention_sweep() == 1
    assert "format version" in capsys.readouterr().err


def test_retention_sweep_fails_on_a_registry_that_is_not_valid_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_path = eventkeys.destructions_path(tmp_path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("v: [unclosed\n", encoding="utf-8")
    (tmp_path / "data" / "speakers.yml").write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")

    assert retention_sweep() == 1
    assert "invalid YAML" in capsys.readouterr().err


def test_retention_sweep_fails_on_a_malformed_speakers_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "speakers.yml").write_text(
        "key: [unclosed\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")

    assert retention_sweep() == 1
    assert "invalid YAML" in capsys.readouterr().err


def test_retention_sweep_with_no_keys_directory_reports_nothing_due(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No event has ever published a key at all -- the ordinary state for
    a repository before its first event, and `keys/events/` itself does
    not exist yet."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "speakers.yml").write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    _github_output(tmp_path, monkeypatch)

    assert retention_sweep() == 0
    assert "nothing due" in capsys.readouterr().out


# -------------------------------------------------------------------- #
# record_destructions(): mutation 2 -- idempotence keeps the day of the
# first destruction, never the day of a retry.
# -------------------------------------------------------------------- #


def test_record_destructions_writes_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DESTROYED_IDS", "mrg-042")
    monkeypatch.setenv("DESTROYED_ON", "2026-04-01")

    assert record_destructions() == 0
    assert "mrg-042" in capsys.readouterr().out

    registry_path = eventkeys.destructions_path(tmp_path)
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert eventkeys.registry_from_data(data) == {"mrg-042": date(2026, 4, 1)}


def test_record_destructions_calls_eventkeys_destroy_and_refuses_a_malformed_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Important 3 / Minor 6: `record_destructions` is also
    `convener-record-destructions`, a console script an operator can run by
    hand against a plain `DESTROYED_IDS` environment variable with no
    guarantee it names a real, published event -- unlike the ids
    `retention_sweep` itself ever produces. Calling `eventkeys.destroy`
    (rather than a bare `dict.setdefault`) is what makes its own
    `_validate_event_id` guard apply here too, and this is the
    reproduction from the review: `DESTROYED_IDS="vw 042 oops"` must
    refuse rather than write a registry entry `registry_from_data` (the
    reader every other command shares) then permanently refuses to load."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DESTROYED_IDS", "vw 042 oops")
    monkeypatch.setenv("DESTROYED_ON", "2026-04-01")

    assert record_destructions() == 1
    assert "not a valid event id" in capsys.readouterr().err
    assert not eventkeys.destructions_path(tmp_path).exists()


def test_record_destructions_refuses_an_id_whose_key_was_never_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of `destroy`'s guard: a legal-looking id that never
    had a published key is not a destruction, it is a typo -- the same
    distinction `eventkeys.destroy`'s own docstring draws."""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DESTROYED_IDS", "mrg-999")
    monkeypatch.setenv("DESTROYED_ON", "2026-04-01")

    assert record_destructions() == 1
    assert "mrg-999" in capsys.readouterr().err
    assert not eventkeys.destructions_path(tmp_path).exists()


def test_record_destructions_deletes_the_published_pub_only_after_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-35 / Important 2: `keys/events/<id>.pub` is the signup relay's
    only "this event is open" gate, so it must go in the same operation
    that records the destruction -- and strictly after, per the ruling's
    own ordering, so `destroy`'s `key_was_published` guard still sees the
    truth. Both ends of that are asserted here: the registry gained the
    entry, and the `.pub` is gone afterward -- which is also, by
    construction, the test that would fail if a future change deleted the
    `.pub` first: `key_was_published` would already read `False` for this
    never-before-recorded id, `destroy` would raise, and this would assert
    `record_destructions() == 0` against a `1`."""
    _, public_pem = _publish_event_key(tmp_path, "mrg-042")
    pub_path = tmp_path / "keys" / "events" / "mrg-042.pub"
    assert pub_path.read_text(encoding="ascii") == public_pem
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DESTROYED_IDS", "mrg-042")
    monkeypatch.setenv("DESTROYED_ON", "2026-04-01")

    assert record_destructions() == 0

    registry_path = eventkeys.destructions_path(tmp_path)
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert eventkeys.registry_from_data(data) == {"mrg-042": date(2026, 4, 1)}
    assert not pub_path.exists()


def test_record_destructions_never_overwrites_an_existing_destruction_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end-to-end guarantee `eventkeys.destroy` promises in isolation
    (`test_destroy_is_idempotent_on_an_already_destroyed_event`,
    `test_eventkeys.py`, task 1) held all the way through the file this
    task actually persists it to. Catches a mutant that recorded the day
    of a retry rather than the day of the first destruction -- exactly
    the task 15 brief's second named mutation."""
    _write_destruction_registry(tmp_path, {"mrg-042": date(2026, 4, 1)})
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DESTROYED_IDS", "mrg-042")
    # A much later retry, as if a rejected push had this step re-run weeks
    # after the original destruction.
    monkeypatch.setenv("DESTROYED_ON", "2026-05-15")

    assert record_destructions() == 0

    registry_path = eventkeys.destructions_path(tmp_path)
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert eventkeys.registry_from_data(data) == {"mrg-042": date(2026, 4, 1)}


def test_record_destructions_with_no_ids_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("DESTROYED_IDS", raising=False)

    assert record_destructions() == 0
    assert not eventkeys.destructions_path(tmp_path).exists()


def test_record_destructions_rejects_an_invalid_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DESTROYED_IDS", "mrg-042")
    monkeypatch.setenv("DESTROYED_ON", "not-a-date")

    assert record_destructions() == 1
    assert "not a valid date" in capsys.readouterr().err


def test_record_destructions_fails_on_a_malformed_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_path = eventkeys.destructions_path(tmp_path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("v: 2\ndestructions: []\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("DESTROYED_IDS", "mrg-042")
    monkeypatch.setenv("DESTROYED_ON", "2026-04-01")

    assert record_destructions() == 1
    assert "format version" in capsys.readouterr().err


# -------------------------------------------------------------------- #
# R-29: the certificate register survives destruction. R-30: so does the
# ciphertext file -- unreadable, not absent.
# -------------------------------------------------------------------- #


def test_destruction_leaves_the_certificate_register_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling 2 (`certificate.py`'s own module docstring), and the task 15
    brief's fourth named mutation: destruction must delete or rewrite
    only `registrations.enc`, never so much as touch `certificates.yml`
    in the same directory. Byte-for-byte, not merely "still parses" --
    a rewrite that reformatted the register would still pass a weaker
    check."""
    _publish_event_key(tmp_path, "mrg-042")
    _write_speaker(tmp_path, "mrg-042", event_date="2026-01-01")
    register_path, register_text_before = _write_certificate_register(
        tmp_path, "mrg-042"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    _github_output(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 4, 1, 3, 0, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    monkeypatch.setenv("DESTROYED_IDS", "mrg-042")
    monkeypatch.setenv("DESTROYED_ON", "2026-04-01")
    assert record_destructions() == 0

    assert register_path.read_text(encoding="utf-8") == register_text_before
    reloaded = register_from_data(
        yaml.safe_load(register_path.read_text(encoding="utf-8"))
    )
    assert len(reloaded) == 1
    assert reloaded[0].event_id == "mrg-042"


def test_destruction_leaves_the_ciphertext_file_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-30: deleting `registrations.enc` would not make anything more
    unreadable than losing the key already has, and would invite the next
    reader to believe deletion is what made it safe. Destruction never
    removes the file -- only the key that could ever open it."""
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    ciphertext_before = enc_path.read_text(encoding="utf-8")
    _write_speaker(tmp_path, "mrg-042", event_date="2026-01-01")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CONVENER_RETENTION_TOKEN", "a-fine-grained-pat")
    _github_output(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "convener_ops.cli.datetime",
        _FixedDatetime(datetime(2026, 4, 1, 3, 0, tzinfo=UTC)),
    )

    assert retention_sweep() == 0
    monkeypatch.setenv("DESTROYED_IDS", "mrg-042")
    monkeypatch.setenv("DESTROYED_ON", "2026-04-01")
    assert record_destructions() == 0

    assert enc_path.exists()
    assert enc_path.read_text(encoding="utf-8") == ciphertext_before


# -------------------------------------------------------------------- #
# erase_registration(): identifies by matching code (preferred) or
# address (fallback, R-32), and proves -- from the registry -- that a
# destroyed event has nothing left to erase.
# -------------------------------------------------------------------- #


def test_erase_registration_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)
    assert erase_registration() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_erase_registration_for_an_unknown_event_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")

    assert erase_registration() == 1
    assert "not known to this repository" in capsys.readouterr().err


def test_erase_registration_after_destruction_proves_nothing_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Step 4 of the task 15 brief: "et c'est demontrable" -- proved from
    the committed registry, not merely asserted. This must not even ask
    for a private key: an event whose destruction is on record has
    nothing left that a key could read."""
    _write_destruction_registry(tmp_path, {"mrg-042": date(2026, 4, 1)})
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert erase_registration() == 0
    out = capsys.readouterr().out
    assert "2026-04-01" in out
    assert "nothing to erase" in out


def test_erase_registration_refuses_a_key_supplied_for_a_destroyed_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Minor 4: a key that still opens `registrations.enc` for an event
    this registry already calls destroyed contradicts the one thing
    `convener-erase-registration` exists to prove -- so this must refuse loudly
    (exit 1) rather than confirm "nothing to erase" over a contradiction,
    which is what the delivered code did (it never looked at
    `EVENT_PRIVATE_KEY` once `destroyed_on` was found)."""
    private_pem, _ = generate()
    _write_destruction_registry(tmp_path, {"mrg-042": date(2026, 4, 1)})
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert erase_registration() == 1
    err = capsys.readouterr().err
    assert "mrg-042" in err
    assert "2026-04-01" in err


def test_erase_registration_with_no_identifying_input_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("MATCHING_CODE", raising=False)
    monkeypatch.delenv("REGISTRATION_EMAIL", raising=False)

    assert erase_registration() == 1
    assert "no matching code or e-mail address" in capsys.readouterr().err


def test_erase_registration_without_a_configured_key_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.delenv("EVENT_PRIVATE_KEY", raising=False)

    assert erase_registration() == 1
    assert "no private key configured" in capsys.readouterr().err


def test_erase_registration_with_nothing_recorded_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert erase_registration() == 1
    assert "no registrations recorded" in capsys.readouterr().err


def test_erase_registration_for_an_unknown_address_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "grace@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert erase_registration() == 1
    assert "no registration found" in capsys.readouterr().err


def test_erase_registration_removes_only_the_named_entry_by_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada, grace)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("MATCHING_CODE", raising=False)

    assert erase_registration() == 0
    assert "erased" in capsys.readouterr().out

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    remaining = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(remaining.entries) == 1
    assert to_registration(json.dumps(remaining.entries[0]), private_pem) == grace


def test_erase_registration_prefers_the_matching_code_over_the_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-32: the code, already in the participant's own confirmation
    e-mail, is tried first -- this test supplies a matching code that
    resolves to Ada and a *wrong* address, and expects Ada to be the one
    erased anyway."""
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada, grace)
    code = matching_code("mrg-042", "ada@example.org", "s3cr3t-salt") or ""
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("MATCHING_CODE", code)
    monkeypatch.setenv("REGISTRATION_EMAIL", "not-ada-at-all@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt")

    assert erase_registration() == 0

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    remaining = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(remaining.entries) == 1
    assert to_registration(json.dumps(remaining.entries[0]), private_pem) == grace


def test_erase_registration_refuses_an_ambiguous_matching_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Minor 8, at the command `convener-erase-registration` an operator
    actually runs: a colliding code with no address to disambiguate it
    must not silently erase whichever entry happens to be stored first.
    Forces the collision the same way
    `test_find_by_matching_code_refuses_a_collision_instead_of_returning_
    the_first` does, and additionally asserts neither entry was touched --
    a refusal that erased one of the two anyway would be worse than
    either concrete choice."""
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada, grace)
    monkeypatch.setattr(
        "convener_ops.registration.matching_code",
        lambda event_id, email, salt: "ABCD-2345",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("MATCHING_CODE", "ABCD-2345")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt")
    monkeypatch.delenv("REGISTRATION_EMAIL", raising=False)

    assert erase_registration() == 1
    err = capsys.readouterr().err
    assert "share one matching code" in err
    # Minor 3 (round 2): the code itself must never reach stderr -- the
    # invariant every other refusal path in convener_ops already holds.
    assert "ABCD-2345" not in err

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    remaining = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(remaining.entries) == 2


def test_erase_registration_refuses_a_collision_the_address_does_not_narrow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third case the coordinator's own ruling names: a code collision
    plus an address, but the address does not pick out exactly one of the
    tied entries either (here, an address belonging to neither Ada nor
    Grace) -- still refuses, the same as no address at all. Reading
    evidence that does not resolve anything is not a reason to guess."""
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada, grace)
    monkeypatch.setattr(
        "convener_ops.registration.matching_code",
        lambda event_id, email, salt: "ABCD-2345",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("MATCHING_CODE", "ABCD-2345")
    monkeypatch.setenv("REGISTRATION_EMAIL", "not-ada-or-grace@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt")

    assert erase_registration() == 1
    err = capsys.readouterr().err
    assert "share one matching code" in err
    assert "ABCD-2345" not in err

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    remaining = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(remaining.entries) == 2


def test_erase_registration_resolves_an_ambiguous_matching_code_using_the_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The middle case a future reader will assume is a bug and is not:
    a code collision, plus an address that narrows the tie to exactly one
    entry, proceeds and erases that one -- using a second field the
    requester actually supplied is not the guess attendance._settle (and
    AmbiguousMatchingCodeError's own docstring) refuses to make. Grace's own
    address disambiguates the tie between Ada and Grace; Ada must survive,
    byte-for-byte untouched."""
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    grace = Registration("Grace", "Hopper", "grace@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada, grace)
    monkeypatch.setattr(
        "convener_ops.registration.matching_code",
        lambda event_id, email, salt: "ABCD-2345",
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("MATCHING_CODE", "ABCD-2345")
    monkeypatch.setenv("REGISTRATION_EMAIL", "grace@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("CONVENER_MATCHING_SALT", "s3cr3t-salt")

    assert erase_registration() == 0

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    remaining = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert len(remaining.entries) == 1
    assert to_registration(json.dumps(remaining.entries[0]), private_pem) == ada


def test_erase_registration_falls_back_to_the_address_without_a_salt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    ada = Registration("Ada", "Lovelace", "ada@example.org", "", False)
    _write_registrations(tmp_path, "mrg-042", private_pem, ada)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("MATCHING_CODE", "ZZZZ-9999")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)
    monkeypatch.delenv("CONVENER_MATCHING_SALT", raising=False)

    assert erase_registration() == 0

    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    remaining = load_registration_file(enc_path.read_text(encoding="utf-8"))
    assert remaining.entries == ()


def test_erase_registration_rejects_a_malformed_committed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_pem, _ = _publish_event_key(tmp_path, "mrg-042")
    enc_path = tmp_path / "data" / "events" / "mrg-042" / "registrations.enc"
    enc_path.parent.mkdir(parents=True, exist_ok=True)
    enc_path.write_text('{"v": 2, "registrations": []}', encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")
    monkeypatch.setenv("EVENT_PRIVATE_KEY", private_pem)

    assert erase_registration() == 1
    assert "not a supported format version" in capsys.readouterr().err


def test_erase_registration_rejects_a_malformed_destruction_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _publish_event_key(tmp_path, "mrg-042")
    registry_path = eventkeys.destructions_path(tmp_path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("v: 2\ndestructions: []\n", encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("REGISTRATION_EMAIL", "ada@example.org")

    assert erase_registration() == 1
    assert "format version" in capsys.readouterr().err
