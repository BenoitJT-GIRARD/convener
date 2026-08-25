"""The boundary between what an instance owns and what the product ships.

Phase 10 exists because a duplicate of this repository updates by
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
written into `data/` is a fact about a repository's past, not a property of
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
   place -- `config/boundary.yml` for the paths outside `config/`, and each
   `config/` file's own `owner:` key for the ones inside it. A file in
   `config/` with no answer is refused by name; a `config/` path named in
   the declaration as well is refused too, because one fact in two places
   is how this repository has drifted every previous time.

2. **No instance path holds code.** Source is the thing upstream fixes bugs
   in. The day a `.py`, a `.ts` or a `.njk` lives under `data/` or
   `keys/`, "upstream never writes here" stops being a promise anybody can
   keep -- not because someone was careless, but because a bug will
   eventually be there and it will have to be fixed. This is the clause
   that bites, and it is checked over the files the working tree really
   holds, not over a list.

3. **Nothing sits inside an instance path by accident.** The two product
   files that live inside instance directories today
   (`data/schema.md`, `keys/signing/README.md`) are named in the
   declaration with their reasons, must exist, and are the only exceptions
   there are. An unjustifiable one cannot be added quietly.

What these three do **not** cover, stated plainly rather than left to be
discovered:

- **Content.** A hard-coded organisation name inside a product file is not
  visible here at all. That is tasks 2 to 4 of this phase, and the build
  sweep of task 5.
- **Completeness.** A new instance-owned file created *outside* the
  declared paths is invisible: the boundary can only hold what somebody
  declared. Clause 2 catches the reverse mistake (code moving into an
  instance path), never this one.
- **Runtime writes.** The instance's own scheduled jobs write into `data/`
  and `public-data/` constantly, and must. Nothing here distinguishes a
  write by the instance from a write by upstream, because in a checkout
  they look identical; the distinction lives in who commits, which is a
  fact about a repository's history and therefore outside this module.
- **Correctness of a judgement.** That `config/queue-drain.yml` is the
  instance's is an argument, written in that file's own header. This module
  holds the answer, never the argument.
"""

from __future__ import annotations

import pkgutil
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
import yaml

import convener_ops
from convener_ops import actions_usage, boundary, queue_watch, registration_routing
from convener_ops.boundary import (
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
)
from convener_ops.paths import repo_root

ROOT = repo_root()

#: A declaration in the shape the real one has, for the synthetic roots
#: below. Deliberately not a copy of `config/boundary.yml`: a fixture that
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
    declaration and a `config/` directory whose files state an owner."""
    (tmp_path / "config").mkdir(exist_ok=True)
    body = _MINIMAL if declaration is None else declaration
    (tmp_path / boundary.DECLARATION_PATH).write_text(
        yaml.safe_dump(body), encoding="utf-8"
    )
    for name, owner in (owners or {}).items():
        (tmp_path / "config" / name).write_text(f"owner: {owner}\n", encoding="utf-8")
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

    `site/src/_data/site.json` was the fourth of these until phase 10 task
    3, which folded its four keys into `config/instance.json`'s own
    `identity` and left `site/.eleventy.js` composing them. The file
    entry went with the file, and nothing under `site/` is the instance's
    now -- so the anchor moved to `docs/governance/register.md`, the one
    path here that a scheduled job rewrites rather than a person.
    """
    declared = load().instance_paths
    for owned in ("data/", "keys/", "public-data/", "docs/governance/register.md"):
        assert owned in declared, f"{owned} is no longer declared: {declared}"


def test_every_file_in_config_states_which_it_is() -> None:
    """`config/` filled up by accumulation and nobody ever decided. Now
    every file answers, and both answers are actually used -- a directory
    where everything said `product` would satisfy a weaker test while
    saying nothing at all.

    Every file in every format `boundary.CONFIG_READERS` knows, compared
    against what the directory really holds: phase 10 task 2 added
    `config/instance.json`, and a check that only ever globbed `*.yml`
    would have let a second format arrive here with nobody deciding what
    it is -- the exact silence this directory was in before.
    """
    owners = load().config_owners
    assert set(owners) == {
        path.relative_to(ROOT).as_posix()
        for suffix in boundary.CONFIG_READERS
        for path in (ROOT / "config").glob(f"*{suffix}")
    }
    assert set(owners.values()) == {INSTANCE, PRODUCT}
    assert owners["config/integrations.yml"] == PRODUCT
    assert owners["config/boundary.yml"] == PRODUCT
    assert owners["config/instance.json"] == INSTANCE


def test_the_packages_own_config_constants_agree_with_the_declaration() -> None:
    """The three threshold files the code reaches for by name, and the one
    it reads as a mirror of itself. If a header and a module ever disagree
    about which side a file is on, this is where it shows."""
    board = load()
    assert board.owner_of(actions_usage.BUDGET_PATH) == INSTANCE
    assert board.owner_of(queue_watch.CONFIG_PATH) == INSTANCE
    assert board.owner_of(registration_routing.CONFIG_PATH) == INSTANCE
    assert board.owner_of(Path("config") / "integrations.yml") == PRODUCT


def test_every_path_this_package_names_is_classified() -> None:
    """A derived sweep, not a list: every `Path` constant any module of
    `convener_ops` declares, put through the boundary.

    Its value is the direction it fails in. The ledgers the scheduled jobs
    write (`data/queue-watch.yml`, `data/actions-usage.yml`,
    `data/retention-last-run.yml`, ...) and the key directories
    (`keys/events`, `keys/signing`) must stay the instance's; a `kept:`
    entry added carelessly, or a declaration narrowed from `data/` to one
    of its files, would quietly un-own them and nothing else would notice.
    """
    board = load()
    named: dict[str, str] = {}
    for module in pkgutil.iter_modules(convener_ops.__path__):
        loaded = import_module(f"convener_ops.{module.name}")
        for name, value in vars(loaded).items():
            if name.isupper() and isinstance(value, Path):
                named[value.as_posix()] = f"convener_ops.{module.name}.{name}"
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
    """The state `config/` was in until this task: a file that works,
    reads, and says nothing about who it belongs to."""
    root = _write_root(tmp_path)
    (root / "config" / "thresholds.yml").write_text("v: 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"config/thresholds\.yml declares no owner"):
        config_owners(root)


def test_a_json_config_file_answers_the_same_question(tmp_path: Path) -> None:
    """`config/instance.json` is JSON because three languages read it and
    only JSON has a parser on all three sides without a dependency two of
    them do not carry. That must not become a way around the rule above:
    a JSON file states the same `owner` key, and one that does not is
    refused by name exactly as a YAML one is."""
    root = _write_root(tmp_path)
    named = root / "config" / "instance.json"

    named.write_text('{"v": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match=r"config/instance\.json declares no owner"):
        config_owners(root)

    named.write_text('{"owner": "instance", "v": 1}', encoding="utf-8")
    assert config_owners(root)["config/instance.json"] == INSTANCE


def test_a_config_file_with_an_invented_owner_is_refused(tmp_path: Path) -> None:
    """Two answers, and only two. `owner: both` is the mixing this task
    exists to end, spelled out."""
    root = _write_root(tmp_path, owners={"thresholds.yml": "both"})

    with pytest.raises(ValueError, match="declares no owner"):
        config_owners(root)


def test_a_config_file_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    root = _write_root(tmp_path)
    (root / "config" / "list.yml").write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"config/list\.yml declares no owner"):
        config_owners(root)


def test_the_declaration_refuses_to_name_a_config_path() -> None:
    """One fact, one place. `config/queue-drain.yml` says what it is in its
    own header; a second home for that answer is how two lists start
    disagreeing, which is this repository's oldest defect."""
    with pytest.raises(ValueError, match="state their own owner"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {"path": "config/queue-drain.yml", "reason": "the instance's"}
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
                    {"path": "data/", "reason": "the records"},
                    {"path": "data/events/", "reason": "the events"},
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
        ({"owner": PRODUCT, "v": 1, "instance": ["data/"]}, "not an entry"),
        (
            {"owner": PRODUCT, "v": 1, "instance": [{"reason": "b"}]},
            "must be a non-empty path",
        ),
        (
            {
                "owner": PRODUCT,
                "v": 1,
                "instance": [{"path": " data/ ", "reason": "b"}],
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
        ({"owner": PRODUCT, "v": 1, "instance": [{"path": "data/"}]}, "carry a reason"),
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
    created yet -- `keys/events/`, `public-data/` -- so its existence is
    not asserted. A *file* entry, and every `kept:` exception, names
    something that is in this repository right now, and an entry pointing
    at nothing is an exception nobody can check."""
    board = load()
    for entry in board.handed:
        if not entry.is_directory:
            assert (ROOT / entry.path).is_file(), f"{entry.path} does not exist"
        for kept in entry.kept:
            assert (ROOT / kept.path).is_file(), f"{kept.path} does not exist"
            assert board.owner_of(kept.path) == PRODUCT


def test_the_kept_exceptions_are_the_two_this_task_found() -> None:
    """Named, so that a third cannot appear without somebody deciding to
    let it. Both are documentation of a contract that lives where an
    operator will meet it, and both are candidates for a move later --
    which is a maintainer's call, not this task's."""
    kept = {kept.path for entry in load().handed for kept in entry.kept}
    assert kept == {"data/schema.md", "keys/signing/README.md"}


def test_a_kept_file_outside_its_own_entry_is_refused() -> None:
    with pytest.raises(ValueError, match="is not a file inside"):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [
                    {
                        "path": "data/",
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
        ([{"path": "data/x.md"}], "carry a reason"),
        ([{"path": "data/sub/", "reason": "a directory"}], "not a file inside"),
    ],
)
def test_a_kept_entry_that_cannot_be_read_stops(kept: Any, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        declaration_from_data(
            {
                "owner": PRODUCT,
                "v": boundary.DECLARATION_VERSION,
                "instance": [{"path": "data/", "reason": "the records", "kept": kept}],
            }
        )


# ------------------------------------------------------------------ #
# `regenerated:` -- the paths upstream's own runs also write
# ------------------------------------------------------------------ #


def test_every_regenerated_path_is_told_to_git_how_to_merge() -> None:
    """The clause `regenerated:` exists to make checkable.

    Declaring a path the instance's says upstream will not *edit* it. It
    cannot say upstream will not *run*: upstream is itself a running
    instance, and `.github/workflows/register.yml` rewrites
    `docs/governance/register.md` in full from the commit history on every
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
    set somebody quietly widened. One path today, and it is the one phase
    10 task 1 found and task 3 ruled on."""
    assert load().regenerated_paths == ("docs/governance/register.md",)
    assert (ROOT / "docs" / "governance" / "register.md").is_file()


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
                        "path": "public-data/",
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
                        "path": "data/x.md",
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
            "instance": [{"path": "data/", "reason": "the records"}],
        }
    )
    assert entry.regenerated is False


# ------------------------------------------------------------------ #
# Clause 2 -- no instance path holds code
# ------------------------------------------------------------------ #


def test_the_walk_sees_the_files_this_repository_really_holds() -> None:
    """An empty walk would make the clause below pass for free, which is
    exactly how a sweep stops meaning anything."""
    found = instance_files(ROOT, load())
    assert "data/config.yml" in found
    assert "data/brand.json" in found
    assert "config/registration-lanes.yml" in found
    assert "docs/governance/register.md" in found
    assert "data/schema.md" not in found, "a kept file is the product's"
    assert "keys/signing/README.md" not in found
    assert "config/integrations.yml" not in found


def test_no_instance_path_holds_code() -> None:
    """The clause that bites.

    Upstream fixes bugs in source. A `.py` under `data/`, a `.ts` under
    `keys/`, a `.njk` under `public-data/` -- each is a file upstream will
    one day have to edit, in a path it promised never to touch. The promise
    does not survive that, however careful everybody is, so the state is
    refused rather than watched.
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
    assert code_among(["data/config.yml", "keys/events/MRG-05.pub", "a/b.md"]) == ()
    assert code_among(["data/x.PY", "site/src/_data/site.json"]) == ("data/x.PY",)


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
    assert board.owner_of("tools/convener_ops/boundary.py") == PRODUCT
    assert board.owner_of("app/src/main.tsx") == PRODUCT
    assert board.owner_of("site/src/_data/events.json") == PRODUCT
    assert board.owner_of("docs/toolkit/intro-scripts.md") == PRODUCT


def test_a_windows_separator_reads_the_same_as_a_posix_one() -> None:
    """Callers hand this module `Path` objects built with `Path("data") /
    "config.yml"`, which spells itself with a backslash on Windows -- where
    this project is developed."""
    board = load()
    assert board.owner_of(Path("data") / "config.yml") == INSTANCE
    assert board.owner_of("data\\config.yml") == INSTANCE


def test_the_two_halves_are_one_list() -> None:
    """`instance_paths` is the enumeration the phase asks for, and it is
    computed from both halves rather than written down a third time."""
    board = Boundary(
        handed=(Handed(path="records/", reason="r", kept=(Kept("records/x", "r"),)),),
        config_owners={"config/a.yml": INSTANCE, "config/b.yml": PRODUCT},
    )
    assert board.instance_paths == ("config/a.yml", "records/")
    assert board.owner_of("records/x") == PRODUCT
    assert board.owner_of("records/y") == INSTANCE


def test_a_directory_entry_is_told_from_a_file_entry() -> None:
    assert Handed(path="data/", reason="r").is_directory
    assert not Handed(path="data/config.yml", reason="r").is_directory
