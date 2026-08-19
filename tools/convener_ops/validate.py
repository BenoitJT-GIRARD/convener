"""Pure validation of the operational data files.

Every function takes already-parsed data and returns a list of human-readable
errors. Nothing here touches the filesystem — that belongs to cli.py.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Any

from .governance import MINIMUM_ELIGIBLE

STATUSES = frozenset(
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
)
GENDERS = frozenset({"M", "F", "NB", "undisclosed"})

#: Governance model (schema v3, see app/src/data/types.ts). Kept in this
#: module rather than imported from governance.py because governance.py
#: does not define these vocabularies - it consumes already-valid ballots
#: and never needed to enumerate the legal values itself.
BALLOT_VALUES = frozenset({"yes", "abstain", "recused"})
CAREER_STAGES = frozenset(
    {"phd", "postdoc", "independent", "group-leader", "other", "undisclosed"}
)
#: '' is a legal consent: the migration sets it for any speaker whose status
#: never reached a publishable state (see scripts/migrate_v3.py, Task 5).
PUBLICATION_CONSENTS = frozenset({"", "granted", "refused", "pending"})
#: Schema v4. The fields the checklists have always asked for and the model
#: never had, so they travelled by e-mail and were lost: a portrait, a short
#: biography, a handle, and the questions the speaker wants the forum
#: discussion opened with.
#:
#: Checked with `in`, never with `entry.get(key)`. An empty value is an
#: answer -- "no biography" is a thing a speaker can say, and the file has to
#: be able to hold it -- while an absent key is a record nobody finished.
#: Truthiness cannot tell those apart, and reading one as the other is how a
#: field ends up silently optional. `app/src/data/validate.ts` draws the same
#: line on the read side.
SPEAKER_TEXT_V4 = ("photo_url", "bio", "linkedin", "seed_questions")
CANDIDATE_DATE_KEYS = frozenset({"date", "time", "answer"})
#: What one line of the journey may say about itself. `assignee` is who owes
#: that line -- not `assigned_to`, which is the board member who owns the
#: lead. The two are different notions at different grains, they are never
#: derived from one another, and this validator checks each against its own
#: rule: `assigned_to` has to be a sitting board member, an item owner does
#: not, because a line of a runbook can be owed by a host who never sat on
#: the board.
CHECKLIST_ITEM_KEYS = frozenset({"assignee"})
#: What a speaker has said about one proposed slot. There is no 'pending' and
#: no fourth value: an answer that has not come back is '', and nothing here
#: can be read as a soft yes by the transition that locks the date in.
DATE_ANSWERS = frozenset({"accepted", "declined", ""})
PUBLICATION_OUTCOMES = frozenset({"published", "withheld", ""})
NOMINATION_OUTCOMES = frozenset({"accepted", "deferred", "waiting", ""})
BOARD_STATUSES = frozenset({"active", "inactive"})

CONFIG_REQUIRED = frozenset(
    {
        "season",
        "vw_counter",
        "overlap_window_days",
        "seminar_duration_minutes",
        "board",
        "nominations",
        "board_min",
        "board_max",
        "vote_window_days",
        "objection_window_working_days",
        "inactivity_months",
        "balance_window_months",
        "sla_days",
        "channels",
    }
)
#: The two fields one promotion channel carries, and the only two.
#:
#: The seven channels the spec named are configuration and not a constant:
#: whether they are still the right seven cannot be confirmed without asking
#: the collaborators, which this project never does. So nothing here counts
#: them, and nothing here names one - a channel added, renamed or dropped in
#: `data/config.yml` passes this validator unchanged, which is the whole
#: point of the list being data.
CHANNEL_KEYS = frozenset({"key", "label"})
#: A channel `key` becomes a checklist key inside `data/speakers.yml`, read
#: back by both languages and skimmed in hand-reviewed diffs. Spaces and
#: capitals would survive the round-trip and read as a different key to a
#: person. The `label`, which nothing stores, carries whatever wording the
#: volunteers want.
CHANNEL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
CONFIG_INTS = (
    "season",
    "vw_counter",
    "overlap_window_days",
    "seminar_duration_minutes",
    "board_min",
    "board_max",
    "vote_window_days",
    "objection_window_working_days",
    "inactivity_months",
    "balance_window_months",
)
SLA_DAYS_KEYS = frozenset(
    {
        "lead_decision",
        "invitation_follow_up",
        "summary_after_delivery",
        "recording_after_delivery",
    }
)
NEEDS_SCHEDULE = frozenset({"scheduled", "delivered", "archived"})

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
EDITION_RE = re.compile(r"^MRG-\d+$")
LOGIN_RE = re.compile(r"^[a-zA-Z0-9-]+$")


def _validate_checklist(checklist: Any, where: str) -> list[str]:
    """Validate `Speaker.checklist` - who owes each line of the journey.

    `{}` is the normal state and never an error: naming an owner is not
    something the series has ever asked of anybody, and a line nobody is down
    for stays the hosts' - which is the behaviour the app has always had. The
    key itself is required all the same, as every other field is, because
    `app/src/data/validate.ts` refuses a record with a key missing and the
    two sides have to agree about what a complete record is. `{}` is the
    answer "nobody is down for anything"; an absent key is a record nobody
    finished.

    What is checked is the shape of what is there: a mapping of runbook item
    to a block carrying an `assignee`, and nothing else. The item keys are
    free-form on purpose - they follow the runbook (`app/src/state/
    phases.ts`), which changes - so only the block is constrained.
    """
    errors: list[str] = []
    if not isinstance(checklist, dict):
        errors.append(f"{where}.checklist: must be a mapping")
        return errors

    for item, entry in checklist.items():
        iwhere = f"{where}.checklist[{item!r}]"
        if not isinstance(entry, dict):
            errors.append(f"{iwhere}: not a mapping")
            continue
        extra = set(entry) - CHECKLIST_ITEM_KEYS
        if extra:
            errors.append(f"{iwhere}: unknown keys {sorted(extra)}")
        if "assignee" not in entry:
            errors.append(f"{iwhere}: missing assignee")
            continue
        assignee = entry["assignee"]
        if not isinstance(assignee, str):
            errors.append(f"{iwhere}: assignee must be a string")
        elif assignee and not LOGIN_RE.match(assignee):
            errors.append(f"{iwhere}: invalid assignee {assignee!r}")
    return errors


def _validate_objections(objections: Any, where: str) -> list[str]:
    """Validate a PublicationObjection[] - shared by Publication and Nomination.

    Both `Speaker.publication.objections` and `Config.nominations[].objections`
    are typed as `PublicationObjection[]` (app/src/data/types.ts): a list of
    {member, reason, date}. One helper, one place to get the shape right.
    """
    errors: list[str] = []
    if objections is None:
        return errors
    if not isinstance(objections, list):
        errors.append(f"{where}.objections: must be a list")
        return errors

    for oindex, objection in enumerate(objections):
        owhere = f"{where}.objections[{oindex}]"
        if not isinstance(objection, dict):
            errors.append(f"{owhere}: not a mapping")
            continue

        member = objection.get("member")
        if member is not None and (
            not isinstance(member, str) or not LOGIN_RE.match(member)
        ):
            errors.append(f"{owhere}: invalid objection member {member!r}")

        date = objection.get("date")
        if date and not DATE_RE.match(str(date)):
            errors.append(f"{owhere}: date must be YYYY-MM-DD, got {date!r}")

        # Publication objections carry the day they were closed; nomination
        # objections do not (an objection there defers the candidate to the
        # annual meeting rather than being resolved). Absent is legal in
        # both, and means the objection still stands - the reading that
        # keeps a recording offline rather than publishing it.
        resolved_on = objection.get("resolved_on")
        if resolved_on and not DATE_RE.match(str(resolved_on)):
            errors.append(
                f"{owhere}: resolved_on must be YYYY-MM-DD, got {resolved_on!r}"
            )

    return errors


def _validate_candidate_dates(dates: Any, where: str) -> list[str]:
    """Validate `Speaker.candidate_dates` - the slots put to the speaker.

    The invitation has always proposed several dates while the record held
    one, so the negotiation lived in a mailbox and only its conclusion was
    ever written down. A slot is a day, an hour and an answer, and all three
    are required: a proposal with no day is not a proposal, and an answer
    outside the vocabulary would reach the transition that freezes `date`,
    which has no reading for it.
    """
    errors: list[str] = []
    if not isinstance(dates, list):
        errors.append(f"{where}.candidate_dates: must be a list")
        return errors

    seen: set[tuple[str, str]] = set()
    for index, slot in enumerate(dates):
        swhere = f"{where}.candidate_dates[{index}]"
        if not isinstance(slot, dict):
            errors.append(f"{swhere}: not a mapping")
            continue

        missing = CANDIDATE_DATE_KEYS - set(slot)
        if missing:
            errors.append(f"{swhere}: missing keys {sorted(missing)}")

        date = slot.get("date")
        if not isinstance(date, str) or not DATE_RE.match(date):
            errors.append(f"{swhere}: date must be YYYY-MM-DD, got {date!r}")

        time = slot.get("time")
        if not isinstance(time, str) or not TIME_RE.match(time):
            errors.append(f"{swhere}: time must be HH:MM, got {time!r}")

        answer = slot.get("answer")
        if answer not in DATE_ANSWERS:
            errors.append(f"{swhere}: invalid answer {answer!r}")

        # The same slot offered twice reads as two answers to one question,
        # and the file cannot say which of them the speaker gave.
        if isinstance(date, str) and isinstance(time, str):
            if (date, time) in seen:
                errors.append(f"{swhere}: duplicate slot {date!r} {time!r}")
            else:
                seen.add((date, time))

    return errors


def _validate_ballots(
    entry: dict[str, Any], where: str, board_logins: Collection[str]
) -> list[str]:
    """Validate one speaker's selection (opened_on and ballots) against the
    governance model.

    Note on scope: this deliberately duplicates none of governance.py's
    eligibility math (threshold_for, eligible_voters, decide) - those answer
    "was this vote decided", a different question from "is this data well
    formed". In particular, decide() silently ignores a ballot cast by a
    login absent from the board (eligible_voters filters the board, so a
    stray ballot never inflates a count) - that tolerance is intentional and
    correct for tallying. Here, the same situation is an error: the
    validator's job is to say the data itself is malformed, not to shrug and
    carry on the way the tally must.
    """
    errors: list[str] = []
    selection = entry.get("selection")
    if not isinstance(selection, dict):
        return errors

    opened_on = selection.get("opened_on")
    if opened_on and not DATE_RE.match(str(opened_on)):
        errors.append(
            f"{where}.selection: opened_on must be YYYY-MM-DD, got {opened_on!r}"
        )

    # decided_on gets copied into every generated ballot's date by the
    # migration (scripts/migrate_v3.py, Task 5) - a malformed value here
    # would propagate into every ballot it touches, not stay in one field.
    decided_on = selection.get("decided_on")
    if decided_on and not DATE_RE.match(str(decided_on)):
        errors.append(
            f"{where}.selection: decided_on must be YYYY-MM-DD, got {decided_on!r}"
        )

    ballots = selection.get("ballots")
    if not isinstance(ballots, list):
        return errors

    seen_voters: set[Any] = set()
    for bindex, raw_ballot in enumerate(ballots):
        bwhere = f"{where}.selection.ballots[{bindex}]"
        if not isinstance(raw_ballot, dict):
            errors.append(f"{bwhere}: not a mapping")
            continue

        value = raw_ballot.get("value")
        if value not in BALLOT_VALUES:
            errors.append(f"{bwhere}: invalid ballot value {value!r}")

        if value == "recused" and not raw_ballot.get("coi_reason"):
            errors.append(f"{bwhere}: recusal requires coi_reason")

        date = raw_ballot.get("date")
        if date and not DATE_RE.match(str(date)):
            errors.append(f"{bwhere}: date must be YYYY-MM-DD, got {date!r}")

        voter = raw_ballot.get("voter")
        if voter in seen_voters:
            errors.append(f"{bwhere}: duplicate ballot from {voter!r}")
        else:
            seen_voters.add(voter)

        # Membership is checked unconditionally, including against an empty
        # board_logins: a config with no board (or an unmigrated one) must
        # not silently disable this check - it should fail loudly instead,
        # same as every ballot in that case would (nobody is a member yet).
        if voter not in board_logins:
            errors.append(f"{bwhere}: ballot from a non-member ({voter!r})")

    return errors


def validate_speakers(
    speakers: Any, board_logins: Collection[str] = frozenset()
) -> list[str]:
    if not isinstance(speakers, list):
        return ["speakers.yml: top-level must be a list"]

    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_editions: set[str] = set()

    for index, entry in enumerate(speakers):
        where = f"speakers[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: not a mapping")
            continue

        sid = entry.get("id")
        where = f"{where} ({sid})"
        if not sid:
            errors.append(f"{where}: missing id")
        elif sid in seen_ids:
            errors.append(f"{where}: duplicate id {sid!r}")
        else:
            seen_ids.add(sid)

        for key in ("name", "status"):
            if not entry.get(key):
                errors.append(f"{where}: missing {key}")

        status = entry.get("status")
        if status not in STATUSES:
            errors.append(f"{where}: invalid status {status!r}")

        gender = entry.get("gender")
        if gender is not None and gender not in GENDERS:
            errors.append(f"{where}: invalid gender {gender!r}")

        date = entry.get("date")
        if date and not DATE_RE.match(str(date)):
            errors.append(f"{where}: date must be YYYY-MM-DD, got {date!r}")

        time = entry.get("time")
        if time and not TIME_RE.match(str(time)):
            errors.append(f"{where}: time must be HH:MM, got {time!r}")

        edition = entry.get("edition_code")
        if edition:
            if not EDITION_RE.match(str(edition)):
                errors.append(f"{where}: edition_code must match MRG-N, got {edition!r}")
            elif edition in seen_editions:
                errors.append(f"{where}: duplicate edition_code {edition!r}")
            else:
                seen_editions.add(edition)

        for key in ("host_1", "host_2"):
            value = entry.get(key, "")
            if value is not None and not isinstance(value, str):
                errors.append(f"{where}: {key} must be a string")

        if status in NEEDS_SCHEDULE:
            if not edition:
                errors.append(f"{where}: status {status} requires edition_code")
            if not date:
                errors.append(f"{where}: status {status} requires date")

        if status == "scheduled" and not (entry.get("host_1") and entry.get("host_2")):
            errors.append(f"{where}: scheduled requires both host_1 and host_2")

        # assigned_to is the board member who owns the lead (ruling P2-15).
        # It is not proposed_by, which is the submitter's self-reported name
        # and is never checked against the board: a member of the public may
        # propose a speaker, but only a member may be handed the follow-up.
        assigned_to = entry.get("assigned_to")
        if not isinstance(assigned_to, str):
            errors.append(f"{where}: assigned_to must be a string")
        elif assigned_to and assigned_to not in board_logins:
            errors.append(
                f"{where}: assigned_to is not a board member ({assigned_to!r})"
            )

        # career_stage and publication are required since the v3 migration
        # (scripts/migrate_v3.py, Task 5) gave every speaker both. They were
        # checked only when present while the real data was still v2; now
        # their absence is a defect - a migration that silently dropped one
        # is exactly what this validator exists to catch.
        career_stage = entry.get("career_stage")
        if career_stage not in CAREER_STAGES:
            errors.append(f"{where}: invalid career_stage {career_stage!r}")

        # Schema v4. Absent is a defect; empty is an answer. Anything that
        # asked `entry.get(key)` here would report the two as one thing, and
        # the field would be optional in everything but its documentation.
        for key in SPEAKER_TEXT_V4:
            if key not in entry:
                errors.append(f"{where}: missing {key}")
            elif not isinstance(entry[key], str):
                errors.append(f"{where}: {key} must be a string")

        if "checklist" not in entry:
            errors.append(f"{where}: missing checklist")
        else:
            errors.extend(_validate_checklist(entry["checklist"], where))

        if "candidate_dates" not in entry:
            errors.append(f"{where}: missing candidate_dates")
        else:
            errors.extend(_validate_candidate_dates(entry["candidate_dates"], where))

        publication = entry.get("publication")
        pub_where = f"{where}.publication"
        if not isinstance(publication, dict):
            errors.append(f"{pub_where}: not a mapping")
        else:
            consent = publication.get("consent")
            if consent not in PUBLICATION_CONSENTS:
                errors.append(f"{pub_where}: invalid publication consent {consent!r}")

            outcome = publication.get("outcome")
            if outcome not in PUBLICATION_OUTCOMES:
                errors.append(f"{pub_where}: invalid publication outcome {outcome!r}")

            approved_on = publication.get("approved_on")
            if approved_on and not DATE_RE.match(str(approved_on)):
                errors.append(
                    f"{pub_where}: approved_on must be YYYY-MM-DD, got {approved_on!r}"
                )

            errors.extend(
                _validate_objections(publication.get("objections"), pub_where)
            )

            # Cross-field checks on the publication block.
            #
            # These are now statements about the past, not live defences.
            # `outcome: published` has exactly one writer in the app
            # (`app/src/state/transitions.ts`, the finalize-archive
            # transition) and that writer asks `governance.canArchive`
            # first, so none of the states below can be produced by using
            # the application. What is left is a file hand-edited outside
            # it - a real possibility for a YAML repository, and the only
            # thing these still catch.
            if consent == "refused" and outcome == "published":
                errors.append(
                    f"{pub_where}: refused consent cannot have outcome published"
                )
            if outcome == "published" and not approved_on:
                errors.append(
                    f"{pub_where}: published recording has no approval on record"
                )
            objections = publication.get("objections")
            if (
                outcome == "published"
                and isinstance(objections, list)
                and any(
                    isinstance(o, dict) and not o.get("resolved_on") for o in objections
                )
            ):
                errors.append(
                    f"{pub_where}: published recording has a standing objection"
                )

        errors.extend(_validate_ballots(entry, where, board_logins))

    return errors


def _active_seats(board: list[Any]) -> int:
    """How many seats the board actually occupies: active entries, not rows."""
    return sum(1 for m in board if isinstance(m, dict) and m.get("status") == "active")


def board_target_report(cfg: Any) -> str | None:
    """One plain line when the board sits below `board_min`, else `None`.

    `board_min` is the size the board aims to be, never a rule: no code path
    anywhere refuses an act because the board is short of it, and the note in
    `validate_config` says why. What a target is owed is that somebody says it
    is not met -- a number nothing reads and nothing reports would not be a
    target, it would be a decoration -- so this is the sentence `convener-validate`
    prints alongside its verdict without changing that verdict.

    `None` when the board is at or above the target, and `None` when either
    number is missing or unreadable: this states a fact about a well-formed
    file, and a malformed one is `validate_config`'s to report.
    """
    if not isinstance(cfg, dict):
        return None
    board = cfg.get("board")
    board_min = cfg.get("board_min")
    if not isinstance(board, list) or not isinstance(board_min, int):
        return None
    seated = _active_seats(board)
    if seated >= board_min:
        return None
    return (
        f"config.yml: board has {seated} active members, below its target of "
        f"{board_min} (board_min). Reported, not enforced - nothing is blocked "
        f"by it; the floor a vote needs is {MINIMUM_ELIGIBLE}."
    )


def validate_config(cfg: Any) -> list[str]:
    if not isinstance(cfg, dict):
        return ["config.yml: top-level must be a mapping"]

    errors: list[str] = []

    # Loud, explicit errors for the two schema-v2 keys schema v3 replaces.
    # A file that still carries either has not been migrated - saying so
    # here is far cheaper than a reader discovering it from a downstream
    # KeyError or, worse, from silently-ignored governance data.
    if "vote_threshold" in cfg:
        errors.append(
            "config.yml: vote_threshold is obsolete, the threshold is now "
            "computed from the eligible board size (see governance.py), not stored"
        )
    if "board_members" in cfg:
        errors.append("config.yml: board_members is obsolete, migrate to board")

    missing = CONFIG_REQUIRED - set(cfg)
    if missing:
        errors.append(f"config.yml: missing keys {sorted(missing)}")

    board = cfg.get("board")
    if "board" in cfg and not isinstance(board, list):
        errors.append("config.yml: board must be a list")
    elif isinstance(board, list):
        for member in board:
            if not isinstance(member, dict):
                errors.append(f"config.yml: invalid board member {member!r}")
                continue

            login = member.get("login")
            if not isinstance(login, str) or not LOGIN_RE.match(login):
                errors.append(f"config.yml: invalid board member {login!r}")

            # Written explicitly by the migration, and required here:
            # governance.active_board keeps only members whose status is
            # exactly 'active', so a member with no status silently leaves
            # the board - and with it the denominator of every vote.
            status = member.get("status")
            if status not in BOARD_STATUSES:
                errors.append(f"config.yml: invalid board member status {status!r}")

            for date_field in ("joined_on", "unavailable_until"):
                value = member.get(date_field)
                if value and not DATE_RE.match(str(value)):
                    errors.append(
                        f"config.yml: board member {date_field} must be "
                        f"YYYY-MM-DD, got {value!r}"
                    )

    board_min = cfg.get("board_min")
    board_max = cfg.get("board_max")
    if (
        isinstance(board_min, int)
        and isinstance(board_max, int)
        and board_min > board_max
    ):
        errors.append("config.yml: board_min cannot exceed board_max")

    # Ordering alone (above) doesn't catch an actual board that has drifted
    # away from its own declared bounds - check the real headcount too. But
    # the two bounds are not one check, because they are not the same kind of
    # thing.
    #
    # `board_max` is a rule, and it is enforced: `board.resolveNominations`
    # counts the seats before it fills one and parks the candidate it cannot
    # seat, so a file over the ceiling is a file the app could not have
    # written. Saying so is exactly what a validator is for.
    #
    # `board_min` is a target, and nothing enforces it. A board under its
    # target still decides - the only floor a vote has is
    # `governance.MINIMUM_ELIGIBLE` - still admits members, and is the board
    # that most needs to. Failing here would stop every unrelated act, a data
    # commit or the nightly sweep included, until somebody edited the target
    # down to meet the board: the target correcting the board instead of the
    # board reaching the target. It is reported instead, by
    # `board_target_report`, which is what a target is owed.
    #
    # *Active* members, not entries, on both counts. G-07's ceiling is about
    # who can vote: an `inactive` entry is out of the denominator
    # (`governance.active_board`), stays in the file with its `login` and
    # `joined_on` intact so coming back costs one word, and must not occupy a
    # seat while it does. The browser reads it the same way -
    # `board.resolveNominations` counts active members before seating - and
    # counting entries here meant the app could write a config this very
    # function then rejected in CI. Pinned by `board_headcount_cases` in
    # tools/tests/fixtures/governance-cases.json.
    if isinstance(board, list) and isinstance(board_max, int):
        seated = _active_seats(board)
        if seated > board_max:
            errors.append(
                f"config.yml: board has {seated} active members, "
                f"over board_max ({board_max})"
            )

    nominations = cfg.get("nominations")
    if "nominations" in cfg and not isinstance(nominations, list):
        errors.append("config.yml: nominations must be a list")
    elif isinstance(nominations, list):
        for nindex, nomination in enumerate(nominations):
            nwhere = f"config.yml: nominations[{nindex}]"
            if not isinstance(nomination, dict):
                errors.append(f"{nwhere}: not a mapping")
                continue

            candidate = nomination.get("candidate")
            if not isinstance(candidate, str) or not LOGIN_RE.match(candidate):
                errors.append(f"{nwhere}: invalid nomination candidate {candidate!r}")

            sponsor = nomination.get("sponsor")
            if not isinstance(sponsor, str) or not LOGIN_RE.match(sponsor):
                errors.append(f"{nwhere}: invalid nomination sponsor {sponsor!r}")

            opened_on = nomination.get("opened_on")
            if opened_on and not DATE_RE.match(str(opened_on)):
                errors.append(
                    f"{nwhere}: opened_on must be YYYY-MM-DD, got {opened_on!r}"
                )

            outcome = nomination.get("outcome")
            if outcome not in NOMINATION_OUTCOMES:
                errors.append(f"{nwhere}: invalid nomination outcome {outcome!r}")

            objections = nomination.get("objections")
            errors.extend(_validate_objections(objections, nwhere))

            # Cross-field backstop (coordinator ruling, phase 2): outcome and
            # objections can express a contradictory state that no type can
            # forbid. The transformations meant to prevent this ship in
            # later tasks; this check is the backstop for a file hand-edited
            # outside them.
            if outcome == "accepted" and isinstance(objections, list) and objections:
                errors.append(f"{nwhere}: accepted nomination has open objections")

            # The other half of the same pair. An acceptance and the seat it
            # implies are written in one transformation
            # (app/src/state/board.ts::resolveNominations), so an accepted
            # nomination whose candidate holds no seat at all cannot come out
            # of the app - only out of a hand edit, and it would leave the
            # board smaller than the record says it is.
            #
            # A seat, not an *active* seat: the nomination attests that the
            # board granted one, which stays true after G-09 moves the member
            # to `inactive`. Requiring `active` here would make the inactivity
            # rule (tools/convener_ops/sweep.py::sweep_inactive_members) unable to
            # touch anyone the board itself admitted, and would push toward
            # deleting the nomination - erasing how a member arrived in order
            # to record that they have gone quiet.
            if outcome == "accepted" and isinstance(candidate, str):
                members = board if isinstance(board, list) else []
                seated = any(
                    isinstance(m, dict) and m.get("login") == candidate for m in members
                )
                if not seated:
                    errors.append(
                        f"{nwhere}: accepted nomination {candidate!r} holds no "
                        f"board seat"
                    )

        # G-08's deferral rule, as a backstop for a hand-edited file. A
        # nomination the board has not finished with -- still pending, or
        # carrying an objection that defers it to the annual meeting -- is the
        # only one open for that candidate: `board.ts::nominationBlocker`
        # refuses a second one, and `board.ts::withdrawObjection` is the only
        # way an objection stops standing. A pair can therefore only be typed
        # in by hand, and left there it would route straight around the
        # objection, which is the whole thing the deferral exists to prevent.
        first_open: dict[str, int] = {}
        for nindex, nomination in enumerate(nominations):
            if not isinstance(nomination, dict):
                continue
            candidate = nomination.get("candidate")
            if not isinstance(candidate, str) or not candidate:
                continue
            outcome = nomination.get("outcome")
            if outcome == "accepted":
                # Already reported above if it carries objections; a seat that
                # was granted is not an open question.
                continue
            objections = nomination.get("objections")
            standing = isinstance(objections, list) and bool(objections)
            if not (outcome in ("", "waiting") or standing):
                continue
            seen_at = first_open.get(candidate)
            if seen_at is None:
                first_open[candidate] = nindex
            else:
                errors.append(
                    f"config.yml: nominations[{nindex}]: {candidate!r} already "
                    f"has an unsettled nomination at nominations[{seen_at}]"
                )

    # The channels an event is announced on. The list is validated; its
    # contents are not judged. An empty list is legal and means nothing is
    # promoted through this app - the "absent configuration does nothing"
    # side of the standing pattern. A list that cannot be read is an error,
    # because a broken list read as an empty one would show a volunteer a
    # promotion phase with no lines in it and nothing to say the file, not
    # the plan, is what is missing.
    channels = cfg.get("channels")
    if "channels" in cfg and not isinstance(channels, list):
        errors.append("config.yml: channels must be a list")
    elif isinstance(channels, list):
        first_seen: dict[str, int] = {}
        for cindex, channel in enumerate(channels):
            cwhere = f"config.yml: channels[{cindex}]"
            if not isinstance(channel, dict):
                errors.append(f"{cwhere}: not a mapping")
                continue

            unknown = sorted(set(channel) - CHANNEL_KEYS)
            if unknown:
                errors.append(f"{cwhere}: unknown keys {unknown}")

            key = channel.get("key")
            if not isinstance(key, str) or not CHANNEL_KEY_RE.match(key):
                errors.append(f"{cwhere}: invalid channel key {key!r}")
            else:
                # Two entries sharing a key share one checklist key: ticking
                # one would tick the other, and which label a screen showed
                # would come down to list order.
                seen_at = first_seen.get(key)
                if seen_at is None:
                    first_seen[key] = cindex
                else:
                    errors.append(
                        f"{cwhere}: {key!r} already used at channels[{seen_at}]"
                    )

            label = channel.get("label")
            if not isinstance(label, str) or not label.strip():
                errors.append(f"{cwhere}: channel {key!r} has no label")

    sla_days = cfg.get("sla_days")
    if "sla_days" in cfg and not isinstance(sla_days, dict):
        errors.append("config.yml: sla_days must be a mapping")
    elif isinstance(sla_days, dict):
        missing_sla = SLA_DAYS_KEYS - set(sla_days)
        if missing_sla:
            errors.append(f"config.yml: missing sla_days keys {sorted(missing_sla)}")

    for key in CONFIG_INTS:
        if key in cfg and not isinstance(cfg[key], int):
            errors.append(f"config.yml: {key} must be an integer")

    return errors
