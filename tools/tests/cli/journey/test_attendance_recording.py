"""release_recording(): retrieve, verify the retrieval, then
delete. This ordering gets a test that fails if deletion
is reachable without a verified retrieval, not a paragraph. Every test
below that expects no deletion asserts directly on
`transport.delete_calls`, never only on the return code -- a change
that returns 1 but deletes anyway would still fail one of these.

`_FakeRecordingTransport` is keyed by the exact path or URL it is asked
for, never a positionless queue: a caller
that resolves the wrong conference id touches a path this fake was
never told about and fails loudly, rather than silently answering with
data that happens to belong to a different conference. `_patch_platform`
forwards whatever `conference_ids` `release_recording` actually built
from `CONVENER_FCC_CONFERENCE_ID` -- never hardcodes it -- so a test that
sets the wrong value genuinely exercises a different path.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import config, speaker
from helpers.command_line import (
    write_data,
)

from convener_ops.cli.journey.attendance import (
    discard_recording,
    release_recording,
)
from convener_ops.journey.platform_fcc import (
    RETRIEVED_TICK,
    FCCRequestError,
    PlatformFCC,
)

_CONFERENCE_ID = "618515381"
_PATH = f"/conferences/{_CONFERENCE_ID}"
_RECORDING_URL = "https://cdn.example.org/rec/618515381"
_VIDEO_URL = _RECORDING_URL + ".video.mp4"


def _recording_payload(
    *, available: bool = True, file_size: int = 900_000_000
) -> dict[str, Any]:
    if not available:
        return {
            "recording_url": "",
            "file_size": 0,
            "is_recorded": False,
            "deleted": False,
        }
    return {
        "recording_url": _RECORDING_URL,
        "file_size": file_size,
        "is_recorded": True,
        "deleted": False,
    }


def _video_headers(*, content_length: int = 900_000_000) -> dict[str, str]:
    """A `head()` response shaped exactly like the provider's own
    converted recording, as measured against the real provider:
    `video/mp4`, `Accept-Ranges: bytes`."""
    return {
        "content_type": "video/mp4",
        "accept_ranges": "bytes",
        "content_length": str(content_length),
    }


class _FakeRecordingTransport:
    """Structurally an `FCCTransport` -- `get_json`/`delete`/`head` --
    keyed by the exact path or URL it is asked for. `get_results` maps a
    path to a list of payload-dicts or exceptions, consumed in call
    order, so the pre-delete and post-delete reads of the same path can
    answer differently. Records every call it receives, so a test can
    assert directly on what was, and was not, called -- never only on
    `release_recording`'s return code."""

    def __init__(
        self,
        get_results: dict[str, list[Any]],
        head_responses: dict[str, dict[str, str] | None] | None = None,
        delete_error: Exception | None = None,
    ) -> None:
        self._get_results = {path: list(queue) for path, queue in get_results.items()}
        self.head_responses = dict(head_responses or {})
        self.delete_error = delete_error
        self.get_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.head_calls: list[str] = []

    def get_json(self, path: str, token: str) -> Any:
        self.get_calls.append(path)
        queue = self._get_results.get(path)
        if not queue:
            raise AssertionError(f"unexpected GET {path}")
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def delete(self, path: str, token: str) -> None:
        self.delete_calls.append(path)
        if self.delete_error is not None:
            raise self.delete_error

    def head(self, url: str) -> dict[str, str] | None:
        self.head_calls.append(url)
        return self.head_responses.get(url)


def _write_speaker_for_recording(
    tmp_path: Path,
    event_id: str = "mrg-042",
    retrieved: bool = False,
    consent_granted: bool = False,
) -> None:
    """`retrieved=True` ticks `RETRIEVED_TICK` on `runbook_progress` --
    trace 1. Never sets `youtube_url`: that field is a
    publication signal, deliberately irrelevant to this guard.

    `consent_granted=True` sets
    `publication.consent: "granted"` and nothing else -- the one condition
    `cli/journey/attendance.py::_consent_granted` requires before `release_recording`
    will even attempt the two-trace check. `outcome` is deliberately left
    blank even when `consent_granted=True`: the whole point is that
    `outcome` (the board's own, later archive gate) must not gate this
    function at all. Defaults to `False` (the ordinary state for a fresh
    talk whose speaker has not yet answered, and the only state
    `discard_recording`'s own tests need, since that function never reads
    `publication` at all)."""
    runbook_progress = {RETRIEVED_TICK: True} if retrieved else {}
    publication: dict[str, Any] = {
        "consent": "granted" if consent_granted else "",
        "approved_by": "",
        "approved_on": "",
        "objections": [],
        "outcome": "",
    }
    write_data(
        tmp_path,
        [
            speaker(
                edition_code=event_id.upper(),
                runbook_progress=runbook_progress,
                publication=publication,
            )
        ],
        config(),
    )


def _set_fcc_env(
    monkeypatch: pytest.MonkeyPatch,
    event_id: str = "mrg-042",
    conference_id: str = _CONFERENCE_ID,
) -> None:
    monkeypatch.setenv("EVENT_ID", event_id)
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.setenv("CONVENER_FCC_CONFERENCE_ID", conference_id)


def _patch_platform(
    monkeypatch: pytest.MonkeyPatch, transport: _FakeRecordingTransport
) -> None:
    def fake_platform_from_env(
        env: Any,
        speakers: Any = (),
        config: Any = None,
        conference_ids: Any = None,
    ) -> PlatformFCC:
        return PlatformFCC(
            access_token="tok",
            speakers=speakers,
            config=config,
            conference_ids=dict(conference_ids or {}),
            transport=transport,
        )

    monkeypatch.setattr(
        "convener_ops.cli.journey.attendance.platform_from_env", fake_platform_from_env
    )


@pytest.mark.parametrize(
    ("label", "publication"),
    [
        ("granted", {"consent": "granted"}),
        ("refused", {"consent": "refused"}),
        ("pending", {"consent": "pending"}),
        ("blank", {"consent": ""}),
        ("unrecognised", {"consent": "yes please"}),
        ("missing_key", {}),
        ("missing_block", None),
        ("malformed_block", "not a mapping"),
    ],
)
def test_consent_granted_is_the_narrow_silence_is_never_a_yes_rule(
    label: str, publication: Any
) -> None:
    """`_consent_granted` is the one place this asymmetry is checked, so
    it is pinned directly rather than only through `release_recording`'s
    own behaviour: only the literal string `"granted"` is a yes; every
    other value, including one this project has never seen before, and a
    missing or malformed `publication` block entirely, is silence."""
    from convener_ops.cli.journey.attendance import _consent_granted

    record: dict[str, Any] = {}
    if publication is not None:
        record["publication"] = publication

    assert _consent_granted(record) == (label == "granted")


def test_release_recording_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert release_recording() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_release_recording_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")

    assert release_recording() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_release_recording_with_an_unknown_event_id_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-999")

    assert release_recording() == 1
    assert "mrg-999" in capsys.readouterr().err


def test_release_recording_reports_a_malformed_speakers_file_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "speakers.yml").write_text("key: [unclosed\n", encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")

    assert release_recording() == 1
    assert "invalid YAML" in capsys.readouterr().out


def test_release_recording_refuses_when_consent_is_not_granted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Enforced, not only documented. A
    fresh talk (the default, unfixtured `publication` block -- consent
    blank, the ordinary state before a speaker has answered) is refused
    before any platform interaction at all -- not the two-trace check
    that ran here before, a different, earlier one."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", retrieved=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.setenv("CONVENER_FCC_CONFERENCE_ID", _CONFERENCE_ID)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert "publication consent is not granted" in err
    assert "discard_recording" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_refuses_when_consent_is_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pins the asymmetry `_consent_granted`'s own docstring names --
    "not did they refuse but did they agree" -- for the one value most
    likely to be mistaken for a soft yes: a speaker who has been asked and
    has not yet answered must not release either."""
    write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                publication={
                    "consent": "pending",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "",
                },
                runbook_progress={RETRIEVED_TICK: True},
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "publication consent is not granted" in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_refuses_when_consent_is_refused_even_with_a_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exact scenario, expected to refuse rather than
    succeed: a speaker who explicitly refused consent, with the host
    having retrieved the recording regardless. `release_recording` is the
    wrong route for this -- `discard_recording` is (see the dedicated
    test in that section)."""
    write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                youtube_url="",
                publication={
                    "consent": "refused",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "withheld",
                },
                runbook_progress={RETRIEVED_TICK: True},
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "publication consent is not granted" in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_succeeds_when_consent_is_granted_regardless_of_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The concrete regression test for the correction: a
    speaker who agreed, on a talk `finalize-archive` has not yet run for
    (the ordinary state right after an event) -- exactly the scenario
    the wrong gate refused. Freeing the
    quota is not publishing, so this must succeed regardless of
    `outcome`."""
    write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                publication={
                    "consent": "granted",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "",
                },
                runbook_progress={RETRIEVED_TICK: True},
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]},
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert transport.delete_calls == [_PATH]
    assert "retrieved, verified, and released" in capsys.readouterr().out


def test_release_recording_without_a_configured_account_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-13: no token is the ordinary state. ManualPlatform holds no
    recording storage of its own, so this is a harmless no-op, not a
    failure. `consent_granted=True` so this test still reaches that branch rather
    than the (new, earlier) publication gate."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", consent_granted=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert release_recording() == 0
    assert "nothing to release" in capsys.readouterr().out


def test_release_recording_is_a_noop_when_nothing_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", consent_granted=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport({_PATH: [_recording_payload(available=False)]})
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert "nothing to release" in capsys.readouterr().out
    assert transport.delete_calls == []


def test_release_recording_treats_a_malformed_runbook_progress_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`runbook_progress` loaded as `None`, or any non-mapping, must
    refuse rather than crash -- the same "empty means missing" reading
    `release_recording` gives a genuinely absent tick. Consent granted
    so this test still reaches the retrieval-tick check, not the (new,
    earlier) publication gate."""
    write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                runbook_progress=None,
                publication={
                    "consent": "granted",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "published",
                },
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert RETRIEVED_TICK in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_refuses_without_the_retrieved_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=False, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert RETRIEVED_TICK in err
    assert transport.delete_calls == []


def test_release_recording_ignores_youtube_url_and_still_requires_the_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`youtube_url` is a publication signal,
    not a retrieval one, and must not satisfy this guard by itself --
    even when it is set to something plausible. Consent granted so
    this test still reaches the retrieval-tick check."""
    write_data(
        tmp_path,
        [
            speaker(
                edition_code="MRG-042",
                youtube_url="https://youtu.be/abc123",
                runbook_progress={},
                publication={
                    "consent": "granted",
                    "approved_by": "",
                    "approved_on": "",
                    "objections": [],
                    "outcome": "published",
                },
            )
        ],
        config(),
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert RETRIEVED_TICK in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_succeeds_once_consent_is_granted_and_both_traces_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive case the consent gate still has to permit: a talk
    whose speaker agreed (`consent: granted`) and whose retrieval is
    genuinely verified must still succeed -- the gate narrows who may use
    this route, it does not additionally weaken the two traces that
    already governed it."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]},
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert transport.delete_calls == [_PATH]
    assert "retrieved, verified, and released" in capsys.readouterr().out


def test_release_recording_refuses_when_the_converted_video_is_not_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    # No head_responses entry: the fake answers `None` for every URL, the
    # same "not yet" `_UrllibTransport.head` gives on a 404.
    transport = _FakeRecordingTransport({_PATH: [_recording_payload()]})
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert "converted recording" in err
    assert transport.delete_calls == []


def test_release_recording_refuses_a_200_that_looks_like_an_error_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reviewer's probe: a 200 with
    `Content-Type: text/html` (a CDN's own error page, or a followed
    redirect to one) must not count as proof of conversion."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]},
        head_responses={_VIDEO_URL: {"content_type": "text/html; charset=utf-8"}},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "converted recording" in capsys.readouterr().err
    assert transport.delete_calls == []


def test_release_recording_does_not_delete_when_get_recording_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard on a failed retrieval: it must never still delete."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [FCCRequestError("GET /conferences/618515381 failed: timeout")]}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "failed" in capsys.readouterr().err.lower()
    assert transport.delete_calls == []


def test_release_recording_refuses_a_non_numeric_conference_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reviewer's probe, with the exact value they
    used (`THIS-IS-THE-WRONG-CONFERENCE`). With `_patch_platform` no
    longer hardcoding `conference_ids`, this reaches `PlatformFCC`'s own
    digit-only validation and is refused before any
    transport call -- never silently deletes whatever the fake happens to
    have registered under a different, hardcoded path."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch, conference_id="THIS-IS-THE-WRONG-CONFERENCE")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert "not a valid FCC conference id" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_refuses_a_path_shaped_conference_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reviewer's probe: a hand-typed conference id
    shaped like a path-traversal payload must never reach `DELETE`."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch, conference_id="618/../999")
    transport = _FakeRecordingTransport(
        {}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    err = capsys.readouterr().err
    assert "not a valid FCC conference id" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_returns_1_when_no_conference_id_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Closes the untested branch of `cli/`'s
    `{event_id: conference_id} if conference_id else {}` conditional
    expression, invisible to `coverage --branch` as a branch (Important
    1) -- an absent `CONVENER_FCC_CONFERENCE_ID` must refuse cleanly, not
    silently resolve to whatever `conference_ids` happened to hold
    before."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.delenv("CONVENER_FCC_CONFERENCE_ID", raising=False)
    transport = _FakeRecordingTransport(
        {}, head_responses={_VIDEO_URL: _video_headers()}
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert "mrg-042" in capsys.readouterr().err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_release_recording_deletes_the_conference_named_by_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proves `CONVENER_FCC_CONFERENCE_ID` genuinely determines which
    conference is released -- a different, non-hardcoded id, registered
    under its own path in the fake, is the one that gets deleted."""
    other_id = "777777"
    other_path = f"/conferences/{other_id}"
    other_video_url = "https://cdn.example.org/rec/777777.video.mp4"
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch, conference_id=other_id)
    transport = _FakeRecordingTransport(
        {
            other_path: [
                {
                    "recording_url": "https://cdn.example.org/rec/777777",
                    "file_size": 900_000_000,
                    "is_recorded": True,
                    "deleted": False,
                },
                _recording_payload(available=False),
            ]
        },
        head_responses={other_video_url: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert transport.delete_calls == [other_path]
    assert transport.get_calls == [other_path, other_path]


def test_release_recording_deletes_once_both_traces_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]},
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 0
    assert transport.delete_calls == [_PATH]
    assert "retrieved, verified, and released" in capsys.readouterr().out


def test_release_recording_reports_when_delete_recording_itself_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]},
        head_responses={_VIDEO_URL: _video_headers()},
        delete_error=FCCRequestError("DELETE /conferences/618515381 returned HTTP 500"),
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert transport.delete_calls == [_PATH]
    # No post-delete confirmation is attempted once the deletion itself
    # failed: only the one pre-delete read happened.
    assert transport.get_calls == [_PATH]
    assert "500" in capsys.readouterr().err


def test_release_recording_alerts_when_space_stays_occupied_after_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An alert, not silence, when the quota is still
    occupied after deletion -- checked *after*, since a saturated quota
    breaks the *next* session's recording."""
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload()]},  # still available
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "occupied" in err
    assert "::error::" in err


def test_release_recording_reports_when_the_post_delete_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(
        tmp_path, event_id="mrg-042", retrieved=True, consent_granted=True
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    transport = _FakeRecordingTransport(
        {
            _PATH: [
                _recording_payload(),
                FCCRequestError("GET /conferences/618515381 failed: timeout"),
            ]
        },
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert release_recording() == 1
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "deleted" in err
    assert "could not be confirmed" in err


# ------------------------------------------------------------------ #
# discard_recording(): the other route, for a
# recording that must never be retrieved (the discussion segment; a talk
# whose publication consent was withheld). Gated on an explicit typed
# operator confirmation, never on the retrieval traces -- every test
# below that expects a refusal asserts directly on `transport.delete_calls`
# and (where relevant) `transport.get_calls`, never only on the return
# code.
# ------------------------------------------------------------------ #


def test_discard_confirmation_names_the_action_and_the_event() -> None:
    from convener_ops.cli.journey.attendance import _discard_confirmation

    assert _discard_confirmation("mrg-042") == "discard mrg-042"


def test_discard_recording_with_no_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EVENT_ID", raising=False)

    assert discard_recording() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_discard_recording_with_an_invalid_event_id_returns_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "../escape")

    assert discard_recording() == 1
    assert "no valid event id" in capsys.readouterr().err


def test_discard_recording_refuses_a_blank_confirmation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `CONVENER_REPO_ROOT` is set up at all -- the confirmation is checked
    before any data file is even opened, so a blank confirmation refuses
    cleanly with no other setup required."""
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.delenv("CONFIRM_DISCARD", raising=False)

    assert discard_recording() == 1
    err = capsys.readouterr().err
    assert "CONFIRM_DISCARD" in err
    assert "discard mrg-042" in err


def test_discard_recording_refuses_a_mismatched_confirmation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "yes please")

    assert discard_recording() == 1
    assert "CONFIRM_DISCARD" in capsys.readouterr().err


def test_discard_recording_refuses_a_confirmation_typed_for_another_event(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A copy-pasted confirmation from a different event's run must not
    silently discard the wrong one."""
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-999")

    assert discard_recording() == 1
    assert "CONFIRM_DISCARD" in capsys.readouterr().err


def test_discard_recording_with_an_unknown_event_id_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-999")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-999")

    assert discard_recording() == 1
    assert "mrg-999" in capsys.readouterr().err


def test_discard_recording_reports_a_malformed_speakers_file_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "instance" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "speakers.yml").write_text("key: [unclosed\n", encoding="utf-8")
    (data_dir / "config.yml").write_text(yaml.safe_dump(config()), encoding="utf-8")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")

    assert discard_recording() == 1
    assert "invalid YAML" in capsys.readouterr().out


def test_discard_recording_without_a_configured_account_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    monkeypatch.delenv("CONVENER_MEETING_API_TOKEN", raising=False)

    assert discard_recording() == 0
    assert "nothing to discard" in capsys.readouterr().out


def test_discard_recording_is_a_noop_when_nothing_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport({_PATH: [_recording_payload(available=False)]})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 0
    assert "nothing to discard" in capsys.readouterr().out
    assert transport.delete_calls == []


def test_discard_recording_refuses_a_non_numeric_conference_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same probe `release_recording` was tested against: a hand-typed
    conference id must be refused before any transport call, on this route
    too."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch, conference_id="THIS-IS-THE-WRONG-CONFERENCE")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport({_PATH: [_recording_payload()]})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    err = capsys.readouterr().err
    assert "not a valid FCC conference id" in err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_discard_recording_returns_1_when_no_conference_id_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Closes the branch of discard_recording's own `if conference_id: ...
    else: ...` resolution -- written as a statement, not the
    ternary a review found invisible to `coverage --branch`, so this
    branch is not merely closed in substance but actually visible to the
    coverage figure)."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-042")
    monkeypatch.setenv("CONVENER_MEETING_API_TOKEN", "test-token")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    monkeypatch.delenv("CONVENER_FCC_CONFERENCE_ID", raising=False)
    transport = _FakeRecordingTransport({})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert "mrg-042" in capsys.readouterr().err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def test_discard_recording_ignores_the_retrieval_tick_and_still_needs_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second constraint on discarding, behaviourally: a ticked
    `RETRIEVED_TICK` must not let a missing or wrong confirmation through."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", retrieved=True)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.delenv("CONFIRM_DISCARD", raising=False)
    transport = _FakeRecordingTransport({_PATH: [_recording_payload()]})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert transport.delete_calls == []


def test_discard_recording_deletes_once_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No retrieval tick at all -- the ordinary shape for the discussion
    segment or a consent-withheld talk -- and no converted video either;
    the typed confirmation alone is enough."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042", retrieved=False)
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]}
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 0
    assert transport.delete_calls == [_PATH]
    out = capsys.readouterr().out
    assert "discarded, never retrieved" in out


def test_discard_recording_warns_but_still_deletes_when_already_converted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If the converted video already answers -- someone clicked Download
    on a recording that should never have been converted -- discarding
    still proceeds (declining would only leave the quota occupied for a
    leak that already happened) but a warning names it."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]},
        head_responses={_VIDEO_URL: _video_headers()},
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 0
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "::warning::" in err
    assert "already reachable" in err


def test_discard_recording_does_not_warn_when_never_converted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload(available=False)]}
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 0
    assert "::warning::" not in capsys.readouterr().err


def test_discard_recording_reports_when_delete_recording_itself_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload()]},
        delete_error=FCCRequestError("DELETE /conferences/618515381 returned HTTP 500"),
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert transport.delete_calls == [_PATH]
    assert transport.get_calls == [_PATH]
    assert "500" in capsys.readouterr().err


def test_discard_recording_alerts_when_space_stays_occupied_after_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {_PATH: [_recording_payload(), _recording_payload()]}
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "occupied" in err
    assert "::error::" in err


def test_discard_recording_reports_when_the_post_delete_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    _set_fcc_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-042")
    transport = _FakeRecordingTransport(
        {
            _PATH: [
                _recording_payload(),
                FCCRequestError("GET /conferences/618515381 failed: timeout"),
            ]
        }
    )
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert transport.delete_calls == [_PATH]
    err = capsys.readouterr().err
    assert "discarded" in err
    assert "could not be confirmed" in err


def test_discard_recording_refuses_a_self_consistent_typo_into_a_nonexistent_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The residual risk: an operator who fat-fingers the same
    wrong event id into both `event_id` and `confirm_discard` produces a
    self-consistent pair that sails past the confirmation check alone --
    but `find_speaker` still refuses it, because the typo does not name a
    real event. This is the half of "narrow it where it is cheap" that
    costs nothing extra: `find_speaker` is already called, unconditionally,
    before any platform is even constructed.

    `CONVENER_FCC_CONFERENCE_ID` used to be
    left unset here, so `conference_ids` resolved to `{}` and
    `PlatformFCC._conference_id` raised its *own* `EventNotFoundError` for
    'mrg-999' the moment `platform.get_recording` ran -- the identical
    message shape, from a different guard entirely. Removing the
    `find_speaker` call this test claims to pin left every assertion
    green: the same exception type, the same event id in the text, and
    `transport.get_calls == []` because the redundant failure happens
    inside `_conference_id`, before any transport call. Setting a
    validly-shaped `CONVENER_FCC_CONFERENCE_ID` for this exact (wrong) event id
    makes `_conference_id('mrg-999')` resolve cleanly, so the only thing
    left that can refuse the run at all is `find_speaker`'s own guard --
    removing it now lets the function reach `transport.get_json` against
    an empty `_FakeRecordingTransport`, which raises `AssertionError`
    instead of returning 1, failing this test loudly rather than quietly
    passing for the wrong reason."""
    _write_speaker_for_recording(tmp_path, event_id="mrg-042")
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("EVENT_ID", "mrg-999")
    monkeypatch.setenv("CONFIRM_DISCARD", "discard mrg-999")
    # Carried item 1: a validly-shaped conference id for the *wrong* event
    # id, so `PlatformFCC._conference_id` cannot coincidentally refuse this
    # run for a reason that has nothing to do with `find_speaker`.
    monkeypatch.setenv("CONVENER_FCC_CONFERENCE_ID", _CONFERENCE_ID)
    transport = _FakeRecordingTransport({})
    _patch_platform(monkeypatch, transport)

    assert discard_recording() == 1
    assert "mrg-999" in capsys.readouterr().err
    assert transport.get_calls == []
    assert transport.delete_calls == []


def _delete_recording_call_sites(package_dir: Path) -> list[str]:
    """Every `.py` file under `package_dir`, at any depth, that calls
    `delete_recording(` for real (excluding `def delete_recording(`
    declarations). `rglob`, not `glob`: nothing sits at the root of this
    package at all, so a non-recursive glob would read no module and
    report the whole of it clean -- reproduced against a synthetic
    package below. `as_posix`, because the answer is compared against a
    path this module writes down, and a backslash on one platform would
    make that comparison a platform test."""
    return [
        path.relative_to(package_dir).as_posix()
        for path in sorted(package_dir.rglob("*.py"))
        for _match in re.finditer(
            r"(?<!def )\bdelete_recording\(", path.read_text(encoding="utf-8")
        )
    ]


def test_delete_recording_has_exactly_two_call_sites_both_in_cli() -> None:
    """The rule, pinned rather than left to a docstring, covering
    both routes: the only calls to
    `Platform.delete_recording` anywhere in `convener_ops` are inside
    `release_recording` and `discard_recording`, both in
    `cli/journey/attendance.py`. A third
    call site anywhere -- a shortcut some future change adds -- would
    bypass whichever guard exists to provide; this test reads every
    module's own source, at any depth, and refuses to let a third one
    exist silently, the same "read the module's own source" idiom
    `test_notify.py::test_the_notification_module_holds_no_transport`
    already uses in this codebase.

    Brittle in one direction only, and deliberately left that way:
    a docstring that happens to contain the literal
    text `delete_recording(` (with the open paren) would also match here
    and fail this test even though it calls nothing. That is the safe
    direction to be brittle in -- it can only ever demand a closer look,
    never hide a real call site."""
    import convener_ops

    package_dir = Path(convener_ops.__file__).parent
    expected = "cli/journey/attendance.py"
    assert _delete_recording_call_sites(package_dir) == [expected, expected]


def test_release_recordings_delete_call_is_gated_on_missing_retrieval_evidence() -> (
    None
):
    """Structural, not merely behavioural: `release_recording`'s own call
    to `delete_recording` must textually follow the point where
    `missing_retrieval_evidence` is checked, so the gate cannot be
    reordered away from the call it exists to protect without this test
    noticing."""
    import inspect

    from convener_ops.cli.journey.attendance import release_recording

    source = inspect.getsource(release_recording)
    evidence_at = source.index("missing_retrieval_evidence(")
    delete_at = source.index("platform.delete_recording(")
    assert evidence_at < delete_at


def test_discard_recordings_delete_call_is_gated_on_the_confirmation() -> None:
    """The same structural pin, for the other route: `discard_recording`'s
    call to `delete_recording` must textually follow the confirmation
    comparison, not merely happen to pass a test today."""
    import inspect

    from convener_ops.cli.journey.attendance import discard_recording

    source = inspect.getsource(discard_recording)
    confirm_at = source.index("confirm_discard != expected")
    delete_at = source.index("platform.delete_recording(")
    assert confirm_at < delete_at


def _code_body_excluding_docstring(func: object) -> str:
    """`inspect.getsource(func)` with the leading docstring stripped --
    the two structural tests below search the *body* for a name, and both
    functions' own docstrings name, in prose, exactly what must be absent
    from the body, so a plain substring search over the whole source would
    trip on its own explanation."""
    import inspect

    source = inspect.getsource(func)  # type: ignore[arg-type]
    return source.split('"""', 2)[-1]


def test_discard_recording_never_reads_the_retrieval_tick_or_evidence() -> None:
    """The second constraint on discarding, pinned structurally: a ticked
    `RETRIEVED_TICK` must never be able to substitute for the typed
    confirmation, because `discard_recording`'s own code body never
    mentions `runbook_progress`, `RETRIEVED_TICK`, or
    `missing_retrieval_evidence` at all -- as a name, an attribute, or a
    string literal such as `record.get("runbook_progress")`."""
    from convener_ops.cli.journey.attendance import discard_recording

    body = _code_body_excluding_docstring(discard_recording)
    assert "missing_retrieval_evidence" not in body
    assert "RETRIEVED_TICK" not in body
    assert "runbook_progress" not in body


def test_release_recording_never_reads_the_discard_confirmation() -> None:
    """The mirror of the test above: `CONFIRM_DISCARD` and
    `_discard_confirmation` must never appear in `release_recording`'s own
    code body, so a typed discard confirmation can never substitute for
    the two retrieval traces it actually requires."""
    from convener_ops.cli.journey.attendance import release_recording

    body = _code_body_excluding_docstring(release_recording)
    assert "CONFIRM_DISCARD" not in body
    assert "_discard_confirmation" not in body


def test_the_call_site_scan_is_recursive(tmp_path: Path) -> None:
    """Reproduces exactly what a review found: a
    non-recursive `glob("*.py")` misses a call hidden one directory down.
    Read against a synthetic package rather than against `convener_ops`
    itself, so what is pinned is the walk and not the shape the real
    package happens to have."""
    (tmp_path / "innocent.py").write_text("def f():\n    pass\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "evil.py").write_text(
        "def sneaky(platform, event_id):\n    platform.delete_recording(event_id)\n",
        encoding="utf-8",
    )

    assert _delete_recording_call_sites(tmp_path) == ["sub/evil.py"]
