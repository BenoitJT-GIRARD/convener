"""What this particular instance is, read from its own declaration.

Two things, one file, one reader per language. The address this project
is published at came first (phase 10, task 2) and the rest of its
identity followed (task 3): the name of the organisation running the
series, what the series is called, the forum it discusses on, and the
address a participant writes to about their own data. Both halves are
in `config/instance.json`, both are read here, and neither is written
down anywhere else.

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
    "IDENTITY_FIELDS",
    "IDENTITY_KEY",
    "INSTANCE_PATH",
    "PUBLISHED_URL_KEY",
    "Identity",
    "Published",
    "from_data",
    "identity_from_data",
    "load",
    "load_identity",
]

#: The instance's own declaration, relative to a repository root. In
#: `config/` rather than beside it, and stating its own `owner:` the way
#: every other file in that directory does -- see `boundary.py`.
INSTANCE_PATH: Final = Path("config") / "instance.json"

#: `config/instance.json`'s own format version.
DECLARATION_VERSION: Final = 1

#: The key the first half of this module is about.
PUBLISHED_URL_KEY: Final = "published_url"

#: The key the second half is about -- an object, not a string, because
#: its fields are read together or not at all: a template that names the
#: organisation almost always names the series in the next line.
IDENTITY_KEY: Final = "identity"

#: Every field `identity` has to carry, in the order `Identity` declares
#: them. Enumerated once, here, and used both to build the object and to
#: refuse a declaration that is missing one -- a duplicate that deletes a
#: key it thinks it does not need must be told so at the first command it
#: runs, not by a template rendering the word "None" into an e-mail.
IDENTITY_FIELDS: Final = (
    "organisation",
    "short_name",
    "series",
    "tagline",
    "forum",
    "contact",
    "proposal_form",
    "repository",
)


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

    @property
    def publish_repository(self) -> str:
        """`owner/repository` -- the repository the built site is pushed
        into, derived from the address it is served at.

        Not a second declaration, and deliberately not one. GitHub Pages
        serves a project repository at `https://<owner>.github.io/<repo>/`
        and at no other shape of address, so the published address *is*
        the push target written differently. Before this, the two
        publishing workflows cloned the target in hard text: changing
        `published_url` moved every address a visitor sees and left the
        push where it was, so a duplicate would have published its own
        site into the previous instance's repository -- worse than either
        half being wrong alone.

        Refuses rather than guessing when the host is not a `github.io`
        one. A custom domain says nothing whatever about which repository
        serves it, and there is no safe default for "push a whole site
        somewhere" (S-4). The owner is taken from the host as GitHub
        itself lower-cases it; a clone URL is case-insensitive on that
        segment, so nothing here has to know the organisation's own
        capitalisation.
        """
        suffix = ".github.io"
        host = self.host
        segments = [part for part in self.path_prefix.split("/") if part]
        if not host.endswith(suffix) or len(host) <= len(suffix) or len(segments) != 1:
            raise ValueError(
                f"{INSTANCE_PATH.as_posix()}: {self.url!r} is not a GitHub "
                "Pages project address "
                "(https://<owner>.github.io/<repository>/), so the repository "
                "the built site is pushed into cannot be derived from it -- "
                "and there is no safe guess for where to push a whole site"
            )
        return f"{host[: -len(suffix)]}/{segments[0]}"

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
    return from_data(_declaration(root))


@dataclass(frozen=True)
class Identity:
    """Who runs this series, and what it is called.

    Every field is prose an outside person reads: the name at the top of
    a public page, the sign-off of an e-mail to a speaker, the address a
    participant writes to about their own data. Frozen, and every field
    required -- see `IDENTITY_FIELDS` for why a missing one is refused
    rather than defaulted.

    `organisation` and `short_name` are both here on purpose. The
    templates use each where the other would read wrong: the full name
    where a stranger is being told who is writing, the short one where a
    correspondent already knows. Collapsing them into one key would have
    rewritten the wording of e-mails that go to real people, which is not
    a decision a refactor gets to take.
    """

    organisation: str
    short_name: str
    series: str
    tagline: str
    forum: str
    contact: str
    proposal_form: str
    repository: str

    @property
    def forum_host(self) -> str:
        """`www.example.org` -- the forum's address as prose names it,
        with no scheme. Templates print the bare host inside a sentence
        and link the whole address; deriving one from the other is what
        keeps a duplicate from having to write its forum down twice."""
        return urlsplit(self.forum).netloc

    @property
    def namespace(self) -> dict[str, str]:
        """The `{{ instance.* }}` vocabulary, exactly as both rendering
        engines resolve it -- `tools/convener_ops/announce.py::_render` here,
        `app/src/content/render.ts::substitute` on the other side of the
        language boundary. Composed here rather than in each caller so
        that adding a field is one edit and not four."""
        values = {name: getattr(self, name) for name in IDENTITY_FIELDS}
        values["forum_host"] = self.forum_host
        return values


def identity_from_data(data: Any) -> Identity:
    """Parse an already JSON-loaded `config/instance.json`.

    Refuses, rather than repairs, for the same reason `from_data` above
    does: what this half of the declaration carries goes out under an
    organisation's name, to people who did not choose to receive a
    placeholder. A missing field is named, with the file it belongs in --
    `«missing: instance.contact»` reaching a participant is the failure
    this refusal exists to prevent, and it would reach them silently.
    """
    named = INSTANCE_PATH.as_posix()
    if not isinstance(data, dict) or data.get("v") != DECLARATION_VERSION:
        raise ValueError(f"{named} is not a supported format version")
    raw = data.get(IDENTITY_KEY)
    if not isinstance(raw, dict):
        raise ValueError(
            f"{named}: {IDENTITY_KEY} must be an object naming the "
            f"organisation running this series, got {raw!r}"
        )
    values: dict[str, str] = {}
    for field in IDENTITY_FIELDS:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{named}: {IDENTITY_KEY}.{field} must be a non-empty string, "
                f"got {value!r} -- every field here is printed to somebody "
                "outside this project, so there is nothing safe to put in its "
                "place"
            )
        if value != value.strip():
            raise ValueError(
                f"{named}: {IDENTITY_KEY}.{field} has surrounding whitespace"
            )
        values[field] = value
    forum = urlsplit(values["forum"])
    if forum.scheme not in ("https", "http") or not forum.netloc:
        raise ValueError(
            f"{named}: {IDENTITY_KEY}.forum must be the forum's own address, "
            f"got {values['forum']!r} -- templates print its host inside a "
            "sentence and link the whole of it, so a bare name resolves to "
            "neither"
        )
    owner, _, name = values["repository"].partition("/")
    if not owner or not name or "/" in name:
        raise ValueError(
            f"{named}: {IDENTITY_KEY}.repository must be `owner/name`, got "
            f"{values['repository']!r}"
        )
    return Identity(**values)


def load_identity(root: Path | None = None) -> Identity:
    """This instance's identity as this repository declares it."""
    return identity_from_data(_declaration(root))


def _declaration(root: Path | None) -> Any:
    """`config/instance.json`, parsed. One reader for both halves: two
    would be two `json.loads` of one path in one language, which is the
    copy this whole design refuses wearing a smaller hat."""
    base = root if root is not None else repo_root()
    return json.loads((base / INSTANCE_PATH).read_text(encoding="utf-8"))
