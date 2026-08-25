"""The one address this project is published at, read from the instance.

Every public address this repository emits is a suffix of a single value:
the registration page a participant follows, the survey page an attendee
is invited to, the certificate-verification page a token is checked on,
the prefix every showcase template's `| url` filter resolves against, the
`base` every bundle's assets are addressed from, the domain a calendar
entry's UID is scoped to, and the origin the two relays answer CORS
preflights for. Before this module they were written out thirty times
across twelve files, bound to each other by tests that could only ever
say "these copies still agree" -- never "there is one".

**One declaration, one derivation, per side of the language boundary.**
`config/instance.json` holds the address; this module is Python's reader
of it, `app/scripts/published.mjs` is the application build's, and
`site/scripts/published.cjs` is the showcase's. That is D-14 applied
literally: a shared declaration read by each language, never three copies
somebody hopes stay in step. Three readers are not three copies -- none
of them holds the value, and a reader that disagreed would disagree about
*parsing*, which is the one kind of drift a single worked example catches
immediately.

**What is derived here and what is not.** The instance owns the root; the
product owns everything under it. `events/`, `survey/`, `verify/#/` and
`app/` are route shapes this repository decides and a duplicate inherits,
so they are spelled out at their call sites rather than configured -- a
duplicate that had to name its own `verify/` path would be configuring
the product, not its instance. The one exception is the `#/` after
`verify/`, which is not a route shape at all: the token it precedes
carries the holder's name, and a URL fragment is the only part of an
address a browser never sends to a server and always strips from
`Referer`. See `certificate.py`'s own module docstring.

**A value this module cannot read stops the process.** No default, no
substitution, no "probably localhost". This is the file that decides
what address goes out under an organisation's name onto a certificate
that is meant to stand forever; the failure mode of a wrong guess is a
dead public link, published, in a document nobody can recall.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from .paths import repo_root

__all__ = [
    "DECLARATION_VERSION",
    "INSTANCE_PATH",
    "PUBLISHED_URL_KEY",
    "Published",
    "from_data",
    "load",
]

#: The instance's own declaration, relative to a repository root. In
#: `config/` rather than beside it, and stating its own `owner:` the way
#: every other file in that directory does -- see `boundary.py`.
INSTANCE_PATH: Final = Path("config") / "instance.json"

#: `config/instance.json`'s own format version.
DECLARATION_VERSION: Final = 1

#: The key the whole of this module is about.
PUBLISHED_URL_KEY: Final = "published_url"


@dataclass(frozen=True)
class Published:
    """One published address, and the parts of it the code actually asks
    for.

    Frozen and computed, never a bag of independently-set fields: an
    `origin` that could be set apart from the `url` it came out of is a
    second copy with extra steps, which is the exact defect this module
    exists to end.
    """

    url: str

    @property
    def origin(self) -> str:
        """`https://host`, no path -- what a browser sends as `Origin`,
        and therefore what the relays compare against. Deliberately
        without the trailing slash: an origin is not a directory."""
        split = urlsplit(self.url)
        return f"{split.scheme}://{split.netloc}"

    @property
    def host(self) -> str:
        """`host`, no scheme -- the domain part alone. Used where a
        *name* is wanted rather than an address: the right-hand side of
        a calendar entry's UID (RFC 5545 asks for a globally unique
        identifier, conventionally scoped to a domain the producer
        controls)."""
        return urlsplit(self.url).netloc

    @property
    def path_prefix(self) -> str:
        """`/repository/` -- the one path segment GitHub Pages serves a
        project repository under, leading and trailing slash included.
        Eleventy's own `pathPrefix` takes exactly this shape, and D-26 is
        about exactly this segment being absent from a local check."""
        return urlsplit(self.url).path

    @property
    def app_base(self) -> str:
        """`/repository/app/` -- where the operators' cockpit and the
        three islands publish, and the `base` every one of their built
        asset URLs is resolved against. A path, not an absolute URL,
        because that is what Vite's own `base` option means."""
        return f"{self.path_prefix}app/"

    def under(self, path: str) -> str:
        """This address with `path` appended -- `path` relative to the
        published root, never root-relative.

        A root-relative argument is refused rather than normalised: `/x`
        against a prefixed deployment resolves to the *domain* root, one
        segment above where this project actually lives, which is the
        whole of the defect D-26 names. Silently accepting it here would
        put that defect back behind a helper that reads correct.
        """
        if path.startswith("/"):
            raise ValueError(
                f"{path!r} is root-relative, so it names an address one path "
                "segment above where this project is published (D-26); pass "
                "it relative to the published root instead"
            )
        return f"{self.url}{path}"


def from_data(data: Any) -> Published:
    """Parse an already JSON-loaded `config/instance.json`.

    Refuses, rather than repairs. Each clause below is a shape that would
    otherwise produce an address which looks plausible and is wrong: a
    missing trailing slash silently swallows a path segment when the
    caller concatenates, a bare origin with no path publishes at a domain
    root this project does not own, and `http` publishes a certificate
    verification link over a transport that can be rewritten in flight.
    """
    named = INSTANCE_PATH.as_posix()
    if not isinstance(data, dict) or data.get("v") != DECLARATION_VERSION:
        raise ValueError(f"{named} is not a supported format version")
    raw = data.get(PUBLISHED_URL_KEY)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            f"{named}: {PUBLISHED_URL_KEY} must be the address this project "
            f"is published at, got {raw!r}"
        )
    if raw != raw.strip():
        raise ValueError(f"{named}: {PUBLISHED_URL_KEY} has surrounding whitespace")
    split = urlsplit(raw)
    if split.scheme != "https":
        raise ValueError(
            f"{named}: {PUBLISHED_URL_KEY} must be an https address, got {raw!r} "
            "-- a certificate verification link is meant to stand for years"
        )
    if not split.netloc:
        raise ValueError(f"{named}: {PUBLISHED_URL_KEY} names no host: {raw!r}")
    if split.query or split.fragment:
        raise ValueError(
            f"{named}: {PUBLISHED_URL_KEY} carries a query or a fragment "
            f"({raw!r}) -- it is the root every other address is built on, "
            "and nothing can be appended after either of those"
        )
    if not split.path.startswith("/") or not split.path.endswith("/"):
        raise ValueError(
            f"{named}: {PUBLISHED_URL_KEY} must end in '/' and start its path "
            f"with '/', got {raw!r} -- every address derived from it is built "
            "by appending, so a missing slash quietly eats a path segment"
        )
    return Published(url=raw)


def load(root: Path | None = None) -> Published:
    """The published address as this repository declares it."""
    base = root if root is not None else repo_root()
    text = (base / INSTANCE_PATH).read_text(encoding="utf-8")
    return from_data(json.loads(text))
