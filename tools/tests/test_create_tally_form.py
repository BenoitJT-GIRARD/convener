"""Building the public proposal form on Tally (scripts/create_tally_form.py).

Three properties matter more than the rest:

* `build_blocks()` is pure -- no network, no environment, no filesystem --
  and deterministic, so it is tested directly, with nothing faked;
* the eleven labels and the two vocabularies come from
  `convener_ops.proposal`, not from a second, hand-typed copy of them (R-3), so
  a rename on either side is expected to break a test here or in
  `test_proposal.py`, not to go unnoticed;
* `main()` and `sync_form()` are the only parts that would ever reach
  `api.tally.so`, and neither is ever called against the real network in
  this file -- every test below runs against `FakeTally`, an in-memory
  double, or against a `TallyClient` built from hand-written callables.

The self-review question this whole task exists to answer -- could a form
built from `build_blocks()` produce a submission that `to_lead` silently
drops or downgrades to `undisclosed` -- is answered directly by the
round-trip tests in the second section: they feed a synthesized submission,
keyed by the same labels `build_blocks()` asks for, through the real
`convener_ops.proposal.to_lead`, and check nothing was lost.
"""

from __future__ import annotations

import io
import urllib.error
from email.message import Message
from typing import Any

import pytest
from conftest import config
from create_tally_form import (
    FORM_TITLE,
    TallyClient,
    TallyError,
    _find_form_id,
    _live_client,
    _request,
    build_blocks,
    main,
    sync_form,
)

from convener_ops.proposal import CAREER_STAGES, FORM_FIELDS, GENDERS, to_lead

TODAY = "2026-01-08"


# --------------------------------------------------------------------- #
# Helpers shared by the tests below
# --------------------------------------------------------------------- #


def _question_pairs(
    blocks: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every (TITLE, answer) pair in `blocks`, in order, skipping the leading
    FORM_TITLE block."""
    rest = blocks[1:]
    return list(zip(rest[0::2], rest[1::2], strict=True))


def _answer_payload(blocks: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for title, answer in _question_pairs(blocks):
        if title["payload"]["html"] == label:
            return dict(answer["payload"])
    raise AssertionError(f"no question titled {label!r}")


def _submission(gender: str = "NB", career_stage: str = "postdoc") -> dict[str, str]:
    """A fields dict shaped exactly like `convener_ops.cli.handle_proposal`
    flattens a Tally webhook into: `{label: value}`, keyed by the same
    canonical labels `build_blocks()` asks for."""
    return {
        "Name": "Ada Lovelace",
        "Email": "ada@example.org",
        "Institution": "Analytical Engines Ltd",
        "Country": "UK",
        "Preliminary title": "On analytical engines",
        "Short abstract": "A survey of the analytical engine's capabilities.",
        "Career stage": career_stage,
        "Gender": gender,
        "Links": "https://example.org/ada, https://scholar.example/ada",
        "Conflicts of interest": "None",
        "Your name": "Charles Babbage",
    }


class FakeTally:
    """An in-memory double for enough of the Tally API to test idempotence
    without a byte crossing the network: `GET /forms` (paginated exactly
    like the real one), `POST /forms`, `PATCH /forms/{id}`."""

    def __init__(self, forms: dict[str, dict[str, Any]]) -> None:
        self.forms = forms
        self._next_id = 1
        self.page_size = 100

    def client(self) -> TallyClient:
        return TallyClient(get=self._get, post=self._post, patch=self._patch)

    def _get(self, path: str) -> dict[str, Any]:
        assert path.startswith("/forms?")
        query = dict(
            part.split("=", 1) for part in path.split("?", 1)[1].split("&") if part
        )
        page = int(query.get("page", "1"))
        items = list(self.forms.values())
        start = (page - 1) * self.page_size
        chunk = items[start : start + self.page_size]
        return {
            "items": chunk,
            "page": page,
            "hasMore": start + self.page_size < len(items),
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert path == "/forms"
        form_id = f"f{self._next_id}"
        self._next_id += 1
        form = {
            "id": form_id,
            "name": payload["blocks"][0]["payload"]["title"],
            "blocks": payload["blocks"],
        }
        self.forms[form_id] = form
        return dict(form)

    def _patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        form_id = path.removeprefix("/forms/")
        assert form_id in self.forms, f"no such form: {form_id}"
        self.forms[form_id] = {**self.forms[form_id], "blocks": payload["blocks"]}
        return dict(self.forms[form_id])


def _is_ascii(text: str) -> bool:
    return all(ord(c) < 128 for c in text)


# --------------------------------------------------------------------- #
# build_blocks() -- pure, deterministic, and shaped the way Tally expects
# --------------------------------------------------------------------- #


def test_build_blocks_needs_no_environment_and_returns_something(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TALLY_API_KEY", raising=False)
    blocks = build_blocks()
    assert blocks


def test_build_blocks_is_pure_and_deterministic() -> None:
    # Two calls -- and, by extension, two separate runs of the script --
    # must produce byte-identical output, or a re-run would look like a
    # change even when nothing did.
    assert build_blocks() == build_blocks()


def test_every_block_has_a_unique_uuid_and_the_shape_tally_requires() -> None:
    blocks = build_blocks()
    uuids = [b["uuid"] for b in blocks]
    group_uuids = [b["groupUuid"] for b in blocks]
    assert len(uuids) == len(set(uuids)), "duplicate block uuid"
    assert len(group_uuids) == len(set(group_uuids)), "duplicate group uuid"
    for block in blocks:
        assert set(block) == {"uuid", "type", "groupUuid", "groupType", "payload"}
        assert isinstance(block["payload"], dict)


def test_the_form_title_block_comes_first_and_names_the_form() -> None:
    first = build_blocks()[0]
    assert first["type"] == "FORM_TITLE"
    assert first["payload"]["title"] == FORM_TITLE
    assert first["payload"]["html"] == FORM_TITLE


def test_the_form_asks_for_exactly_the_eleven_canonical_labels_in_order() -> None:
    # Pinned as a literal list, independent of FORM_FIELDS, so that renaming
    # a canonical label breaks this test even if both sides of the sharing
    # moved together.
    titles = [t["payload"]["html"] for t, _a in _question_pairs(build_blocks())]
    assert titles == [
        "Name",
        "Email",
        "Institution",
        "Country",
        "Preliminary title",
        "Short abstract",
        "Career stage",
        "Gender",
        "Links",
        "Conflicts of interest",
        "Your name",
    ]


def test_the_form_labels_are_shared_from_proposal_py_not_a_second_copy() -> None:
    titles = [t["payload"]["html"] for t, _a in _question_pairs(build_blocks())]
    assert titles == [aliases[0] for aliases, _required in FORM_FIELDS]


def test_only_name_is_marked_required_matching_to_lead() -> None:
    pairs = _question_pairs(build_blocks())
    required = {t["payload"]["html"] for t, a in pairs if a["payload"]["isRequired"]}
    assert required == {"Name"}


def test_the_your_name_question_is_worded_to_distinguish_it_from_name() -> None:
    # "Your name" (the submitter) and "Name" (the proposed speaker) read as
    # near-duplicates side by side; the label itself cannot carry the
    # disambiguation (it must stay exactly "Your name" for `_get` to find
    # it), so the placeholder is where it has to live.
    name_placeholder = _answer_payload(build_blocks(), "Name")["placeholder"]
    your_name_placeholder = _answer_payload(build_blocks(), "Your name")["placeholder"]
    assert "proposing" in name_placeholder or "speaker" in name_placeholder
    assert "submitting" in your_name_placeholder
    assert name_placeholder != your_name_placeholder


def test_no_question_uses_a_tally_picker_type() -> None:
    # DROPDOWN / MULTIPLE_CHOICE / CHECKBOXES / MULTI_SELECT / RANKING submit
    # the option's internal id as `value` (a list), never the option's
    # display text -- confirmed against Tally's own webhook documentation
    # and OpenAPI spec, see the module docstring. `convener_ops.cli.handle_proposal`
    # takes that value as-is, so any of these types on any of the eleven
    # questions would make the submitted value un-comparable to anything
    # `to_lead` expects. None of the eleven may ever be one.
    picker_types = {
        "DROPDOWN",
        "MULTIPLE_CHOICE",
        "CHECKBOXES",
        "MULTI_SELECT",
        "RANKING",
    }
    answer_types = {
        b["type"] for b in build_blocks() if b["type"] not in {"FORM_TITLE", "TITLE"}
    }
    assert not answer_types & picker_types


def test_the_vocabulary_this_form_offers_is_pinned() -> None:
    # A change to either set changes what the form should ask for; pinned
    # literally so that change is caught here, not only inferred from a form
    # nobody happened to be looking at.
    assert {"M", "F", "NB", "undisclosed"} == GENDERS
    assert {
        "phd",
        "postdoc",
        "independent",
        "group-leader",
        "other",
        "undisclosed",
    } == CAREER_STAGES


def test_the_gender_placeholder_names_every_value_and_offers_undisclosed() -> None:
    placeholder = _answer_payload(build_blocks(), "Gender")["placeholder"]
    for value in GENDERS - {"undisclosed"}:
        assert value in placeholder
    assert "undisclosed if you'd rather not say" in placeholder


def test_the_career_stage_placeholder_names_every_value_and_undisclosed() -> None:
    placeholder = _answer_payload(build_blocks(), "Career stage")["placeholder"]
    for value in CAREER_STAGES - {"undisclosed"}:
        assert value in placeholder
    assert "undisclosed if you'd rather not say" in placeholder


def test_no_placeholder_or_label_carries_non_ascii_text() -> None:
    # The form's content is not what the ASCII-only rule is about (that is
    # the operator's console, see `_ascii`) -- but nothing here needs
    # anything outside ASCII either, and staying inside it removes one more
    # thing that could render as mojibake somewhere unexpected.
    for block in build_blocks():
        for value in block["payload"].values():
            if isinstance(value, str):
                assert _is_ascii(value), value


# --------------------------------------------------------------------- #
# The self-review question: does a submission through this form survive
# to_lead intact, for every question and every accepted vocabulary value?
# --------------------------------------------------------------------- #


def test_a_submission_through_every_question_round_trips_into_a_lead() -> None:
    lead = to_lead(_submission(), [], config(), TODAY)
    assert lead is not None
    assert lead["name"] == "Ada Lovelace"
    assert lead["email"] == "ada@example.org"
    assert lead["affiliation"] == "Analytical Engines Ltd"
    assert lead["country"] == "UK"
    assert lead["title"] == "On analytical engines"
    assert lead["abstract"] == "A survey of the analytical engine's capabilities."
    assert lead["career_stage"] == "postdoc"
    assert lead["gender"] == "NB"
    assert lead["links"] == [
        "https://example.org/ada",
        "https://scholar.example/ada",
    ]
    assert lead["conflicts_of_interest"] == "None"
    assert lead["proposed_by"] == "Charles Babbage"


@pytest.mark.parametrize("value", sorted(GENDERS - {"undisclosed"}))
def test_every_accepted_gender_value_is_kept_verbatim_not_downgraded(
    value: str,
) -> None:
    lead = to_lead(_submission(gender=value), [], config(), TODAY)
    assert lead is not None
    assert lead["gender"] == value


@pytest.mark.parametrize("value", sorted(CAREER_STAGES - {"undisclosed"}))
def test_every_accepted_career_stage_value_is_kept_verbatim_not_downgraded(
    value: str,
) -> None:
    lead = to_lead(_submission(career_stage=value), [], config(), TODAY)
    assert lead is not None
    assert lead["career_stage"] == value


def test_undisclosed_is_a_kept_answer_not_only_a_silent_fallback() -> None:
    lead = to_lead(
        _submission(gender="undisclosed", career_stage="undisclosed"),
        [],
        config(),
        TODAY,
    )
    assert lead is not None
    assert lead["gender"] == "undisclosed"
    assert lead["career_stage"] == "undisclosed"


def test_the_name_only_question_is_enough_on_its_own_to_produce_a_lead() -> None:
    # Every other field is optional, matching to_lead/skip_reason -- a form
    # that marked one of them required would refuse a submission to_lead
    # would have accepted.
    lead = to_lead({"Name": "Ada Lovelace"}, [], config(), TODAY)
    assert lead is not None
    assert lead["career_stage"] == "undisclosed"
    assert lead["gender"] == "undisclosed"


# --------------------------------------------------------------------- #
# _find_form_id -- paging through GET /forms since it has no filter-by-name
# --------------------------------------------------------------------- #


def test_find_form_id_returns_none_on_an_empty_account() -> None:
    def empty(path: str) -> dict[str, Any]:
        return {"items": [], "hasMore": False}

    assert _find_form_id(empty, FORM_TITLE) is None


def test_find_form_id_finds_a_match_on_the_first_page() -> None:
    def get(path: str) -> dict[str, Any]:
        return {"items": [{"id": "x", "name": FORM_TITLE}], "hasMore": False}

    assert _find_form_id(get, FORM_TITLE) == "x"


def test_find_form_id_pages_through_to_a_later_match() -> None:
    calls = []

    def get(path: str) -> dict[str, Any]:
        calls.append(path)
        if "page=1" in path:
            return {"items": [{"id": "a", "name": "Some other form"}], "hasMore": True}
        return {"items": [{"id": "b", "name": FORM_TITLE}], "hasMore": False}

    assert _find_form_id(get, FORM_TITLE) == "b"
    assert len(calls) == 2


def test_find_form_id_gives_up_rather_than_paging_forever() -> None:
    # A fake (or a real API) that never reports hasMore: false must not hang
    # this script forever -- it must fail loudly instead.
    with pytest.raises(TallyError, match="giving up"):
        _find_form_id(lambda path: {"items": [], "hasMore": True}, FORM_TITLE)


# --------------------------------------------------------------------- #
# sync_form -- idempotence, pinned against FakeTally, never the real API
# --------------------------------------------------------------------- #


def test_sync_form_creates_a_new_form_when_none_exists() -> None:
    fake = FakeTally(forms={})
    form_id, created = sync_form(fake.client(), FORM_TITLE, build_blocks())
    assert created is True
    assert fake.forms[form_id]["name"] == FORM_TITLE
    assert fake.forms[form_id]["blocks"] == build_blocks()


def test_sync_form_updates_the_existing_form_instead_of_creating_a_second_one() -> None:
    fake = FakeTally(
        forms={"existing": {"id": "existing", "name": FORM_TITLE, "blocks": []}}
    )
    form_id, created = sync_form(fake.client(), FORM_TITLE, build_blocks())
    assert created is False
    assert form_id == "existing"
    assert len(fake.forms) == 1
    assert fake.forms["existing"]["blocks"] == build_blocks()


def test_running_sync_form_twice_never_creates_a_second_form() -> None:
    fake = FakeTally(forms={})
    first_id, first_created = sync_form(fake.client(), FORM_TITLE, build_blocks())
    second_id, second_created = sync_form(fake.client(), FORM_TITLE, build_blocks())
    assert first_created is True
    assert second_created is False
    assert first_id == second_id
    assert len(fake.forms) == 1


def test_sync_form_never_touches_a_form_with_a_different_title() -> None:
    fake = FakeTally(
        forms={"other": {"id": "other", "name": "Some other form", "blocks": ["kept"]}}
    )
    form_id, created = sync_form(fake.client(), FORM_TITLE, build_blocks())
    assert created is True
    assert form_id != "other"
    assert fake.forms["other"]["blocks"] == ["kept"]
    assert len(fake.forms) == 2


# --------------------------------------------------------------------- #
# main() -- the only part that would talk to the network; every test below
# injects a client_factory instead, so no test ever calls the real one.
# --------------------------------------------------------------------- #


def test_main_reports_a_missing_api_key_and_never_touches_a_client(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TALLY_API_KEY", raising=False)

    def _must_not_be_called(api_key: str) -> TallyClient:
        raise AssertionError("client_factory must not run without an API key")

    assert main(client_factory=_must_not_be_called) == 1
    captured = capsys.readouterr()
    assert "TALLY_API_KEY" in captured.err
    assert _is_ascii(captured.err)


def test_main_creates_the_form_on_a_fresh_account(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TALLY_API_KEY", "tly-test-key")
    fake = FakeTally(forms={})
    assert main(client_factory=lambda api_key: fake.client()) == 0
    captured = capsys.readouterr()
    assert "created form" in captured.out
    assert len(fake.forms) == 1


def test_main_updates_rather_than_duplicates_on_a_second_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TALLY_API_KEY", "tly-test-key")
    fake = FakeTally(forms={})
    main(client_factory=lambda api_key: fake.client())
    capsys.readouterr()

    assert main(client_factory=lambda api_key: fake.client()) == 0
    captured = capsys.readouterr()
    assert "updated form" in captured.out
    assert len(fake.forms) == 1


def test_main_reports_an_api_error_in_plain_ascii_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TALLY_API_KEY", "tly-test-key")

    def _get(path: str) -> dict[str, Any]:
        raise TallyError("GET /forms: HTTP 401 -- jeton invalide, réessayez")

    broken = TallyClient(get=_get, post=lambda *a: {}, patch=lambda *a: {})
    assert main(client_factory=lambda api_key: broken) == 1
    captured = capsys.readouterr()
    assert _is_ascii(captured.err)
    assert "jeton invalide" in captured.err  # the ASCII part survives untouched
    assert "réessayez" not in captured.err  # the accented word does not
    assert "r\\xe9essayez" in captured.err  # escaped instead, information kept


# --------------------------------------------------------------------- #
# _live_client / _request -- the real transport, exercised with urlopen
# replaced by an in-memory stand-in so nothing ever opens a socket.
# --------------------------------------------------------------------- #


class _FakeHTTPResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_request_returns_the_parsed_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def fake_urlopen(request: Any, timeout: int = 0) -> _FakeHTTPResponse:
        seen["auth"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return _FakeHTTPResponse(b'{"id": "abc"}')

    monkeypatch.setattr("create_tally_form.urllib.request.urlopen", fake_urlopen)
    assert _request("tly-test-key", "GET", "/forms") == {"id": "abc"}
    assert seen["auth"] == "Bearer tly-test-key"


def test_request_wraps_an_http_error_as_a_tally_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: int = 0) -> Any:
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            Message(),
            io.BytesIO(b"bad key"),
        )

    monkeypatch.setattr("create_tally_form.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(TallyError, match="HTTP 401"):
        _request("bad-key", "GET", "/forms")


def test_request_wraps_a_connection_failure_as_a_tally_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: int = 0) -> Any:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("create_tally_form.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(TallyError, match="no route to host"):
        _request("tly-test-key", "GET", "/forms")


def test_request_rejects_a_response_that_is_not_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "create_tally_form.urllib.request.urlopen",
        lambda request, timeout=0: _FakeHTTPResponse(b"not json"),
    )
    with pytest.raises(TallyError, match="not valid JSON"):
        _request("tly-test-key", "GET", "/forms")


def test_live_client_wires_the_api_key_into_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str, str, dict[str, Any] | None]] = []

    def fake_request(
        api_key: str, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        seen.append((api_key, method, path, payload))
        return {"ok": True}

    monkeypatch.setattr("create_tally_form._request", fake_request)
    client = _live_client("tly-abc")
    client.get("/forms")
    client.post("/forms", {"a": 1})
    client.patch("/forms/1", {"b": 2})
    assert seen == [
        ("tly-abc", "GET", "/forms", None),
        ("tly-abc", "POST", "/forms", {"a": 1}),
        ("tly-abc", "PATCH", "/forms/1", {"b": 2}),
    ]
