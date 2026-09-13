"""The boundary between what an instance owns and what the product ships.

This boundary exists because a duplicate of this repository updates by
**merging**: it works when upstream's commits and the instance's commits
never touch the same file, and it collapses into conflicts otherwise. The
rule the phase states in one sentence is *upstream never writes into an
instance path*. This module is what holds it, so it had better be honest
about what that sentence can mean offline.

What it cannot mean
-------------------
"No future commit touches this." No test sees the future, and any check
claiming to would be worse than none: a reviewer trusts it instead of
looking. Nothing here reads git history either -- that upstream *has* not
written into `instance/data/` is a fact about a repository's past, not a property of
its current state, and a green suite would say nothing about the next pull
request.

What it does mean, and what is actually checked
-----------------------------------------------
The formulation held is the one that survives being read twice:

    **In the repository as the product ships it, no instance path holds
    anything upstream would ever need to edit, and no ownership is left
    undecided.**

Three decidable clauses come out of that, one test each:

1. **Decided once.** Every path an instance owns is named in exactly one
   place -- `declarations/boundary.yml` for the paths outside
   `declarations/`, and each configuration file's own `owner:` key for the
   ones inside it. A file in `declarations/` with no answer is refused by
   name; a configuration path named in
   the declaration as well is refused too, because one fact in two places
   is how this repository has drifted every previous time.

2. **No instance path holds code.** Source is the thing upstream fixes bugs
   in. The day a `.py`, a `.ts` or a `.njk` lives under `instance/data/` or
   `instance/keys/`, "upstream never writes here" stops being a promise anybody can
   keep -- not because someone was careless, but because a bug will
   eventually be there and it will have to be fixed. This is the clause
   that bites, and it is checked over the files the working tree really
   holds, not over a list.

3. **Nothing sits inside an instance path by accident.** The two product
   files that live inside instance directories today
   (`instance/data/schema.md`, `instance/keys/signing/README.md`) are named in the
   declaration with their reasons, must exist, and are the only exceptions
   there are. An unjustifiable one cannot be added quietly.

What these three do **not** cover, stated plainly rather than left to be
discovered:

- **Content.** A hard-coded organisation name inside a product file is not
  visible here at all. That is what the substitution vocabulary and the
  second-instance build sweep are for.
- **Completeness.** A new instance-owned file created *outside* the
  declared paths is invisible: the boundary can only hold what somebody
  declared. Clause 2 catches the reverse mistake (code moving into an
  instance path), never this one.
- **Runtime writes.** The instance's own scheduled jobs write into `instance/data/`
  and `instance/public-data/` constantly, and must. Nothing here distinguishes a
  write by the instance from a write by upstream, because in a checkout
  they look identical; the distinction lives in who commits, which is a
  fact about a repository's history and therefore outside this module.
- **Correctness of a judgement.** That `instance/queue-drain.yml` is the
  instance's is an argument, written in that file's own header. This module
  holds the answer, never the argument.
"""

from __future__ import annotations

import ast
import pkgutil
import subprocess  # nosec B404
from importlib import import_module
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

import convener_ops
from convener_ops.declaration import boundary
from convener_ops.declaration.boundary import (
    INSTANCE,
    PRODUCT,
    Boundary,
    Handed,
    Kept,
    code_among,
    config_owners,
    declaration_from_data,
    instance_files,
    load,
    retirements_must_land_where_the_instance_is,
)
from convener_ops.declaration.paths import repo_root
from convener_ops.journey import registration_routing
from convener_ops.maintenance import actions_usage, queue_watch

ROOT = repo_root()

#: A declaration in the shape the real one has, for the synthetic roots
#: below. Deliberately not a copy of `declarations/boundary.yml`: a fixture that
#: tracked the real file would make every assertion here restate the thing
#: it is meant to check.
_MINIMAL = {
    "owner": PRODUCT,
    "v": boundary.DECLARATION_VERSION,
    "instance": [{"path": "records/", "reason": "the instance's own records"}],
}


def _write_root(
    tmp_path: Path,
    *,
    declaration: Any = None,
    owners: dict[str, str] | None = None,
) -> Path:
    """A repository root holding only what this module reads: a
    declaration, and the two directories whose configuration files state
    an owner. `owners` names a file inside one of them, path and all, so a
    case can put the same file on either side of `boundary.CONFIG_DIRS`."""
    for directory in boundary.CONFIG_DIRS:
        (tmp_path / directory).mkdir(exist_ok=True)
    body = _MINIMAL if declaration is None else declaration
    (tmp_path / boundary.DECLARATION_PATH).write_text(
        yaml.safe_dump(body), encoding="utf-8"
    )
    for name, owner in (owners or {}).items():
        (tmp_path / name).write_text(f"owner: {owner}\n", encoding="utf-8")
    return tmp_path


# ------------------------------------------------------------------ #
# Clause 1 -- decided once
# ------------------------------------------------------------------ #


def test_this_repository_declares_a_boundary_that_reads() -> None:
    """The anchors, so that nothing below can pass over an empty set.

    Four paths named on purpose: the records, the keys, the published
    derivative and the decision register. They are asserted as
    *membership*, never as the whole list -- a test that restated the list
    would be the second copy this whole design exists to refuse.

    `site/src/_data/site.json` was the fourth of these until
    its four keys were folded into `instance/config.json`'s own
    `identity` and left `site/.eleventy.js` composing them. The file
    entry went with the file, and nothing under `site/` is the instance's
    now -- so the anchor moved to `docs/handbook/governance/register.md`, the one
    path here that a scheduled job rewrites rather than a person.
    """
    declared = load().instance_paths
    for owned in (
        "instance/data/",
        "instance/keys/",
        "instance/public-data/",
        "docs/handbook/governance/register.md",
    ):
        assert owned in declared, f"{owned} is no longer declared: {declared}"


def test_every_file_in_config_states_which_it_is() -> None:
    """The self-declaring directory filled up by accumulation and nobody
    ever decided. Now
    every file answers, and both answers are actually used -- a directory
    where everything said `product` would satisfy a weaker test while
    saying nothing at all.

    Every file in every format `boundary.CONFIG_READERS` knows, in both
    the directories `boundary.CONFIG_DIRS` names, compared against what
    they really hold: `instance/config.json` is JSON, and a check that
    only ever globbed `*.yml` would have let a second format arrive with
    nobody deciding what it is -- the exact silence that directory was in
    before.
    """
    owners = load().config_owners
    assert set(owners) == {
        path.relative_to(ROOT).as_posix()
        for directory in boundary.CONFIG_DIRS
        for suffix in boundary.CONFIG_READERS
        for path in (ROOT / directory).glob(f"*{suffix}")
    }
    assert set(owners.values()) == {INSTANCE, PRODUCT}
    assert owners["declarations/integrations.yml"] == PRODUCT
    assert owners["declarations/boundary.yml"] == PRODUCT
    assert owners["instance/config.json"] == INSTANCE


def test_the_packages_own_config_constants_agree_with_the_declaration() -> None:
    """The three threshold files the code reaches for by name, and the one
    it reads as a mirror of itself. If a header and a module ever disagree
    about which side a file is on, this is where it shows."""
    board = load()
    assert board.owner_of(actions_usage.BUDGET_PATH) == INSTANCE
    assert board.owner_of(queue_watch.CONFIG_PATH) == INSTANCE
    assert board.owner_of(registration_routing.CONFIG_PATH) == INSTANCE
    assert board.owner_of(Path("declarations") / "integrations.yml") == PRODUCT


def test_every_path_this_package_names_is_classified() -> None:
    """A derived sweep, not a list: every `Path` constant any module of
    `convener_ops` declares, at any depth, put through the boundary.

    `walk_packages`, not `iter_modules`: the package is seven sub-packages
    and nothing at its root, so a walk that stopped at the top level would
    read no module at all and still hand back a plausible-looking
    dictionary.

    Its value is the direction it fails in. The ledgers the scheduled jobs
    write (`instance/data/queue-watch.yml`, `instance/data/actions-usage.yml`,
    `instance/data/retention-last-run.yml`, ...) and the key directories
    (`instance/keys/events`, `instance/keys/signing`) must stay the
    instance's; a `kept:` entry added carelessly, or a declaration narrowed
    from `instance/data/` to one
    of its files, would quietly un-own them and nothing else would notice.
    """
    board = load()
    named: dict[str, str] = {}
    for module in pkgutil.walk_packages(convener_ops.__path__, "convener_ops."):
        loaded = import_module(module.name)
        for name, value in vars(loaded).items():
            if name.isupper() and isinstance(value, Path):
                named[value.as_posix()] = f"{module.name}.{name}"
    assert len(named) >= 15, f"the sweep found almost nothing: {named}"
    handed_roots = tuple(entry.path for entry in board.handed if entry.is_directory)
    for path, where in sorted(named.items()):
        if path.startswith(handed_roots):
            assert board.owner_of(path) == INSTANCE, (
                f"{where} names {path}, which sits under a path this "
                "repository hands to the instance, yet the declaration "
                "reads it as the product's"
            )


def test_a_config_file_with_no_owner_is_refused_by_name(tmp_path: Path) -> None:
    """The state that directory was in before `owner:` existed: a file that
    works, reads, and says nothing about who it belongs to."""
    root = _write_root(tmp_path)
    (root / "declarations" / "thresholds.yml").write_text("v: 1\n", encoding="utf-8")

    with pytest.raises(
        ValueError, match=r"declarations/thresholds\.yml declares no owner"
    ):
        config_owners(root)


def test_a_json_config_file_answers_the_same_question(tmp_path: Path) -> None:
    """`instance/config.json` is JSON because three languages read it and
    only JSON has a parser on all three sides without a dependency two of
    them do not carry. That must not become a way around the rule above:
    a JSON file states the same `owner` key, and one that does not is
    refused by name exactly as a YAML one is."""
    root = _write_root(tmp_path)
    named = root / "instance" / "config.json"

    named.write_text('{"v": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match=r"instance/config\.json declares no owner"):
        config_owners(root)

    named.write_text('{"owner": "instance", "v": 1}', encoding="utf-8")
    assert config_owners(root)["instance/config.json"] == INSTANCE


def test_a_config_file_with_an_invented_owner_is_refused(tmp_path: Path) -> None:
    """Two answers, and only two. `owner: both` is the mixing this
    declaration exists to end, spelled out."""
    root = _write_root(tmp_path, owners={"declarations/thresholds.yml": "both"})

    with pytest.raises(ValueError, match="declares no owner"):
        config_owners(root)


def test_a_config_file_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    root = _write_root(tmp_path)
    (root / "declarations" / "list.yml").write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"declarations/list\.yml declares no owner"):
        config_owners(root)


def test_the_declaration_refuses_to_name_a_config_path() -> None:
    """One fact, one place. `instance/queue-drain.yml` says what it is in its
    own header; a second home for that answer is how two lists start
    disagreeing, which is this repository's oldest defect."""
    with pytest.raises(ValueError, match="state their own owner"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {"path": "instance/queue-drain.yml", "reason": "the instance's"}
                ],
            }
        )


def test_the_declaration_refuses_one_entry_inside_another() -> None:
    """Nesting is not an error a reader sees: both entries look correct,
    and whichever is read first silently decides."""
    with pytest.raises(ValueError, match="sits inside"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {"path": "instance/data/", "reason": "the records"},
                    {"path": "instance/data/events/", "reason": "the events"},
                ],
            }
        )


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("not a mapping", "not a supported format version"),
        ({"owner": PRODUCT}, "not a supported format version"),
        ({"owner": PRODUCT, "v": 99, "instance": []}, "not a supported format"),
        (
            {"owner": INSTANCE, "v": 1, "instance": [{"path": "a/", "reason": "b"}]},
            "must declare `owner: product`",
        ),
        ({"owner": PRODUCT, "v": 1}, "must be a non-empty list"),
        ({"owner": PRODUCT, "v": 1, "instance": []}, "must be a non-empty list"),
        ({"owner": PRODUCT, "v": 1, "instance": ["instance/data/"]}, "not an entry"),
        (
            {"owner": PRODUCT, "v": 1, "instance": [{"reason": "b"}]},
            "must be a non-empty path",
        ),
        (
            {
                "owner": PRODUCT,
                "v": 1,
                "instance": [{"path": " instance/data/ ", "reason": "b"}],
            },
            "surrounding whitespace",
        ),
        (
            {"owner": PRODUCT, "v": 1, "instance": [{"path": "/data/", "reason": "b"}]},
            "relative POSIX path",
        ),
        (
            {"owner": PRODUCT, "v": 1, "instance": [{"path": "..\\x", "reason": "b"}]},
            "relative POSIX path",
        ),
        (
            {"owner": PRODUCT, "v": 1, "instance": [{"path": "../x/", "reason": "b"}]},
            "relative POSIX path",
        ),
        (
            {"owner": PRODUCT, "v": 1, "instance": [{"path": "instance/data/"}]},
            "carry a reason",
        ),
    ],
)
def test_a_declaration_that_cannot_be_read_stops_rather_than_guesses(
    data: Any, expected: str
) -> None:
    """The file that decides what upstream may write is the last one that
    may quietly substitute a default for a value it could not read."""
    with pytest.raises(ValueError, match=expected):
        declaration_from_data(data)


# ------------------------------------------------------------------ #
# Clause 3 -- the product's own files inside an instance directory
# ------------------------------------------------------------------ #


def test_every_declared_file_exists_and_every_kept_file_with_it() -> None:
    """A directory entry may name something a fresh duplicate has not
    created yet -- `instance/keys/events/`, `instance/public-data/` -- so
    its existence is not asserted. A *file* entry, and every `kept:` exception, names
    something that is in this repository right now, and an entry pointing
    at nothing is an exception nobody can check."""
    board = load()
    for entry in board.handed:
        if not entry.is_directory:
            assert (ROOT / entry.path).is_file(), f"{entry.path} does not exist"
        for kept in entry.kept:
            assert (ROOT / kept.path).is_file(), f"{kept.path} does not exist"
            assert board.owner_of(kept.path) == PRODUCT


def test_every_kept_exception_is_named_here() -> None:
    """Named, so that one more cannot appear without somebody deciding to
    let it. Every one is documentation of a contract that lives where an
    operator will meet it, and every one is a candidate for a move later
    -- which is a maintainer's call, not this module's."""
    kept = {kept.path for entry in load().handed for kept in entry.kept}
    assert kept == {
        "instance/data/schema.md",
        "instance/keys/events/README.md",
        "instance/keys/signing/README.md",
        "instance/public-data/README.md",
    }


def test_a_directory_is_the_instance_s_only_when_all_of_it_is() -> None:
    """`owns_directory`, added for the derivation guard, which meets
    directories as tree objects whose path has no trailing slash and
    cannot spell the question `owner_of` answers.

    The `True` half is asked of a declaration built here, because every
    directory the real one hands over now carries a `kept:` file: the
    schema stub, and one README in each of the three directories that are
    empty in a fresh clone. A directory with no exception inside it is
    still the shape the method has to answer for, and this is where that
    shape now exists.

    The `False` half is the one that earns the method, and it is asked of
    the real declaration: a directory holding a file the product keeps
    cannot be dropped without dropping that file with it, so it is not the
    instance's however the entry above it reads.
    """
    whole = Boundary(
        handed=declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [{"path": "instance/records/", "reason": "the records"}],
            }
        ),
        config_owners={},
    )
    assert whole.owns_directory("instance/records")
    assert whole.owns_directory("instance/records/")

    board = load()
    assert not board.owns_directory("site")
    for kept in (kept for entry in board.handed for kept in entry.kept):
        parent = kept.path.rsplit("/", 1)[0]
        assert board.owner_of(parent + "/") == INSTANCE
        assert not board.owns_directory(parent), parent


def test_a_kept_file_outside_its_own_entry_is_refused() -> None:
    with pytest.raises(ValueError, match="is not a file inside"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {
                        "path": "instance/data/",
                        "reason": "the records",
                        "kept": [{"path": "docs/schema.md", "reason": "elsewhere"}],
                    }
                ],
            }
        )


def test_a_file_entry_cannot_keep_anything_inside_itself() -> None:
    with pytest.raises(ValueError, match="names a single file"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {
                        "path": "site/src/_data/site.json",
                        "reason": "the identity",
                        "kept": [{"path": "site/src/_data/x", "reason": "no"}],
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("kept", "expected"),
    [
        ("a string", "must be a list"),
        (["a string"], "not an entry"),
        ([{"path": "instance/data/x.md"}], "carry a reason"),
        (
            [{"path": "instance/data/sub/", "reason": "a directory"}],
            "not a file inside",
        ),
    ],
)
def test_a_kept_entry_that_cannot_be_read_stops(kept: Any, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {"path": "instance/data/", "reason": "the records", "kept": kept}
                ],
            }
        )


# ------------------------------------------------------------------ #
# `regenerated:` -- the paths upstream's own runs also write
# ------------------------------------------------------------------ #


def test_every_regenerated_path_is_told_to_git_how_to_merge() -> None:
    """The clause `regenerated:` exists to make checkable.

    Declaring a path the instance's says upstream will not *edit* it. It
    cannot say upstream will not *run*: upstream is itself a running
    instance, and `.github/workflows/derive-decision-register.yml` rewrites
    `docs/handbook/governance/register.md` in full from the commit history on every
    push, on both sides of any merge. Both renderings are correct, they
    are entirely different, and they touch the same lines -- a conflict on
    every merge, for ever, whose only correct resolution is "mine".

    `.gitattributes` is where that resolution is written down. This is
    what stops the declaration and the attribute drifting apart: a path
    declared `regenerated:` and never given `merge=ours` is a promise
    nobody kept, and it would only be discovered by somebody else, a year
    later, in their own repository.
    """
    declared = load().regenerated_paths
    assert declared, "no path is declared regenerated -- the clause is dead"
    attributes = (ROOT / boundary.GIT_ATTRIBUTES_PATH).read_text(encoding="utf-8")
    lines = [
        line.split("#", 1)[0].split()
        for line in attributes.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for path in declared:
        matching = [parts for parts in lines if parts and parts[0] == path]
        assert matching, (
            f"{path} is declared regenerated: in "
            f"{boundary.DECLARATION_PATH.as_posix()} but "
            f"{boundary.GIT_ATTRIBUTES_PATH.as_posix()} says nothing about "
            "it -- every merge in every duplicate will conflict on it"
        )
        assert any(
            boundary.REGENERATED_MERGE_ATTRIBUTE in parts for parts in matching
        ), f"{path} has git attributes but not {boundary.REGENERATED_MERGE_ATTRIBUTE!r}"


def test_the_register_is_the_regenerated_path_this_task_found() -> None:
    """The anchor, so the clause above cannot pass over an empty set or a
    set somebody quietly widened. One path today, and it is the one this
    repository found and ruled on."""
    assert load().regenerated_paths == ("docs/handbook/governance/register.md",)
    assert (ROOT / "docs" / "handbook" / "governance" / "register.md").is_file()


def test_a_directory_cannot_be_declared_regenerated() -> None:
    """`merge=ours` is an attribute of a file. A directory declared
    regenerated would be a promise `.gitattributes` cannot be held to
    entry by entry, so it is refused rather than approximated."""
    with pytest.raises(ValueError, match="regenerated: names"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {
                        "path": "instance/public-data/",
                        "reason": "the published derivative",
                        "regenerated": True,
                    }
                ],
            }
        )


def test_a_regenerated_flag_that_is_not_a_flag_is_refused() -> None:
    with pytest.raises(ValueError, match="must be true or false"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {
                        "path": "instance/data/x.md",
                        "reason": "a record",
                        "regenerated": "yes",
                    }
                ],
            }
        )


def test_a_path_nobody_declared_regenerated_is_not() -> None:
    """The default, asserted rather than assumed: the flag is off unless
    the declaration turns it on."""
    (entry,) = declaration_from_data(
        {
            "owner": PRODUCT,
            "v": boundary.DECLARATION_VERSION,
            "instance": [{"path": "instance/data/", "reason": "the records"}],
        }
    )
    assert entry.regenerated is False


# ------------------------------------------------------------------ #
# Where the instance's paths used to be
# ------------------------------------------------------------------ #


def _retiring(*entries: dict[str, Any]) -> dict[str, Any]:
    """A whole declaration whose `retired:` list is `entries`."""
    return {
        "owner": PRODUCT,
        "v": boundary.DECLARATION_VERSION,
        "instance": [{"path": "instance/data/", "reason": "the records"}],
        "retired": list(entries),
    }


def test_the_two_questions_have_two_answers() -> None:
    """`owner_of` is present tense and `ever_owned` is not. Conflating
    them is how every version of this instance's records written before
    they moved into `instance/` read as the product's."""
    board = load()
    for path in board.retired_paths:
        probe = path + "left-behind.yml" if path.endswith("/") else path
        assert board.owner_of(probe) == PRODUCT
        assert board.ever_owned(probe)


def test_no_retired_path_is_in_this_repository_any_more() -> None:
    """A retired path that still exists is a live one, and the entry for
    it says the opposite of what the tree does."""
    for path in load().retired_paths:
        assert not (ROOT / path).exists(), f"{path} is still here"


def test_every_retired_path_carries_its_reason() -> None:
    for entry in load().retired:
        assert entry.reason.strip()


def test_the_retirement_this_repository_did_not_notice_is_declared() -> None:
    """`site/src/_data/site.json` held four identity keys the showcase's
    build read, and they were folded into `instance/config.json` and the
    file deleted. That removed it from the working tree and from nothing
    else, and nothing excluded it: it was instance data with an entry
    nowhere for as long as it took somebody to move a directory and go
    looking."""
    assert "site/src/_data/site.json" in load().retired_paths


def test_a_retired_path_may_be_a_configuration_file() -> None:
    """Where a live one may not. A file in `declarations/` states its own owner
    in its own header, so naming a live one here would put one fact in
    two places -- and a file that is not there any more states nothing,
    which leaves this list as the only place its former ownership can be
    written."""
    (entry,) = boundary.retired_from_data(
        _retiring(
            {
                "path": "config/instance.json",
                "became": "instance/data/",
                "reason": "where it was",
            }
        )
    )
    assert entry.path == "config/instance.json"


def test_a_path_cannot_be_retired_and_handed_over_at_once() -> None:
    """One of the two entries would be a copy of the other, which is the
    defect this whole declaration exists downstream of."""
    with pytest.raises(ValueError, match="retired and is also"):
        boundary.retired_from_data(
            _retiring(
                {
                    "path": "instance/data/",
                    "became": "instance/config.json",
                    "reason": "where it was",
                }
            )
        )
    with pytest.raises(ValueError, match="retired and is also"):
        boundary.retired_from_data(
            _retiring(
                {
                    "path": "instance/data/speakers.yml",
                    "became": "instance/data/",
                    "reason": "where it was",
                }
            )
        )


def test_a_retired_path_cannot_be_regenerated() -> None:
    """The flag says a scheduled job rewrites a path in full on both
    sides of a merge, which is a statement about a file git still has to
    merge."""
    with pytest.raises(ValueError, match="nothing regenerates it"):
        boundary.retired_from_data(
            _retiring(
                {
                    "path": "data/",
                    "became": "instance/data/",
                    "reason": "where it was",
                    "regenerated": False,
                }
            )
        )


def test_a_retired_path_says_what_it_became() -> None:
    """The key the list was missing, and the whole of what it costs to
    add one wrongly.

    A retirement is a move: the instance's files sat at this path and are
    at that one now. An entry that cannot name a destination is describing
    a *deletion*, which is what the product does to its own files, and
    retiring one of those takes the product's own history out of the
    repository the product is published from -- with every gate green,
    because until this key existed nothing in an entry's shape said
    otherwise.
    """
    with pytest.raises(ValueError, match="became must be a non-empty path"):
        boundary.retired_from_data(
            _retiring({"path": "data/", "reason": "where they were"})
        )


def test_a_live_path_has_not_become_anything() -> None:
    """The mirror of the refusal above, and the same argument the
    `regenerated:` pair makes: a key that is only meaningful about a path
    that is gone has no answer for one that is here, and a live entry
    carrying one is somebody using the wrong list."""
    with pytest.raises(ValueError, match="has not become anything"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {
                        "path": "instance/data/",
                        "became": "instance/records/",
                        "reason": "the records",
                    }
                ],
            }
        )


def test_a_retirement_cannot_be_its_own_destination() -> None:
    """Neither spelling of the same non-move: the path itself, and
    somewhere under it. Both would satisfy every later check while saying
    nothing about where the content went."""
    with pytest.raises(ValueError, match="became itself"):
        boundary.retired_from_data(
            _retiring({"path": "data/", "became": "data/", "reason": "where they were"})
        )
    with pytest.raises(ValueError, match="sits inside"):
        boundary.retired_from_data(
            _retiring(
                {
                    "path": "data/",
                    "became": "data/somewhere/",
                    "reason": "where they were",
                }
            )
        )


def _retired_landing(became: str) -> Boundary:
    """A boundary whose one retirement lands at `became`."""
    return Boundary(
        handed=(Handed(path="instance/data/", reason="the records"),),
        config_owners={"instance/config.json": INSTANCE},
        retired=(Handed(path="data/", reason="where they were", became=became),),
    )


def test_a_retirement_landing_outside_the_instance_is_refused() -> None:
    """The refusal itself, on the whole boundary rather than on one list.

    Whether a destination is the instance's is a question `instance:`
    alone cannot answer -- four of this repository's own retirements land
    on configuration files that state their own owner in their own
    header -- so this is the one check that needs both halves, and it runs
    where they meet.
    """
    for landing in ("tools/migrations-that-ran/", "docs/handbook/", "README.md"):
        with pytest.raises(ValueError, match="does not hand to the instance"):
            retirements_must_land_where_the_instance_is(_retired_landing(landing))


def test_a_retirement_lands_on_either_half_of_the_declaration() -> None:
    """The positive control, on both shapes the answer can come from: a
    directory `instance:` hands over, and a configuration file whose own
    header states it. A check that only read the first would refuse
    `config/instance.json`'s own entry, which is correct."""
    for landing in (
        "instance/data/",
        "instance/data/speakers.yml",
        "instance/config.json",
    ):
        retirements_must_land_where_the_instance_is(_retired_landing(landing))


def test_a_configuration_file_this_tree_does_not_hold_is_unknown_and_not_refused() -> (
    None
):
    """The one tolerance, and the shape of tree it is for.

    Half of this boundary is read off the configuration files themselves,
    so a tree carrying the declaration and not the files -- the scratch
    repositories the derivation and the directory map build -- has no
    answer for the four retirements landing on one, and `owner_of`
    reports the default, which is the product. *Not asked* is not *not
    the instance's*, and refusing on it would refuse those trees rather
    than the mistake.

    `instance/` only. A file's location already says which side it is on
    and the header refuses the one that landed on the wrong side, so an
    absent file in `instance/` is unknown and an absent one in
    `declarations/` is the product's -- the same sentence, read twice.
    """
    unknown = Boundary(
        handed=(Handed(path="instance/data/", reason="the records"),),
        config_owners={},
        retired=(
            Handed(
                path="data/", reason="where they were", became="instance/config.json"
            ),
        ),
    )
    retirements_must_land_where_the_instance_is(unknown)

    product_side = Boundary(
        handed=(Handed(path="instance/data/", reason="the records"),),
        config_owners={},
        retired=(
            Handed(
                path="data/",
                reason="where they were",
                became="declarations/boundary.yml",
            ),
        ),
    )
    with pytest.raises(ValueError, match="does not hand to the instance"):
        retirements_must_land_where_the_instance_is(product_side)


def test_every_retirement_this_repository_carries_lands_on_the_instance() -> None:
    """The declaration as it stands, read rather than assumed. `load`
    raises rather than returns for a landing that is not the instance's,
    so this is the same statement spelled where a reader of the list will
    look for it."""
    board = load()
    for entry in board.retired:
        assert entry.became, f"{entry.path} says nothing about where it went"
        probe = (
            entry.became + "anything" if entry.became.endswith("/") else entry.became
        )
        assert board.owner_of(probe) == INSTANCE, (
            f"{entry.path} became {entry.became}, which is not the instance's"
        )


def test_a_retired_entry_that_cannot_be_read_stops_rather_than_guesses() -> None:
    """A declaration that cannot be read must stop the check rather than
    run it against a guess -- the same rule the live list is held to."""
    with pytest.raises(ValueError, match="must carry a reason"):
        boundary.retired_from_data(_retiring({"path": "data/"}))
    with pytest.raises(ValueError, match="must be a non-empty path"):
        boundary.retired_from_data(_retiring({"reason": "no path at all"}))
    document = _retiring(
        {"path": "data/", "became": "instance/data/", "reason": "where they were"}
    )
    document["retired"] = ["data/"]
    with pytest.raises(ValueError, match="not an entry"):
        boundary.retired_from_data(document)


def test_an_empty_retired_list_is_refused() -> None:
    """Absent and empty are different claims. Absent says nothing has
    moved; empty says somebody looked and there is nothing, which is a
    statement a list of zero entries cannot support."""
    assert (
        boundary.retired_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [{"path": "instance/data/", "reason": "the records"}],
            }
        )
        == ()
    )
    with pytest.raises(ValueError, match="must be a non-empty list"):
        boundary.retired_from_data(_retiring())


def test_one_retired_entry_cannot_sit_inside_another() -> None:
    with pytest.raises(ValueError, match="sits inside"):
        boundary.retired_from_data(
            _retiring(
                {
                    "path": "data/",
                    "became": "instance/data/",
                    "reason": "where they were",
                },
                {
                    "path": "data/keys/",
                    "became": "instance/keys/",
                    "reason": "where the keys were",
                },
            )
        )


def test_the_product_keeps_its_own_files_inside_a_retired_directory_too() -> None:
    """`kept:` reads the same on this list as on the other one, through
    the same parser -- and `kept_files` is what a walk of a history asks,
    because it meets a retired directory's kept file as readily as a live
    one's."""
    board = load()
    assert set(board.kept_files) >= {
        "data/schema.md",
        "keys/signing/README.md",
        "instance/data/schema.md",
        "instance/keys/signing/README.md",
    }
    for kept in board.kept_files:
        assert not board.ever_owned(kept)


# ------------------------------------------------------------------ #
# Clause 2 -- no instance path holds code
# ------------------------------------------------------------------ #


def test_the_walk_sees_the_files_this_repository_really_holds() -> None:
    """An empty walk would make the clause below pass for free, which is
    exactly how a sweep stops meaning anything."""
    found = instance_files(ROOT, load())
    assert "instance/data/config.yml" in found
    # `speakers.yml` and not `brand.json`: an instance's charter is
    # optional by declaration (`brand.INSTANCE_PATH`), so a repository
    # whose declaration names one of the product's charters holds no such
    # file and this list would be asserting the absence of a state rather
    # than the presence of a walk.
    assert "instance/data/speakers.yml" in found
    assert "instance/registration-lanes.yml" in found
    assert "docs/handbook/governance/register.md" in found
    assert "instance/data/schema.md" not in found, "a kept file is the product's"
    assert "instance/keys/signing/README.md" not in found
    assert "declarations/integrations.yml" not in found


def test_no_instance_path_holds_code() -> None:
    """The clause that bites.

    Upstream fixes bugs in source. A `.py` under `instance/data/`, a `.ts`
    under `instance/keys/`, a `.njk` under `instance/public-data/` -- each
    is a file upstream will one day have to edit, in a path it promised
    never to touch. The promise does not survive that, however careful
    everybody is, so the state is refused rather than watched.
    """
    offenders = code_among(instance_files(ROOT, load()))
    assert offenders == (), (
        "these instance paths hold source code, which upstream will "
        f"eventually have to edit: {', '.join(offenders)}"
    )


def test_the_code_detector_finds_code_when_there_is_some(tmp_path: Path) -> None:
    """The rule is only worth having if the sweep can see a violation. A
    real tree, a real walk, and a module dropped where the instance's
    records live."""
    root = _write_root(tmp_path)
    records = root / "records"
    (records / "events").mkdir(parents=True)
    (records / "config.yml").write_text("season: 2026\n", encoding="utf-8")
    (records / "events" / "helper.py").write_text("x = 1\n", encoding="utf-8")

    found = instance_files(root, load(root))
    assert "records/config.yml" in found
    assert code_among(found) == ("records/events/helper.py",)


def test_the_code_detector_leaves_data_alone() -> None:
    """Pure, so it can be exercised against a list somebody made up rather
    than only against whatever this repository happens to hold."""
    assert (
        code_among(
            ["instance/data/config.yml", "instance/keys/events/MRG-05.pub", "a/b.md"]
        )
        == ()
    )
    assert code_among(["instance/data/x.PY", "site/src/_data/site.json"]) == (
        "instance/data/x.PY",
    )


def test_the_walk_ignores_a_file_entry_that_is_not_there(tmp_path: Path) -> None:
    """A declaration may name a file a duplicate has not created; the walk
    reports what exists and leaves the "does it exist" question to the
    test that asks it by name."""
    root = _write_root(
        tmp_path,
        declaration={
            "owner": PRODUCT,
            "v": boundary.DECLARATION_VERSION,
            "instance": [{"path": "site/identity.json", "reason": "the identity"}],
        },
    )
    assert instance_files(root, load(root)) == ()


# ------------------------------------------------------------------ #
# The answer itself
# ------------------------------------------------------------------ #


def test_a_path_nobody_declared_belongs_to_the_product() -> None:
    """The default, and it is the safe direction: a path only becomes the
    instance's by being named, never by being forgotten."""
    board = load()
    assert board.owner_of("tools/convener_ops/declaration/boundary.py") == PRODUCT
    assert board.owner_of("app/src/main.tsx") == PRODUCT
    assert board.owner_of("site/src/_data/events.json") == PRODUCT
    assert board.owner_of("docs/handbook/toolkit/intro-scripts.md") == PRODUCT


def test_a_windows_separator_reads_the_same_as_a_posix_one() -> None:
    """Callers hand this module `Path` objects built with `DATA_DIR /
    "config.yml"`, which spells itself with a backslash on Windows -- where
    this project is developed."""
    board = load()
    assert board.owner_of(Path("instance") / "data" / "config.yml") == INSTANCE
    assert board.owner_of("instance\\data\\config.yml") == INSTANCE


def test_the_two_halves_are_one_list() -> None:
    """`instance_paths` is the enumeration the phase asks for, and it is
    computed from both halves rather than written down a third time."""
    board = Boundary(
        handed=(Handed(path="records/", reason="r", kept=(Kept("records/x", "r"),)),),
        config_owners={"declarations/a.yml": INSTANCE, "declarations/b.yml": PRODUCT},
    )
    assert board.instance_paths == ("declarations/a.yml", "records/")
    assert board.owner_of("records/x") == PRODUCT
    assert board.owner_of("records/y") == INSTANCE


def test_a_directory_entry_is_told_from_a_file_entry() -> None:
    assert Handed(path="instance/data/", reason="r").is_directory
    assert not Handed(path="instance/data/config.yml", reason="r").is_directory


# ------------------------------------------------------------------ #
# What a derived repository meets first: this suite's own imports
# ------------------------------------------------------------------ #

#: The calls that make a statement a *read* rather than a mention.
#: `DELIBERATELY_ABSENT` in `test_second_instance.py` names every instance
#: path there is, with a reason beside each, and names nothing it opens --
#: a sweep that could not tell the two apart would have to be argued with
#: rather than obeyed.
_READERS: Final = frozenset(
    {"read_text", "read_bytes", "open", "load", "loads", "safe_load"}
)


def _module_level_reads(source: str) -> list[tuple[int, str]]:
    """Every module-level statement that opens a path spelt as a run of
    string literals, as (line, path).

    The run has to start at the statement's first literal, which is what
    `_ROOT / "instance" / "config.json"` looks like and what
    `ROOT / "examples" / "the-example-collective" / "instance" / "config.json"` does
    not: the second names the example's own file, which is the product's,
    and reading it at import is exactly right.
    """
    found: list[tuple[int, str]] = []
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            continue
        calls = [
            call.func.attr
            if isinstance(call.func, ast.Attribute)
            else getattr(call.func, "id", "")
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
        ]
        if not _READERS & set(calls):
            continue
        literals = sorted(
            (child.lineno, child.col_offset, child.value)
            for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        )
        run = ""
        for _line, _column, value in literals:
            run = value if not run else f"{run}/{value}"
            found.append((node.lineno, run))
    return found


def test_no_test_module_reads_an_instance_path_while_it_loads() -> None:
    """A read at module scope is not a failing test, it
    is a module that never collects: in a derived repository, where these
    paths are the derivation's to lay back in, every test in the file goes
    down together and the report is a stack trace rather than a sentence.
    Four modules did it, and each now reads behind a function, so what
    fails is the assertion that is actually about the declaration.

    **What this sweep cannot see, stated rather than left to be found.** A
    path nobody spells: `published.load()` and
    `actions_usage.budget_path()` each open an instance file and name
    none, and both were among the four. A list of such readers here would
    be the copy this whole module exists against, so the sweep holds the
    spelt half and this docstring holds the rest. It also stops at
    `tools/tests/`: `services/*/test/index.test.js` used to read the same
    declaration at module scope, and nothing offline parses JavaScript
    here.
    """
    board = load()
    offending: list[str] = []
    for path in sorted((ROOT / "tools" / "tests").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for line, candidate in _module_level_reads(source):
            if board.owner_of(candidate) == INSTANCE or board.owns_directory(candidate):
                offending.append(f"{path.name}:{line} reads {candidate}")
    assert offending == [], (
        "a test module opens a path the boundary hands to the instance "
        "before pytest has a test to fail: move the read into a function "
        f"so that only the tests needing it go red -- {offending}"
    )


# --------------------------------------------------------------------- #
# The instance's directories, on a merge.
# --------------------------------------------------------------------- #


def _resolved_merge_attribute(paths: list[str]) -> dict[str, str]:
    """What git itself resolves, rather than what `.gitattributes` reads like.

    The file is a list of patterns whose order matters and whose globs do not
    always mean what they look like. A reading that only parsed the text would
    pass over a rule that matches nothing, which is the failure it exists to
    catch.
    """
    result = subprocess.run(  # nosec B603 B607
        ["git", "check-attr", "merge", "--", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    resolved: dict[str, str] = {}
    for line in result.stdout.splitlines():
        path, _, value = line.rpartition(": merge: ")
        if path:
            resolved[path] = value
    return resolved


def test_every_directory_the_instance_owns_keeps_its_own_on_a_merge() -> None:
    """The clause `regenerated:` states for one file, stated for the rest.

    `boundary.yml` gives these directories to the instance and says upstream
    does not *edit* them. It cannot say upstream does not *run*: upstream is
    itself a running instance, and its scheduled jobs commit into all three --
    the sweep, retention, the deploy projections, the certificate workflows.

    **And the bad outcome was not a conflict.** Measured on a duplicate one
    release behind, upstream's own edits went into the duplicate's
    `instance/data/speakers.yml` with no conflict at all: the header and the
    records sit in different regions of the file, so git applied upstream's
    hunks in silence. A conflict would have been the good outcome. This is
    what makes the resolution -- a duplicate's records are the duplicate's --
    something git performs rather than something a page promises.
    """
    declaration = load()
    directories = [path for path in declaration.instance_paths if path.endswith("/")]
    assert directories, (
        "the declaration hands the instance no directory at all, so this "
        "reading is comparing two empty sets"
    )

    # One real file from each, so the question asked is the one that matters:
    # not "is there a line" but "does git resolve it".
    probes = {
        directory: f"{directory}a-file-a-running-instance-writes"
        for directory in directories
    }
    resolved = _resolved_merge_attribute(list(probes.values()))
    for directory, probe in probes.items():
        assert resolved.get(probe) == "ours", (
            f"{directory} is the instance's by "
            f"{boundary.DECLARATION_PATH.as_posix()}, and git resolves "
            f"merge={resolved.get(probe)!r} for a file in it. Upstream runs on "
            "these paths even though it does not edit them, so a merge that "
            "does not take the instance's version takes upstream's -- and it "
            "does so without a conflict wherever the two changed different "
            f"regions. Give it {boundary.REGENERATED_MERGE_ATTRIBUTE} in "
            f"{boundary.GIT_ATTRIBUTES_PATH.as_posix()}"
        )


def test_the_files_upstream_keeps_inside_them_merge_the_ordinary_way() -> None:
    """The mirror, and it is not symmetry for its own sake.

    `kept:` names the files upstream maintains inside a directory it handed
    over -- the schema appendix and three READMEs. Sweeping them into the rule
    above would be a promise upstream cannot keep: it would go on improving
    them and no duplicate would ever see it, silently, which is the same
    failure in the other direction.

    `!merge` leaves the attribute unspecified, which is the ordinary
    three-way merge. Not `-merge`, which means "take ours and declare a
    conflict" and would be the opposite of the intent.
    """
    kept = list(load().kept_files)
    assert kept, "no kept: file is declared, so this reading holds nothing"

    resolved = _resolved_merge_attribute(kept)
    for path in kept:
        assert resolved.get(path) == "unspecified", (
            f"{path} is declared kept: -- upstream maintains it -- and git "
            f"resolves merge={resolved.get(path)!r}. Under "
            f"{boundary.REGENERATED_MERGE_ATTRIBUTE} an instance would never "
            "receive an upstream improvement to it, and would never be told"
        )


def test_a_file_that_is_nobody_special_merges_the_ordinary_way() -> None:
    """Non-vacuity, and the shape of a rule that swallowed the repository: a
    blanket `merge=ours` would satisfy both readings above and quietly stop
    every duplicate receiving any upstream fix at all."""
    resolved = _resolved_merge_attribute(
        ["app/src/App.tsx", "tools/convener_ops/declaration/boundary.py", "README.md"]
    )
    assert set(resolved.values()) == {"unspecified"}, resolved


#: The page an operator reads before every merge, and the only place the
#: direction of `merge=ours` can be made safe.
UPDATE_PAGE: Final = Path("docs/operating/taking-an-update.md")


def test_the_procedure_takes_origin_before_it_merges_upstream() -> None:
    """`merge=ours` cannot tell one remote from another, so the procedure has
    to.

    The rules above are correct against upstream and exactly wrong against
    `origin`: the cockpit writes there from volunteers' browsers all day, so a
    clone that has been sitting is the stale side, and a merge run in it
    discards what the cockpit wrote -- measured on real commits, two leads
    gone, `git merge` reporting success and naming no file.

    A fast-forward consults no merge rule at all. Doing it first is what makes
    "ours" mean the live instance rather than a clone, and it is the whole of
    the defence, so its position in the page is the thing to hold: after the
    upstream merge it would protect nothing.
    """
    page = (ROOT / UPDATE_PAGE).read_text(encoding="utf-8")

    fast_forward = page.find("git pull --ff-only")
    upstream_merge = page.find("git merge upstream/main")
    assert fast_forward != -1, (
        f"{UPDATE_PAGE.as_posix()} no longer fast-forwards from origin before "
        "merging. Without it the merge rules in "
        f"{boundary.GIT_ATTRIBUTES_PATH.as_posix()} treat a stale clone as the "
        "instance and drop everything the cockpit wrote"
    )
    assert upstream_merge != -1, (
        f"{UPDATE_PAGE.as_posix()} no longer shows the upstream merge, so this "
        "reading cannot say what order the two are in -- widen it with the "
        "reason rather than leaving it green about a page it cannot see"
    )
    assert fast_forward < upstream_merge, (
        "the fast-forward from origin comes after the upstream merge in "
        f"{UPDATE_PAGE.as_posix()}, which protects nothing: by then the merge "
        "has already run in a tree that was behind"
    )


def test_the_page_names_the_merge_these_rules_also_govern() -> None:
    """The gap this was filed for. The attribute is set for the operator, in a
    step they are told to run once, with a rationale entirely about upstream --
    and it then governs a merge they will run far more often, in the direction
    where it destroys rather than protects. Naming it is the minimum.
    """
    page = (ROOT / UPDATE_PAGE).read_text(encoding="utf-8")
    assert "git merge origin/main" in page, (
        f"{UPDATE_PAGE.as_posix()} documents "
        f"{boundary.REGENERATED_MERGE_ATTRIBUTE} without naming the merge from "
        "origin, which the same attribute governs and in which it drops the "
        "cockpit's work rather than upstream's example data"
    )
