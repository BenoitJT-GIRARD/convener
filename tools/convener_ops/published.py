"""What this particular instance is, read from its own declaration.

Three things, one file, one reader per language. The address this project
is published at came first (phase 10, task 2) and the rest of its
identity followed (task 3): the name of the organisation running the
series, what the series is called, the forum it discusses on, and the
address a participant writes to about their own data. Phase 11 task 4
added the third, the prefix its editions are numbered under. All three
are in `config/instance.json`, all three are read here, and none of them
is written down anywhere else.

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
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from .paths import repo_root

__all__ = [
    "DECLARATION_VERSION",
    "DEGRADABLE_FIELDS",
    "EDITION_PREFIX_KEY",
    "EDITION_PREFIX_MAX_LENGTH",
    "EDITION_PREFIX_RE",
    "EXAMPLE_INSTANCE_PATH",
    "EXAMPLE_INSTANCE_ROOT",
    "IDENTITY_FIELDS",
    "IDENTITY_KEY",
    "INSTANCE_PATH",
    "PLACEHOLDER_MARKER",
    "PUBLISHED_URL_KEY",
    "EditionPrefix",
    "Identity",
    "Published",
    "declared_values",
    "edition_prefix_from_data",
    "from_data",
    "identity_from_data",
    "is_placeholder",
    "load",
    "load_edition_prefix",
    "load_identity",
    "unconfigured",
    "unconfigured_from_data",
]

#: The instance's own declaration, relative to a repository root. In
#: `config/` rather than beside it, and stating its own `owner:` the way
#: every other file in that directory does -- see `boundary.py`.
INSTANCE_PATH: Final = Path("config") / "instance.json"

#: The declaration the *product* ships, as its own worked example --
#: `instances/example/`'s copy of the file above, at the same relative
#: path the boundary gives it. Product-owned: upstream ships it, upstream
#: maintains it, and `test_second_instance.py` already lays it into this
#: repository's own hole on every run.
#:
#: Read here for one purpose: telling an instance that has been configured
#: from one that is still publishing the template's identity. See
#: `unconfigured` below for what that comparison is and is not.
EXAMPLE_INSTANCE_PATH: Final = Path("instances") / "example" / INSTANCE_PATH

#: The example instance's own root -- the tree the declaration above and
#: `instances/example/data/brand.json` both sit under, at the same
#: relative paths a real instance uses. Derived from the path above
#: rather than spelled a second time: one of them moving has to move
#: the other.
#:
#: Anything that has to render *as* the example -- rather than merely
#: read one of its files -- takes this as its `root`. Phase 12 task 1
#: is why it exists: `cli.render_visual_fixtures` renders the poster
#: the committed reference images pin, and rendering it from this
#: repository's own root made those images a frozen photograph of one
#: real instance's charter, in a product-side directory.
EXAMPLE_INSTANCE_ROOT: Final = EXAMPLE_INSTANCE_PATH.parent.parent

#: `config/instance.json`'s own format version.
DECLARATION_VERSION: Final = 1

#: The key the first half of this module is about.
PUBLISHED_URL_KEY: Final = "published_url"

#: The key the second half is about -- an object, not a string, because
#: its fields are read together or not at all: a template that names the
#: organisation almost always names the series in the next line.
IDENTITY_KEY: Final = "identity"

#: The key the third part is about: the prefix this instance numbers its
#: editions under -- an abbreviation of the series' own name, declared
#: by the instance and by nothing in the product.
#:
#: **Its own key, beside `identity` rather than inside it.** Everything
#: under `identity` is prose, checked the one uniform way prose can be
#: checked -- a non-empty string, no surrounding whitespace, no
#: placeholder -- and rendered wherever a template asks for it. A prefix
#: is not prose: it is a token with a grammar, fixed by the three places
#: it ends up in, and the shape it may take is the whole of what this
#: declaration has to say about it. `published_url` is the precedent, not
#: `organisation`: one declared string, refused unless it is the right
#: shape, with several derived forms taken off it (`origin`, `host`,
#: `path_prefix`, `app_base`) rather than declared a second time.
#:
#: **And not derived from `short_name` either.** The two must be free to
#: differ: a series can want one abbreviation in an e-mail subject and
#: another in an identifier, and deriving one from the other ties two decisions
#: that have no reason to move together. Worse, `short_name` is prose and
#: prose gets reworded -- and this value cannot be reworded, see
#: `EditionPrefix` below for the three places that make it permanent.
EDITION_PREFIX_KEY: Final = "edition_prefix"

#: How long a declared prefix may be. Nothing downstream breaks at nine:
#: `eventkeys._EVENT_ID_MAX_LENGTH` and the signup relay's own
#: `EVENT_ID_RE` both stop at 64 characters, and `formats.
#: qr_module_size_mm` still clears `formats.SCANNABLE_QR_MODULE_MM` at
#: that full length (measured, not assumed: 0.456mm against a 0.4mm
#: floor). This is a data-contract choice with room to spare, exactly as
#: `EditionPrefix.pattern`'s own four digits are -- an *abbreviation* is
#: what goes in front of an edition number, and a prefix long enough to be
#: a sentence is a sign the wrong value was declared, which is cheaper to
#: say here than to discover in a published address.
EDITION_PREFIX_MAX_LENGTH: Final = 8

#: What a declared prefix may be made of: ASCII capitals and digits,
#: starting with a capital. Each restriction is one of the three places
#: the prefix ends up, refused here rather than where it lands.
#:
#: * **Upper case, and ASCII.** An edition code is stored upper-cased and
#:   an event id *is* that code lower-cased (D-19), so the pair only
#:   round-trips while the declaration fixes the case. Allowing `Vw`
#:   would make `Vw-1` and `MRG-1` two codes with one URL, one
#:   `keys/events/mrg-1.pub` and one `CONVENER_EVENT_KEY_MRG_1`; allowing a
#:   non-ASCII capital would make `str.lower()` a place where a URL path
#:   segment quietly acquires a percent-encoding.
#: * **No `-`, `.` or `_` inside it.** The product puts exactly one `-`
#:   between the prefix and the number. `eventkeys.secret_name` folds `.`
#:   and `-` to `_` before uppercasing, and says itself that the fold is
#:   lossy: a prefix carrying a second separator would make `A-B-1` and
#:   `A.B.1` the same repository secret, and the operator would find out
#:   when a certificate failed to verify.
#: * **A letter first.** `commit_format._TOKEN`, which `eventkeys` reuses
#:   as its event-id shape, already requires an alphanumeric first
#:   character; requiring a letter is what keeps `<prefix>-<n>` readable
#:   as a code rather than as a range of numbers.
EDITION_PREFIX_RE: Final = re.compile(
    rf"^[A-Z][A-Z0-9]{{0,{EDITION_PREFIX_MAX_LENGTH - 1}}}$"
)

#: Every field `identity` has to carry, in the order `Identity` declares
#: them. Enumerated once, here, and used both to build the object and to
#: refuse a declaration that is missing one -- a duplicate that deletes a
#: key it thinks it does not need must be told so at the first command it
#: runs, not by a template rendering the word "None" into an e-mail.
IDENTITY_FIELDS: Final = (
    "organisation",
    "short_name",
    "series",
    "strapline",
    "tagline",
    "forum",
    "contact",
    "proposal_form",
    "repository",
)

#: What this repository writes into a declared value nobody has filled in
#: yet. Not invented here: `services/*/wrangler.toml` ships
#: `REPLACE_WITH_KV_NAMESPACE_ID`, and `deploy-form-relay.yml` and
#: `deploy-signup-relay.yml` already grep for exactly this token before
#: deciding an integration is configured. A placeholder is not a value; it
#: is the absence of one, spelled so a human can see it -- and the whole
#: point of naming it here is that until now only a human could.
PLACEHOLDER_MARKER: Final = "REPLACE"

#: The identity fields the product can publish *without*, and therefore
#: the only ones allowed to still carry a placeholder.
#:
#: `proposal_form` is one because the showcase has somewhere else to send
#: a visitor -- `contact`, which the same page already prints -- so an
#: unfilled form degrades visibly (D-13: an unconfigured integration is a
#: normal state that degrades, not a failure) instead of stopping every
#: command a duplicate runs. Every other field is prose with no substitute
#: at all: there is nothing to render in place of an organisation's name,
#: so a placeholder there is refused exactly as a missing key is.
#:
#: Found by phase 10's own bilan (section 7.2): this instance has shipped
#: `proposal_form: https://forms.example.test/propose` since before the
#: declaration existed, and the showcase published it as the one call to
#: action on `/propose/` -- a link that resolves to nothing, on a public
#: page, with no check anywhere able to see it.
DEGRADABLE_FIELDS: Final = ("proposal_form",)


def is_placeholder(value: str) -> bool:
    """Whether a declared value is still the placeholder that stands in
    for one. Mirrored on the other side of the language boundary by
    `site/scripts/published.cjs`, and the two are held together by
    `tools/tests/test_published.py::test_the_showcase_feeds_its_templates_
    the_declared_identity`, which compares what that build hands its
    templates against what this reader derives."""
    return PLACEHOLDER_MARKER in value


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

    `strapline` and `tagline` are two on purpose for the same reason, and
    the distinction is a typographic one rather than a shade of meaning.
    `tagline` is a sentence, with a full stop: the showcase's masthead
    and feed description print it, and so does the flyer's own sub-line
    (`brand_templates.py`). `strapline` is a display line -- two or three
    words, set in heavy capitals across the poster's own hero band above
    the talk's title (`visual.py::_series_html`). Setting a sentence
    there wraps to three lines at 4vw and pushes the composition into the
    ribbon, which is the failure D-08 already names; setting a strapline
    in the feed's `<description>` says nothing a reader can act on. The
    example instance's two -- `instances/example/config/instance.json` --
    are a two-word display line and a full sentence, and neither
    substitutes for the other. Until phase 11 the strapline was typed
    into `visual.py` with no key at all, which is why a second
    instance's poster carried the first instance's motto.
    """

    organisation: str
    short_name: str
    series: str
    strapline: str
    tagline: str
    forum: str
    contact: str
    proposal_form: str
    repository: str

    @property
    def proposal_form_url(self) -> str:
        """The proposal form's address, or the empty string while the
        declaration still carries a placeholder in place of one.

        The showcase links this rather than `proposal_form` itself, so a
        duplicate that has not built its form yet -- and this instance,
        which had not -- publishes a page that says so instead of a button
        that resolves to nothing. `proposal_form` stays the declared value
        and stays a needle of the second-instance sweep; this is the one
        derivation that decides whether a reader is ever shown it."""
        return "" if is_placeholder(self.proposal_form) else self.proposal_form

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
        if is_placeholder(value) and field not in DEGRADABLE_FIELDS:
            raise ValueError(
                f"{named}: {IDENTITY_KEY}.{field} is still a placeholder "
                f"({value!r}) -- {PLACEHOLDER_MARKER} is how this repository "
                "writes a value nobody has filled in, and there is nothing to "
                "print in place of this one, so it is refused here rather "
                f"than published. See {DEGRADABLE_FIELDS} for the fields that "
                "have a fallback and degrade instead"
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


@dataclass(frozen=True)
class EditionPrefix:
    """The prefix this instance numbers its editions under, and the forms
    the rest of the repository actually uses.

    **Declared once and then permanent.** An edition code is not a label
    that can be reworded later; it is a primary key that has already left
    the building by the time anybody could want to change it:

    * it is **in a published URL** -- `site/src/event.njk`'s permalink is
      `/events/<event id>/`, and an event id is the edition code
      lower-cased (D-19), so `MRG-05` is `/events/mrg-05/` for as long as
      the address exists;
    * it is **on an issued certificate** -- `certificate.py` binds the
      event id into the token a holder is given and into the verification
      link printed beside it, and a certificate is meant to stand for
      years;
    * it is **in a key filename** -- `keys/events/<event id>.pub`, and in
      the `CONVENER_EVENT_KEY_<ID>` repository secret `eventkeys.secret_name`
      derives from the same id.

    So a duplicate declares its own before its first edition, and after
    that the declaration and the editions already assigned hold each
    other in place: `validate.validate_speakers` builds its pattern from
    this value, so moving the value makes every code already written fail
    by name, and it says why rather than only that. That is the freeze --
    not a second mechanism beside the derivation, the derivation itself
    read from the other end.

    Frozen and computed for the reason `Published` is: a `code_prefix`
    that could be set apart from the `value` it comes from would be a
    second copy with extra steps.
    """

    value: str

    @property
    def code_prefix(self) -> str:
        """`MRG-` -- what an edition code starts with, separator included.
        The `-` belongs to the product, not to the declaration: it is what
        makes the number legible, and an instance that could choose it
        could choose one `eventkeys.secret_name` folds."""
        return f"{self.value}-"

    @property
    def event_prefix(self) -> str:
        """`mrg-` -- what an event id starts with, which is the code
        prefix lower-cased (D-19). The form that reaches a URL, a key
        filename and a certificate's verification link."""
        return self.code_prefix.lower()

    @property
    def pattern(self) -> re.Pattern[str]:
        """The whole shape of an edition code under this prefix: the
        prefix, a hyphen, and one to four digits.

        Four digits is `validate.py`'s own long-standing bound and stays
        there in spirit: "MRG-9999" is centuries of headroom at a handful
        of editions a year, and an unbounded id is one more thing that
        can only be found out by printing it."""
        return re.compile(rf"^{re.escape(self.value)}-\d{{1,4}}$")

    def describes(self, code: str) -> bool:
        """Whether `code` is an edition code of *this* instance."""
        return self.pattern.match(code) is not None


def edition_prefix_from_data(data: Any) -> EditionPrefix:
    """Parse an already JSON-loaded `config/instance.json`.

    Refuses, rather than repairs, and refuses **at declaration** rather
    than where the value lands. Every shape below is one that reads
    perfectly well as a string and then fails somewhere a person cannot
    see: a lower-case prefix breaks the round trip between an edition code
    and its event id, a prefix carrying its own separator collides two
    editions on one repository secret, and a prefix that is not a prefix
    at all -- a whole series title, say -- is only visible as a mistake
    once it is in an address somebody has published.
    """
    named = INSTANCE_PATH.as_posix()
    if not isinstance(data, dict) or data.get("v") != DECLARATION_VERSION:
        raise ValueError(f"{named} is not a supported format version")
    raw = data.get(EDITION_PREFIX_KEY)
    if not isinstance(raw, str) or not raw:
        raise ValueError(
            f"{named}: {EDITION_PREFIX_KEY} must be the prefix this instance "
            f"numbers its editions under, got {raw!r} -- it is the first half "
            "of every edition code, of every event page's address and of "
            "every certificate issued under it, and there is nothing to "
            "number an edition with in its absence"
        )
    if EDITION_PREFIX_RE.match(raw):
        return EditionPrefix(value=raw)
    if raw != raw.strip():
        wrong = "has surrounding whitespace"
    elif raw != raw.upper():
        wrong = (
            "is not upper case -- an event id is the edition code "
            "lower-cased (D-19), so the two only stay one identifier while "
            f"the case is fixed here; write {raw.upper()!r}"
        )
    elif not raw[0].isascii() or not raw[0].isalpha():
        wrong = (
            "does not start with an ASCII letter -- an edition code is read "
            "aloud, typed off a printed certificate and resolved as a URL "
            "path segment"
        )
    elif len(raw) > EDITION_PREFIX_MAX_LENGTH:
        wrong = (
            f"is longer than {EDITION_PREFIX_MAX_LENGTH} characters -- what "
            "goes in front of an edition number is an abbreviation, not a "
            "name"
        )
    else:
        wrong = (
            "carries something other than ASCII capitals and digits -- the "
            "product puts the one `-` an edition code has between this and "
            "the number, and `eventkeys.secret_name` folds any further `.` "
            "or `-` into `_`, which would give two editions one repository "
            "secret"
        )
    raise ValueError(f"{named}: {EDITION_PREFIX_KEY} {wrong}, got {raw!r}")


def load_edition_prefix(root: Path | None = None) -> EditionPrefix:
    """The edition prefix as this repository declares it."""
    return edition_prefix_from_data(_declaration(root))


def declared_values(data: Any) -> dict[str, str]:
    """Every value one declaration carries about *who* is publishing,
    under the name the declaration itself gives it.

    Eleven: the address, the edition prefix, and the nine fields of
    `identity`. Read raw rather than through `from_data`,
    `identity_from_data` and `edition_prefix_from_data`, and that is the
    one place in this module where raw is right -- the question this feeds
    is "is this still somebody else's value", which is a question about
    the text somebody typed, and it has to stay answerable for a
    declaration those three would refuse. A non-string is simply not a
    value anybody typed, so it is left out rather than coerced.

    The names are the declaration's own, dotted where the declaration
    nests (`identity.organisation`), because they are printed to a person
    who then has to go and edit that key.
    """
    values: dict[str, str] = {}
    if not isinstance(data, dict):
        return values
    for key in (PUBLISHED_URL_KEY, EDITION_PREFIX_KEY):
        value = data.get(key)
        if isinstance(value, str) and value:
            values[key] = value
    raw = data.get(IDENTITY_KEY)
    if isinstance(raw, dict):
        for field in IDENTITY_FIELDS:
            value = raw.get(field)
            if isinstance(value, str) and value:
                values[f"{IDENTITY_KEY}.{field}"] = value
    return values


def unconfigured_from_data(data: Any, example: Any) -> tuple[str, ...]:
    """Which of `data`'s declared values are still `example`'s.

    Sorted, and named rather than counted: a banner that says "this
    instance is not configured" and cannot say *what* is not configured
    sends its reader looking through a file; one that names
    `identity.contact` sends them to a line.
    """
    ours = declared_values(data)
    theirs = declared_values(example)
    return tuple(
        sorted(name for name, value in ours.items() if theirs.get(name) == value)
    )


def unconfigured(root: Path | None = None) -> tuple[str, ...]:
    """Which declared values this instance has not made its own.

    **What "not configured" means here, mechanically.** A duplicate is
    unconfigured exactly while its declaration still carries a value the
    product ships in `instances/example/config/instance.json` -- the
    invented instance this repository already builds itself as on every
    run of `tools/tests/test_second_instance.py`. Every value in that file
    is unmistakably synthetic and reserved: `.test` is RFC 2606's, no
    registry will ever delegate it, `example-instance.github.io` is a name
    nobody is asked to register, and "The Example Collective" is nobody.
    So a match is never a coincidence, and this cannot fire on an instance
    that has been configured.

    **Value by value, not file against file.** The dangerous state is the
    half-done one: a duplicate that renames the organisation and forgets
    the address publishes at somebody else's prefix while every page reads
    as its own. Comparing the two declarations whole would call that
    configured.

    **Not the placeholder marker, and that is a decision.** `REPLACE` is
    how this repository writes a value nobody has filled in, and it is
    already handled -- twice, in opposite directions, both of them right.
    In the eight identity fields there is nothing to print instead, so
    `identity_from_data` refuses the declaration outright and no build
    exists to carry a banner. In `proposal_form`, the one field with a
    fallback, D-13 makes the absence an ordinary state that degrades at
    the point of use: `/propose/` offers the contact address instead of a
    dead link, and it says so on the page where it matters. A banner
    across every page of a working site because one optional form is not
    open yet is a banner somebody deletes within the week, and it would
    take the real warning with it. So the marker decides nothing here.

    **The charter is not in this set either.** `data/brand.json` is the
    instance's too, and a duplicate that keeps the example's palette has
    kept a palette -- it has not published somebody else's name, address
    or contact, which is the whole of what this warns about.

    Raises rather than reporting "configured" when the example cannot be
    read: with nothing to compare against, nothing can be *proved* about
    this declaration, and a check that answers "fine" when it could not
    run is D-25's own definition of not being a check. The application's
    build already depends on that directory outright
    (`app/scripts/example-instance.mjs`, which throws for the same reason),
    so this adds no failure a duplicate did not already have.
    """
    base = root if root is not None else repo_root()
    example_path = base / EXAMPLE_INSTANCE_PATH
    try:
        example = json.loads(example_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(
            f"{EXAMPLE_INSTANCE_PATH.as_posix()} cannot be read ({error}), so "
            "there is nothing to tell this instance's declaration apart from "
            "the example the product ships -- restore it rather than publish a "
            "page that cannot say whether it is configured"
        ) from error
    return unconfigured_from_data(_declaration(root), example)


def _declaration(root: Path | None) -> Any:
    """`config/instance.json`, parsed. One reader for both halves: two
    would be two `json.loads` of one path in one language, which is the
    copy this whole design refuses wearing a smaller hat."""
    base = root if root is not None else repo_root()
    return json.loads((base / INSTANCE_PATH).read_text(encoding="utf-8"))
