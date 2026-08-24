"""Pins `.github/workflows/survey.yml` against the properties a Python test
cannot see on its own -- what a step actually reads and passes, and that
the concurrency group is scoped per event.

`test_registration_workflow.py` is this module's own twin, for the sibling
workflow; the reachability failure mode both exist to catch is the same
one this phase has paid for four times: a page nothing routes to, or a
dispatch no workflow receives, is not delivered work.

Read as text and asserted against with `in` checks -- never parsed and
executed, which would mean a real GitHub Actions runner.
"""

from __future__ import annotations

from convener_ops.paths import repo_root

_ROOT = repo_root()
_SURVEY = (_ROOT / ".github" / "workflows" / "survey.yml").read_text(encoding="utf-8")


def test_the_workflow_is_triggered_by_the_relays_own_dispatch_type() -> None:
    """The one property that makes this workflow reachable at all: the
    relay dispatches `survey-response-submitted`
    (`services/signup-relay/src/index.js`), and nothing runs this job
    unless the trigger names exactly that type."""
    assert "types: [survey-response-submitted]" in _SURVEY


def test_the_workflow_declares_no_concurrency_group() -> None:
    """Phase 7, task 2 (spec 6 ter) supersedes task 16's own decision here:
    `queue: max`, this block's own key, was never a valid `concurrency`
    key at all (`actionlint`, 2026-08-24), and what a `group` plus
    `cancel-in-progress: false` leaves behind cancels a *waiting* run
    rather than queuing it -- a lost survey response, not a delayed one.
    This workflow's own retry loop (fetch, reset --hard, re-run the
    handler) already makes a concurrent write to
    `survey-responses.enc` -- an append-only file with no identity to
    deduplicate on -- safe on its own, so it stays ungrouped."""
    assert "concurrency:" not in _SURVEY


def test_neither_survey_nor_registration_declares_a_concurrency_group() -> None:
    """Task 16's own decision here was a *separate* group from
    registration.yml's, because the two workflows write different files
    for the same event and have nothing to serialise against each other
    for. Phase 7, task 2 supersedes that: neither workflow groups runs at
    all any more (see this module's own
    test_the_workflow_declares_no_concurrency_group), so there is nothing
    left to keep distinct."""
    registration = (_ROOT / ".github" / "workflows" / "registration.yml").read_text(
        encoding="utf-8"
    )
    assert "concurrency:" not in _SURVEY
    assert "concurrency:" not in registration


def test_the_job_checks_out_the_branch_tip_not_the_pinned_dispatch_commit() -> None:
    assert "ref: ${{ env.TARGET_BRANCH }}" in _SURVEY
    assert "TARGET_BRANCH: ${{ github.event.repository.default_branch }}" in _SURVEY


def test_the_resolve_step_runs_the_survey_specific_entry_point() -> None:
    assert "uv run convener-survey-secret-name" in _SURVEY
    assert "SURVEY_PAYLOAD: ${{ github.event.client_payload.body }}" in _SURVEY


def test_the_handle_step_runs_the_survey_specific_entry_point() -> None:
    assert "uv run convener-handle-survey-response" in _SURVEY


def test_the_handle_step_selects_the_secret_by_the_resolve_steps_own_output() -> None:
    """The same GitHub Actions constraint `registration.yml` documents: a
    secret can only be selected through an expression in the workflow file
    itself, never computed inside a running step."""
    assert (
        "EVENT_PRIVATE_KEY: ${{ secrets[steps.resolve.outputs.secret_name] }}"
        in _SURVEY
    )


def test_the_retry_loop_re_derives_rather_than_rebases() -> None:
    """The same defence `registration.yml`'s own retry loop uses: a
    rejected push is handled by fetching the branch tip, hard-resetting,
    and re-running the handler -- never actually *running* `git pull
    --rebase`, which destroyed a record once (the phrase itself is named in
    an explanatory comment, which this checks for separately, on
    uncommented lines only)."""
    commands = [
        line for line in _SURVEY.splitlines() if not line.strip().startswith("#")
    ]
    assert not any("git pull" in line for line in commands)
    assert 'git fetch origin "$TARGET_BRANCH"' in _SURVEY
    assert 'git reset --hard "origin/$TARGET_BRANCH"' in _SURVEY
    assert "for attempt in 1 2 3; do" in _SURVEY


def test_the_committed_file_path_is_the_events_own_survey_responses_file() -> None:
    assert 'git add "data/events/$EVENT_ID/survey-responses.enc"' in _SURVEY


def test_the_job_grants_only_contents_write() -> None:
    job = _SURVEY.split("jobs:")[1]
    permissions_block = job.split("permissions:")[1].split("env:")[0]
    assert "contents: write" in permissions_block


def test_there_is_no_third_step_sending_anything() -> None:
    """Unlike registration.yml, nothing is returned to a participant for
    answering a survey -- there is no confirmation to send, so no step
    here should reference an SMTP secret or a confirmation-sending entry
    point."""
    for needle in ("CONVENER_SMTP_", "convener-send-confirmation", "CONVENER_MATCHING_SALT"):
        assert needle not in _SURVEY
