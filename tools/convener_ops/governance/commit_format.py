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
That is the general form of the rule that `tools/tests/maintenance/test_inactivity.py`
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
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

#: The domain prefix a decision commit carries. Decisions are recorded in
#: `instance/data/`, so they are `data:` commits and nothing else.
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
    # The date negotiation. Neither act carries the day: which evenings a
    # researcher was offered, and which they turned down, is their
    # availability rather than the programme -- `candidate_dates` is
    # classified NEVER_PUBLISHED for that reason -- and a commit subject is
    # the one thing here nothing can take back. The day is in the diff, as
    # `lock-date`'s is.
    "date-propose": "propose a date for",
    "date-answer": "record a date reply for",
    "lock-date": "lock the date of",
    # The talk itself, recorded by the hosts on the day rather than left to
    # the overnight sweep. The day is not in the subject: it is already on
    # the record, and `lock-date` sets the same precedent.
    "mark-delivered": "record the delivery of",
    # A talk that was announced and will not happen. The *why* rides in the
    # qualifier below rather than in free text: a commit subject is permanent
    # and unrewritable, and a reason typed at a keyboard is the one thing in
    # this grammar that could name a person's illness.
    "cancel-edition": "cancel",
    # Publishing a recording (G-07, G-08).
    "consent-set": "record the recording consent of",
    "publication-approve": "approve publication of",
    "publication-object": "record an objection to publishing",
    "publication-resolve": "resolve the objections on",
    "finalize-archive": "publish the recording of",
    # Its other half. Publishing and archiving are two things: a recording
    # the speaker or the board has refused still leaves a record worth
    # closing, and closing it writes no published outcome.
    "archive-unpublished": "archive without publishing the recording of",
    # And the way back. An archived event reports what was decided rather
    # than offering the gate again, so a speaker who withdraws their
    # permission -- or a board that changes its mind -- reopens the record
    # first and answers second. The act says only that the question is open
    # again; nothing about the answer is written here.
    "publication-reopen": "reopen the publication decision on",
    # Who sits on the board (G-05), and who is available to vote (G-14).
    #
    # `availability-set` is a decision like the rest and not a diary
    # entry: `unavailable_until` is read by `activeBoard`, so declaring
    # oneself away changes `N` and with it the majority a speaker needs. An
    # act that moves the threshold belongs in the register. The day it runs
    # to is not in the subject, for the same reason `lock-date` does not
    # carry the date it locked: the subject names the record and the actor,
    # and the value is in the diff the commit carries.
    "availability-set": "record the availability of",
    "nomination-open": "open a nomination for",
    "nomination-support": "record support for the nomination of",
    "nomination-object": "record an objection to the nomination of",
    "nomination-withdraw-objection": "withdraw an objection to the nomination of",
    "nomination-resolve": "settle the nomination of",
    # Administrative acts, which the register records exactly like the rest.
    "override": "override the status of",
    # Creating a record names the record, never the person in it: the browser
    # knows the lead's full name at this point and the subject carries the id
    # it has just assigned instead.
    "speaker-create": "record a new lead for",
    "speaker-delete": "delete the record of",
}

#: The qualifier each act admits, as a closed set. An act absent from this
#: mapping takes no qualifier at all, and one present takes nothing outside
#: its set -- so `record a ballot on spk-001 by ana (maybe)` is not a message
#: this grammar can express, nor one it will accept.
QUALIFIERS: Final[dict[str, frozenset[str]]] = {
    "ballot-cast": frozenset({"yes", "abstain", "recused"}),
    "availability-set": frozenset({"away", "back"}),
    "consent-set": frozenset({"granted", "refused"}),
    # `cleared` is a reply taken back, which the record stores as `answer:
    # ""`. The act records what happened, so it has a word the field does
    # not.
    "date-answer": frozenset({"accepted", "declined", "cleared"}),
    # Four, and deliberately no catch-all: a vocabulary with an `other` in it
    # is a vocabulary that stops being read. Between them they cover who
    # withdrew -- the speaker, the Board -- and what made the slot impossible,
    # whether the day itself or the series pausing.
    "cancel-edition": frozenset(
        {
            "speaker-withdrew",
            "board-withdrew",
            "date-unworkable",
            "series-paused",
        }
    ),
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
            "cancelled",
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
#: irregular, and `left` is exactly one of the six words this grammar bans.
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
    stream works too. Only the range under review is passed: the oldest
    commits predate this grammar and do not follow it, and a check that
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


#: `git log`'s own option for "only this branch's own commits", and the one
#: option every caller of `log_range` inherits rather than spelling out.
#:
#: **A repository answers for the commits it wrote, not for the ones it
#: fetched.** Without this, a duplicate that merges an upstream release puts
#: every commit of that release under its own grammar check -- and the first
#: one that fails turns *its* `Quality` red for something it did not write and
#: cannot fix without rewriting another repository's history. That is the same
#: argument `check_commits` already makes for not judging this project's own
#: phase 1, applied across a repository boundary instead of across time: a
#: check that demanded the past be rewritten would be turned off rather than
#: obeyed.
#:
#: It is not an amnesty. A merge commit stays under review -- it is this
#: branch's own -- and so does every commit made here. What leaves the range
#: is the second-parent side of a merge, which is another branch's work, judged
#: where it was written: on its own pull request, where `base` names that
#: branch's own starting point and the range covers exactly its commits.
#:
#: Named here, in the value `convener-commit-range` prints, so that
#: `quality.yml` and `gates.sh` cannot be given different `git log` options --
#: which is half of the defect this constant was added for.
FIRST_PARENT: Final = "--first-parent"


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
    That is what `tests/governance/test_commit_range.py` exercises against a real
    repository: the arguments are handed to `git log` and the commits that come
    back are counted, so a range that resolves to nothing fails there rather
    than passing in CI.

    Every shape carries `FIRST_PARENT` -- see that constant for why a
    repository answers for its own commits and not for the ones a merge
    brought in.
    """
    head = head.strip() or "HEAD"
    start = base.strip() or before.strip()
    if not start or not start.strip("0"):
        return [FIRST_PARENT, "-1", head]
    return [FIRST_PARENT, f"{start}..{head}"]


#: Where a run with no GitHub event behind it looks for its starting point, in
#: order, stopping at the first that names a commit.
#:
#: `@{u}` is the branch's own upstream, which is literally what the next push
#: will be measured against, so a local run and the `push` run it precedes
#: read the same commits. `origin/HEAD` answers for a branch that has never
#: been pushed and therefore has no upstream yet -- the ordinary state of work
#: in progress -- and selects what a pull request from it would, which is the
#: run that will actually judge it.
_LOCAL_STARTS: Final = ("@{u}", "origin/HEAD")


def _adds_commits(name: str) -> bool:
    """Whether `name..HEAD` names at least one commit, on the first-parent
    line, in the repository `git` is run from.

    One question, not two, and deliberately the *stronger* one. A starting
    point that exists but selects nothing is worse than no starting point at
    all: `convener-check-commits` reads an empty stream, prints "0 commit
    message(s) OK" and the gate goes green having verified nothing -- the
    exact failure `tests/governance/test_commit_range.py` was written
    against, and the one an earlier draft of `local_start` reintroduced by
    offering `origin/HEAD` on a branch that had not committed yet. `rev-list`
    answers both halves: an unknown ref is a non-zero exit, a known one that
    adds nothing is a count of zero.
    """
    result = subprocess.run(  # nosec B603 B607
        ["git", "rev-list", "--count", FIRST_PARENT, f"{name}..HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return False
    return result.stdout.strip() not in ("", "0")


def local_start(adds_commits: Callable[[str], bool] = _adds_commits) -> str:
    """The starting point for a run with no GitHub event, or `""` if the
    repository offers none that selects anything.

    **Why this exists.** `log_range` falls back to `-1 head` when it is given
    no starting point, which is right for the one case it was written for --
    the first push to a branch, where there is genuinely nothing to subtract
    from. Run by hand there is no event either, so `gates.sh` took that same
    fallback and checked **one** commit while the push it was verifying
    checked thirty-six. The gate that opens by promising it runs "every gate
    `quality.yml` runs, one target each" answered a narrower question than CI
    without saying so, and a duplicate taking a release got a red run on a
    commit its own green verification could not reach.

    Erring towards too few commits is still the safe direction, and a run
    that finds no usable starting point still ends at `-1 HEAD` -- one real
    commit, never none. That is why the question asked of each candidate is
    "does it select anything" rather than "does it exist": on a branch with
    no commits of its own, `origin/HEAD` exists and selects nothing, and
    offering it would turn this fix into the very defect it is for.

    `adds_commits` is injected so the tests can drive every branch without a
    remote; nothing in the product passes it.
    """
    for name in _LOCAL_STARTS:
        if adds_commits(name):
            return name
    return ""


def commit_range() -> int:
    """`convener-commit-range`: print the arguments, for the shell to expand.

    The workflow reads them unquoted into `git log`, so this prints one line
    and nothing else. Reading the three values from the environment rather
    than from `sys.argv` keeps the workflow's `env:` block the single place
    the GitHub event is named.

    With no event in the environment -- a run by hand, `gates.sh` -- the
    starting point comes from the repository instead (`local_start`), so that
    the two ask the same question. Only `BEFORE` is filled in that way, never
    `BASE`: a pull request's base is a fact about a pull request, and
    inventing one locally would claim a review that is not happening.
    """
    base = os.environ.get("BASE", "")
    before = os.environ.get("BEFORE", "")
    head = os.environ.get("HEAD", "")
    if not base.strip() and not before.strip():
        before = local_start()
    print(" ".join(log_range(base, before, head)))
    return 0
