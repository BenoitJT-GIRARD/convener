from __future__ import annotations

from convener_ops.yaml_safe import safe_load


def test_unquoted_hh_mm_stays_a_string_not_a_sexagesimal_int() -> None:
    assert safe_load("time: 12:30") == {"time": "12:30"}


def test_unquoted_iso_date_stays_a_string_not_a_datetime_date() -> None:
    assert safe_load("date: 2026-05-01") == {"date": "2026-05-01"}


def test_ordinary_integers_still_parse_as_integers() -> None:
    assert safe_load("season: 2026") == {"season": 2026}
    assert safe_load("x: -12") == {"x": -12}
    assert safe_load("x: 0") == {"x": 0}


def test_other_scalar_types_are_unaffected() -> None:
    assert safe_load("x: true") == {"x": True}
    assert safe_load("x: null") == {"x": None}
    assert safe_load("x: 3.14") == {"x": 3.14}
    assert safe_load("x: hello") == {"x": "hello"}


def test_quoted_values_are_unaffected() -> None:
    assert safe_load("time: '12:30'") == {"time": "12:30"}
    assert safe_load("date: '2026-05-01'") == {"date": "2026-05-01"}
