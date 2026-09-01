"""A deliberately independent RFC 5545 reader, for testing an iCalendar
feed the way a real client would -- unfolding, parsing and unescaping from
scratch -- rather than by calling back into `convener_ops.publication.agenda`'s or
`site/.eleventy.js`'s own escape/fold functions.

The point of this module existing at all is that a test built from the same
escape/fold code the generator uses cannot catch the generator's own
mistake about what the RFC requires: both sides would share it. Everything
below is written straight from RFC 5545 §3.1 (content lines and line
folding) and §3.3.11 (the TEXT value type's escaping), independently of
`tools/convener_ops/publication/agenda.py` and `site/.eleventy.js`.

Deliberately not a general-purpose iCalendar library: it reads exactly the
shape of file this project's own two generators produce (`BEGIN:VEVENT`
blocks inside one `BEGIN:VCALENDAR`, no nested components, no quoted
parameter values, no `\\N` versus `\\n` case games beyond what §3.3.11
already allows for either), and raises loudly on anything that surprises
it rather than silently accepting a malformed file the way a lenient real
client might.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Property names whose value type is TEXT (RFC 5545 §3.8.1) and so must be
#: unescaped -- everything else this project's two feeds write (UID,
#: DTSTAMP, DTSTART, DTEND, URL, VERSION, PRODID, CALSCALE) is a DATE-TIME,
#: DATE, URI or plain token, none of which uses backslash escaping at all.
_TEXT_PROPERTIES = frozenset({"SUMMARY", "DESCRIPTION", "LOCATION", "X-WR-CALNAME"})

#: RFC 5545 §3.1: a content line must not exceed this many octets.
_FOLD_LIMIT = 75


def unescape_text(value: str) -> str:
    """The inverse of RFC 5545 §3.3.11 TEXT escaping, read one character at
    a time rather than by chained `.replace()` calls -- a sequential
    global replace can misread an escape sequence that sits next to
    another one, which a real parser (reading left to right, one token at
    a time) cannot do. An unrecognised escape (`\\x`) passes `x` through
    unchanged, the RFC's own lenient fallback.
    """
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt == "\\":
                out.append("\\")
            elif nxt == ";":
                out.append(";")
            elif nxt == ",":
                out.append(",")
            elif nxt in ("n", "N"):
                out.append("\n")
            else:
                out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


@dataclass
class Component:
    """One `BEGIN:...`/`END:...` block: bare property names (params
    stripped) mapped to their value, TEXT properties already unescaped, and
    a parallel map of whatever parameter string followed the first `;` (for
    example `VALUE=DATE`), keyed the same way -- `''` when a property
    carried none.
    """

    properties: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedCalendar:
    calendar: Component
    events: list[Component]


def parse_calendar(raw: bytes) -> ParsedCalendar:
    """Parse a complete `.ics` file's raw bytes into its calendar-level
    properties and its `VEVENT` components, unfolding continuation lines
    and unescaping TEXT values as it goes.

    Raises `AssertionError` -- deliberately, not a quieter return -- on
    anything this project's own feeds must never produce: a bare line feed
    not preceded by a carriage return (CRLF discipline), or a physical line
    longer than the 75 octets RFC 5545 §3.1 allows. A test that wants to
    prove one of those defects is caught calls this function and expects
    exactly this exception.
    """
    for i, byte in enumerate(raw):
        if byte == 0x0A and (i == 0 or raw[i - 1] != 0x0D):
            raise AssertionError(f"bare LF (not preceded by CR) at byte offset {i}")

    text = raw.decode("utf-8")
    physical = text.split("\r\n")
    for line in physical:
        octets = len(line.encode("utf-8"))
        if octets > _FOLD_LIMIT:
            raise AssertionError(
                f"physical line is {octets} octets, over the {_FOLD_LIMIT}-octet "
                f"fold limit: {line!r}"
            )

    logical: list[str] = []
    for line in physical:
        if line == "":
            continue
        if line[0] in (" ", "\t") and logical:
            logical[-1] += line[1:]
        else:
            logical.append(line)

    calendar = Component()
    events: list[Component] = []
    stack: list[Component] = [calendar]
    for line in logical:
        name_part, sep, value = line.partition(":")
        if not sep:
            raise AssertionError(f"content line has no ':' at all: {line!r}")
        bare_name, _, params = name_part.partition(";")
        bare_name = bare_name.upper()

        if bare_name == "BEGIN":
            if value == "VEVENT":
                stack.append(Component())
            continue
        if bare_name == "END":
            if value == "VEVENT":
                finished = stack.pop()
                events.append(finished)
            continue

        target = stack[-1]
        target.properties[bare_name] = (
            unescape_text(value) if bare_name in _TEXT_PROPERTIES else value
        )
        target.params[bare_name] = params

    return ParsedCalendar(calendar=calendar, events=events)
