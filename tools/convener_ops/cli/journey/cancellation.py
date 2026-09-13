"""The two commands `.github/workflows/cancel-edition.yml` runs.

One says which cancelled editions nobody has written to yet; the other writes
to one edition's registrants and records that it did. The split is the one
`retention.yml` already uses -- compute, then act, then record -- and it is
what lets a run that fails halfway be re-run without sending anybody a second
message or leaving anybody unsent.

`journey/cancellation.py` holds the decisions and touches nothing; everything
that reads a file, sends a message or asks the clock is here.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from convener_ops.cli import step_output, store
from convener_ops.cli.journey.event import load_registrations
from convener_ops.declaration.paths import DATA_DIR, repo_root
from convener_ops.governance.rule import paris_today
from convener_ops.journey import cancellation, confirmation
from convener_ops.journey.platform import Room
from convener_ops.journey.platform_fcc import platform_from_env
from convener_ops.journey.registration import load_registration_file


def cancellations_pending(argv: Sequence[str] | None = None) -> int:
    """`convener-cancellations-pending`: the cancelled editions whose
    registrants have not been written to, one id per line and nothing else on
    stdout.

    What it read goes to stderr, so a run that finds nothing stays
    distinguishable from a run that looked at nothing -- the distinction
    `credential_expiry.summary` exists for, and the one a cancellation cannot
    afford to blur: "nobody to tell" and "could not read the records" look
    identical from a green Actions tab.
    """
    parser = argparse.ArgumentParser(prog="convener-cancellations-pending")
    parser.parse_args(argv)

    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    if errors:
        for line in errors:
            print(f"::error::{line}", file=sys.stderr)
        return 1

    ledger_path = root / cancellation.LEDGER_PATH
    if ledger_path.exists():
        data, ledger_errors = store.load(ledger_path)
        if ledger_errors:
            for line in ledger_errors:
                print(f"::error::{line}", file=sys.stderr)
            return 1
    else:
        data = None
    try:
        told = cancellation.ledger_from_data(data)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    waiting = cancellation.pending(speakers if isinstance(speakers, list) else [], told)
    print(
        f"{len(speakers) if isinstance(speakers, list) else 0} record(s) read, "
        f"{len(told)} cancellation(s) already told, {len(waiting)} waiting",
        file=sys.stderr,
    )
    for event_id in waiting:
        print(event_id)
    return 0


def tell_cancelled(argv: Sequence[str] | None = None) -> int:
    """`convener-tell-cancelled`: write to everyone registered for one
    cancelled edition, then record that it was done.

    Reads `EVENT_ID` and `EVENT_PRIVATE_KEY` -- the same per-event secret
    every other reader of `registrations.enc` reads -- and the SMTP settings
    `confirmation.deliver` resolves for itself.

    **An edition with no registrations is a success, not a failure.** It is
    the commonest case by far: most cancellations happen before anybody has
    signed up, and a command that exited non-zero on it would leave a red
    Actions tab for a series doing nothing wrong, which is how an operator
    learns to stop reading that tab.

    **It records nothing.** `convener-record-cancellation` does that, in a
    separate step, and the split is the whole reason there are two commands:
    writing the ledger means committing it, committing means a push that can
    be rejected, and the re-derive loop that answers a rejected push runs its
    handler again. A command that sent and recorded together would send a
    second message to everybody every time somebody else pushed first.
    """
    parser = argparse.ArgumentParser(prog="convener-tell-cancelled")
    parser.parse_args(argv)

    event_id = os.environ.get("EVENT_ID", "").strip().lower()
    if not event_id:
        print("::error::no event id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    speakers, errors = store.load(root / DATA_DIR / "speakers.yml")
    if errors:
        for line in errors:
            print(f"::error::{line}", file=sys.stderr)
        return 1
    speaker_list = speakers if isinstance(speakers, list) else []

    # Refused rather than trusted. A workflow that sent to an edition still
    # scheduled would tell a room full of people not to come to a talk that
    # is going ahead, and nothing downstream could undo it.
    record = next(
        (s for s in speaker_list if str(s.get("id", "")).lower() == event_id), None
    )
    if record is None:
        print(f"::error::no record matches event {event_id}", file=sys.stderr)
        return 1
    if record.get("status") != cancellation.CANCELLED:
        print(
            f"::error::{event_id} is {record.get('status')!r}, not "
            f"{cancellation.CANCELLED!r} -- nothing is sent for an edition "
            "that has not been cancelled",
            file=sys.stderr,
        )
        return 1

    cfg, _cfg_errors = store.load(root / DATA_DIR / "config.yml")
    platform = platform_from_env(
        os.environ, speaker_list, cfg if isinstance(cfg, dict) else None
    )
    try:
        event = confirmation.event_details(speaker_list, event_id, platform)
    except confirmation.EventNotFoundError:
        event = confirmation.EventDetails(
            title="", date="", room=Room(join_url="", instructions="")
        )

    sent = unsent = unreadable = 0
    enc_path = root / DATA_DIR / "events" / event_id / "registrations.enc"
    if enc_path.exists():
        private_pem = os.environ.get("EVENT_PRIVATE_KEY", "")
        if not private_pem:
            print(
                f"::error::{event_id} has registrations and no private key is "
                "configured, so nobody can be told",
                file=sys.stderr,
            )
            return 1
        try:
            current = load_registration_file(enc_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"::error::{enc_path.name}: {exc}", file=sys.stderr)
            return 1
        registrations, unreadable = load_registrations(current.entries, private_pem)
        for message in cancellation.every_registrant(registrations, event):
            if confirmation.deliver(message, os.environ).sent:
                sent += 1
            else:
                unsent += 1

    print(cancellation.summary(event_id, sent, unsent, unreadable))
    step_output.write(f"told={sent}\nunsent={unsent}\n")
    return 0


def record_cancellation(argv: Sequence[str] | None = None) -> int:
    """`convener-record-cancellation`: write one event id into the ledger.

    Reads `EVENT_ID`. Sends nothing, reads no registration and needs no key --
    which is the point: this is the half that gets run again when a push is
    rejected, and the half that must be safe to run again is the half that
    does nothing to anybody.

    **The ledger is written whatever the sending found**, including nothing to
    send. What it records is that this edition was handled, not that e-mail
    worked; a re-run that found nothing to do would otherwise keep finding it
    for ever. What did happen is on the sending step's own log.

    Idempotent: an event already in the ledger keeps the day it was first
    written, because that is the day the people were told.
    """
    parser = argparse.ArgumentParser(prog="convener-record-cancellation")
    parser.parse_args(argv)

    event_id = os.environ.get("EVENT_ID", "").strip().lower()
    if not event_id:
        print("::error::no event id supplied", file=sys.stderr)
        return 1

    root = repo_root()
    ledger_path = root / cancellation.LEDGER_PATH
    data = None
    if ledger_path.exists():
        data, ledger_errors = store.load(ledger_path)
        if ledger_errors:
            for line in ledger_errors:
                print(f"::error::{line}", file=sys.stderr)
            return 1
    try:
        told = cancellation.ledger_from_data(data)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    updated = cancellation.recorded(told, event_id, paris_today(datetime.now(UTC)))
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        store.dump(cancellation.ledger_to_data(updated)),
        encoding="utf-8",
        newline="",
    )
    print(f"{event_id} recorded in {cancellation.LEDGER_PATH.as_posix()}")
    return 0
