"""One sequence, two readers, and the control that keeps them one.

`STANDING-UP.yml` declares what somebody with no repositories and no accounts
does to have a running instance. `docs/reference/standing-up.md` is that
sequence as a person reads it, and an agent skill carries the same sequence
out from the same file. Two documents describing one procedure diverge; the
whole point of the declaration is that there is only one, so this module is
what makes "only one" a fact rather than an intention.

**Three bindings, in order of how much each one proves.**

1. The committed page is byte-for-byte what the declaration derives. That is
   the strongest of the three and it subsumes the others: a step present in
   one artefact and not the other, an actor changed on one side, a check
   command corrected in the page instead of in the declaration -- all of them
   fail here, without anybody having named them.
2. The page is read back and each declared step is found in it by number, by
   title, by actor line and by check. Redundant with the byte comparison by
   construction, and kept anyway: when the byte comparison fails it says only
   that the file differs, and these say which step and which field, which is
   the difference between a failure somebody fixes and one they regenerate
   past.
3. `config/integrations.yml` and the declaration cover each other. Every
   integration row is completed by exactly one step, and every secret those
   rows name is either set by a step or listed in `not_at_setup:` with a
   reason. An eleventh integration added upstream therefore has to be decided
   about rather than quietly left out of the one page that says how to stand
   an instance up.

**The mutations are tests, not something somebody remembers to try.** Each of
the drifts above is performed against a scratch repository and the guard is
required to notice: a step added to the declaration and nothing regenerated, a
check reworded on the page, an actor flipped. `--check` is also held to
repairing nothing, for the reason `test_schema_doc.py` states for its own
generator -- a check that rewrote the file it was checking would be a green
tick over the exact defect it exists to catch.

The parser is exercised on declarations written here rather than on the
repository's own, so that a test about "a human step with no walkthrough" does
not require the repository to hold one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from generate_standing_up_doc import (
    ACTOR_LINE,
    COMMAND,
    DECLARATION_PATH,
    DOC_PATH,
    INTEGRATIONS_PATH,
    Sequence,
    integration_rows,
    load_sequence,
    main,
    render_page,
    sequence_from_data,
    standing_up_doc,
    uncovered_integrations,
    unnamed_integrations,
)

from convener_ops.paths import repo_root

ROOT = repo_root()


def declaration() -> Sequence:
    return load_sequence(ROOT)


def page() -> str:
    return (ROOT / DOC_PATH).read_text(encoding="utf-8")


def section_of(text: str, number: int) -> str:
    """One step's own block of the page, from its heading to the next one.

    Reading each field back inside its own section rather than anywhere on the
    page is what makes the field checks mean something: a check sentence that
    survived on the wrong step would otherwise pass a whole-page search.
    """
    marker = f"\n### {number}. "
    start = text.index(marker)
    rest = text[start + 1 :]
    end = rest.find("\n### ")
    tail = rest.find("\n## ")
    if tail != -1 and (end == -1 or tail < end):
        end = tail
    return rest if end == -1 else rest[:end]


# --------------------------------------------------------------------------
# The repository's own declaration and page
# --------------------------------------------------------------------------


def test_the_committed_page_is_what_the_declaration_derives() -> None:
    """The whole binding, on the real tree.

    A step added to `STANDING-UP.yml` without regenerating fails here, and so
    does a page corrected by hand -- which is the drift every generated page in
    this repository has actually suffered at least once.
    """
    assert page() == standing_up_doc(ROOT), (
        f"{DOC_PATH.as_posix()} is not what {DECLARATION_PATH.as_posix()} "
        f"derives; run `{COMMAND}` from `tools/`."
    )


def test_the_page_says_it_is_generated_and_names_what_derives_it() -> None:
    """A derived file that does not say so is one somebody will edit."""
    head = page()[:900]
    assert "generated" in head
    assert COMMAND in head
    assert DECLARATION_PATH.as_posix() in head
    assert INTEGRATIONS_PATH.as_posix() in head


def test_every_declared_step_is_on_the_page_under_its_own_number() -> None:
    sequence = declaration()
    text = page()
    for step in sequence.steps:
        heading = f"### {sequence.number_of(step)}. {step.title}"
        assert heading in text, step.id


def test_the_page_holds_no_step_the_declaration_does_not() -> None:
    """The other direction, so the sweep cannot pass over a shorter page."""
    headings = re.findall(r"^### (\d+)\. ", page(), re.MULTILINE)
    assert [int(number) for number in headings] == list(
        range(1, len(declaration().steps) + 1)
    )


def test_every_step_states_the_actor_the_declaration_gives_it() -> None:
    """The field the later agent skill acts on.

    A step whose actor drifts is a step handed to the wrong reader: an agent
    attempting a browser-only flow, or a person doing by hand what a command
    would have done in a second.
    """
    sequence = declaration()
    text = page()
    for step in sequence.steps:
        block = section_of(text, sequence.number_of(step))
        assert ACTOR_LINE[step.actor] in block, step.id
        other = ACTOR_LINE["human" if step.actor == "agent" else "agent"]
        assert other not in block, step.id


def test_every_step_states_the_check_the_declaration_gives_it() -> None:
    """What proves a step is done, read back word for word.

    Compared with the page's own wrapping taken off: the renderer wraps prose
    to a column, so a substring search against the declaration's single line
    would fail on every step for a reason that is not drift.
    """
    sequence = declaration()
    text = page()
    for step in sequence.steps:
        block = " ".join(section_of(text, sequence.number_of(step)).split())
        assert f"**Proves it is done.** {step.check}" in block, step.id


def test_every_step_with_a_command_shows_it_in_a_fenced_block() -> None:
    sequence = declaration()
    text = page()
    for step in sequence.steps:
        if not step.command:
            continue
        block = section_of(text, sequence.number_of(step))
        assert f"```bash\n{step.command}\n```" in block, step.id


def test_every_human_step_carries_its_whole_walkthrough() -> None:
    """The sections handed to a person verbatim, present in full.

    Registering a GitHub App and creating a mailbox have no interface anything
    could call, so the page is the only thing standing between an operator and
    a browser form with twenty fields on it.
    """
    sequence = declaration()
    text = page()
    for step in sequence.steps:
        if not step.walkthrough:
            continue
        block = " ".join(section_of(text, sequence.number_of(step)).split())
        assert "**In a browser, in full:**" in block, step.id
        for item in step.walkthrough:
            assert item in block, (step.id, item[:40])


def test_every_declared_credential_is_in_the_table() -> None:
    for secret in declaration().secrets:
        assert f"| `{secret.name}` | {secret.kind} |" in page(), secret.name


def test_the_two_repositories_and_their_visibilities_are_stated() -> None:
    for repository in declaration().repositories:
        assert f"| `{repository.id}` | {repository.visibility} |" in page()


# --------------------------------------------------------------------------
# The declaration against `config/integrations.yml`
# --------------------------------------------------------------------------


def test_every_integration_row_is_completed_by_exactly_one_step() -> None:
    """Branching onto the report rather than writing a second one.

    `convener-check-config` already knows every integration, what each waits
    on and what degrades meanwhile. This sequence names those rows instead of
    restating them, so the two have to agree about which rows exist: a row
    added upstream and named by no step, or a step naming a row that has been
    removed, fails here by name.
    """
    sequence = declaration()
    assert unnamed_integrations(sequence, integration_rows(ROOT)) == ()
    named = [name for step in sequence.steps for name in step.integrations]
    assert len(named) == len(set(named))


def test_every_integration_secret_is_set_by_a_step_or_deferred_with_a_reason() -> None:
    """The gap this closes is an integration nobody is told how to switch on.

    A secret in `config/integrations.yml` that this sequence never sets, and
    never explains away, is an integration whose row a reader will meet in the
    report with no step anywhere that turns it green.
    """
    sequence = declaration()
    assert uncovered_integrations(sequence, integration_rows(ROOT)) == ()
    for entry in sequence.not_at_setup:
        assert entry.reason


def test_no_declared_credential_carries_anything_that_looks_like_a_value() -> None:
    """The one rule this file has that is not about drift.

    A declaration naming credentials is exactly the file somebody would paste
    one into "just to test it". Every scalar in it is swept for an unbroken
    run of credential-shaped characters -- the shape a token, a key or a
    base64 blob takes, and a shape ordinary English never does, because
    English has spaces in it.
    """
    run = re.compile(r"(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/=-]{32,}")

    def credential_shaped(text: str) -> bool:
        """Upper, lower and digit in one unbroken run of that length.

        A path (`services/signup-relay/wrangler`) and a name shouted in
        capitals (`CONVENER_MEETING_API_TOKEN`) both fail at least one of the
        three; a token, a key and a base64 blob pass all three by
        construction.
        """
        return (
            any(c.islower() for c in text)
            and any(c.isupper() for c in text)
            and any(c.isdigit() for c in text)
        )

    raw = yaml.safe_load((ROOT / DECLARATION_PATH).read_text(encoding="utf-8"))
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            found.extend(m for m in run.findall(node) if credential_shaped(m))

    walk(raw)
    assert found == []


def test_the_rendering_is_a_function_of_the_two_declarations_alone() -> None:
    """Byte-identical over two runs, which is what makes `--check` a fact."""
    assert standing_up_doc(ROOT) == standing_up_doc(ROOT)


# --------------------------------------------------------------------------
# Reading a declaration
# --------------------------------------------------------------------------

SAMPLE: dict[str, Any] = {
    "v": 1,
    "repositories": [
        {"id": "private-one", "visibility": "private", "what": "Holds everything."},
        {"id": "public-one", "visibility": "public", "what": "Holds the output."},
    ],
    "stages": [
        {"id": "first", "title": "The first", "purpose": "Before anything."},
        {"id": "second", "title": "The second", "purpose": "After the first."},
    ],
    "steps": [
        {
            "id": "open_a_mailbox",
            "stage": "first",
            "title": "Open a mailbox",
            "actor": "human",
            "does": "Create an address the organisation owns.",
            "check": "A second person signs in to it.",
            "degraded": "Everything is tied to one person.",
            "walkthrough": ["Choose a provider.", "Create the address."],
        },
        {
            "id": "edit_the_declaration",
            "stage": "second",
            "title": "Edit the declaration",
            "actor": "agent",
            "does": "Write your own values into it.",
            "check": "The banner is gone.",
            "command": "cd tools && uv run convener-validate",
            "degraded": "Every page says it is not configured.",
            "sets": ["A_TOKEN"],
        },
    ],
    "secrets": [
        {
            "name": "A_TOKEN",
            "kind": "repository-secret",
            "home": "private-one",
            "set_through": "Settings, then Secrets.",
            "why": "Lets the build publish.",
        }
    ],
    "not_at_setup": [{"secret": "A_PER_EVENT_KEY", "reason": "One per event."}],
}


def sample(**changes: Any) -> dict[str, Any]:
    """The sample declaration with one thing altered, deep-copied.

    Written out above rather than trimmed from the repository's own, so these
    tests keep meaning what they say when the real sequence moves.
    """
    import copy

    data = copy.deepcopy(SAMPLE)
    data.update(copy.deepcopy(changes))
    return data


def test_the_sample_declaration_parses_and_renders() -> None:
    """Without this, every refusal below could be passing vacuously."""
    parsed = sequence_from_data(sample())
    rendered = render_page(parsed, integration_rows(ROOT))
    assert "### 1. Open a mailbox" in rendered
    assert "### 2. Edit the declaration" in rendered


def test_a_human_step_without_a_walkthrough_is_refused() -> None:
    data = sample()
    del data["steps"][0]["walkthrough"]
    with pytest.raises(ValueError, match="walkthrough"):
        sequence_from_data(data)


def test_an_agent_step_with_a_walkthrough_is_refused() -> None:
    """A browser walkthrough beside a command is a second source."""
    data = sample()
    data["steps"][1]["walkthrough"] = ["Click the thing."]
    with pytest.raises(ValueError, match="walkthrough"):
        sequence_from_data(data)


def test_a_step_that_both_names_an_integration_and_restates_it_is_refused() -> None:
    data = sample()
    data["steps"][1]["integrations"] = ["auth_proxy"]
    with pytest.raises(ValueError, match="integrations"):
        sequence_from_data(data)


def test_a_step_with_neither_a_degradation_nor_an_integration_is_refused() -> None:
    data = sample()
    del data["steps"][1]["degraded"]
    with pytest.raises(ValueError, match="integrations"):
        sequence_from_data(data)


def test_an_actor_that_is_neither_of_the_two_is_refused() -> None:
    data = sample()
    data["steps"][1]["actor"] = "somebody"
    with pytest.raises(ValueError, match="actor"):
        sequence_from_data(data)


def test_a_step_in_an_undeclared_stage_is_refused() -> None:
    data = sample()
    data["steps"][1]["stage"] = "third"
    with pytest.raises(ValueError, match="stage"):
        sequence_from_data(data)


def test_a_stage_returned_to_after_another_one_is_refused() -> None:
    """The page renders one heading per stage, in order.

    A stage revisited later would either lose those steps or renumber the
    sequence somebody is following, so it is refused where it is written
    rather than rendered into a page nobody can follow.
    """
    data = sample()
    data["steps"].append(
        {
            "id": "back_to_the_first",
            "stage": "first",
            "title": "Back to the first",
            "actor": "agent",
            "does": "Something else.",
            "check": "It is done.",
            "degraded": "Nothing.",
        }
    )
    with pytest.raises(ValueError, match="returned to"):
        sequence_from_data(data)


def test_a_step_setting_an_undeclared_credential_is_refused() -> None:
    data = sample()
    data["steps"][1]["sets"] = ["A_TOKEN", "AN_UNDECLARED_ONE"]
    with pytest.raises(ValueError, match="AN_UNDECLARED_ONE"):
        sequence_from_data(data)


def test_a_credential_no_step_sets_is_refused() -> None:
    data = sample()
    del data["steps"][1]["sets"]
    with pytest.raises(ValueError, match="A_TOKEN"):
        sequence_from_data(data)


def test_a_credential_on_a_repository_that_does_not_exist_is_refused() -> None:
    data = sample()
    data["secrets"][0]["home"] = "a-third-one"
    with pytest.raises(ValueError, match="a-third-one"):
        sequence_from_data(data)


def test_a_worker_credential_outside_services_is_refused() -> None:
    data = sample()
    data["secrets"][0]["kind"] = "worker-secret"
    data["secrets"][0]["home"] = "somewhere"
    with pytest.raises(ValueError, match="worker"):
        sequence_from_data(data)


def test_a_step_declared_twice_is_refused() -> None:
    data = sample()
    data["steps"].append(dict(data["steps"][1]))
    with pytest.raises(ValueError, match="twice"):
        sequence_from_data(data)


def test_a_missing_field_is_refused_by_name() -> None:
    data = sample()
    del data["steps"][1]["check"]
    with pytest.raises(ValueError, match="edit_the_declaration"):
        sequence_from_data(data)


def test_an_unsupported_version_is_refused() -> None:
    with pytest.raises(ValueError, match="format version"):
        sequence_from_data(sample(v=2))


# --------------------------------------------------------------------------
# The command, and the drifts it has to catch
# --------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository holding the two declarations, with the page not written."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.yml").write_text("{}\n", encoding="utf-8")
    (tmp_path / INTEGRATIONS_PATH).parent.mkdir(parents=True)
    (tmp_path / INTEGRATIONS_PATH).write_text(
        (ROOT / INTEGRATIONS_PATH).read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / DECLARATION_PATH).write_text(
        (ROOT / DECLARATION_PATH).read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setenv("CONVENER_REPO_ROOT", str(tmp_path))
    return tmp_path


def test_check_fails_when_the_page_has_never_been_written(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A guard around something that does not exist has to fail loudly."""
    assert main(["--check"]) == 1
    assert not (fake_repo / DOC_PATH).exists()
    err = capsys.readouterr().err
    assert DOC_PATH.as_posix() in err
    assert COMMAND in err


def test_check_leaves_a_stale_page_exactly_as_it_found_it(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A check that repairs is not a check."""
    written = fake_repo / DOC_PATH
    written.parent.mkdir(parents=True)
    written.write_text("stale\n", encoding="utf-8")

    assert main(["--check"]) == 1
    assert written.read_text(encoding="utf-8") == "stale\n"
    assert COMMAND in capsys.readouterr().err


def test_writing_then_checking_passes(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    assert main(["--check"]) == 0
    assert "matches the declaration" in capsys.readouterr().out


def test_a_second_write_changes_nothing_and_says_so(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    capsys.readouterr()
    assert main([]) == 0
    assert "unchanged" in capsys.readouterr().out


def _mutate_declaration(fake_repo: Path, old: str, new: str) -> None:
    path = fake_repo / DECLARATION_PATH
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_a_step_added_and_not_regenerated_makes_the_check_fail(
    fake_repo: Path,
) -> None:
    """A step in one artefact and not the other, as a test.

    The page is generated, then a step is added to the declaration and nothing
    is regenerated -- which is exactly what somebody does when they add a step
    and commit.
    """
    assert main([]) == 0
    path = fake_repo / DECLARATION_PATH
    text = path.read_text(encoding="utf-8")
    marker = "\nsecrets:\n"
    assert marker in text
    invented = (
        "\n  - id: an_invented_step\n"
        "    stage: optional\n"
        "    title: An invented step\n"
        "    actor: agent\n"
        "    does: Something nobody regenerated the page for.\n"
        "    check: Nothing proves it.\n"
        "    degraded: Nothing at all.\n"
    )
    path.write_text(text.replace(marker, invented + marker, 1), encoding="utf-8")
    assert main(["--check"]) == 1


def test_a_check_reworded_on_the_page_makes_the_check_fail(
    fake_repo: Path,
) -> None:
    """The drift this guard exists for, in its commonest shape.

    Somebody corrects the wrong file: the page reads badly, so they fix the
    page. The declaration -- which the agent reads -- keeps the old sentence.
    """
    assert main([]) == 0
    written = fake_repo / DOC_PATH
    text = written.read_text(encoding="utf-8")
    assert "**Proves it is done.**" in text
    written.write_text(
        text.replace("**Proves it is done.**", "**Proof.**", 1), encoding="utf-8"
    )
    assert main(["--check"]) == 1


def test_a_command_drifted_in_the_declaration_makes_the_check_fail(
    fake_repo: Path,
) -> None:
    assert main([]) == 0
    _mutate_declaration(
        fake_repo,
        "command: cd tools && uv run convener-validate",
        "command: cd tools && uv run convener-validate --strict",
    )
    assert main(["--check"]) == 1


def test_an_actor_flipped_on_the_page_makes_the_check_fail(
    fake_repo: Path,
) -> None:
    """The field with the widest blast radius, since an agent acts on it.

    Flipped on the page rather than in the declaration, because that is the
    drift that would otherwise go unseen: the declaration refuses a human step
    with no walkthrough on its own, while a page telling a reader that an
    agent may register a GitHub App is well formed, readable, and wrong.
    """
    assert main([]) == 0
    written = fake_repo / DOC_PATH
    text = written.read_text(encoding="utf-8")
    assert ACTOR_LINE["human"] in text
    written.write_text(
        text.replace(ACTOR_LINE["human"], ACTOR_LINE["agent"], 1), encoding="utf-8"
    )
    assert main(["--check"]) == 1


def test_a_degradation_reworded_upstream_makes_the_check_fail(
    fake_repo: Path,
) -> None:
    """The other file this page derives from, held the same way.

    What an absent integration costs is `config/integrations.yml`'s to say,
    and this page quotes it. A row reworded there and a page not regenerated
    is the same drift as any other, and is caught by the same guard.
    """
    assert main([]) == 0
    path = fake_repo / INTEGRATIONS_PATH
    text = path.read_text(encoding="utf-8")
    old = "Recording URLs are entered by hand after publishing."
    assert old in text
    path.write_text(
        text.replace(old, "Recording addresses are typed in afterwards.", 1),
        encoding="utf-8",
    )
    assert main(["--check"]) == 1


def test_the_terminal_output_is_ascii(
    fake_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The page is written in the handbook's English; the console is not.

    Nothing this repository's Python prints may be non-ASCII, which is why
    there is no mode that prints the page itself.
    """
    main([])
    main(["--check"])
    captured = capsys.readouterr()
    (captured.out + captured.err).encode("ascii")
