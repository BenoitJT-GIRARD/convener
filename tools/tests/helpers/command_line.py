"""What a test of a `convener_ops.cli` command needs on disk before it can
call one.

A command reads a repository: an instance declaration, a published event
key, an encrypted registration file, an attendance export, a certificate
register. Building one of those is not what any single command's tests are
about, and each of these was written once in the module that first needed
it and then reached for from three or four others -- which is how a file
holding the tests of six sub-packages ends up holding the fixtures of six
sub-packages too. Splitting that file put them here rather than leaving
one of its eleven modules importing out of another, which is the shape
that makes a test module's own subject unreadable from its imports.

`tools/tests/helpers/` and not `tools/tests/cli/`, for the reason this
directory's neighbours already give: what is here is read from more than
one module, and a helper inside `cli/` would be a module of that tree
named after nothing in `convener_ops/cli/`.
"""

from __future__ import annotations

from email.message import EmailMessage
from functools import cache
from pathlib import Path
from typing import ClassVar

import yaml
from conftest import config, speaker

from convener_ops.declaration.paths import repo_root
from convener_ops.journey import eventkeys
from convener_ops.journey.registration import (
    Registration,
    dump_registration_file,
    load_registration_file,
    upsert,
)
from convener_ops.journey.signing import generate

#: The name and address every certificate test in this section attends
#: with -- shared so `assert_no_personal_data_leaked` below sweeps for
#: the same three strings everywhere it is called.
ADA_PERSONAL_DATA = ("Ada", "Lovelace", "ada@example.org")


def assert_no_personal_data_leaked(text: str) -> None:
    """The original sweep
    (`test_issue_certificates_issues_one_certificate_for_an_eligible_attendee`)
    only ever ran on the freshly-issued path. A name and an address
    printed on the `already_registered` branch alone -- the branch every
    retry and every scheduled re-run actually takes -- survived the full
    suite. Factored into one helper so every call site sweeps the same
    three strings the same way, and a new branch is one call away from
    being covered rather than one omission away from leaking."""
    for leaked in ADA_PERSONAL_DATA:
        assert leaked not in text


def certificates_register_path(tmp_path: Path, event_id: str = "mrg-042") -> Path:
    return tmp_path / "instance" / "data" / "events" / event_id / "certificates.yml"


#: `revoke_certificate` do anything else with it, so every certificate id
#: a test hands either command through this env var must have
#: `_new_identifier`'s own shape -- 32 lowercase hex characters -- where
#: the old, human-readable "cert-under-test" would once have done just as
#: well. `CERT_ID` is reused everywhere a test only needs
#: *some* valid id; `CERT_ID_OTHER` is a second, distinct one for the few
#: tests that need two.
CERT_ID = "1" * 32
CERT_ID_OTHER = "2" * 32


def write_certificate_register(
    tmp_path: Path,
    event_id: str = "mrg-042",
    *,
    identifier: str = CERT_ID,
    fingerprint_value: str = "f" * 64,
    state: str = "issued",
    issued_on: str = "2026-08-20",
) -> None:
    """A hand-built one-row `certificates.yml`, for a test that needs
    `CERTIFICATE_ID` to resolve against *some* register row without caring
    which real attendee it names -- most of `reissue_certificate`'s and
    `revoke_certificate`'s own refusal paths never reach the point where
    the row's `fingerprint` is compared against anything, so a dummy value
    is honest here, not a shortcut. Tests that exercise the fingerprint
    match itself compute a real one with `certificate_fingerprint` instead
    (see `test_reissue_certificate_reissues_the_certificate_named_by_id`)."""
    path = certificates_register_path(tmp_path, event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "v": 1,
                "certificates": [
                    {
                        "identifier": identifier,
                        "event_id": event_id,
                        "issued_on": issued_on,
                        "fingerprint": fingerprint_value,
                        "state": state,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def prepare_event(
    tmp_path: Path,
    *,
    event_id: str = "mrg-042",
    registrations: tuple[Registration, ...] = (),
    attendance_rows: tuple[str, ...] = (),
    threshold_share: float = 0.6666666666666666,
) -> tuple[str, str]:
    """Everything `issue_certificates` needs on disk for one event, short
    of the environment variables a test still sets for itself (which
    secrets are present is exactly what most of these tests vary). Returns
    `(event_private_pem, signing_private_pem)`, so a test can pass both
    straight to `monkeypatch.setenv`."""
    private_pem, _ = publish_event_key(tmp_path, event_id)
    if registrations:
        # A single call carrying every registration -- `write_registrations`
        # starts from an empty file on each call it is given (`upsert`ing
        # onto `load_registration_file(None)`), so calling it once per
        # registration, as an earlier version of this loop did, overwrote
        # the file with only the *last* one and silently dropped the rest.
        # Never exercised until a test needed more than one registrant.
        write_registrations(tmp_path, event_id, private_pem, *registrations)
    if attendance_rows:
        write_attendance_csv(tmp_path, event_id, *attendance_rows)
    # Not `write_data` (used elsewhere in this file): that helper's own
    # `data_dir.mkdir(parents=True)` has no `exist_ok`, and `write_registrations` /
    # `write_attendance_csv` above already created `instance/data/events/<id>/`.
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "speakers.yml").write_text(
        yaml.safe_dump(
            [
                speaker(
                    edition_code=event_id.upper(),
                    title="On analytical engines",
                    date="2026-08-20",
                )
            ]
        ),
        encoding="utf-8",
    )
    (data_dir / "config.yml").write_text(
        yaml.safe_dump(config(eligibility_share=threshold_share)), encoding="utf-8"
    )
    signing_private_pem, _ = generate()
    return private_pem, signing_private_pem


#: The real declaration, copied into every scratch root below rather than
#: re-typed. `convener-validate` reads `instance/config.json` for the prefix its
#: editions are numbered under, and a second hand-typed
#: declaration here would be a second answer to what this instance is --
#: the same choice `test_publication_visuals.py::_fake_root` already makes.
#: Read on demand, never while this module loads.
#: `declarations/boundary.yml` hands this path to the instance, and a derived
#: repository is entitled not to have it until the derivation lays an
#: example's own file there. At module scope the read took the whole
#: module down at collection, every test in it with a stack trace; from
#: here it fails the tests that are actually about the declaration, and
#: says which file is missing.


@cache
def real_instance() -> str:
    return (repo_root() / "instance" / "config.json").read_text(encoding="utf-8")


def write_data(tmp_path: Path, speakers: object, cfg: object) -> None:
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "speakers.yml").write_text(yaml.safe_dump(speakers), encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "config.json").write_text(real_instance(), encoding="utf-8")


def publish_event_key(tmp_path: Path, event_id: str = "mrg-042") -> tuple[str, str]:
    private_pem, public_pem = eventkeys.generate()
    keys_dir = tmp_path / "instance" / "keys" / "events"
    keys_dir.mkdir(parents=True)
    (keys_dir / f"{event_id}.pub").write_text(public_pem, encoding="ascii")
    return private_pem, public_pem


#: Every string that would identify Ada personally, in the fields the
#: fixture above submits. Checked case-insensitively against whatever the
#: job printed -- never against the encrypted file, whose base64 content
#: can legitimately contain a short substring like "ada" by pure chance;
#: `eventkeys.py`'s own tests already cover the file's confidentiality
#: property directly, and a leak test on this job belongs on what the job
#: prints.
LEAK_STRINGS = (
    "Ada",
    "Lovelace",
    "ada@example.org",
    "Analytical Engines Institute",
)


class RecordingSmtpClient:
    """A fake `smtplib.SMTP`, substituted so `handle_registration` can
    exercise a genuine "sent" outcome without opening a socket.

    `sent` holds `EmailMessage`, not `object`: this double stands in for
    `convener_ops.journey.confirmation`'s own `smtplib.SMTP`, and that module builds an
    `EmailMessage` before every send. It is also what the tests below read
    back -- `get_content()` and header subscripting are `EmailMessage`'s
    own API, which the base `email.message.Message` does not carry."""

    sent: ClassVar[list[EmailMessage]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port

    def starttls(self) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        pass

    def send_message(self, message: EmailMessage) -> None:
        RecordingSmtpClient.sent.append(message)

    def __enter__(self) -> RecordingSmtpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


ATTENDANCE_CSV_HEADER = "display_name,email,joined_at,left_at,duration_seconds"


def write_registrations(
    tmp_path: Path, event_id: str, private_pem: str, *registrations: Registration
) -> None:
    file = load_registration_file(None)
    for registration in registrations:
        file, _replaced = upsert(file, registration, private_pem=private_pem)
    path = tmp_path / "instance" / "data" / "events" / event_id / "registrations.enc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_registration_file(file), encoding="utf-8")


def write_attendance_csv(tmp_path: Path, event_id: str, *rows: str) -> None:
    path = (
        tmp_path / "instance" / "data" / "events" / event_id / "attendance-import.csv"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join((ATTENDANCE_CSV_HEADER, *rows)) + "\n", encoding="utf-8")
