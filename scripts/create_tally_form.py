"""Build the public speaker-proposal form on Tally, from code.

Why this exists
----------------
`convener_ops.proposal.to_lead` has always looked a submission up by field label,
against an interface that, until now, no form implemented. A form clicked
together in Tally's editor cannot be recreated if the account is ever lost;
a form built from this script can -- D-03 applied to something other than
code. Re-running it is safe: it finds the existing form by its title
(`FORM_TITLE` below) and updates it in place rather than creating a second
one.

`build_blocks()` is the whole testable surface: pure, no network, no
environment, no filesystem. `main()` is the only part that talks to the
API, reading `TALLY_API_KEY` from the environment -- nothing here can be
exercised against the real network from a test.

The labels are shared, not copied
----------------------------------
`convener_ops.proposal` reads a submission by label -- `Name`, `Email`,
`Institution`, and so on, several with aliases it also accepts. Those labels
are not retyped here: this module imports `convener_ops.proposal.FORM_FIELDS` and
walks it to build each question, so a label renamed in `proposal.py` changes
the live form the next time this script runs, and a label renamed in one
place without the other breaks a test rather than breaking the form in
production.

Gender and career stage are free text, not a picker -- and this is the part
worth explaining
-----------------------------------------------------------------------------
`proposal.py` compares a submission's `Gender` and `Career stage` literally
against `GENDERS` and `CAREER_STAGES`, falling back to `"undisclosed"` on
anything else. The tempting design is a Tally DROPDOWN or MULTIPLE_CHOICE
question whose options read `M`, `F`, `NB`, ... so the exact vocabulary
reaches the code. It does not work, and it is worth recording why, because
the failure is silent and total rather than an edge case:

Tally's own webhook documentation
(https://tally.so/help/webhooks, `DROPDOWN`/`MULTIPLE_CHOICE`/`CHECKBOXES`/
`MULTI_SELECT` entries) and its OpenAPI spec
(`DropdownOptionPayload`/`MultipleChoiceOptionPayload`, which carry only a
display `text`) agree: a picker-type question submits the **option's
internal id** as `value` -- always as a list, e.g. `"value": ["6010d529-...
"]` -- never the option's display text. The text lives only in a sibling
`options: [{id, text}]` array on the same field. `convener_ops.cli.handle_proposal`
flattens a webhook payload with `f.get("value", "")` and never consults
`options`, so a picker-type Gender or Career-stage question would submit a
value like `"['6010d529-...']"` for *every* respondent -- never a member of
`GENDERS`/`CAREER_STAGES`, so every single submission would silently
downgrade to `"undisclosed"`, independent of what the option's display text
said. That is not a labelled-option problem to route around with careful
wording; it is a shape mismatch between what a picker submits and what
`_get`/`to_lead` compare, and fixing it would mean teaching
`convener_ops.cli.handle_proposal` to resolve `options`, which is outside this
task's file list and this script's reach (`build_blocks()` cannot change how
the webhook is parsed).

So `Gender` and `Career stage` are `INPUT_TEXT` questions here, each with a
placeholder spelling out the exact accepted words -- generated from
`GENDERS`/`CAREER_STAGES` themselves via `_vocabulary_hint`, not a second,
hand-typed copy of the vocabulary -- so what a respondent types is what
`to_lead` compares, and `"undisclosed"` is offered in that placeholder as a
legitimate answer ("... or undisclosed if you'd rather not say"), not
worded as a refusal. The risk this leaves is an ordinary free-text one --
already the risk `proposal.py`'s own comment names ("a free-text field, a
renamed form option, a translation") -- a typo reads as `"undisclosed"`
rather than as its intended value, which is the existing, accepted fallback,
not a new failure this script introduces.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    TALLY_API_KEY=tly-xxxx uv run python ../scripts/create_tally_form.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from convener_ops.proposal import (
    CAREER_STAGES,
    GENDERS,
    LABEL_ABSTRACT,
    LABEL_CAREER_STAGE,
    LABEL_CONFLICTS,
    LABEL_COUNTRY,
    LABEL_EMAIL,
    LABEL_GENDER,
    LABEL_INSTITUTION,
    LABEL_LINKS,
    LABEL_NAME,
    LABEL_PROPOSED_BY,
    LABEL_TITLE,
)

#: The form's name in Tally, and the idempotency key: `sync_form` finds the
#: existing form by this exact name (`GET /forms` has no filter-by-name
#: parameter, so it is found by paging through every form and comparing) and
#: updates it in place rather than creating a second one.
FORM_TITLE: Final = "Propose a speaker for The Example Collective"

#: `api.tally.so`, the one host this script ever talks to.
API_BASE: Final = "https://api.tally.so"

#: Fixed, arbitrary, and never reused for anything else -- see `_uuid`.
_NAMESPACE: Final = uuid.UUID("2f6a6b0a-2f0e-4f2a-9a7b-6a2b9b7f9c31")


def _uuid(name: str) -> str:
    """A block uuid that is a deterministic function of `name`.

    `uuid.uuid4()` would make `build_blocks()` return something different on
    every call, which is disqualifying for a function this module's tests
    (and a human diffing two runs) need to treat as pure. `uuid5` is a hash,
    not a random draw: the same `name` always yields the same uuid, so two
    calls to `build_blocks()` -- in the same run, or a year apart -- return
    byte-identical output. Tally requires *a* uuid, not *this specific*
    scheme; `name` only has to be unique per block, which `_block` below
    ensures by deriving it from the field label and the block's role.
    """
    return str(uuid.uuid5(_NAMESPACE, name))


def _block(
    block_type: str, group_type: str, name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """One Tally block: its own uuid, and its own single-block group.

    Every question below is two blocks -- a `TITLE` and an answer block --
    and neither shares a group with the other or with any other question's
    blocks (unlike a DROPDOWN's options, which share one `groupUuid` on
    purpose). `name` must be unique across the whole form for that to hold;
    `build_blocks` passes a string built from the field label and the
    block's role for exactly that reason.
    """
    return {
        "uuid": _uuid(name),
        "type": block_type,
        "groupUuid": _uuid(f"{name}:group"),
        "groupType": group_type,
        "payload": payload,
    }


def _vocabulary_hint(values: set[str]) -> str:
    """'a, b, c, or undisclosed if you'd rather not say'.

    Read from the live vocabulary set rather than typed out a second time,
    so a value added to or removed from `GENDERS`/`CAREER_STAGES` changes
    this placeholder on the next run instead of needing a second, hand-kept
    copy (the same reasoning as `FORM_FIELDS` for the labels themselves).
    `undisclosed` is named last and framed as a choice, not omitted --
    R-2: it must read as a legitimate answer, not a refusal to answer.
    """
    named = sorted(v for v in values if v != "undisclosed")
    return ", ".join(named) + ", or undisclosed if you'd rather not say"


@dataclass(frozen=True)
class _Question:
    """One form question: which label reads it back, and how it is asked.

    `aliases` comes straight from `convener_ops.proposal.FORM_FIELDS` --
    `aliases[0]` is the canonical label the form uses; the rest are the
    aliases `to_lead` also accepts from older or hand-run submissions, never
    offered here since the form only ever produces its own canonical label.
    """

    aliases: tuple[str, ...]
    answer_type: str
    required: bool
    placeholder: str

    @property
    def label(self) -> str:
        return self.aliases[0]

    def blocks(self) -> list[dict[str, Any]]:
        return [
            _block("TITLE", "QUESTION", f"{self.label}:title", {"html": self.label}),
            _block(
                self.answer_type,
                self.answer_type,
                f"{self.label}:answer",
                {"isRequired": self.required, "placeholder": self.placeholder},
            ),
        ]


#: The eleven questions, in the order `convener_ops.proposal.FORM_FIELDS` lists
#: them. `Name` is the only required one, matching `to_lead`/`skip_reason`:
#: every other field is optional there, so marking one required here that
#: `to_lead` does not require would let the form refuse a submission
#: `to_lead` would have accepted.
_QUESTIONS: Final[tuple[_Question, ...]] = (
    _Question(
        LABEL_NAME,
        "INPUT_TEXT",
        True,
        "Full name of the person you are proposing as a speaker",
    ),
    _Question(
        LABEL_EMAIL,
        "INPUT_EMAIL",
        False,
        "So the Board can reach the proposed speaker directly",
    ),
    _Question(
        LABEL_INSTITUTION,
        "INPUT_TEXT",
        False,
        "University, lab, or organization",
    ),
    _Question(
        LABEL_COUNTRY,
        "INPUT_TEXT",
        False,
        "Country of residence or affiliation",
    ),
    _Question(
        LABEL_TITLE,
        "INPUT_TEXT",
        False,
        "Working title for the talk -- it can change later",
    ),
    _Question(
        LABEL_ABSTRACT,
        "TEXTAREA",
        False,
        "A few sentences on what the talk would cover",
    ),
    _Question(
        LABEL_CAREER_STAGE,
        "INPUT_TEXT",
        False,
        _vocabulary_hint(CAREER_STAGES),
    ),
    _Question(
        LABEL_GENDER,
        "INPUT_TEXT",
        False,
        _vocabulary_hint(GENDERS),
    ),
    _Question(
        LABEL_LINKS,
        "INPUT_TEXT",
        False,
        "Comma-separated links: personal site, Google Scholar, LinkedIn, etc.",
    ),
    _Question(
        LABEL_CONFLICTS,
        "TEXTAREA",
        False,
        "Any conflicts of interest the Board should know about, or leave"
        " blank if there are none",
    ),
    _Question(
        LABEL_PROPOSED_BY,
        "INPUT_TEXT",
        False,
        "Your own name -- the person submitting this proposal, not the"
        " speaker named above",
    ),
)


def build_blocks() -> list[dict[str, Any]]:
    """The public proposal form, as the list of Tally blocks `POST`/`PATCH
    /forms` expect.

    Pure: no network call, no environment read, no filesystem access -- the
    whole of this function's output is determined by this module's own
    constants and by `convener_ops.proposal`'s shared label and vocabulary
    constants. Calling it twice, in the same process or a year apart,
    returns byte-identical output (see `_uuid`).
    """
    blocks: list[dict[str, Any]] = [
        _block(
            "FORM_TITLE",
            "TEXT",
            "form-title",
            {"html": FORM_TITLE, "title": FORM_TITLE},
        )
    ]
    for question in _QUESTIONS:
        blocks.extend(question.blocks())
    return blocks


# --------------------------------------------------------------------- #
# Talking to Tally -- the only part of this module a test may not run for
# real. Every function below takes its network access as a parameter
# (`get`/`post`/`patch`), so `sync_form` and `_find_form_id` are exercised in
# tests against an in-memory fake, never against `api.tally.so`.
# --------------------------------------------------------------------- #


class TallyError(RuntimeError):
    """A Tally API call failed. The message is written for a terminal --
    see `main`, the only caller that prints one."""


@dataclass(frozen=True)
class TallyClient:
    """The three calls this script makes, each already carrying the API
    key. `_live_client` builds the real one; tests build a fake with the
    same shape instead."""

    get: Callable[[str], dict[str, Any]]
    post: Callable[[str, dict[str, Any]], dict[str, Any]]
    patch: Callable[[str, dict[str, Any]], dict[str, Any]]


def _request(
    api_key: str, method: str, path: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """One HTTP call to the Tally API, raising `TallyError` -- never a raw
    `urllib` exception -- on anything that goes wrong, so `main` only ever
    has one exception type to catch and report legibly."""
    url = f"{API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {api_key}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise TallyError(f"{method} {path}: HTTP {exc.code} -- {detail}") from exc
    except urllib.error.URLError as exc:
        raise TallyError(f"{method} {path}: {exc.reason}") from exc
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise TallyError(f"{method} {path}: response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise TallyError(f"{method} {path}: response was not a JSON object")
    return parsed


def _live_client(api_key: str) -> TallyClient:
    return TallyClient(
        get=lambda path: _request(api_key, "GET", path),
        post=lambda path, payload: _request(api_key, "POST", path, payload),
        patch=lambda path, payload: _request(api_key, "PATCH", path, payload),
    )


#: A page holds at most this many forms per call (Tally's own maximum), and
#: this many pages is far more than any real account will ever hold -- a
#: ceiling so a client that never sets `hasMore: false` (a broken fake in a
#: test, or a broken API) fails loudly with `TallyError` instead of paging
#: forever.
_PAGE_SIZE: Final = 100
_MAX_PAGES: Final = 1000


def _find_form_id(get: Callable[[str], dict[str, Any]], title: str) -> str | None:
    """The id of the form named exactly `title`, or None.

    `GET /forms` has no filter-by-name query parameter (checked against
    Tally's own OpenAPI spec, not assumed), so every form is paged through
    and compared by `name` -- which is why the form's title matters: it is
    both what a human sees in the Tally dashboard and the idempotency key
    `sync_form` searches on.
    """
    for page in range(1, _MAX_PAGES + 1):
        body = get(f"/forms?page={page}&limit={_PAGE_SIZE}")
        items = body.get("items")
        if isinstance(items, list):
            for form in items:
                if isinstance(form, dict) and form.get("name") == title:
                    form_id = form.get("id")
                    return form_id if isinstance(form_id, str) else None
        if not body.get("hasMore"):
            return None
    raise TallyError(f"GET /forms: more than {_MAX_PAGES} pages, giving up")


def sync_form(
    client: TallyClient, title: str, blocks: list[dict[str, Any]]
) -> tuple[str, bool]:
    """Create the form named `title`, or update it if it already exists.

    Returns `(form_id, created)`. Idempotent: a second call with the same
    `title` and `blocks` finds the form `_find_form_id` already returned and
    `PATCH`es it, rather than creating a second form with the same name --
    Tally does not itself refuse a duplicate name, so this is the only thing
    that keeps a second run from doing that.
    """
    form_id = _find_form_id(client.get, title)
    if form_id is not None:
        client.patch(f"/forms/{form_id}", {"blocks": blocks})
        return form_id, False

    response = client.post("/forms", {"status": "PUBLISHED", "blocks": blocks})
    new_id = response.get("id")
    if not isinstance(new_id, str) or not new_id:
        raise TallyError("POST /forms: response had no form id")
    return new_id, True


def _ascii(text: str) -> str:
    """Escape non-ASCII for a terminal.

    The operator's console renders anything outside ASCII as mojibake, and
    this is the one thing this script prints that is not written by this
    file's own author -- a Tally error body can hold anything.
    """
    return text.encode("ascii", "backslashreplace").decode("ascii")


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[str], TallyClient] = _live_client,
) -> int:
    """Create or update the public proposal form. The only entry point that
    talks to the network, reading `TALLY_API_KEY` from the environment.

    Every failure this function can reach prints one plain-ASCII line to
    stderr and returns 1 -- no traceback -- because the first person to run
    this script is running it blind: there is no dry run against the real
    API (a form is either created or it is not), and this file cannot be
    exercised against `api.tally.so` in a test.

    `client_factory` defaults to `_live_client`, the real transport; tests
    pass one that returns a `TallyClient` backed by an in-memory fake, so
    this function is exercised in full -- missing key, success, and API
    failure -- without a single test reaching the network.
    """
    del argv  # No arguments yet; kept for symmetry with the other scripts.
    api_key = os.environ.get("TALLY_API_KEY", "").strip()
    if not api_key:
        print("error: TALLY_API_KEY is not set", file=sys.stderr)
        return 1

    client = client_factory(api_key)
    try:
        form_id, created = sync_form(client, FORM_TITLE, build_blocks())
    except TallyError as exc:
        print(f"error: {_ascii(str(exc))}", file=sys.stderr)
        return 1

    verb = "created" if created else "updated"
    print(f"{verb} form {form_id}: {_ascii(FORM_TITLE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
