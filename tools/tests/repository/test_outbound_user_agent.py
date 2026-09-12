"""Every outbound call this package makes names this software.

`convener_ops/declaration/user_agent.py` states the header once and says
why. This module is what stops it from being stated once and applied
twice: it reads every module the package and the scripts ship, finds every
`urllib.request.Request` built anywhere in them, and fails on one whose
enclosing function never names `USER_AGENT`.

It is a sweep rather than three assertions because the failure it guards
against is a fourth call site, written later by somebody who has not read
that module. That is not hypothetical -- it is how the three that exist
came to be written without the header, while `services/form-relay` next
door had carried one from the day it was written, with the reason in a
comment beside it.

**Where this sweep stops.** At Python. The relays make outbound calls
too, and each of them is held by its own suite in its own language, which
is where a JavaScript reader will look. A Python test scanning JavaScript
text would be the weaker check of the two and would put the rule somewhere
nobody working on a relay would find it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import urlsplit

from convener_ops.declaration.paths import repo_root
from convener_ops.declaration.user_agent import USER_AGENT

ROOT = repo_root()

#: The two trees this package ships Python from. `tools/scripts/` is here
#: because the Tally call lives there rather than in the package proper,
#: and it is the one call site an operator meets in person.
TREES: tuple[str, ...] = ("tools/convener_ops", "tools/scripts")

HEADER = "User-Agent"
CONSTANT = "USER_AGENT"


def _shipped() -> set[str]:
    return {
        path.relative_to(ROOT).as_posix()
        for tree in TREES
        for path in (ROOT / tree).rglob("*.py")
    }


def _modules() -> list[tuple[str, ast.Module]]:
    return [
        (rel, ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel))
        for rel in sorted(_shipped())
    ]


def _builds_a_request(node: ast.AST) -> bool:
    """`urllib.request.Request(...)`, read as the attribute call it is.

    Matching on the attribute rather than the full dotted path keeps an
    aliased import (`from urllib.request import Request`) inside the
    sweep, which a match on `urllib.request.Request` would drop in
    silence -- and a call site this sweep cannot see is the one thing it
    exists to prevent."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Request"
    ) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Request"
    )


def _functions_that_call_out() -> list[tuple[str, str, ast.AST]]:
    found: list[tuple[str, str, ast.AST]] = []
    for rel, tree in _modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if any(_builds_a_request(child) for child in ast.walk(node)):
                found.append((rel, node.name, node))
    return found


def _names_the_header(node: ast.AST) -> bool:
    """Both halves, because either alone is satisfiable by accident: a
    function may mention the constant while building some other request,
    and the literal `"User-Agent"` may appear in a docstring."""
    body = list(ast.walk(node))
    says_header = any(
        isinstance(child, ast.Constant) and child.value == HEADER for child in body
    )
    says_constant = any(
        isinstance(child, ast.Name) and child.id == CONSTANT for child in body
    )
    return says_header and says_constant


# ------------------------------------------------------------------ #
# The sweep is real: it reads code, and it finds calls to judge.
# ------------------------------------------------------------------ #


def test_the_sweep_reads_every_module_these_trees_ship() -> None:
    """A walk that quietly found nothing would make the rule below pass
    over an empty list."""
    read = {rel for rel, _ in _modules()}

    assert read == _shipped(), (
        f"the sweep reads {len(read)} of the {len(_shipped())} modules "
        f"{' and '.join(TREES)} ship. Every one of them has to be read, or "
        "an outbound call in the ones it misses is held by nothing."
    )


def test_there_are_outbound_calls_for_this_sweep_to_judge() -> None:
    """Three, today: the Tally form creation, and the FCC calls and
    recording lookups. A sweep with nothing to find passes forever."""
    sites = _functions_that_call_out()

    assert len(sites) >= 3, (
        f"this sweep found {len(sites)} outbound call sites and the "
        "repository has at least three. Finding fewer means the sweep "
        "stopped seeing them, not that they stopped existing."
    )


# ------------------------------------------------------------------ #
# The rule.
# ------------------------------------------------------------------ #


def test_every_outbound_request_names_this_software() -> None:
    silent = [
        f"{rel}::{name}"
        for rel, name, node in _functions_that_call_out()
        if not _names_the_header(node)
    ]

    assert not silent, (
        "these functions build an outbound request without naming "
        f"{CONSTANT}: {silent}. urllib sends `Python-urllib/3.x` when "
        "nothing else is set, and Cloudflare refuses that string with a "
        "403 the API never sees -- so the call fails as an authentication "
        "problem it is not. `convener_ops/declaration/user_agent.py` has "
        "the header and the reasoning."
    )


def _homepage() -> str:
    """The `(+URL)` comment a User-Agent is allowed to carry, read out of
    the header rather than searched for inside it.

    Reading it is the point. `"https://github.com/" in USER_AGENT` was the
    first version of the rule below and CodeQL was right to refuse it: a
    substring test on a URL passes for a host that merely contains the one
    meant, and it would have passed just as happily on a value where the
    address was not the comment at all."""
    comment = re.search(r"\(\+(?P<url>[^)]+)\)", USER_AGENT)
    assert comment, (
        f"the User-Agent {USER_AGENT!r} carries no `(+URL)` comment. That "
        "comment is the whole of what an operator on the receiving end can "
        "follow back to whoever called them."
    )
    return comment.group("url")


def test_the_header_names_the_software_and_where_to_find_it() -> None:
    """What an operator on the receiving end needs from a string in their
    logs: which software called, and where to go about it."""
    assert "convener-ops" in USER_AGENT

    home = urlsplit(_homepage())
    assert home.scheme == "https", home
    assert home.hostname == "github.com", home
    # Owner and repository, so the address reaches this project rather than
    # the host it is kept on.
    assert len(home.path.strip("/").split("/")) == 2, home


def test_the_header_impersonates_nothing() -> None:
    """A filter that exists to tell automated clients apart is not
    answered honestly by dressing as a browser, and any honest value
    passes it -- curl's own default does."""
    for token in ("Mozilla", "AppleWebKit", "Chrome", "Safari", "Gecko"):
        assert token not in USER_AGENT, (
            f"the User-Agent carries {token!r}, which claims to be a "
            "browser this software is not."
        )


def test_the_module_stating_it_is_where_the_package_keeps_declarations() -> None:
    """One home for the value, named here so that a second copy of the
    string somewhere else fails this rather than passing quietly."""
    home = Path("tools/convener_ops/declaration/user_agent.py")
    assert (ROOT / home).is_file()

    elsewhere = [
        rel
        for rel in sorted(_shipped())
        if rel != home.as_posix()
        and "convener-ops (+https://" in (ROOT / rel).read_text(encoding="utf-8")
    ]
    assert not elsewhere, (
        f"the User-Agent string is written out again in {elsewhere}. It is "
        f"declared in {home.as_posix()}, and a second copy is a value that "
        "can drift from the one every other call site sends."
    )
