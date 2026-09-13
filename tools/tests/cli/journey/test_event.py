"""`convener-mint-event-key`: one pair, and the order that keeps it safe.

The private half is printed and stored nowhere else, so these readings are
about two things a later reader cannot check by inspection: that the pair
actually belongs together, and that nothing is published for an edition that
already has a live key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from convener_ops.cli.journey.event import mint_event_key
from convener_ops.declaration import paths
from convener_ops.journey import eventkeys


def test_the_printed_private_half_is_the_one_the_public_half_belongs_to(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property nothing downstream could recover from. The secret is set
    from stdout and the published file from `--public-out`, and if the two
    were ever not a pair every registration would encrypt to a key the job
    does not hold -- silently, because encrypting works fine against any valid
    public half."""
    out = tmp_path / "mrg-042.pub"
    assert mint_event_key(["--event", "mrg-042", "--public-out", str(out)]) == 0

    private = capsys.readouterr().out
    assert eventkeys.derive_public_pem(private) == out.read_text(encoding="utf-8")


def test_the_bytes_printed_are_bytes_that_decrypt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What this prints is what `gh secret set` stores, byte for byte, and
    what the decrypting job later reads out of its environment. So the
    reading is the round trip on exactly those bytes rather than a rule about
    trailing whitespace, which the PEM parser does not care about and which
    would go stale the first time anybody reformatted `generate`."""
    out = tmp_path / "mrg-042.pub"
    mint_event_key(["--event", "mrg-042", "--public-out", str(out)])

    private = capsys.readouterr().out
    public = out.read_text(encoding="utf-8")
    assert private.startswith("-----BEGIN")
    assert eventkeys.decrypt(private, eventkeys.encrypt(public, b"a registration")) == (
        b"a registration"
    )


def test_it_refuses_an_edition_that_already_has_a_live_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Minting cannot be undone and cannot be re-read: the pair it made last
    time is in a secret store nothing can read back. So the published half
    being there is the stop, and it is checked before anything is generated."""
    root = tmp_path
    published = root / eventkeys.KEYS_DIR
    published.mkdir(parents=True)
    (published / "mrg-042.pub").write_text(
        "-----BEGIN PUBLIC KEY-----", encoding="utf-8"
    )
    monkeypatch.setattr(paths, "repo_root", lambda: root)

    out = tmp_path / "elsewhere.pub"
    assert mint_event_key(["--event", "mrg-042", "--public-out", str(out)]) == 1
    assert not out.exists()
    assert "already exists" in capsys.readouterr().err


def test_the_id_is_lower_cased_before_anything_looks_for_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The published path, the secret name and the events feed all use the
    lower-cased id. A run given `MRG-042` must find the same live key a run
    given `mrg-042` would."""
    root = tmp_path
    published = root / eventkeys.KEYS_DIR
    published.mkdir(parents=True)
    (published / "mrg-042.pub").write_text(
        "-----BEGIN PUBLIC KEY-----", encoding="utf-8"
    )
    monkeypatch.setattr(paths, "repo_root", lambda: root)

    assert (
        mint_event_key(["--event", "MRG-042", "--public-out", str(tmp_path / "x.pub")])
        == 1
    )
    assert "already exists" in capsys.readouterr().err
