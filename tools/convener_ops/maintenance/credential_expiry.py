"""Dates nothing in this repository can read, declared so that something can.

Four watchdogs live beside this one and every one of them watches a thing
that *stops*: the Actions budget, the submission queue, the retention run,
the registration routing. None of them watches a thing that *expires*, and
the difference matters, because an expiry gives no signal at all until the
moment it is too late.

The three credentials this product's own documents say expire fail in three
different ways, and only one of them is loud:

* `CONVENER_RETENTION_TOKEN` turns the retention job red every day it is
  dead, which `standing-up.yml` calls "the right way round".
* `SHOWCASE_DEPLOY_TOKEN` is quieter: both publishing workflows log a line
  and exit clean, which is that step's own documented degraded state. The
  site simply stops being updated.
* `CONVENER_MEETING_API_TOKEN` is silent by design. `platform_from_env`
  falls back to the manual adapter the moment it is unset or refused, the
  instance keeps working, the Actions tab stays green -- and the day it
  matters is a seminar day, with a room to open and a register to take.

**The design was written down and not built.** `platform_fcc.py` describes
exactly this -- "*a notice is posted to the board thread ... rather than the
integration failing silently on the day of a seminar*" -- and then says
"*None of that renewal or notice logic lives in this module*", and
`operations.md` agrees that it is "not wired up yet". This module is that
paragraph, built.

Declared rather than discovered, and why there is no choice
-----------------------------------------------------------
GitHub reports a fine-grained token's expiry only to the account that owns
it, so no workflow of this repository's can read the date of the token it
is running under, let alone of a credential held at a third party. Every
other watchdog here recomputes its signal from something the repository
holds. This one cannot, and pretending otherwise would have meant an
integration, a credential to reach it with, and an expiry date on *that*.

So the dates are written down by whoever mints the credential, in
`instance/data/credential-renewals.yml`, and this module reads them. That
puts a cost on the operator -- a line to write at the moment of renewal --
and it is the only cost that buys anything: a date nobody wrote down is a
date nobody can be reminded of, which is the state this module exists to
leave.

An undeclared credential is an ordinary state, and said rather than assumed
-----------------------------------------------------------------------------
A fresh duplicate has minted nothing and declares nothing, and the file is
absent. That is D-13's shape and it is not a finding. What would be wrong
is passing over it in silence, so `summary` says how many dates were read
every time it runs, including when the answer is none -- a reader of the
run's log can see the difference between "nothing is due" and "nothing was
looked at".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

from convener_ops.declaration.paths import DATA_DIR, repo_root
from convener_ops.declaration.yaml_safe import safe_load

#: Where the dates are declared. Under `instance/data/`, which
#: `declarations/boundary.yml` hands to the instance whole: these dates are
#: this series' own and upstream could not ship one correctly for anybody.
RENEWALS_PATH: Final = DATA_DIR / "credential-renewals.yml"

#: How much notice a renewal gets. A fortnight, because the renewal this was
#: built for is a browser consent step somebody has to find time for, and
#: because `operations.md` already puts the meeting token's renewal
#: "alongside the other T-7 preparations" -- a notice arriving after that
#: point would arrive after the moment it was meant to inform.
NOTICE_DAYS: Final = 14


@dataclass(frozen=True)
class Renewal:
    """One credential and the day it stops working.

    `renewed_by` is a pointer rather than a procedure: the procedures live
    in `docs/operating/operations.md`, one per integration, and copying a
    line of one here would make two homes for it.
    """

    secret: str
    expires: date
    renewed_by: str


@dataclass(frozen=True)
class Finding:
    """A renewal within the notice window, or already past it."""

    renewal: Renewal
    days_left: int

    @property
    def expired(self) -> bool:
        return self.days_left < 0

    @property
    def secret_name(self) -> str:
        return self.renewal.secret


def parse_date(value: Any, secret: str) -> date:
    """One parser, so a malformed date is one message rather than a
    traceback from wherever it was first compared."""
    if not isinstance(value, str):
        raise ValueError(
            f"{RENEWALS_PATH.as_posix()}: {secret} has expires {value!r}, "
            "which is not a date written as YYYY-MM-DD"
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{RENEWALS_PATH.as_posix()}: {secret} has expires {value!r} "
            f"({exc}). Dates are ISO 8601: YYYY-MM-DD."
        ) from exc


def from_data(data: Any) -> list[Renewal]:
    """Parse an already-loaded declaration.

    Refuses rather than repairs, the way every declaration in this project
    does: a credential whose date cannot be read is worse than one nobody
    declared, because it looks declared.
    """
    if data is None:
        return []
    if not isinstance(data, dict):
        raise ValueError(f"{RENEWALS_PATH.as_posix()} is not a mapping")
    rows = data.get("renewals")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError(
            f"{RENEWALS_PATH.as_posix()}: renewals is {type(rows).__name__}, "
            "and it has to be a list"
        )
    renewals: list[Renewal] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(
                f"{RENEWALS_PATH.as_posix()}: a renewals entry is "
                f"{type(row).__name__} rather than a mapping"
            )
        secret = row.get("secret")
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError(
                f"{RENEWALS_PATH.as_posix()}: a renewals entry names no secret"
            )
        renewed_by = row.get("renewed_by")
        if not isinstance(renewed_by, str) or not renewed_by.strip():
            raise ValueError(
                f"{RENEWALS_PATH.as_posix()}: {secret} says nothing about how "
                "it is renewed. Point at the section of "
                "docs/operating/operations.md that does."
            )
        renewals.append(
            Renewal(
                secret=secret,
                expires=parse_date(row.get("expires"), secret),
                renewed_by=renewed_by,
            )
        )
    return renewals


def load(root: Path | None = None) -> list[Renewal]:
    """The declared renewals, or none when nothing is declared.

    An absent file is not an error: see this module's docstring. It is the
    state every duplicate starts in.
    """
    base = root if root is not None else repo_root()
    path = base / RENEWALS_PATH
    if not path.is_file():
        return []
    return from_data(safe_load(path.read_text(encoding="utf-8")))


def due(
    renewals: list[Renewal], today: date, within: int = NOTICE_DAYS
) -> list[Finding]:
    """Everything inside the window, and everything already past it.

    Sorted by how little time is left, so the first line of a notice is the
    most urgent one rather than whichever happened to be declared first.
    """
    found = [
        Finding(renewal=renewal, days_left=(renewal.expires - today).days)
        for renewal in renewals
        if (renewal.expires - today).days <= within
    ]
    return sorted(found, key=lambda finding: (finding.days_left, finding.secret_name))


def summary(renewals: list[Renewal], findings: list[Finding], today: date) -> str:
    """What the run's log says even when nothing is due.

    Reading how many dates were considered is the difference between
    "nothing is due" and "nothing was looked at", and only one of those is
    good news.
    """
    if not renewals:
        return (
            f"{RENEWALS_PATH.as_posix()} declares no renewal dates, so nothing "
            "here is being watched for expiry. That is the ordinary state of "
            "an instance that has minted no expiring credential; it is also "
            "what an instance that simply never wrote them down looks like."
        )
    counted = f"{len(renewals)} declared renewal date(s) read against {today}"
    if not findings:
        soonest = min(renewal.expires for renewal in renewals)
        return f"{counted}; nothing due within {NOTICE_DAYS} days (next: {soonest})"
    return f"{counted}; {len(findings)} due or overdue"


def message(findings: list[Finding], today: date) -> str:
    """The notice, written for a volunteer reading a thread on a phone."""
    lines = ["**A credential is about to stop working.**", ""]
    for finding in findings:
        renewal = finding.renewal
        when = (
            f"expired {-finding.days_left} day(s) ago"
            if finding.expired
            else f"expires in {finding.days_left} day(s)"
        )
        lines.append(f"- `{renewal.secret}` — {when}, on {renewal.expires}.")
        lines.append(f"  Renewed through: {renewal.renewed_by}")
    lines += [
        "",
        f"Read against {today}, from `{RENEWALS_PATH.as_posix()}`. Whoever "
        "renews one of these writes the new date back into that file in the "
        "same sitting — a date nobody wrote down is a date nobody can be "
        "reminded of.",
    ]
    return "\n".join(lines)


def annotation_lines(findings: list[Finding]) -> list[str]:
    """One workflow annotation per finding, so a run's own summary carries
    them without anybody opening the log."""
    return [
        (
            f"::{'error' if finding.expired else 'warning'}::"
            f"{finding.renewal.secret} "
            + (
                f"expired on {finding.renewal.expires}"
                if finding.expired
                else f"expires on {finding.renewal.expires}, in "
                f"{finding.days_left} day(s)"
            )
        )
        for finding in findings
    ]
