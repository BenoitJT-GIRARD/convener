"""Build the public speaker-proposal form on Tally, from code.

Why this exists
----------------
`convener_ops.journey.proposal.to_lead` has always looked a submission up by
field label, against an interface that, until now, no form implemented. A form
clicked
together in Tally's editor cannot be recreated if the account is ever lost;
a form built from this script can -- D-03 applied to something other than
code. Re-running it is safe: it finds the existing form by its title
(`FORM_TITLE` below) and updates it in place rather than creating a second
one -- and see the note on renaming the form in Tally's own UI, near the
bottom of this docstring, before ever doing that.

`build_blocks()` is the whole testable surface: pure, no network, no
environment, no filesystem. `main()` is the only part that talks to the
API, reading `TALLY_API_KEY` from the environment -- nothing here can be
exercised against the real network from a test.

The labels are shared, not copied
----------------------------------
`convener_ops.journey.proposal` reads a submission by label -- `Name`, `Email`,
`Institution`, and so on, several with aliases it also accepts. Those labels
are not retyped here: `_QUESTIONS` below is built by walking
`convener_ops.journey.proposal.FORM_FIELDS` itself, reading each label and its
`required` flag from there rather than restating them, so a label renamed
in `proposal.py` changes the live form the next time this script runs, and
a label renamed in one place without the other breaks a test rather than
breaking the form in production.

Gender and Career stage are DROPDOWNs, and the ids are resolved
----------------------------------------------------------------
`proposal.py` compares a submission's `Gender` and `Career stage` literally
against `GENDERS` and `CAREER_STAGES`, falling back to `"undisclosed"` on
anything else. An earlier version of this script answered that by asking
both as free text, with a placeholder spelling out the accepted words --
reasoning, wrongly, that a Tally DROPDOWN could not deliver the vocabulary
intact. That reasoning stopped at "the submitted `value` is the option's
internal id, not its text" and did not go the one step further: Tally's
webhook payload carries the id-to-text mapping *alongside* that id, on the
very same field --

    { "label": "Career stage",
      "value": ["6010d529-..."],
      "options": [{"id": "260c201f-...", "text": "phd"},
                  {"id": "6010d529-...", "text": "postdoc"}] }

-- so resolving it is self-describing and trivial, and a dropdown, once
resolved, delivers the exact vocabulary token every time. Free text over a
closed six-token vocabulary does the opposite: a respondent who types
`Postdoc`, `post-doc` or `Senior Lecturer` fails the literal membership
test in `to_lead` and is written as `"undisclosed"`, silently, with no log
line and no signal -- precisely the outcome a closed vocabulary exists to
prevent, and at a steady rate rather than as an edge case.

So `Gender` and `Career stage` are `DROPDOWN` questions here, and the
resolution the earlier design avoided lives in
`convener_ops.journey.proposal.field_value` instead -- read by
`convener_ops.cli.handle_proposal` before a submission ever
reaches `to_lead`, so `to_lead`'s `fields: dict[str, str]` stays an honest
contract. Each option's `text` is the bare vocabulary token (`phd`, `NB`,
`group-leader`, ...) and nothing else: any friendly gloss belongs in the
question's own wording, never smuggled into the option text, or the next
"helpful" rewording of an option silently breaks the build.
`undisclosed` is offered as an ordinary option among the others, not singled
out or worded as a refusal: it is a real answer.

Option order matters and is not incidental
-------------------------------------------
`GENDER_ORDER`/`CAREER_STAGE_ORDER` in `proposal.py` are ordered tuples, not
the `GENDERS`/`CAREER_STAGES` sets: iterating a `set` of `str` is
`PYTHONHASHSEED`-dependent across processes, so building a dropdown's
options from the set (rather than from the tuple the set is derived from)
would put them in a different order on every run, rewriting the live form
each time for no reason other than the interpreter's own hash seed.

Usage (from `tools/`, so that the `convener_ops` package is importable):

    uv run python scripts/create_tally_form.py --key-file ../.env

`--key-file` names a file holding `TALLY_API_KEY=` and the key, which
`.gitignore` already refuses to track, rather than putting the key on the
command line, where a shell would keep it in its history and any terminal
recording would keep it for ever. `take_key_file` removes that file in a
`finally`, so it is gone whether the run then succeeded or not and it exists
for one command and no longer.

The three lines this replaced were `set -a`, a dot-source and an `rm -f`,
and not one of the three is a thing Windows PowerShell 5.1 can be asked to
do. The guarantee is the same and it is now in the tool rather than in a
shell the reader may not have.

Without `--key-file` the key is read from `TALLY_API_KEY` in the
environment, which is what every test here does and what nothing else has
ever needed. This is the only credential in the whole standing-up sequence
ever put in a file on the machine running the commands -- every other one is
typed into a browser or into a prompt that reads it without showing it.

The form is found again on every re-run by matching `FORM_TITLE` against
each existing form's name (`_find_form_id`) -- so renaming the form inside
Tally's own editor breaks that match, and the next run creates a second
form rather than updating the renamed one.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from convener_ops.declaration.published import load_identity
from convener_ops.journey.proposal import (
    CAREER_STAGE_ORDER,
    FORM_FIELDS,
    GENDER_ORDER,
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
#: The form a proposer lands on names whoever runs the series. Read
#: from `instance/config.json` like every other public name.
FORM_TITLE: Final = f"Propose a speaker for {load_identity().organisation}"

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
    block_type: str,
    group_type: str,
    name: str,
    payload: dict[str, Any],
    *,
    group_name: str | None = None,
) -> dict[str, Any]:
    """One Tally block: its own uuid, and -- by default -- its own
    single-block group.

    `group_name` defaults to `name`, so a plain question's `TITLE` and its
    single answer block each sit alone in their own group, as Tally's own
    examples do it. A DROPDOWN is the one exception: every `DROPDOWN_OPTION`
    block that offers a value for the *same* question must share one
    `groupUuid` with its sibling options -- that grouping is how Tally knows
    they are options of one dropdown rather than five unrelated blocks --
    so `_Question._option_blocks` passes the same explicit `group_name` for
    every option belonging to one question.
    """
    return {
        "uuid": _uuid(name),
        "type": block_type,
        "groupUuid": _uuid(f"{group_name or name}:group"),
        "groupType": group_type,
        "payload": payload,
    }


@dataclass(frozen=True)
class _Question:
    """One form question: which label reads it back, and how it is asked.

    `aliases` comes straight from `convener_ops.journey.proposal.FORM_FIELDS` --
    `aliases[0]` is the canonical label the form uses; the rest are the
    aliases `to_lead` also accepts from older or hand-run submissions, never
    offered here since the form only ever produces its own canonical label.

    `answer_type == "DROPDOWN"` is the one case with more than one answer
    block: `options` then holds the ordered vocabulary tuple (`GENDER_ORDER`
    / `CAREER_STAGE_ORDER`), and `blocks()` emits one `DROPDOWN_OPTION` per
    value instead of a single answer block. Tally's own schema has no
    standalone "dropdown" block type distinct from its options -- confirmed
    against the full `Block` union in Tally's OpenAPI spec, which lists
    `DropdownOptionBlock` and nothing else named `Dropdown*` -- so a
    question's option blocks *are* its dropdown, immediately following the
    question's own `TITLE` block.
    """

    aliases: tuple[str, ...]
    answer_type: str
    required: bool
    placeholder: str = ""
    options: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.aliases[0]

    def blocks(self) -> list[dict[str, Any]]:
        title = _block("TITLE", "QUESTION", f"{self.label}:title", {"html": self.label})
        if self.answer_type == "DROPDOWN":
            return [title, *self._option_blocks()]
        return [
            title,
            _block(
                self.answer_type,
                self.answer_type,
                f"{self.label}:answer",
                {"isRequired": self.required, "placeholder": self.placeholder},
            ),
        ]

    def _option_blocks(self) -> list[dict[str, Any]]:
        group_name = f"{self.label}:answer"
        last_index = len(self.options) - 1
        blocks: list[dict[str, Any]] = []
        for index, value in enumerate(self.options):
            payload: dict[str, Any] = {
                "index": index,
                "isFirst": index == 0,
                "isLast": index == last_index,
                "text": value,
            }
            if index == 0:
                # Group-level settings, and Tally's own convention (see
                # `hasBadge`/`randomize`/etc. in its option payload schema)
                # is to set them once, on the first option, rather than
                # repeat them identically on every sibling. `placeholder`
                # existing on `DropdownOptionPayload` is confirmed against
                # Tally's own OpenAPI spec; that it renders the way
                # INPUT_TEXT's placeholder does -- a hint shown before a
                # value is chosen -- is inferred from the field's presence
                # and name, not confirmed by a worked example the way the
                # option block's own shape was.
                payload["isRequired"] = self.required
                payload["placeholder"] = self.placeholder
            blocks.append(
                _block(
                    "DROPDOWN_OPTION",
                    "DROPDOWN",
                    # Name-derived from the value, not the index, so an
                    # option's uuid is stable even if `options` is ever
                    # reordered -- reordering the tuple must not read as
                    # deleting every option and adding them all back.
                    f"{self.label}:option:{value}",
                    payload,
                    group_name=group_name,
                )
            )
        return blocks


#: What each non-`"undisclosed"` token in `GENDER_ORDER`/`CAREER_STAGE_ORDER`
#: means, for `_dropdown_placeholder` below to fold into a disambiguating
#: placeholder. Resolving the option ids makes the vocabulary arrive
#: intact; it does not make a
#: respondent pick the *right* token -- "independent" and "group-leader"
#: read as near-synonyms side by side, and "NB" means nothing to a
#: respondent who has never seen the abbreviation. The gloss lives here,
#: never in the option `text` itself (a "helpful" rewording of an
#: option's own text would silently break the build, since option text is
#: what `test_the_gender_options_are_exactly_the_imported_vocabulary_in_order`
#: pins against the shared vocabulary). A token present in the order tuple
#: but missing here raises `KeyError` at import time -- a vocabulary added
#: without a gloss fails the build loudly rather than shipping a dropdown
#: with one undisambiguated option.
_GENDER_GLOSS: Final[dict[str, str]] = {
    "F": "female",
    "M": "male",
    "NB": "non-binary",
}
_CAREER_STAGE_GLOSS: Final[dict[str, str]] = {
    "phd": "PhD student",
    "postdoc": "postdoctoral researcher",
    "independent": "no lab of their own",
    "group-leader": "runs a lab",
    "other": "none of the above",
}


def _dropdown_placeholder(order: tuple[str, ...], gloss: dict[str, str]) -> str:
    """'token (gloss), token (gloss), ..., or undisclosed if you'd rather
    not say' -- built from the live vocabulary and its gloss rather than a
    second hand-typed sentence, so the wording always lists whatever the
    vocabulary actually is. `undisclosed` is named last and framed as a
    choice, never omitted: it must read as a legitimate answer, not
    a refusal to answer."""
    named = [f"{value} ({gloss[value]})" for value in order if value != "undisclosed"]
    return ", ".join(named) + ", or undisclosed if you'd rather not say"


#: Per-question specifics `FORM_FIELDS` does not carry: how the question is
#: asked (`answer_type`), and either its placeholder or its dropdown
#: options. Keyed by the same alias tuple `FORM_FIELDS` uses for that
#: field, so `_QUESTIONS` below walks `FORM_FIELDS` itself for the label and
#: the `required` flag -- neither is restated here.
_ANSWER_SPECS: Final[dict[tuple[str, ...], tuple[str, str, tuple[str, ...]]]] = {
    LABEL_NAME: (
        "INPUT_TEXT",
        "Full name of the person you are proposing as a speaker",
        (),
    ),
    LABEL_EMAIL: (
        "INPUT_EMAIL",
        "So the Board can reach the proposed speaker directly",
        (),
    ),
    LABEL_INSTITUTION: ("INPUT_TEXT", "University, lab, or organization", ()),
    LABEL_COUNTRY: ("INPUT_TEXT", "Country of residence or affiliation", ()),
    LABEL_TITLE: (
        "INPUT_TEXT",
        "Working title for the talk -- it can change later",
        (),
    ),
    LABEL_ABSTRACT: ("TEXTAREA", "A few sentences on what the talk would cover", ()),
    LABEL_CAREER_STAGE: (
        "DROPDOWN",
        _dropdown_placeholder(CAREER_STAGE_ORDER, _CAREER_STAGE_GLOSS),
        CAREER_STAGE_ORDER,
    ),
    LABEL_GENDER: (
        "DROPDOWN",
        _dropdown_placeholder(GENDER_ORDER, _GENDER_GLOSS),
        GENDER_ORDER,
    ),
    LABEL_LINKS: (
        "INPUT_TEXT",
        "Comma-separated links: personal site, Google Scholar, LinkedIn, etc.",
        (),
    ),
    LABEL_CONFLICTS: (
        "TEXTAREA",
        "Any conflicts of interest the Board should know about, or leave"
        " blank if there are none",
        (),
    ),
    LABEL_PROPOSED_BY: (
        "INPUT_TEXT",
        "Your own name -- the person submitting this proposal, not the"
        " speaker named above",
        (),
    ),
}


def _build_questions() -> tuple[_Question, ...]:
    """Walk `FORM_FIELDS` for the label and the `required` flag, and
    `_ANSWER_SPECS` for how each is asked -- `required` is read from
    `FORM_FIELDS`, never re-declared here, so `to_lead`'s eleventh field
    (`Name`, the only required one) and this form's required question stay
    the same field by construction rather than by two people remembering to
    agree."""
    questions = []
    for aliases, required in FORM_FIELDS:
        answer_type, placeholder, options = _ANSWER_SPECS[aliases]
        questions.append(
            _Question(
                aliases,
                answer_type,
                required,
                placeholder=placeholder,
                options=options,
            )
        )
    return tuple(questions)


#: The eleven questions, in the order `convener_ops.journey.proposal.FORM_FIELDS` lists
#: them.
_QUESTIONS: Final[tuple[_Question, ...]] = _build_questions()


def build_blocks() -> list[dict[str, Any]]:
    """The public proposal form, as the list of Tally blocks `POST`/`PATCH
    /forms` expect.

    Pure: no network call, no environment read, no filesystem access -- the
    whole of this function's output is determined by this module's own
    constants and by `convener_ops.journey.proposal`'s shared label and vocabulary
    constants. Calling it twice, in the same process or a year apart,
    returns byte-identical output (see `_uuid`, and `GENDER_ORDER`/
    `CAREER_STAGE_ORDER` in `proposal.py` for why the vocabulary itself is
    order-stable too).
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
    `urllib`/`http.client` exception -- on anything that goes wrong, so
    `main` only ever has one exception type to catch and report legibly.

    `urllib`'s own `OSError -> URLError` translation covers only
    `h.request(...)`; in CPython's `AbstractHTTPHandler.do_open`, the
    matching `r = h.getresponse()` sits under a bare `except: raise`, so
    `http.client.BadStatusLine`, `IncompleteRead` and `RemoteDisconnected`
    would otherwise propagate unwrapped -- a traceback for the first,
    blind-running operator instead of one plain-ASCII line. The
    success-path decode uses `"replace"` for the same reason the error path
    already did: a body containing invalid UTF-8 must not turn a legible
    HTTP failure into an illegible decode failure.
    """
    url = f"{API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {api_key}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise TallyError(f"{method} {path}: HTTP {exc.code} -- {detail}") from exc
    except urllib.error.URLError as exc:
        raise TallyError(f"{method} {path}: {exc.reason}") from exc
    except (OSError, http.client.HTTPException, UnicodeDecodeError) as exc:
        raise TallyError(f"{method} {path}: {exc}") from exc
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

    A form whose `name` matches but whose `id` cannot be read raises rather
    than being treated as "no match": returning `None` here would tell
    `sync_form` to `POST` a second form with the same name, silently, which
    is a worse outcome than stopping to say the found form is unreadable.
    """
    for page in range(1, _MAX_PAGES + 1):
        body = get(f"/forms?page={page}&limit={_PAGE_SIZE}")
        items = body.get("items")
        if isinstance(items, list):
            for form in items:
                if isinstance(form, dict) and form.get("name") == title:
                    form_id = form.get("id")
                    if not isinstance(form_id, str) or not form_id:
                        raise TallyError(
                            f"GET /forms: found a form named {title!r} with"
                            " no readable id"
                        )
                    return form_id
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

    Created as `"DRAFT"`, not `"PUBLISHED"`: the first run's whole point is
    for a human to look at the result in the Tally dashboard before
    anything public depends on it, and creating it live would defeat that.
    A later run never touches `status` on the `PATCH` path, so publishing it
    (by hand, once) is never silently undone by a re-run.

    `POST /forms` has no `name` field (checked against Tally's own OpenAPI
    spec) -- the form's name can only come from the `FORM_TITLE` block's own
    `payload.title`, an assumption about a service this script does not
    control. If that assumption is ever wrong (Tally names the form
    something else, or normalises the string), `_find_form_id` would never
    match it again, and every future run would create another form, each
    one reported as `created form <id>` -- success that silently is not.
    The `response.get("name") != title` check below turns that unverifiable
    assumption into a verified, self-healing one: found wrong, corrected
    with one `PATCH`, in the same run that created it.
    """
    form_id = _find_form_id(client.get, title)
    if form_id is not None:
        client.patch(f"/forms/{form_id}", {"blocks": blocks})
        return form_id, False

    response = client.post("/forms", {"status": "DRAFT", "blocks": blocks})
    new_id = response.get("id")
    if not isinstance(new_id, str) or not new_id:
        raise TallyError("POST /forms: response had no form id")
    if response.get("name") != title:
        client.patch(f"/forms/{new_id}", {"name": title})
    return new_id, True


def _ascii(text: str) -> str:
    """Escape non-ASCII for a terminal.

    The operator's console renders anything outside ASCII as mojibake.
    Applied to both strings `main` prints -- `FORM_TITLE` is a local ASCII
    constant and does not strictly need it, but `form_id` is API-controlled,
    and escaping both unconditionally means this guarantee never depends on
    remembering which of the two might someday not be ASCII.
    """
    return text.encode("ascii", "backslashreplace").decode("ascii")


#: The one name a key file may carry, and the one variable the environment
#: is asked for. Written once so the two doors cannot come to want two
#: different spellings of the same credential.
KEY_NAME: Final = "TALLY_API_KEY"


def take_key_file(path: Path) -> str:
    """The key `path` holds, with `path` removed in the same act.

    The removal is in a `finally`, so the file is gone whether the read
    succeeded, found no key, or raised: it exists for one command and no
    longer, which is what `declarations/standing-up.yml`'s `tally_form` step
    promises a reader. That guarantee used to be a trailing `; rm -f` on the
    command line, where it held only for shells that have one.

    What is parsed is a list of `NAME=value` lines and nothing more of the
    `.env` convention -- no quoting, no `export`, no interpolation. The file
    this reads is one line, written by hand by whoever is standing an
    instance up, and a parser that accepted more shapes would be a parser
    with more ways to hand back the wrong string.
    """
    if not path.exists():
        print(f"error: no key file at {_ascii(str(path))}", file=sys.stderr)
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    finally:
        path.unlink(missing_ok=True)
        print(f"removed {_ascii(str(path))}")
    for line in text.splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == KEY_NAME:
            return value.strip()
    return ""


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[str], TallyClient] = _live_client,
) -> int:
    """Create or update the public proposal form. The only entry point that
    talks to the network, reading the key from `--key-file` or, without one,
    from `TALLY_API_KEY` in the environment.

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
    parser = argparse.ArgumentParser(
        description="Create or update the public speaker-proposal form on Tally."
    )
    parser.add_argument(
        "--key-file",
        help=f"a file holding `{KEY_NAME}=` and the key. It is deleted as it "
        "is read, whether the rest of the run then succeeds or not. Without "
        f"it the key is read from {KEY_NAME} in the environment.",
    )
    args = parser.parse_args(argv)

    if args.key_file is None:
        api_key = os.environ.get(KEY_NAME, "").strip()
    else:
        api_key = take_key_file(Path(args.key_file)).strip()
    if not api_key:
        where = "the environment" if args.key_file is None else args.key_file
        print(
            f"error: {KEY_NAME} is not set in {_ascii(str(where))}",
            file=sys.stderr,
        )
        return 1

    client = client_factory(api_key)
    try:
        form_id, created = sync_form(client, FORM_TITLE, build_blocks())
    except TallyError as exc:
        print(f"error: {_ascii(str(exc))}", file=sys.stderr)
        return 1

    verb = "created" if created else "updated"
    print(f"{verb} form {_ascii(form_id)}: {_ascii(FORM_TITLE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
