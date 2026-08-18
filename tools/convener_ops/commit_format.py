"""The grammar of decision commits.

This project has no database. The git history *is* the register: who voted,
who recused themselves, who objected, who was seated. A message that records
one of those acts is therefore a data format, not prose, and this module is
its grammar -- shared with the browser, whose copy lives in
`app/src/state/decisions.ts` and is pinned to this one by
`tools/tests/fixtures/governance-cases.json`.

One line, three slots and nothing else::

    data: <act> <entity> by <actor>
    data: <act> <entity> by <actor> (<qualifier>)

`act` is a closed vocabulary (`ACTS`) of imperative phrases, each naming a
*record* -- a ballot, a nomination, a vote, an invitation, a recording. There
is no free verb slot, so no message can pass judgement on a volunteer: the
strongest thing the grammar can say about a person is that a record about them
changed, and who changed it. `qualifier` is closed too, per act (`QUALIFIERS`),
so the whole message is drawn from a fixed vocabulary plus two identifiers.
That is the general form of the rule that `tools/tests/test_inactivity.py`
states for six words: it is not those six words that are banned, it is the
whole grammatical position they would have had to occupy, and that position
does not exist. `judgemental_terms` keeps the vocabulary honest.

Only *decision* messages answer to this. An ordinary commit -- code, docs, a
runbook tick -- is not a decision and is never flagged: a grammar that made
every commit an obstacle would be abandoned inside a week.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Final

#: The domain prefix a decision commit carries. Decisions are recorded in
#: `data/`, so they are `data:` commits and nothing else.
DOMAIN: Final = "data"

#: Every act the register can record, as an imperative phrase ending in the
#: preposition that introduces the record it acts on. Adding a kind here is
#: the only way to add a sentence to the register's vocabulary.
ACTS: Final[dict[str, str]] = {
    # Selecting a lead (`app/src/state/transitions.ts`).
    "ballot-cast": "record a ballot on",
    "ballot-withdraw": "withdraw a ballot on",
    "lead-park": "park",
    "lead-decline": "decline",
    "reactivate": "reopen the review of",
    "vote-reopen": "reopen the vote on",
    # Inviting and scheduling.
    "send-invitation": "send the invitation for",
    "invited-accept": "record an accepted invitation for",
    "invited-decline": "record a declined invitation for",
    "lock-date": "lock the date of",
    # Publishing a recording (G-10, G-15).
    "consent-set": "record the recording consent of",
    "publication-approve": "approve publication of",
    "publication-object": "record an objection to publishing",
    "publication-resolve": "resolve the objections on",
    "finalize-archive": "publish the recording of",
    # Who sits on the board (G-08).
    "nomination-open": "open a nomination for",
    "nomination-object": "record an objection to the nomination of",
    "nomination-withdraw-objection": "withdraw an objection to the nomination of",
    "nomination-resolve": "settle the nomination of",
    # Administrative acts, which the register records exactly like the rest.
    "override": "override the status of",
    "speaker-delete": "delete the record of",
}

#: The qualifier each act admits, as a closed set. An act absent from this
#: mapping takes no qualifier at all, and one present takes nothing outside
#: its set -- so `record a ballot on spk-001 by ana (maybe)` is not a message
#: this grammar can express, nor one it will accept.
QUALIFIERS: Final[dict[str, frozenset[str]]] = {
    "ballot-cast": frozenset({"yes", "abstain", "recused"}),
    "consent-set": frozenset({"granted", "refused"}),
    "publication-resolve": frozenset({"lift", "withhold"}),
    "override": frozenset(
        {
            "lead",
            "approved",
            "invited",
            "confirmed",
            "scheduled",
            "delivered",
            "archived",
            "parked",
            "decline-board",
            "decline-speaker",
        }
    ),
}

#: A speaker id (`spk-001`), a GitHub login, or `board` for an act on the
#: board as a whole. Never a person's name: a name is prose about a person,
#: and the register points at records.
_TOKEN: Final = r"[A-Za-z0-9][A-Za-z0-9._-]*"

_DECISION_RE: Final = re.compile(
    rf"^(?P<entity>{_TOKEN}) by (?P<actor>{_TOKEN})(?: \((?P<detail>[a-z-]+)\))?$"
)

#: An attribution trailer, or a claim that something other than a person did
#: the work. Checked on *every* message, decision or not: it is a repository
#: rule, not a rule of this grammar.
_FORBIDDEN_MENTIONS: Final[tuple[tuple[str, str], ...]] = (
    (r"co-authored-by:", "an attribution trailer"),
    (r"signed-off-by:\s*claude", "an attribution trailer"),
    (r"\bclaude\b", "a mention of an assistant"),
    (r"\banthropic\b", "a mention of an assistant"),
    (r"generated with", "a mention of an assistant"),
)


def _forms(stem: str) -> set[str]:
    """The inflected family of one stem, by mechanical morphology.

    The point is that the wording rule is stated once per *idea* and covers
    the words that idea can take, rather than listing tokens and missing the
    seventh one somebody writes next year.
    """
    out = {stem, stem + "s"}
    if stem.endswith("e"):
        out |= {stem + "d", stem[:-1] + "ing", stem[:-1] + "al"}
    else:
        out |= {stem + "ed", stem + "ing", stem + "al", stem + "ment", stem + "ure"}
    if stem.endswith("s"):
        out |= {stem + "es", stem + "ed", stem + "ing"}
    # expel -> expelled, drop -> dropping: a final consonant doubles after a
    # single vowel. Without this the rule would miss half of exactly the
    # family it exists to cover.
    vowels = "aeiou"
    if (
        len(stem) >= 3
        and stem[-1] not in vowels + "wxy"
        and stem[-2] in vowels
        and stem[-3] not in vowels
    ):
        out |= {stem + stem[-1] + "ed", stem + stem[-1] + "ing"}
    return out


#: Ideas a decision message may not carry, not tokens it may not contain. A
#: message says what was recorded; it never says what a volunteer is.
_JUDGEMENT_STEMS: Final[tuple[str, ...]] = (
    "remove",
    "expel",
    "eject",
    "oust",
    "dismiss",
    "banish",
    "purge",
    "sack",
    "fail",
    "neglect",
    "blame",
    "punish",
    "shame",
    "disgrace",
    "slack",
    "delinquent",
    "derelict",
    "negligent",
    "incompetent",
    "unreliable",
    "unworthy",
    "unfit",
    "useless",
    "lazy",
    "guilty",
    "culprit",
    "deadwood",
    "absentee",
)

#: Families the mechanical rule cannot reach: English keeps a few of these
#: irregular, and `left` is exactly one of the six words phase 2 already bans.
_JUDGEMENT_IRREGULAR: Final[tuple[str, ...]] = (
    "drop",
    "drops",
    "dropped",
    "dropping",
    "leave",
    "leaves",
    "leaving",
    "left",
    "failure",
    "expulsion",
    "negligence",
)

JUDGEMENTAL: Final[frozenset[str]] = frozenset(
    {word for stem in _JUDGEMENT_STEMS for word in _forms(stem)}
    | set(_JUDGEMENT_IRREGULAR)
)


def judgemental_terms(text: str) -> list[str]:
    """Every word in `text` that judges a person rather than naming a record.

    Used to keep `ACTS` and `QUALIFIERS` honest, and to catch a hand-written
    decision message that reaches for one.
    """
    return sorted({w for w in re.findall(r"[a-z]+", text.lower()) if w in JUDGEMENTAL})


@dataclass(frozen=True)
class Decision:
    """One line of the register, taken apart.

    `kind` is a key of `ACTS`; `entity` is the record acted on; `actor` is the
    login that acted; `detail` is the act's qualifier, or `""`.
    """

    kind: str
    entity: str
    actor: str
    detail: str = ""


class DecisionRejectedError(ValueError):
    """A decision that cannot be written down as asked."""


def format_decision(kind: str, entity: str, actor: str, detail: str = "") -> str:
    """The one line that records this decision.

    Raises `DecisionRejectedError` rather than emitting something the register
    cannot read back: an unknown kind, an identifier that is not a token, or a
    qualifier the act does not admit. None of those can be *expressed* by the
    browser's copy of this table -- the types there have no slot for them --
    so reaching this exception means the caller invented a value.
    """
    if kind not in ACTS:
        raise DecisionRejectedError(f"unknown decision kind: {kind!r}")
    allowed = QUALIFIERS.get(kind, frozenset())
    if detail not in allowed and not (detail == "" and not allowed):
        raise DecisionRejectedError(f"{kind} does not admit the qualifier {detail!r}")
    for slot, value in (("entity", entity), ("actor", actor)):
        if not re.fullmatch(_TOKEN, value):
            raise DecisionRejectedError(f"{slot} is not an identifier: {value!r}")
    line = f"{DOMAIN}: {ACTS[kind]} {entity} by {actor}"
    return f"{line} ({detail})" if detail else line


def _claimed_kind(message: str) -> str | None:
    """The kind a message claims to record, by its opening act phrase.

    Longest match wins, so `record an objection to the nomination of` is never
    read as `record an objection to publishing`. A message whose opening
    phrase is in no act's vocabulary claims nothing, and the grammar leaves
    it alone -- that is what keeps ordinary commits out of this.
    """
    prefix = f"{DOMAIN}: "
    if not message.startswith(prefix):
        return None
    body = message[len(prefix) :]
    matches = [k for k, act in ACTS.items() if body.startswith(act + " ")]
    return max(matches, key=lambda k: len(ACTS[k])) if matches else None


def parse_decision(message: str) -> Decision | None:
    """Read a decision back out of a commit subject, or `None`.

    `None` means "not a decision commit" *and* "not a malformed one" -- the
    caller cannot tell them apart here on purpose, because only
    `validate_messages` needs to, and only it knows the difference matters.
    """
    kind = _claimed_kind(message)
    if kind is None:
        return None
    rest = message[len(f"{DOMAIN}: {ACTS[kind]} ") :]
    m = _DECISION_RE.fullmatch(rest)
    if m is None:
        return None
    detail = m.group("detail") or ""
    allowed = QUALIFIERS.get(kind, frozenset())
    # An act that has a qualifier always carries it: `record a ballot on
    # spk-007 by ada` with the value left off would record that somebody
    # voted and not what they voted, which is not a record of anything.
    if detail not in allowed and not (detail == "" and not allowed):
        return None
    return Decision(kind, m.group("entity"), m.group("actor"), detail)


def validate_messages(messages: list[str]) -> list[str]:
    """Every problem in `messages`, as sentences an operator can act on.

    Two rules, and deliberately no third:

    * a message that *claims* to record a decision -- it opens with one of the
      register's act phrases -- has to be readable as one;
    * no message, decision or not, carries an attribution trailer or credits
      an assistant.

    Everything else passes. A commit that fixes a test is not a decision, is
    not checked, and must never have to be.
    """
    problems: list[str] = []
    for message in messages:
        subject = message.splitlines()[0] if message else ""
        lowered = message.lower()
        for pattern, what in _FORBIDDEN_MENTIONS:
            if re.search(pattern, lowered):
                problems.append(f"{subject!r} carries {what}")
                break

        kind = _claimed_kind(subject)
        if kind is None:
            continue
        if len(message.splitlines()) > 1:
            problems.append(f"{subject!r} records a decision, so it must be one line")
            continue
        found = judgemental_terms(subject)
        if found:
            problems.append(
                f"{subject!r} judges a person ({', '.join(found)}); "
                "a decision message names the record, never the person"
            )
            continue
        if parse_decision(subject) is None:
            problems.append(
                f"{subject!r} opens like a decision but does not read as one; "
                f"expected '{DOMAIN}: {ACTS[kind]} <record> by <login>'"
                + (
                    f" ({'|'.join(sorted(QUALIFIERS[kind]))})"
                    if kind in QUALIFIERS
                    else ""
                )
            )
    return problems


def check_commits() -> int:
    """`convener-check-commits`: read commit messages on stdin.

    Fed by `git log --format=%B%x00 <range>` in CI, so a message keeps its
    body and the one-line rule stays checkable; a plain line-per-message
    stream works too. Only the range under review is passed: phase 1 is
    already written and does not follow this grammar, and a check that
    demanded the past be rewritten would be turned off rather than obeyed.
    """
    raw = sys.stdin.read()
    parts = raw.split("\0") if "\0" in raw else raw.splitlines()
    messages = [part.strip("\n") for part in parts if part.strip()]
    problems = validate_messages(messages)
    for problem in problems:
        print(f"error: {problem}")
    if problems:
        print(f"{len(problems)} commit message(s) to fix.")
        return 1
    print(f"{len(messages)} commit message(s) OK.")
    return 0


#: The all-zero object name GitHub sends as `github.event.before` for the first
#: push to a branch. It names no commit: there is no "before" to start from.
NO_PARENT: Final = "0" * 40


def log_range(base: str, before: str, head: str) -> list[str]:
    """The `git log` arguments naming exactly the commits under review.

    Three shapes, because a run knows its starting point in three ways. A
    pull request gives the base it would merge into (`base`); a push gives the
    branch tip it moved from (`before`); the first push to a branch gives the
    all-zero name, which is no commit at all, and neither is an absent value.
    In that last case the head alone is checked, because there is nothing to
    subtract it from.

    Erring towards too few commits is deliberate -- a check that demanded phase
    1 be rewritten would be turned off rather than obeyed -- but "too few" must
    never quietly become "none", which is a green result that verified nothing.
    That is what `tests/test_commit_range.py` exercises against a real
    repository: the arguments are handed to `git log` and the commits that come
    back are counted, so a range that resolves to nothing fails there rather
    than passing in CI.
    """
    head = head.strip() or "HEAD"
    start = base.strip() or before.strip()
    if not start or not start.strip("0"):
        return ["-1", head]
    return [f"{start}..{head}"]


def commit_range() -> int:
    """`convener-commit-range`: print the arguments, for the shell to expand.

    The workflow reads them unquoted into `git log`, so this prints one line
    and nothing else. Reading the three values from the environment rather
    than from `sys.argv` keeps the workflow's `env:` block the single place
    the GitHub event is named.
    """
    print(
        " ".join(
            log_range(
                os.environ.get("BASE", ""),
                os.environ.get("BEFORE", ""),
                os.environ.get("HEAD", ""),
            )
        )
    )
    return 0
