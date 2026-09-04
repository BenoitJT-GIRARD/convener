"""The hosted demonstration: this product, built as the instance it ships.

A visitor is owed a link, not an instruction. Until this existed the answer
to *what does it look like?* was "clone it, install two toolchains and run
it yourself", which is an answer almost nobody takes -- and the one thing
this product has to argue is what it runs.

What it builds
--------------
Exactly the tree the two publishing workflows push, for the example
instance rather than for a series somebody runs:

    <prefix>/            the showcase
    <prefix>/events/<id>/  one page per edition, with the registration form
    <prefix>/verify/     certificate verification
    <prefix>/survey/<id>/  the post-event survey
    <prefix>/app/        the cockpit, which opens on `?demo=1`

Nothing here is a demonstration-only artefact. `second_instance_build`
lays `examples/the-example-collective/` into a scratch copy of this
repository and runs the product's own publishing commands and both
bundlers; this module adds two things to that, and only two.

**One: the address.** The build reads its own prefix from `published_url`,
and the example declares `https://example-instance.github.io/example-showcase/`
-- an address nothing resolves, on purpose, so that the derivation
`Published.publish_repository` performs is exercised by an instance that
is not this one. A demonstration served under it would have every internal
link one path segment away from where it is actually published, which is
D-26's own defect. So the *demonstration build* overrides the address, and
the example's declaration is left exactly as it is: it has to stay an
invented, neutral instance, and this is a property of one build.

**Two: the flag.** `CONVENER_DEMO=1`, which
`site/scripts/demonstration.cjs` reads. It puts `?demo=1` on the two links
into the cockpit, so a visitor following one lands in the demonstration
rather than on a sign-in screen, and it prints a band on every page saying
whose records these are. It may not change a page or move a link, and
`tools/tests/repository/test_navigation.py` is what holds that.

What it cannot do here
----------------------
Publish. Hosting needs a repository on GitHub with Pages turned on, and
that is the maintainer's act.
`.github/workflows/demonstration.yml` is written and runs this; going live
is turning that repository's Pages source to *GitHub Actions* and letting
the workflow run.

**And one thing generated, because two of the five surfaces are otherwise
not shown at all.** An instance that has published an event page has
published that event's public key with it, and the registration form and
the survey both refuse to render without one -- correctly (D-13), and the
demonstration would then be demonstrating two "not available" notices. So
a throw-away key pair is generated per edition and only the public half is
ever written, which is the same act `.github/workflows/a11y.yml` already
performs for the same reason and with the same argument: the private half
is returned in memory and discarded with the process, and this build
pushes nothing anywhere. Nothing is signed with it and nothing can be
decrypted with it, which is exactly the state a visitor filling in the
form is in -- their browser encrypts under a key whose private half has
never existed on disk, and the demonstration has no relay to send it to.

What the demonstration honestly does not have
---------------------------------------------
A repository, a signing key and a register of certificates. The cockpit in
demonstration mode makes no network call at all -- `app/src/net/request.ts`
refuses every request that is not a read from the origin that served the
page -- so nothing here can write anywhere, and the verifier answers
*this certificate is not in the register* to whatever it is given, which
is the same answer an instance that has issued none gives. Nothing is
staged to make it look otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import second_instance_build

#: The one environment variable that turns the showcase's own
#: demonstration mode on. `site/scripts/demonstration.cjs` is the other
#: reader of it, in the language the showcase's build speaks;
#: `tools/tests/repository/test_navigation.py` reads the name out of that
#: file and refuses this one if the two ever disagree -- a build that set
#: a variable nothing read would publish a demonstration with no band on
#: it and a sign-in screen behind every link into the cockpit.
DEMO_ENV: Final = "CONVENER_DEMO"

#: The example instance's own declaration, in the built tree's terms --
#: the file `second_instance_build.lay_out` puts where an instance's own
#: declaration goes.
DECLARATION: Final = Path("instance") / "config.json"

#: Where the cockpit is published, relative to the showcase's root. The
#: product's own topology, not an instance's: `app/vite.config.ts` builds
#: to this base and both publishing workflows push to it.
COCKPIT: Final = "app"

#: What the showcase publishes about its own editions, in the built tree's
#: terms -- the file the key generator below reads its event ids from,
#: rather than reading the store a second time.
PUBLIC_EVENTS: Final = Path("instance") / "public-data" / "events-public.json"

#: Where an event's published public key goes. `app/scripts/copy-event-keys.mjs`
#: copies this directory into the cockpit's own build, which is where both
#: islands fetch a key from.
EVENT_KEYS: Final = Path("instance") / "keys" / "events"


def generate_event_keys(root: Path) -> list[str]:
    """A throw-away key pair per published edition, public half only.

    See the module docstring for why this exists and why it is honest.
    The import is here rather than at the top of the file so that
    `--help` and the argument checking run on a machine that has not
    installed the cryptography package.
    """
    from convener_ops.journey import eventkeys

    published = json.loads((root / PUBLIC_EVENTS).read_text(encoding="utf-8"))
    directory = root / EVENT_KEYS
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for event in published:
        event_id = str(event["id"]).lower()
        _private, public_pem = eventkeys.generate()
        (directory / f"{event_id}.pub").write_text(public_pem, encoding="utf-8")
        written.append(event_id)
    return written


def override_address(root: Path, url: str) -> None:
    """Point the built tree at the address this demonstration is served
    at, without touching what the example declares.

    A rewrite of the scratch tree's own copy, which is where every one of
    the three readers looks (`published.py`, `published.mjs`,
    `published.cjs`), so the showcase's path prefix, the cockpit's four
    bases and every absolute address the build composes all move together
    -- which is the whole of why the address is declared once.
    """
    declaration = root / DECLARATION
    data = json.loads(declaration.read_text(encoding="utf-8"))
    data["published_url"] = url
    declaration.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def assemble(root: Path, into: Path, prefix: str) -> None:
    """The published tree, laid out the way GitHub Pages serves it.

    The showcase at the declared prefix and the cockpit one level under
    it, which is what `deploy.yml` and `publish-showcase.yml` push into
    one repository root between them.
    `tools/visuals/render-readme-shots.mjs::assemble` stages the identical
    shape for the same reason: a build served at a bare root looks right
    and is not the shape anybody visits (D-26).
    """
    if into.exists():
        shutil.rmtree(into)
    served = into.joinpath(*[part for part in prefix.split("/") if part])
    served.mkdir(parents=True)
    shutil.copytree(root / "site" / "_site", served, dirs_exist_ok=True)
    shutil.copytree(root / "app" / "dist", served / COCKPIT, dirs_exist_ok=True)


def build(url: str, into: Path) -> Path:
    """Build the demonstration into `into`. Returns the directory a server
    has to answer the declared prefix with -- which is what a host already
    serving under that prefix (GitHub Pages, for a project repository)
    takes as its root."""
    prefix = urlsplit(url).path
    os.environ[DEMO_ENV] = "1"
    scratch = Path(tempfile.mkdtemp(prefix="convener-demonstration-")) / "repository"
    scratch.mkdir()
    links: list[Path] = []
    try:
        second_instance_build.lay_out(scratch)
        override_address(scratch, url)
        links = second_instance_build.link_node_modules(scratch, ("app", "site"))
        second_instance_build.publish(scratch)
        keys = generate_event_keys(scratch)
        print(f"demonstration: {len(keys)} throw-away event key(s): {', '.join(keys)}")
        second_instance_build.build(scratch)
        assemble(scratch, into, prefix)
    finally:
        second_instance_build.unlink_node_modules(links)
        shutil.rmtree(scratch.parent, ignore_errors=True)
    return into.joinpath(*[part for part in prefix.split("/") if part])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "output",
        type=Path,
        help="the directory to write the published tree into",
    )
    parser.add_argument(
        "--url",
        default=None,
        help=(
            "the address the demonstration is served at, trailing slash "
            "included (default: the address the example instance declares, "
            "which resolves nowhere -- pass the real one when publishing)"
        ),
    )
    args = parser.parse_args(argv)

    url = args.url
    if url is None:
        example = json.loads(
            (
                second_instance_build.ROOT / second_instance_build.EXAMPLE / DECLARATION
            ).read_text(encoding="utf-8")
        )
        url = str(example["published_url"])
    if not url.endswith("/"):
        print(
            f"::error::--url must end in '/' ({url}) -- every address the "
            "build composes is made by appending to it, so a missing slash "
            "quietly eats a path segment",
            file=sys.stderr,
        )
        return 1

    served = build(url, args.output)
    prefix = urlsplit(url).path
    print(f"demonstration: built into {args.output} for {url}")
    print(f"demonstration: the showcase is at {prefix}, the cockpit at {prefix}app/")
    # What a host already serving under that prefix takes as its root, as
    # opposed to what a plain static server rooted at `output` does. The
    # two are the same tree read from two places, and saying which is
    # which here is what stops a publish putting the prefix in twice.
    print(f"demonstration: publish the contents of {served}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
