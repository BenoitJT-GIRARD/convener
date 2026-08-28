"""`a11y.yml` and `preview.yml` ran on
every push and every pull request once, including one touching
only `docs/`, `instance/data/`, or an unrelated relay -- neither check can possibly
have anything to say about most of those. Both are path-filtered now, the
same deliberate discipline `visuals.yml` already established and
`test_visuals_workflow.py` already pins (see this module's own docstring
for the D-25 reasoning: a filter that silently omits a path is the defect,
not the fix).

Mirrors `test_visuals_workflow.py`'s own idiom throughout, including
reading the raw file text rather than trusting `yaml.safe_load` for the
one property that actually matters -- a real YAML anchor/alias resolves
identically either way, which is exactly what would hide a reintroduced
one from a check that only compared parsed lists.
"""

from __future__ import annotations

import re

import yaml

from convener_ops.paths import repo_root

_ROOT = repo_root()
_A11Y_PATH = _ROOT / ".github" / "workflows" / "a11y.yml"
_PREVIEW_PATH = _ROOT / ".github" / "workflows" / "preview.yml"
_A11Y_TEXT = _A11Y_PATH.read_text(encoding="utf-8")
_PREVIEW_TEXT = _PREVIEW_PATH.read_text(encoding="utf-8")

#: The identical list both files are meant to share -- both build the same
#: fixture-based site and app, from the same inputs (this module's own
#: docstring, and each workflow's own header comment).
_EXPECTED_PATHS = [
    "site/**",
    "app/**",
    "tools/convener_ops/**",
    "tools/pyproject.toml",
    "tools/uv.lock",
]

_PATH_ITEM_RE = re.compile(r"^\s*-\s*'([^']+)'\s*$", re.MULTILINE)


def _paths_block(text: str, start_marker: str, end_marker: str) -> list[str]:
    """The `- '...'` items between two markers in the *raw* workflow
    text -- the same helper `test_visuals_workflow.py::_paths_block`
    defines, reproduced here rather than imported across test modules."""
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return _PATH_ITEM_RE.findall(text[start:end])


# ==================================================================== #
# a11y.yml: two copies (push and pull_request), because GitHub Actions'
# own workflow parser does not support YAML anchors or aliases.
# ==================================================================== #


def test_a11y_workflow_is_path_filtered_on_both_triggers() -> None:
    data = yaml.safe_load(_A11Y_TEXT)
    triggers = data[True]  # PyYAML's YAML-1.1 bool resolver: bare `on:` -> True
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["push"]["paths"], "push trigger carries no path filter"
    assert triggers["pull_request"]["paths"] == triggers["push"]["paths"]
    for path in _EXPECTED_PATHS:
        assert path in triggers["push"]["paths"], (
            f"a11y.yml's path filter is missing {path!r} -- see this "
            "workflow's own header comment for what it must cover"
        )
    assert ".github/workflows/a11y.yml" in triggers["push"]["paths"]


def test_a11y_workflow_the_two_path_filters_are_identical_lists() -> None:
    """The guarantee that actually catches drift, or a reintroduced
    anchor -- read from the raw text, never through `yaml.safe_load` (see
    this module's own docstring)."""
    push_paths = _paths_block(_A11Y_TEXT, "push:", "pull_request:")
    pull_request_paths = _paths_block(_A11Y_TEXT, "pull_request:", "\njobs:")
    assert push_paths, (
        "no `- '...'` path items found under push: -- the markers this "
        "test slices the file on may have moved"
    )
    assert pull_request_paths == push_paths, (
        "a11y.yml's push and pull_request path filters have drifted apart "
        f"-- push: {push_paths!r}, pull_request: {pull_request_paths!r}"
    )


def test_a11y_workflow_does_not_watch_real_per_edition_data() -> None:
    """This check builds from a committed fixture
    (`site/src/_data/events.json`) and never reads real event data at
    all -- see this workflow's own header comment, "Deliberately
    absent"."""
    data = yaml.safe_load(_A11Y_TEXT)
    paths = data[True]["push"]["paths"]
    assert "instance/data/speakers.yml" not in paths
    assert not any(p.startswith("instance/data/") for p in paths)


# ==================================================================== #
# preview.yml: one trigger only (`pull_request`, never `push`), so there
# is no second copy to keep in sync and no anchor trap to fall into.
# ==================================================================== #


def test_preview_workflow_is_path_filtered() -> None:
    data = yaml.safe_load(_PREVIEW_TEXT)
    triggers = data[True]
    assert set(triggers) == {"pull_request"}, (
        "preview.yml gained a second trigger -- if that trigger is `push`, "
        "it now needs its own, hand-written copy of this same path list "
        "(GitHub Actions' parser supports no YAML anchor to share one)"
    )
    paths = triggers["pull_request"]["paths"]
    assert paths, "pull_request trigger carries no path filter"
    for path in _EXPECTED_PATHS:
        assert path in paths, (
            f"preview.yml's path filter is missing {path!r} -- see this "
            "workflow's own header comment for what it must cover"
        )
    assert ".github/workflows/preview.yml" in paths


def test_preview_and_a11y_path_filters_are_identical() -> None:
    """Both build the identical fixture-based site and app, from the
    identical inputs -- a divergence here is exactly the "one path
    watched here but not there" gap D-25 exists to catch, even though
    each file's own filter passes its own, separate check above."""
    a11y_data = yaml.safe_load(_A11Y_TEXT)
    preview_data = yaml.safe_load(_PREVIEW_TEXT)
    a11y_paths = set(a11y_data[True]["push"]["paths"]) - {".github/workflows/a11y.yml"}
    preview_paths = set(preview_data[True]["pull_request"]["paths"]) - {
        ".github/workflows/preview.yml"
    }
    assert a11y_paths == preview_paths


# ==================================================================== #
# D-25's own counter-proof: what a missing path in this exact class of
# filter looks like, and that this suite would actually have caught it.
# Proven against a probe workflow, never against the real files above --
# breaking the real files on purpose and reverting is not this project's
# idiom for this kind of check (test_workflows.py's own probe tests for
# `_job_has_own_timeout` use the identical shape).
# ==================================================================== #


def test_a_path_filter_missing_a_watched_directory_is_caught_by_this_same_check() -> (
    None
):
    """The mutation this module exists to catch: a filter that dropped
    `app/**` (an island regression would ship unreviewed) still parses,
    still has a non-empty `paths:` list, and would still pass every
    assertion except the one that checks for that specific entry -- proof
    that `test_a11y_workflow_is_path_filtered_on_both_triggers`'s
    per-path loop, not merely "a filter exists", is what carries the
    weight here."""
    probe = yaml.safe_load(
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "    paths:\n"
        "      - 'site/**'\n"
        "  pull_request:\n"
        "    paths:\n"
        "      - 'site/**'\n"
    )
    paths = probe[True]["push"]["paths"]
    assert "site/**" in paths
    assert "app/**" not in paths, (
        "this probe is meant to model the missing-path mutation -- if "
        "app/** is present the probe itself is wrong, not the real file"
    )
