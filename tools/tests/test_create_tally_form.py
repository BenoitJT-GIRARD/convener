"""Building the public proposal form on Tally (scripts/create_tally_form.py).

Three properties matter more than the rest:

* `build_blocks()` is pure -- no network, no environment, no filesystem --
  and deterministic, so it is tested directly, with nothing faked;
* the eleven labels, the two vocabularies, and their order come from
  `convener_ops.proposal`, not from a second, hand-typed copy of them, so
  a rename or reorder on either side is expected to break a test here or in
  `test_proposal.py`, not to go unnoticed;
* `main()` and `sync_form()` are the only parts that would ever reach
  `api.tally.so`, and neither is ever called against the real network in
  this file -- every test below runs against `FakeTally`, an in-memory
  double, or against a `TallyClient` built from hand-written callables.

The self-review question this whole task exists to answer -- could a form
built from `build_blocks()` produce a submission that `to_lead` silently
drops or downgrades to `undisclosed` -- is answered directly by the
round-trip tests below: they build the exact webhook shape
Tally sends for a chosen dropdown option, using `build_blocks()`'s own
option uuids (never hand-typed ones), resolve it through the real
`convener_ops.proposal.field_value`, and feed the result to the real `to_lead`.
"""

from __future__ import annotations

import http.client
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

from convener_ops.proposal import (
    CAREER_STAGE_ORDER,
    FORM_FIELDS,
    GENDER_ORDER,
    field_value,
    to_lead,
)

TODAY = "2026-01-08"


# --------------------------------------------------------------------- #
# Helpers shared by the tests below
# --------------------------------------------------------------------- #


def _question_groups(
    blocks: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Every (TITLE, [body blocks]) group in `blocks`, in order, skipping
    the leading FORM_TITLE block. A plain question has one body block; a
    DROPDOWN question has one DROPDOWN_OPTION block per offered value, so
    this scans from each TITLE to the next one rather than assuming a fixed
    number of blocks per question."""
    title_indices = [i for i, b in enumerate(blocks) if b["type"] == "TITLE"]
    groups = []
    for position, start in enumerate(title_indices):
        end = (
            title_indices[position + 1]
            if position + 1 < len(title_indices)
            else len(blocks)
        )
        groups.append((blocks[start], blocks[start + 1 : end]))
    return groups


def _body_blocks(blocks: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    for title, body in _question_groups(blocks):
        if title["payload"]["html"] == label:
            return body
    raise AssertionError(f"no question titled {label!r}")


def _answer_payload(blocks: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """The single answer block's payload for a plain (non-DROPDOWN)
    question."""
    body = _body_blocks(blocks, label)
    assert len(body) == 1, f"{label!r} is not a single-answer question"
    return dict(body[0]["payload"])


def _first_option_payload(blocks: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """The first option's payload for a DROPDOWN question -- where the
    group-level settings (`isRequired`, `placeholder`) live."""
    return dict(_body_blocks(blocks, label)[0]["payload"])


def _option_texts(blocks: list[dict[str, Any]], label: str) -> list[str]:
    return [b["payload"]["text"] for b in _body_blocks(blocks, label)]


def _dropdown_options(blocks: list[dict[str, Any]], label: str) -> list[dict[str, str]]:
    """Every option of a DROPDOWN question as Tally's own webhook shapes
    it: `{"id": <the block's uuid>, "text": <its display text>}`."""
    return [
        {"id": b["uuid"], "text": b["payload"]["text"]}
        for b in _body_blocks(blocks, label)
    ]


def _resolved_field(blocks: list[dict[str, Any]], label: str, chosen_text: str) -> str:
    """The string `field_value()` would produce for a real Tally submission
    that picked `chosen_text` on the DROPDOWN question titled `label` --
    built from that question's own option uuids (via `_dropdown_options`),
    exactly the shape Tally's webhook sends, never a hand-typed id."""
    options = _dropdown_options(blocks, label)
    chosen_id = next(o["id"] for o in options if o["text"] == chosen_text)
    field = {"label": label, "value": [chosen_id], "options": options}
    return field_value(field)


def _submission() -> dict[str, str]:
    """A fields dict shaped exactly like `convener_ops.proposal.field_value`
    resolves a Tally webhook into: `{label: value}`, keyed by the same
    canonical labels `build_blocks()` asks for. `Gender` and `Career stage`
    are left for the caller to fill via `_resolved_field` -- they are
    DROPDOWN questions now, and a bare hand-typed string is not the shape a
    real submission for either one takes."""
    return {
        "Name": "Ada Lovelace",
        "Email": "ada@example.org",
        "Institution": "Analytical Engines Ltd",
        "Country": "UK",
        "Preliminary title": "On analytical engines",
        "Short abstract": "A survey of the analytical engine's capabilities.",
        "Links": "https://example.org/ada, https://scholar.example/ada",
        "Conflicts of interest": "None",
        "Your name": "Charles Babbage",
    }


class FakeTally:
    """An in-memory double for enough of the Tally API to test idempotence
    without a byte crossing the network: `GET /forms` (paginated exactly
    like the real one), `POST /forms`, `PATCH /forms/{id}`.

    `misname_new_forms`, when set, has `POST /forms` name a freshly created
    form something other than what its FORM_TITLE block asked for -- the
    case where Tally does not honour the assumed
    title-from-block naming. `sync_form` is expected to notice and correct
    it with a follow-up `PATCH`.
    """

    def __init__(
        self, forms: dict[str, dict[str, Any]], *, misname_new_forms: bool = False
    ) -> None:
        self.forms = forms
        self.misname_new_forms = misname_new_forms
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
        wanted_name = payload["blocks"][0]["payload"]["title"]
        form = {
            "id": form_id,
            "name": "Untitled" if self.misname_new_forms else wanted_name,
            "status": payload.get("status"),
            "blocks": payload["blocks"],
        }
        self.forms[form_id] = form
        return dict(form)

    def _patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        form_id = path.removeprefix("/forms/")
        assert form_id in self.forms, f"no such form: {form_id}"
        self.forms[form_id] = {**self.forms[form_id], **payload}
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
    assert len(uuids) == len(set(uuids)), "duplicate block uuid"
    for block in blocks:
        assert set(block) == {"uuid", "type", "groupUuid", "groupType", "payload"}
        assert isinstance(block["payload"], dict)


def test_every_dropdown_shares_exactly_one_group_and_nothing_else_does() -> None:
    blocks = build_blocks()
    by_group: dict[str, list[dict[str, Any]]] = {}
    for block in blocks:
        by_group.setdefault(block["groupUuid"], []).append(block)

    for title, body in _question_groups(blocks):
        label = title["payload"]["html"]
        # Every TITLE block sits alone in its own group.
        assert by_group[title["groupUuid"]] == [title], label
        if label in {"Gender", "Career stage"}:
            group_uuids = {b["groupUuid"] for b in body}
            assert len(group_uuids) == 1, label
            assert by_group[group_uuids.pop()] == body, label
        else:
            assert len(body) == 1, label
            assert by_group[body[0]["groupUuid"]] == body, label


def test_the_form_title_block_comes_first_and_names_the_form() -> None:
    first = build_blocks()[0]
    assert first["type"] == "FORM_TITLE"
    assert first["payload"]["title"] == FORM_TITLE
    assert first["payload"]["html"] == FORM_TITLE


def test_the_form_asks_for_exactly_the_eleven_canonical_labels_in_order() -> None:
    # Pinned as a literal list, independent of FORM_FIELDS, so that renaming
    # a canonical label breaks this test even if both sides of the sharing
    # moved together.
    titles = [t["payload"]["html"] for t, _body in _question_groups(build_blocks())]
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
    titles = [t["payload"]["html"] for t, _body in _question_groups(build_blocks())]
    assert titles == [aliases[0] for aliases, _required in FORM_FIELDS]


def test_only_name_is_marked_required_matching_to_lead() -> None:
    # `isRequired` lives on the single answer block for a plain question,
    # and on the first option only for a DROPDOWN (the group-level
    # convention `_option_blocks` follows) -- `body[0]` is the right block
    # to check in both cases.
    required_labels = {
        title["payload"]["html"]
        for title, body in _question_groups(build_blocks())
        if body[0]["payload"].get("isRequired")
    }
    assert required_labels == {"Name"}


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


def test_gender_and_career_stage_are_dropdowns_and_no_other_question_is_a_picker() -> (
    None
):
    # Every choice-type block Tally has, other than DROPDOWN_OPTION, which
    # is exactly what Gender and Career stage must be.
    other_picker_types = {
        "MULTIPLE_CHOICE_OPTION",
        "CHECKBOX",
        "RANKING_OPTION",
        "MULTI_SELECT_OPTION",
    }
    for title, body in _question_groups(build_blocks()):
        label = title["payload"]["html"]
        types = {b["type"] for b in body}
        if label in {"Gender", "Career stage"}:
            assert types == {"DROPDOWN_OPTION"}, label
        else:
            assert not types & (other_picker_types | {"DROPDOWN_OPTION"}), label


def test_the_gender_options_are_exactly_the_imported_vocabulary_in_order() -> None:
    # List equality, not just set equality: it is strictly stronger, and it
    # is what makes a "helpful" rewording of one option's text -- or a
    # silent reordering -- break this test.
    assert _option_texts(build_blocks(), "Gender") == list(GENDER_ORDER)


def test_the_career_stage_options_are_exactly_the_imported_vocabulary_in_order() -> (
    None
):
    assert _option_texts(build_blocks(), "Career stage") == list(CAREER_STAGE_ORDER)


def test_every_question_has_a_non_empty_placeholder() -> None:
    # Resolving the option ids makes the vocabulary arrive intact; it does
    # not make a respondent
    # pick the *right* token. A dropdown with bare tokens and no
    # disambiguation ("independent" vs "group-leader"; an unexplained "NB")
    # would still let every choice pass vocabulary membership -- nothing
    # downstream would ever flag the resulting noise, a quieter version of
    # the failure a closed vocabulary exists to prevent. The nine plain
    # questions already
    # carry a placeholder; this pins that Gender and Career stage's first
    # option does too, across all eleven in one assertion.
    for title, body in _question_groups(build_blocks()):
        label = title["payload"]["html"]
        assert body[0]["payload"].get("placeholder"), label


def test_the_gender_placeholder_explains_nb_and_offers_undisclosed_legitimately() -> (
    None
):
    placeholder = _first_option_payload(build_blocks(), "Gender")["placeholder"]
    assert "NB" in placeholder
    assert "non-binary" in placeholder
    assert "undisclosed if you'd rather not say" in placeholder


def test_the_career_stage_placeholder_distinguishes_independent_from_group_leader() -> (
    None
):
    placeholder = _first_option_payload(build_blocks(), "Career stage")["placeholder"]
    assert "no lab" in placeholder
    assert "runs a lab" in placeholder
    assert "undisclosed if you'd rather not say" in placeholder


def test_the_dropdown_placeholder_glosses_never_touch_the_bare_option_text() -> None:
    # A second time: the gloss belongs in the placeholder only. Option
    # text (already pinned exactly against GENDER_ORDER/CAREER_STAGE_ORDER
    # above) must stay the bare token, with no parenthetical explanation
    # smuggled in -- that is what the next "helpful" rewording would touch
    # first, silently breaking the vocabulary the build produces.
    for label in ("Gender", "Career stage"):
        for text in _option_texts(build_blocks(), label):
            assert "(" not in text and ")" not in text, (label, text)


def test_no_option_text_or_placeholder_or_label_carries_non_ascii_text() -> None:
    # The form's content is not what the ASCII-only rule is about (that is
    # the operator's console, see `_ascii`) -- but nothing here needs
    # anything outside ASCII either, and staying inside it removes one more
    # thing that could render as mojibake somewhere unexpected.
    for block in build_blocks():
        for value in block["payload"].values():
            if isinstance(value, str):
                assert _is_ascii(value), value


# --------------------------------------------------------------------- #
# Does a submission through this form survive to_lead intact, for
# every question and every accepted vocabulary value -- resolved through
# the real field_value, from build_blocks()'s own option ids, not a
# hand-typed string standing in for one?
# --------------------------------------------------------------------- #


def test_a_submission_through_every_question_round_trips_into_a_lead() -> None:
    blocks = build_blocks()
    fields = _submission()
    fields["Gender"] = _resolved_field(blocks, "Gender", "NB")
    fields["Career stage"] = _resolved_field(blocks, "Career stage", "postdoc")

    lead = to_lead(fields, [], config(), TODAY)
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


@pytest.mark.parametrize("value", list(GENDER_ORDER))
def test_every_gender_dropdown_option_resolves_through_the_real_pipeline(
    value: str,
) -> None:
    blocks = build_blocks()
    fields = _submission()
    fields["Gender"] = _resolved_field(blocks, "Gender", value)
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["gender"] == value


@pytest.mark.parametrize("value", list(CAREER_STAGE_ORDER))
def test_every_career_stage_dropdown_option_resolves_through_the_real_pipeline(
    value: str,
) -> None:
    blocks = build_blocks()
    fields = _submission()
    fields["Career stage"] = _resolved_field(blocks, "Career stage", value)
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["career_stage"] == value


def test_an_empty_dropdown_selection_yields_undisclosed_not_a_crash() -> None:
    # An unanswered DROPDOWN -- Tally sends an empty selection rather than
    # omitting the field, or the field is simply absent; both must resolve
    # the same way "undisclosed" already does when declared nowhere at all.
    fields = _submission()
    fields["Gender"] = field_value({"label": "Gender", "value": [], "options": []})
    fields["Career stage"] = field_value(
        {"label": "Career stage", "value": [], "options": []}
    )
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["gender"] == "undisclosed"
    assert lead["career_stage"] == "undisclosed"


def test_an_unmapped_option_id_does_not_leak_a_stringified_list_into_the_lead() -> None:
    # A malformed or truncated payload -- an id with no entry in `options`
    # -- must not resurrect the original bug ("['not-a-known-id']" reaching
    # the record). field_value falls back to the raw id as plain text,
    # which to_lead's existing membership check then correctly treats as an
    # unrecognised value.
    fields = _submission()
    fields["Gender"] = field_value(
        {"label": "Gender", "value": ["not-a-known-id"], "options": []}
    )
    lead = to_lead(fields, [], config(), TODAY)
    assert lead is not None
    assert lead["gender"] == "undisclosed"


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


def test_find_form_id_raises_when_a_matching_form_has_no_readable_id() -> None:
    # "found it but its id is unreadable" must not be treated as "no such
    # form" -- that would let sync_form POST a second form with the same
    # name, the sibling risk on the read side.
    def get(path: str) -> dict[str, Any]:
        return {"items": [{"name": FORM_TITLE}], "hasMore": False}

    with pytest.raises(TallyError, match="no readable id"):
        _find_form_id(get, FORM_TITLE)


# --------------------------------------------------------------------- #
# sync_form -- idempotence, pinned against FakeTally, never the real API
# --------------------------------------------------------------------- #


def test_sync_form_creates_a_new_form_when_none_exists() -> None:
    fake = FakeTally(forms={})
    form_id, created = sync_form(fake.client(), FORM_TITLE, build_blocks())
    assert created is True
    assert fake.forms[form_id]["name"] == FORM_TITLE
    assert fake.forms[form_id]["blocks"] == build_blocks()
    # Created as a draft, not live, so the first run leaves a human a form
    # to look at before anything public depends on it.
    assert fake.forms[form_id]["status"] == "DRAFT"


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


def test_sync_form_corrects_a_form_tally_named_differently_than_asked() -> None:
    # Nothing but the FORM_TITLE block's own payload.title tells
    # Tally what to call the form on creation -- if that assumption turns
    # out wrong, sync_form must notice and fix the name in the same run,
    # rather than silently leaving a form _find_form_id can never match
    # again.
    fake = FakeTally(forms={}, misname_new_forms=True)
    form_id, created = sync_form(fake.client(), FORM_TITLE, build_blocks())
    assert created is True
    assert fake.forms[form_id]["name"] == FORM_TITLE

    second_id, second_created = sync_form(fake.client(), FORM_TITLE, build_blocks())
    assert second_created is False
    assert second_id == form_id
    assert len(fake.forms) == 1


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


def test_main_ascii_escapes_the_form_id_not_only_the_title(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # form_id is the one API-controlled string on that printed
    # line, and it must be escaped exactly like FORM_TITLE is.
    monkeypatch.setenv("TALLY_API_KEY", "tly-test-key")

    def _get(path: str) -> dict[str, Any]:
        return {"items": [], "hasMore": False}

    def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": "café-id", "name": FORM_TITLE}

    client = TallyClient(get=_get, post=_post, patch=lambda *a: {})
    assert main(client_factory=lambda api_key: client) == 0
    captured = capsys.readouterr()
    assert _is_ascii(captured.out)
    assert "café" not in captured.out


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


def test_request_wraps_a_raw_http_client_exception_as_a_tally_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # http.client.getresponse() sits under urllib's bare
    # `except: raise`, unlike h.request() -- so BadStatusLine and friends
    # reach here as themselves, never as URLError, unless _request catches
    # them too.
    def fake_urlopen(request: Any, timeout: int = 0) -> Any:
        raise http.client.BadStatusLine("garbage")

    monkeypatch.setattr("create_tally_form.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(TallyError):
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
