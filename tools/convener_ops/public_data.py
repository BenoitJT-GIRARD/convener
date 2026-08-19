"""Reduce the speaker list to what may be published.

This is an allowlist, deliberately. With a denylist, adding an internal field
would publish it by accident — which is exactly the failure this guards
against.

The allowlist is no longer written out but derived from a classification of
every field a speaker record has, in three parts: what the programme of a
public seminar consists of, what is a further disclosure about the person and
so waits on a recorded consent, and what never leaves at all. The same three
sets live in `app/src/state/consent.ts` -- which carries the argument for each
placement -- and the two copies are bound by
`tools/tests/fixtures/governance-cases.json`, read from both languages. Their
union is exactly the set of keys of `Speaker`, checked on both sides, so a
field added to the model later cannot reach this file unclassified: it fails a
test instead of being published by omission.
"""

from __future__ import annotations

from typing import Any

PUBLIC_STATUSES = frozenset({"scheduled", "delivered", "archived"})

#: The statuses at which a recording may be linked. `archived` and nothing
#: else, because `archived` is what the publication gate itself writes:
#: `finalize-archive` is the single writer of `outcome: published` and it
#: sets this status in the same expression. A `delivered` record with a URL
#: typed into the wrap-up checklist is a recording that exists, not a
#: recording anyone cleared -- the checklist field records where the file
#: is, the gate decides whether it is linked. Keeping `delivered` here made
#: the checklist a second door into the feed.
RECORDING_STATUSES = frozenset({"archived"})

#: The programme of a public seminar: what a person accepted by accepting the
#: invitation to speak. Naming them, with the institution they speak for and
#: the country the talk is billed from, is what an announcement *is*; the
#: title and abstract are the text they wrote for that audience; the date,
#: time and status are when it happens; `zoom_link` is how the public joins
#: and `forum_thread` where the public discussion sits. Withholding any of
#: these would not protect the speaker, it would cancel the announcement.
#: See `app/src/state/consent.ts` for the argument in full -- it is stated
#: once, on the side a reader is likelier to open first.
PUBLISHABLE_ALWAYS = frozenset(
    {
        "edition_code",
        "title",
        "abstract",
        "date",
        "time",
        "status",
        "name",
        "affiliation",
        "country",
        "zoom_link",
        "forum_thread",
    }
)

#: The person, as distinct from the fact that they spoke: their face, their
#: biography, the identities that tie this record to the rest of their online
#: presence, the sentences they drafted for a forum, and the recording of them
#: speaking. None of it is needed to announce a seminar, and every one of them
#: is a disclosure somebody could accept for one talk and refuse for the next.
#: So each waits on a recorded permission, asked in the affirmative.
PUBLISHABLE_ON_CONSENT = frozenset(
    {
        "photo_url",
        "bio",
        "linkedin",
        "links",
        "seed_questions",
        "youtube_url",
    }
)

#: Nothing here leaves the repository on any consent: a way to reach the
#: person (`email`), attributes collected for an aggregate (`gender`,
#: `career_stage`), the team's own working record of how a decision was
#: reached -- including `publication` itself, which this module reads and
#: never emits -- and `host_1`/`host_2` plus `checklist`, which are other
#: people: the second names one volunteer per line of the runbook. A speaker's
#: consent cannot answer for a volunteer, so a field naming one can never be
#: unlocked by this gate.
NEVER_PUBLISHED = frozenset(
    {
        "id",
        "gender",
        "career_stage",
        "email",
        "conflicts_of_interest",
        "source",
        "proposed_by",
        "assigned_to",
        "host_1",
        "host_2",
        "selection",
        "publication",
        "candidate_dates",
        "runbook_progress",
        "checklist",
        "metrics",
        "notes",
    }
)

#: Where each field of the public feed comes from in a speaker record.
#:
#: The two vocabularies differ on purpose: the feed calls the seminar's number
#: `id` and the speaker's name `speaker_name`, whilst the record calls them
#: `edition_code` and `name`. The classification above is expressed in the
#: record's vocabulary, because that is the one the model is exhaustive over
#: (`SPEAKER_FIELDS`); this mapping is the only place the two are reconciled,
#: so a published column always names the field it discloses.
#:
#: Not every publishable field is here, and that is not an oversight: the
#: three sets say what *may* leave, this mapping says what the feed actually
#: carries. `links` is a list where every other column is a string and no
#: consumer of the feed asks for it, so it is permitted and unpublished. The
#: asymmetry only ever runs this way -- a column can be absent from the feed
#: whilst permitted, never present whilst forbidden, because `PUBLIC_FIELDS`
#: is filtered through the classification below.
PUBLIC_FIELD_SOURCES = {
    "id": "edition_code",
    "title": "title",
    "date": "date",
    "status": "status",
    "abstract": "abstract",
    "photo_url": "photo_url",
    "bio": "bio",
    "linkedin": "linkedin",
    "seed_questions": "seed_questions",
    "youtube_url": "youtube_url",
    "registration_link": "zoom_link",
    "forum_thread": "forum_thread",
    "speaker_name": "name",
    "speaker_affiliation": "affiliation",
    "speaker_country": "country",
}

#: The allowlist, now derived rather than written.
#:
#: A column whose source field is classified `NEVER_PUBLISHED` is *dropped
#: here*, not reported: `to_public` projects its row through this set, so
#: adding a line to `PUBLIC_FIELD_SOURCES` for an internal field publishes
#: nothing. The contradictory state is made unbuildable rather than detected,
#: which is the same move the consent vocabulary itself makes.
PUBLIC_FIELDS = frozenset(
    name
    for name, source in PUBLIC_FIELD_SOURCES.items()
    if source in PUBLISHABLE_ALWAYS or source in PUBLISHABLE_ON_CONSENT
)


def recording_withheld(entry: dict[str, Any]) -> bool:
    """Whether this speaker's recording must not appear in the public feed.

    The takedown half of the second gate (G-10, G-15). The app decides
    whether a recording may be published in the first place
    (`app/src/state/governance.ts::canArchive`); this decides whether one
    already in the feed has to come out of it, which is the half an
    unattended job can reach. The two are different questions, so there is
    one implementation of each and nothing to pin in
    `tools/tests/fixtures/governance-cases.json` -- that fixture binds the
    field *classification*, which is written in both languages, not this
    predicate, which is written in one.

    A recording appears only when two things are recorded, and each is asked
    for in the affirmative:

    - the speaker's consent is `granted` (G-15). Not "did they refuse" but
      "did they agree": `pending`, `''` and any value nobody recognises are
      silence, and silence is never a permission. This is the only path on
      which anything leaves the repository, so it is the last place an
      absent answer may be read as a yes;
    - the publication gate opened: `publication.outcome == "published"`,
      written by the single transition `finalize-archive`, which refuses
      unless the board approved and its objection window has run
      (`app/src/state/governance.ts::canArchive`). `withheld`, `''` and an
      untouched record are all "the gate was never run".

    Either half turning back to silence is also a takedown, and so is one
    more thing: a standing objection, i.e. an entry in `objections` with no
    `resolved_on`. A missing key reads as standing, never as settled, so a
    hand-edited file errs towards leaving the talk offline.

    The programme fields -- name, affiliation, country, title, abstract,
    date -- are published for every speaker at a public status: agreeing to
    give a public webinar is agreeing to appear in its programme. The
    recording is the separate artefact the consent model exists for, and it
    is the only field *this* function governs; the rest of what a person
    agreed to is decided by `personal_disclosure_withheld`, on the same two
    affirmative questions.

    Requiring the gate's own verdict can only ever keep a link out of the
    feed, never put one in, and that is the direction this function is
    allowed to be wrong in: a recording whose clearance the file does not
    record stays offline until somebody records it. Whether any particular
    file has such recordings in it is not part of the argument -- a rule that
    had to be checked against today's data before it could be called safe
    would have to be re-checked after every commit.
    """
    return _gate_closed(entry)


def personal_disclosure_withheld(entry: dict[str, Any]) -> bool:
    """Whether this speaker's personal fields must stay out of the feed.

    The fields in `PUBLISHABLE_ON_CONSENT` other than the recording: a
    portrait, a biography, a LinkedIn handle and the other identities the
    record carries, and the questions the speaker wrote to open the forum
    discussion. Agreeing to give a public talk is not agreeing to any of
    them, so they travel on the same recorded permission the recording
    does, asked the same way round: did the speaker agree, and did the gate
    open. Silence -- `pending`, `''`, an unrecognised value, an untouched
    or unreadable block -- withholds, on every one of them.

    Deliberately the same gate as the recording, not a second, gentler one.
    The repository stores one answer per speaker; a rule that let a portrait
    out on a weaker condition would be reading a permission nobody gave.
    The visible consequence is that a portrait does not appear on an
    upcoming seminar, because `outcome: published` is only written when the
    talk is archived. That is a real cost and it is the right one: if
    portraits are wanted on announcements, the answer is to ask for that
    consent and record it, not to loosen this.

    Kept as its own function rather than folded into `recording_withheld`
    because they answer different questions about different artefacts, and
    the day one of them gains a condition the other must not inherit it.
    Today they agree, and share `_gate_closed` so they cannot drift on the
    part they do agree on.
    """
    return _gate_closed(entry)


def _gate_closed(entry: dict[str, Any]) -> bool:
    """The publication gate's verdict, read from a record.

    The two affirmative questions plus the standing-objection check,
    written once. Both callers above answer their own question with it; see
    `recording_withheld` for why each arm reads the way it does.
    """
    publication = entry.get("publication")
    if not isinstance(publication, dict):
        # An unreadable publication block is not a permission. `validate.py`
        # reports it; here it simply keeps the recording out.
        return True
    if publication.get("consent") != "granted":
        # Not "did they refuse" but "did they agree": `pending`, `''` and a
        # hand-written value nobody recognises are all silence.
        return True
    if publication.get("outcome") != "published":
        # Not "is it withheld" but "did the gate open": `withheld` and an
        # untouched record both land here.
        return True
    objections = publication.get("objections")
    if isinstance(objections, list):
        return any(isinstance(o, dict) and not o.get("resolved_on") for o in objections)
    return False


def to_public(speakers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in speakers:
        if not isinstance(entry, dict):
            continue
        status = entry.get("status", "")
        if status not in PUBLIC_STATUSES:
            continue
        # One decision, read once and applied to every field the
        # classification puts behind the gate, so they cannot come apart:
        # either this record carries the permission or every one of them is
        # empty.
        personal_ok = not personal_disclosure_withheld(entry)
        # The row is built *from* the classification rather than written out
        # and checked against it. A column whose source field is
        # `NEVER_PUBLISHED` never enters `PUBLIC_FIELDS` and so is not built
        # at all; a column whose source is `PUBLISHABLE_ON_CONSENT` is empty
        # unless the gate opened, whichever column it is. Moving a field
        # between the two publishable sets therefore changes what this
        # function emits -- which is what makes the classification a rule and
        # not a comment.
        row: dict[str, Any] = {}
        for column, source in PUBLIC_FIELD_SOURCES.items():
            if column not in PUBLIC_FIELDS:
                continue
            value = entry.get(source, "")
            if source in PUBLISHABLE_ON_CONSENT and not personal_ok:
                value = ""
            row[column] = value
        # Two columns carry a further condition that has nothing to do with
        # consent, and it is deliberately not expressed in the sets: a
        # recording is linked only at the status the gate itself writes, and
        # a joining link only whilst the seminar is still ahead.
        if "youtube_url" in row and (
            status not in RECORDING_STATUSES or recording_withheld(entry)
        ):
            row["youtube_url"] = ""
        if "registration_link" in row and status != "scheduled":
            row["registration_link"] = ""
        out.append(row)
    out.sort(key=lambda row: row.get("date", ""), reverse=True)
    return out
