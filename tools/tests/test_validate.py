from __future__ import annotations

from conftest import config, speaker

from convener_ops.validate import validate_config, validate_speakers


def test_a_minimal_lead_is_valid() -> None:
    assert validate_speakers([speaker()]) == []


def test_top_level_must_be_a_list() -> None:
    errors = validate_speakers({"id": "spk-001"})
    assert errors == ["speakers.yml: top-level must be a list"]


def test_duplicate_id_is_rejected() -> None:
    errors = validate_speakers([speaker(), speaker(name="Grace Hopper")])
    assert any("duplicate id 'spk-001'" in e for e in errors)


def test_unknown_status_is_rejected() -> None:
    errors = validate_speakers([speaker(status="wrapped")])
    assert any("invalid status 'wrapped'" in e for e in errors)


def test_scheduled_requires_edition_date_and_two_hosts() -> None:
    errors = validate_speakers([speaker(status="scheduled")])
    joined = " | ".join(errors)
    assert "requires edition_code" in joined
    assert "requires date" in joined
    assert "requires both host_1 and host_2" in joined


def test_duplicate_edition_code_is_rejected() -> None:
    common = {
        "status": "scheduled",
        "host_1": "A",
        "host_2": "B",
        "edition_code": "MRG-01",
    }
    errors = validate_speakers(
        [
            speaker(id="spk-001", date="2026-01-08", **common),
            speaker(id="spk-002", date="2026-02-12", **common),
        ]
    )
    assert any("duplicate edition_code 'MRG-01'" in e for e in errors)


def test_malformed_date_and_time_are_rejected() -> None:
    errors = validate_speakers([speaker(date="08/01/2026", time="12h30")])
    joined = " | ".join(errors)
    assert "date must be YYYY-MM-DD" in joined
    assert "time must be HH:MM" in joined


def test_config_missing_keys_are_reported() -> None:
    cfg = config()
    del cfg["season"]
    errors = validate_config(cfg)
    assert any("missing keys ['season']" in e for e in errors)


def test_config_board_member_must_look_like_a_login() -> None:
    errors = validate_config(config(board_members=["not a login!"]))
    assert any("invalid board_member" in e for e in errors)


def test_valid_config_produces_no_error() -> None:
    assert validate_config(config()) == []
