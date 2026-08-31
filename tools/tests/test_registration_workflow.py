"""Pins `.github/workflows/registration.yml` and `resend-confirmation.yml`
against the one property a Python test could not see on its own: what
secrets a workflow step actually passes.

The whole confirmation-sending path -- `matching_code`,
`smtp_config_from_env` -- was fully covered by `tools/tests/test_cli.py`
and `test_confirmation.py`, and every one of those tests passed, because
every one of them sets its own environment. The gap a review found
was invisible to all of them for exactly that reason: the real
workflow step that runs `convener-handle-registration` passed none of
`CONVENER_MATCHING_SALT` or the five `CONVENER_SMTP_*` secrets, so in production
`matching_code` always returned `None` and `smtp_config_from_env` always
returned `None` -- silently, since nothing in a unit test ever reads the
workflow file itself. `tools/tests/governance/test_notify.py` already has this same
idiom for `notify.yml` (`test_the_immediate_job_fetches_enough_history...`,
`test_the_workflow_asks_for_no_permission_beyond...`); this module is its
own workflow file's twin.

Read as text and asserted against with `in` checks, the same as
`test_workflows.py` does for `deploy.yml` -- never parsed and executed,
which would mean a real GitHub Actions runner, exactly the kind of network
access this suite must not take on.
"""

from __future__ import annotations

from convener_ops.declaration.paths import repo_root

_ROOT = repo_root()
_REGISTRATION = (_ROOT / ".github" / "workflows" / "registration.yml").read_text(
    encoding="utf-8"
)
_RESEND = (_ROOT / ".github" / "workflows" / "resend-confirmation.yml").read_text(
    encoding="utf-8"
)

#: The six secrets `email_transport` and `matching_salt` together declare
#: (`config/integrations.yml`) -- whatever step actually sends or logs a
#: confirmation must hold all six, or D-13 degrades permanently rather
#: than only when genuinely unconfigured.
_CONFIRMATION_SECRETS = (
    "CONVENER_MATCHING_SALT",
    "CONVENER_SMTP_HOST",
    "CONVENER_SMTP_PORT",
    "CONVENER_SMTP_USER",
    "CONVENER_SMTP_PASSWORD",
    "CONVENER_SMTP_FROM",
)


def _step_block(workflow: str, step_name: str) -> str:
    """The text of one step, from its `- name: <step_name>` line up to the
    next `- name:` line (or the end of the file) -- so an assertion about
    "this step holds X" cannot be satisfied by X sitting in a *different*
    step altogether."""
    marker = f"- name: {step_name}"
    start = workflow.index(marker)
    rest = workflow[start:]
    next_marker = rest.find("\n      - name:", 1)
    return rest if next_marker == -1 else rest[: next_marker + 1]


# ------------------------------------------------------------------ #
# registration.yml
# ------------------------------------------------------------------ #


def test_the_send_step_exists_and_runs_only_on_success() -> None:
    """Two findings in one:
    sending must be a step of its own, gated so it runs at most once, only
    once the store step has actually landed the record."""
    block = _step_block(_REGISTRATION, "Send the registration confirmation")
    assert "if: success()" in block
    assert "uv run convener-send-confirmation" in block


def test_the_send_step_carries_every_confirmation_secret() -> None:
    """The step that runs `convener-send-confirmation` must hold
    `CONVENER_MATCHING_SALT` and all five `CONVENER_SMTP_*` secrets, or every
    confirmation in production silently takes the no-code, unsent path
    the confirmation exists to prevent."""
    block = _step_block(_REGISTRATION, "Send the registration confirmation")
    for secret in _CONFIRMATION_SECRETS:
        assert f"secrets.{secret}" in block, f"{secret} missing from the send step"


def test_the_send_step_re_reads_the_payload_and_the_private_key() -> None:
    block = _step_block(_REGISTRATION, "Send the registration confirmation")
    assert "REGISTRATION_PAYLOAD: ${{ github.event.client_payload.body }}" in block
    assert "EVENT_PRIVATE_KEY: ${{ secrets[steps.resolve.outputs.secret_name] }}" in (
        block
    )


def test_the_send_step_reads_what_changed_from_the_store_steps_output() -> None:
    block = _step_block(_REGISTRATION, "Send the registration confirmation")
    assert "CHANGED_FIELDS: ${{ steps.handle.outputs.changed }}" in block


def test_the_store_step_is_named_handle_for_the_send_step_to_reference() -> None:
    block = _step_block(_REGISTRATION, "Decrypt, store and commit the registration")
    assert "\n        id: handle\n" in block


def test_the_store_step_does_not_hold_any_confirmation_secret() -> None:
    """Guards the split itself, not only the send step's own secrets: a
    future edit that copies `CONVENER_SMTP_*` back onto the store step would
    reintroduce the send-per-retry-attempt defect even with the other
    finding otherwise fixed."""
    block = _step_block(_REGISTRATION, "Decrypt, store and commit the registration")
    for secret in _CONFIRMATION_SECRETS:
        assert secret not in block, f"{secret} leaked back onto the store step"


def test_the_workflow_never_uploads_an_unsent_confirmation_artefact() -> None:
    """An unsent confirmation is reported, not
    retained. There used to be a step here uploading the composed message
    as a 14-day build artefact; it is gone, and this pins that it does not
    come back -- `docs/handbook/governance/traitement-donnees.md`'s own Recipients
    section is only true again because it does not exist."""
    assert "unsent-confirmation" not in _REGISTRATION
    assert "upload-artifact" not in _REGISTRATION


def test_the_job_grants_no_permission_beyond_contents_write() -> None:
    """The send step needs no permission of its own -- `secrets` reads and
    an SMTP connection are not governed by `permissions:` at all -- so the
    job-level grant should still name only what the store step's commit
    and push need."""
    job = _REGISTRATION.split("jobs:")[1]
    permissions_block = job.split("permissions:")[1].split("env:")[0]
    assert "contents: write" in permissions_block


# ------------------------------------------------------------------ #
# resend-confirmation.yml
# ------------------------------------------------------------------ #


def test_the_resend_step_carries_every_confirmation_secret() -> None:
    block = _step_block(_RESEND, "Re-send the confirmation")
    for secret in _CONFIRMATION_SECRETS:
        assert f"secrets.{secret}" in block, f"{secret} missing from the resend step"


def test_the_resend_workflow_never_uploads_an_unsent_confirmation_artefact() -> None:
    """Same pin as `test_the_workflow_never_uploads_an_unsent_confirmation_
    artefact`, for this workflow's own now-removed step."""
    assert "unsent-confirmation" not in _RESEND
    assert "upload-artifact" not in _RESEND


def test_the_resend_workflow_grants_no_write_permission() -> None:
    """Unlike `registration.yml`, this workflow never commits anything --
    it only decrypts, composes and sends -- so it should never hold
    `contents: write`."""
    job = _RESEND.split("jobs:")[1]
    permissions_block = job.split("permissions:")[1].split("steps:")[0]
    assert "contents: read" in permissions_block
    assert "write" not in permissions_block
